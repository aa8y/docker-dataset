"""Unit tests for duckdb/scripts/pgsql/transform (PostgreSQL dump -> DuckDB).

A thin fork of the SQLite hook, and the tests mirror test_sqlite_pgsql.py case
for case -- but only for the rules that survived the fork. DuckDB's parser is
PostgreSQL-derived, so most of SQLite's rewrites were deleted; those deletions
are asserted here too (a cast, a mixed-case identifier or a ``COMMENT ON`` that
quietly went missing would be a silent fidelity regression the row-count
integration test cannot see).

The sharp edges are the two buffered-statement paths. ``CREATE TABLE`` is read
whole so a table-level ``FOREIGN KEY`` can be removed together with the comma
before it -- dropping the line alone would leave a dangling comma. ``ALTER
TABLE`` is read whole and then *filtered*, because DuckDB implements exactly
one of its forms (``ADD CONSTRAINT ... PRIMARY KEY``) and the verb that decides
lives on the continuation line.

The third is the environment knobs -- PGSQL_EMPTY_BYTEA, PGSQL_EXTRA_SCHEMAS,
PGSQL_DROP_VIEWS, PGSQL_TYPE_MAP and PGSQL_COPY_CSV. Each is a rewrite that is
right for the one dataset that asks for it and wrong for the rest, so all five
are off by default and every test for one comes with a default-off guard: the
eight tags that symlink straight to scripts/pgsql must keep byte-identical
output.
"""
import io
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pgsql"


# --- copy_value: one COPY TEXT field -> SQL literal -----------------------

def test_copy_value_null_sentinel(duckdb_pgsql):
    assert duckdb_pgsql.copy_value("\\N") == "NULL"


def test_copy_value_doubles_single_quote(duckdb_pgsql):
    assert duckdb_pgsql.copy_value("it's") == "'it''s'"


def test_copy_value_unescapes_tab_newline(duckdb_pgsql):
    # COPY encodes tab/newline as \t / \n; the literal must carry the real
    # control character.
    assert duckdb_pgsql.copy_value("a\\tb") == "'a\tb'"
    assert duckdb_pgsql.copy_value("a\\nb") == "'a\nb'"
    assert duckdb_pgsql.copy_value("a\\rb") == "'a\rb'"


def test_copy_value_collapses_escaped_backslash(duckdb_pgsql):
    assert duckdb_pgsql.copy_value("a\\\\b") == "'a\\b'"


# --- split_copy_row: split on unescaped delimiter only --------------------

def test_split_copy_row_plain(duckdb_pgsql):
    assert duckdb_pgsql.split_copy_row("a\tb\tc", "\t") == ["a", "b", "c"]


def test_split_copy_row_keeps_escaped_delimiter(duckdb_pgsql):
    assert duckdb_pgsql.split_copy_row("a\\\tb", "\t") == ["a\\\tb"]


def test_split_copy_row_escaped_backslash_then_delimiter(duckdb_pgsql):
    assert duckdb_pgsql.split_copy_row("a\\\\\tb", "\t") == ["a\\\\", "b"]


# --- clean_ddl: the per-line fixes that were KEPT --------------------------

def test_clean_ddl_strips_schema_qualifiers(duckdb_pgsql):
    # CREATE SCHEMA is dropped, so every table has to land in `main`.
    assert duckdb_pgsql.clean_ddl("CREATE TABLE public.Foo (") == "CREATE TABLE Foo ("
    assert duckdb_pgsql.clean_ddl("  ON cd.Bookings") == "  ON Bookings"


def test_clean_ddl_strips_access_method(duckdb_pgsql):
    # "Binder Error: Unknown index type: BTREE".
    for method in ("btree", "hash", "lsm"):
        out = duckdb_pgsql.clean_ddl("CREATE INDEX ix ON t USING {} (id);".format(method))
        assert method not in out, method
        assert "CREATE INDEX ix ON t" in out and "(id);" in out


def test_clean_ddl_strips_oids(duckdb_pgsql):
    assert "OIDS" not in duckdb_pgsql.clean_ddl("CREATE TABLE t (id integer) WITH (OIDS=FALSE);")


def test_clean_ddl_demotes_serial(duckdb_pgsql):
    # DuckDB has no serial pseudo-type; the dumps supply every id explicitly.
    assert duckdb_pgsql.clean_ddl("    id serial NOT NULL,") == "    id integer NOT NULL,"
    assert duckdb_pgsql.clean_ddl("    id SERIAL UNIQUE NOT NULL,") == \
        "    id integer UNIQUE NOT NULL,"
    assert duckdb_pgsql.clean_ddl("    id bigserial,") == "    id bigint,"
    assert duckdb_pgsql.clean_ddl("    id smallserial,") == "    id smallint,"


def test_clean_ddl_serial_needs_a_word_boundary(duckdb_pgsql):
    # `pg_get_serial_sequence` and a column named `serial_no` are not the type.
    assert duckdb_pgsql.clean_ddl("    serial_no text,") == "    serial_no text,"
    assert "pg_get_serial_sequence" in duckdb_pgsql.clean_ddl(
        "SELECT pg_get_serial_sequence('t', 'id');")


def test_clean_ddl_strips_regclass_but_keeps_nextval(duckdb_pgsql):
    # DuckDB has sequences but no regclass type, so only the cast goes.
    assert duckdb_pgsql.clean_ddl("    id integer DEFAULT nextval('s'::regclass),") == \
        "    id integer DEFAULT nextval('s'),"


# --- clean_ddl: the rewrites that were DELETED ----------------------------

def test_clean_ddl_keeps_type_casts(duckdb_pgsql):
    # DuckDB speaks PostgreSQL casts; world's CHECK constraint relies on it.
    line = "    CONSTRAINT c CHECK ((continent = 'Asia'::text))"
    assert duckdb_pgsql.clean_ddl(line) == line


def test_clean_ddl_keeps_identifier_case(duckdb_pgsql):
    # DuckDB identifiers are case-insensitive and case-preserving, so
    # frenchtowns' `CREATE TABLE Regions` needs no folding.
    assert duckdb_pgsql.clean_ddl("CREATE TABLE Regions (") == "CREATE TABLE Regions ("


def test_clean_ddl_keeps_alter_table_only(duckdb_pgsql):
    assert duckdb_pgsql.clean_ddl("ALTER TABLE ONLY Foo") == "ALTER TABLE ONLY Foo"


# --- drop_foreign_keys: the clause, its comma, and its actions ------------

def test_drop_foreign_keys_takes_the_preceding_comma(duckdb_pgsql):
    # Dropping the line alone would leave `slots integer NOT NULL,` before `)`.
    sql = ('CREATE TABLE bookings (\n'
           '    bookid integer NOT NULL PRIMARY KEY,\n'
           '    slots integer NOT NULL,\n'
           '        FOREIGN KEY (facid) REFERENCES facilities(facid),\n'
           '        FOREIGN KEY (memid) REFERENCES members(memid)\n'
           ');')
    out = duckdb_pgsql.drop_foreign_keys(sql)
    assert "FOREIGN KEY" not in out
    assert "slots integer NOT NULL\n);" in out


def test_drop_foreign_keys_takes_referential_actions(duckdb_pgsql):
    # "FOREIGN KEY constraints cannot use CASCADE, SET NULL or SET DEFAULT".
    sql = ('CREATE TABLE members (\n'
           '    memid integer NOT NULL PRIMARY KEY,\n'
           '    recommendedby integer,\n'
           '    FOREIGN KEY (recommendedby) REFERENCES members(memid) ON DELETE SET NULL\n'
           ');')
    out = duckdb_pgsql.drop_foreign_keys(sql)
    assert "FOREIGN KEY" not in out and "ON DELETE" not in out
    assert "recommendedby integer\n);" in out


def test_drop_foreign_keys_keeps_other_constraints(duckdb_pgsql):
    sql = ('CREATE TABLE t (\n'
           '    a integer,\n'
           '    CONSTRAINT t_pkey PRIMARY KEY (a),\n'
           '    FOREIGN KEY (a) REFERENCES u(b)\n'
           ');')
    out = duckdb_pgsql.drop_foreign_keys(sql)
    assert 'CONSTRAINT t_pkey PRIMARY KEY (a)\n);' in out


def test_drop_foreign_keys_without_a_referenced_column_list(duckdb_pgsql):
    # `REFERENCES t` (PostgreSQL's "t's primary key" shorthand) is how every FK
    # in northwind is written. Matching the referenced table as one token is
    # what keeps a column-list-less clause from swallowing the whole of the
    # *next* FOREIGN KEY line hunting for a '(' -- which used to leave
    # `PRIMARY KEY (...) REFERENCES customers` and a parse error.
    sql = ('CREATE TABLE customer_customer_demo (\n'
           '    customer_id bpchar NOT NULL,\n'
           '    customer_type_id bpchar NOT NULL,\n'
           '    PRIMARY KEY (customer_id, customer_type_id),\n'
           '    FOREIGN KEY (customer_type_id) REFERENCES customer_demographics,\n'
           '    FOREIGN KEY (customer_id) REFERENCES customers\n'
           ');')
    out = duckdb_pgsql.drop_foreign_keys(sql)
    assert "FOREIGN KEY" not in out and "REFERENCES" not in out
    assert "    PRIMARY KEY (customer_id, customer_type_id)\n);" in out


def test_drop_foreign_keys_column_list_less_with_actions(duckdb_pgsql):
    sql = ('CREATE TABLE t (\n'
           '    a integer,\n'
           '    FOREIGN KEY (a) REFERENCES u ON DELETE CASCADE\n'
           ');')
    out = duckdb_pgsql.drop_foreign_keys(sql)
    assert out == 'CREATE TABLE t (\n    a integer\n);'


# --- keep_alter: DuckDB implements ADD PRIMARY KEY and nothing else -------

def test_keep_alter_primary_key(duckdb_pgsql):
    assert duckdb_pgsql.keep_alter(
        "ALTER TABLE ONLY city\n    ADD CONSTRAINT city_pkey PRIMARY KEY (id);")


def test_keep_alter_rejects_foreign_key_and_unique(duckdb_pgsql):
    # "Not implemented Error: No support for that ALTER TABLE option yet!"
    assert not duckdb_pgsql.keep_alter(
        "ALTER TABLE ONLY country\n"
        "    ADD CONSTRAINT c_fkey FOREIGN KEY (capital) REFERENCES city(id);")
    assert not duckdb_pgsql.keep_alter(
        "ALTER TABLE t\n    ADD CONSTRAINT t_uq UNIQUE (a);")


def test_keep_alter_rejects_owner_to(duckdb_pgsql):
    assert not duckdb_pgsql.keep_alter("ALTER TABLE t OWNER TO postgres;")


# --- ends_statement: quote-aware statement termination --------------------

def test_ends_statement_plain(duckdb_pgsql):
    assert duckdb_pgsql.ends_statement("SELECT 1;", False) == (False, True)


def test_ends_statement_semicolon_inside_literal(duckdb_pgsql):
    # A data row holding a semicolon must not end the INSERT early.
    assert duckdb_pgsql.ends_statement("(1, 'a;b'),", False) == (False, False)


def test_ends_statement_carries_open_literal_across_lines(duckdb_pgsql):
    in_string, done = duckdb_pgsql.ends_statement("(1, 'multi", False)
    assert in_string and not done
    assert duckdb_pgsql.ends_statement("line');", in_string) == (False, True)


def test_ends_statement_escaped_quote_does_not_close(duckdb_pgsql):
    assert duckdb_pgsql.ends_statement("(1, 'it''s; fine'),", False) == (False, False)


# --- convert_file: the COPY / buffered-statement state machine -------------

def _convert(mod, text):
    out = io.StringIO()
    mod.convert_file(text, out)
    return out.getvalue()


def test_convert_file_copy_block_to_insert(duckdb_pgsql):
    out = _convert(duckdb_pgsql,
                   "COPY public.Foo (id, name) FROM stdin;\n"
                   "1\talice\n"
                   "2\t\\N\n"
                   "\\.\n")
    # De-qualified but not folded: DuckDB resolves `Foo` and `foo` alike.
    assert out == (
        "INSERT INTO Foo (id, name) VALUES\n"
        "('1', 'alice'),\n"
        "('2', NULL);\n"
        "\n")


def test_convert_file_copy_honours_delimiter(duckdb_pgsql):
    out = _convert(duckdb_pgsql, "COPY foo (a, b) FROM stdin DELIMITER '|';\n"
                                 "1|x\n\\.\n")
    assert "('1', 'x')" in out


def test_convert_file_copy_batches_at_limit(duckdb_pgsql, monkeypatch):
    monkeypatch.setattr(duckdb_pgsql, "BATCH", 2)
    rows = "".join("{}\tn\n".format(i) for i in range(3))
    out = _convert(duckdb_pgsql, "COPY foo (id, name) FROM stdin;\n" + rows + "\\.\n")
    assert out.count("INSERT INTO foo") == 2


def test_convert_file_keeps_single_line_alter_table_primary_key(duckdb_pgsql):
    out = _convert(duckdb_pgsql,
                   "ALTER TABLE foo ADD CONSTRAINT pk PRIMARY KEY (id);\n"
                   "SELECT 1;")
    assert out == ("ALTER TABLE foo ADD CONSTRAINT pk PRIMARY KEY (id);\n"
                   "SELECT 1;\n")


def test_convert_file_keeps_multi_line_alter_table_primary_key(duckdb_pgsql):
    out = _convert(duckdb_pgsql,
                   "ALTER TABLE ONLY public.foo\n"
                   "    ADD CONSTRAINT pk PRIMARY KEY (id);\n"
                   "SELECT 1;")
    assert out == ("ALTER TABLE ONLY foo\n"
                   "    ADD CONSTRAINT pk PRIMARY KEY (id);\n"
                   "SELECT 1;\n")


def test_convert_file_drops_multi_line_alter_table_foreign_key(duckdb_pgsql):
    # The deciding verb is on the continuation line, so the statement has to be
    # buffered before the drop decision -- and the next statement must survive.
    out = _convert(duckdb_pgsql,
                   "ALTER TABLE ONLY country\n"
                   "    ADD CONSTRAINT c_fkey FOREIGN KEY (capital) REFERENCES city(id);\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_foreign_key_from_create_table(duckdb_pgsql):
    out = _convert(duckdb_pgsql,
                   "CREATE TABLE m (\n"
                   "    memid integer NOT NULL PRIMARY KEY,\n"
                   "    rec integer,\n"
                   "    FOREIGN KEY (rec) REFERENCES m(memid) ON DELETE SET NULL\n"
                   ");\n"
                   "SELECT 1;")
    assert "FOREIGN KEY" not in out
    assert "rec integer\n);" in out and out.endswith("SELECT 1;\n")


def test_convert_file_drops_function_block(duckdb_pgsql):
    out = _convert(duckdb_pgsql,
                   "CREATE OR REPLACE FUNCTION f() RETURNS int AS $$\n"
                   "BEGIN RETURN 1; END;\n"
                   "$$ LANGUAGE plpgsql;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_noise_lines(duckdb_pgsql):
    for line in ("SET search_path = public;",
                 "SET client_encoding = 'LATIN1';",
                 "SELECT pg_catalog.setval('s', 1, true);",
                 "SELECT pg_catalog.set_config('search_path', '', false);",
                 "GRANT ALL ON TABLE foo TO postgres;",
                 "REVOKE ALL ON TABLE foo FROM public;",
                 "WITHOUT OIDS;",
                 "  USING btree",
                 "CREATE SCHEMA cd;",
                 "\\connect mydb"):
        assert _convert(duckdb_pgsql, line) == "", line


def test_convert_file_drops_create_domain(duckdb_pgsql):
    # "Parser Error: syntax error at or near ..." -- sportsdb's
    # `CREATE DOMAIN primary_id AS integer;`, which nothing downstream uses.
    out = _convert(duckdb_pgsql,
                   "CREATE DOMAIN primary_id AS integer;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_multi_line_create_domain(duckdb_pgsql):
    # Buffered to the ';': half a domain left behind is a parse error of its
    # own, and the statement after it must survive.
    out = _convert(duckdb_pgsql,
                   "CREATE DOMAIN posint AS integer\n"
                   "    CONSTRAINT posint_check CHECK ((VALUE > 0));\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_keeps_statements_sqlite_drops(duckdb_pgsql):
    # DuckDB has real sequences, COMMENT ON, and PostgreSQL's transaction and
    # maintenance statements; none of them may be swallowed.
    for line in ("CREATE SEQUENCE items_id_seq;",
                 "COMMENT ON TABLE foo IS 'x';",
                 "BEGIN;", "COMMIT;", "ANALYZE country;"):
        assert _convert(duckdb_pgsql, line) == line + "\n", line


def test_convert_file_passes_multi_row_insert_through_untouched(duckdb_pgsql):
    # Only the header names the table; every data line is copied verbatim, so a
    # value that reads like DDL ("serial", "cd.", a cast) is never rewritten.
    text = ("-- a comment\n"
            "INSERT INTO cd.facilities (id, note) VALUES\n"
            "(1, 'serial cd. A::B'),\n"
            "(2, 'x');\n"
            "SELECT 1;")
    assert _convert(duckdb_pgsql, text) == (
        "-- a comment\n"
        "INSERT INTO facilities (id, note) VALUES\n"
        "(1, 'serial cd. A::B'),\n"
        "(2, 'x');\n"
        "SELECT 1;\n")


# --- PGSQL_EMPTY_BYTEA: the one environment knob ---------------------------
#
# northwind writes its empty bytea values as `'\x'`, which DuckDB's BLOB parser
# rejects ("Invalid hex escape code"). The rewrite to `''` is opt-in because the
# hook sees no column types and the identical token in a *text* column is the
# literal two-character string `\x` -- so every test here comes in an enabled
# flavour and a default-off guard.

KNOBS = ("PGSQL_EMPTY_BYTEA", "PGSQL_EXTRA_SCHEMAS", "PGSQL_DROP_VIEWS",
         "PGSQL_TYPE_MAP", "PGSQL_COPY_CSV")


@pytest.fixture
def knob_env(duckdb_pgsql, monkeypatch):
    """Set transform knobs in the environment and re-run configure().

    Restores the default (knob-free) module configuration afterwards, so the
    session-scoped module fixture never leaks knob state into other tests.
    """
    def activate(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        duckdb_pgsql.configure()
    yield activate
    for knob in KNOBS:
        monkeypatch.delenv(knob, raising=False)
    duckdb_pgsql.configure()


def test_empty_bytea_default_off(duckdb_pgsql):
    # Guard: without the knob the dump reaches DuckDB byte-for-byte, so the six
    # datasets that symlink straight to scripts/pgsql are untouched.
    assert duckdb_pgsql.rewrite_empty_bytea("(1, 'Beverages', '\\x'),") == \
        "(1, 'Beverages', '\\x'),"


def test_empty_bytea_knob_rewrites_the_literal(duckdb_pgsql, knob_env):
    knob_env(PGSQL_EMPTY_BYTEA="1")
    assert duckdb_pgsql.rewrite_empty_bytea("(1, 'Beverages', '\\x'),") == \
        "(1, 'Beverages', ''),"
    # Every occurrence, across lines.
    assert duckdb_pgsql.rewrite_empty_bytea("a '\\x'\nb '\\x'\n") == "a ''\nb ''\n"


def test_empty_bytea_knob_leaves_non_empty_bytea(duckdb_pgsql, knob_env):
    # A bytea with actual hex in it converts fine; only the empty one is a
    # problem, so only the empty one may be touched.
    knob_env(PGSQL_EMPTY_BYTEA="1")
    for line in ("(1, '\\x89ABCDEF'),", "(1, '\\xff'),"):
        assert duckdb_pgsql.rewrite_empty_bytea(line) == line, line


def test_empty_bytea_knob_matches_only_the_whole_literal(duckdb_pgsql, knob_env):
    # The token is quote-backslash-x-quote: a value that merely *ends* in \x,
    # one that merely starts with it, and two adjacent literals that happen to
    # abut are all left alone.
    knob_env(PGSQL_EMPTY_BYTEA="1")
    for line in ("(1, 'C:\\x'),", "(1, '\\x is a prefix'),", "(1, 'a\\', 'x'),"):
        assert duckdb_pgsql.rewrite_empty_bytea(line) == line, line


def test_main_applies_the_knob_in_place(duckdb_pgsql, tmp_path, monkeypatch):
    # End to end: main() reads the knob via configure(), so the northwind hook
    # only has to export it before exec'ing this one.
    work = tmp_path / "data.sql"
    work.write_text("INSERT INTO categories VALUES\n(1, 'Beverages', '\\x');\n",
                    encoding="utf-8")
    monkeypatch.setenv("SQL_FILES", str(work))
    monkeypatch.setenv("PGSQL_EMPTY_BYTEA", "1")
    monkeypatch.chdir(tmp_path)
    duckdb_pgsql.main()
    monkeypatch.delenv("PGSQL_EMPTY_BYTEA")
    duckdb_pgsql.configure()
    assert work.read_text(encoding="utf-8") == \
        "INSERT INTO categories VALUES\n(1, 'Beverages', '');\n\n"


# --- detect_encoding / stream_lines: the streaming reader ------------------
#
# The dump is read a line at a time (the airlines one is 499 MB), so the
# encoding has to be decided without holding the file, and the line stream has
# to hand convert_lines() exactly what ``text.split("\n")`` used to.

def test_detect_encoding_utf8(duckdb_pgsql, tmp_path):
    p = tmp_path / "u.sql"
    p.write_bytes("café\n".encode("utf-8"))
    assert duckdb_pgsql.detect_encoding(str(p)) == "utf-8"


def test_detect_encoding_latin1_fallback(duckdb_pgsql, tmp_path):
    # world / usda / dellstore ship Latin-1; DuckDB validates UTF-8 and would
    # abort on the first accented value.
    p = tmp_path / "l.sql"
    p.write_bytes("café\n".encode("latin-1"))
    assert duckdb_pgsql.detect_encoding(str(p)) == "latin-1"


def test_detect_encoding_spans_chunk_boundaries(duckdb_pgsql, tmp_path,
                                                monkeypatch):
    # A multi-byte character split across two reads must not read as Latin-1;
    # that is the whole reason the sniff uses an incremental decoder.
    monkeypatch.setattr(duckdb_pgsql, "CHUNK", 4)
    p = tmp_path / "c.sql"
    p.write_bytes("abcé-tail\n".encode("utf-8"))
    assert duckdb_pgsql.detect_encoding(str(p)) == "utf-8"


@pytest.mark.parametrize("text", ["a\nb\n", "a\nb", "", "\n", "a\r\nb\r\n"])
def test_stream_lines_matches_split(duckdb_pgsql, tmp_path, text):
    p = tmp_path / "s.sql"
    p.write_text(text, encoding="utf-8", newline="")
    assert list(duckdb_pgsql.stream_lines(str(p), "utf-8")) == text.split("\n")


# --- main(): file selection -----------------------------------------------

def test_main_exits_without_sql_files(duckdb_pgsql, tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_FILES", "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        duckdb_pgsql.main()


def test_main_writes_no_preamble(duckdb_pgsql, tmp_path, monkeypatch):
    # The SQLite hook opens its first file with PRAGMA synchronous=OFF; DuckDB
    # has no such pragma and would fail on it.
    work = tmp_path / "a.sql"
    work.write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.setenv("SQL_FILES", str(work))
    monkeypatch.chdir(tmp_path)
    duckdb_pgsql.main()
    assert work.read_text(encoding="utf-8") == "SELECT 1;\n\n"


# --- golden: full main() run, in place -------------------------------------

def test_golden_dump(duckdb_pgsql, tmp_path, monkeypatch):
    # Same input dump as test_pgsql.py / test_sqlite_pgsql.py's goldens, so the
    # three dialects' whole-file output can be diffed against each other by eye.
    work = tmp_path / "work.sql"
    work.write_bytes((FIXTURES / "dump.sql").read_bytes())
    monkeypatch.setenv("SQL_FILES", str(work))
    monkeypatch.chdir(tmp_path)
    duckdb_pgsql.main()
    assert work.read_text(encoding="utf-8") == \
        (FIXTURES / "dump.expected_duckdb.sql").read_text(encoding="utf-8")


# --- PGSQL_EXTRA_SCHEMAS: extra qualifiers to flatten ----------------------
#
# The airlines demo qualifies every object to a `bookings` schema it also
# creates; CREATE SCHEMA is dropped unconditionally, so the qualifier has to go
# with it or nothing resolves.

def test_extra_schemas_default_off(duckdb_pgsql):
    assert duckdb_pgsql.strip_schema("CREATE TABLE bookings.flights (") == \
        "CREATE TABLE bookings.flights ("


def test_extra_schemas_knob_strips_the_named_schema(duckdb_pgsql, knob_env):
    knob_env(PGSQL_EXTRA_SCHEMAS="bookings")
    assert duckdb_pgsql.strip_schema("CREATE TABLE bookings.flights (") == \
        "CREATE TABLE flights ("
    # ...without losing the two the hook has always stripped.
    assert duckdb_pgsql.strip_schema("ON public.t, cd.u") == "ON t, u"


def test_extra_schemas_knob_accepts_several(duckdb_pgsql, knob_env):
    knob_env(PGSQL_EXTRA_SCHEMAS="bookings, demo")
    assert duckdb_pgsql.strip_schema("bookings.a demo.b") == "a b"


def test_extra_schemas_knob_needs_a_word_boundary(duckdb_pgsql, knob_env):
    # `mybookings.t` is a different schema; only the whole name matches.
    knob_env(PGSQL_EXTRA_SCHEMAS="bookings")
    assert duckdb_pgsql.strip_schema("mybookings.t") == "mybookings.t"


def test_strip_schema_takes_only_the_leading_qualifier(duckdb_pgsql, knob_env):
    # The airlines demo's `bookings` schema holds a `bookings` table, so
    # pg_dump writes `COMMENT ON COLUMN bookings.bookings.book_ref`. Stripping
    # every occurrence would leave `COMMENT ON COLUMN book_ref`, a Binder Error
    # with no table left in it.
    knob_env(PGSQL_EXTRA_SCHEMAS="bookings")
    assert duckdb_pgsql.strip_schema(
        "COMMENT ON COLUMN bookings.bookings.book_ref IS 'Booking number';") == \
        "COMMENT ON COLUMN bookings.book_ref IS 'Booking number';"
    assert duckdb_pgsql.strip_schema("CREATE TABLE bookings.bookings (") == \
        "CREATE TABLE bookings ("


def test_strip_schema_default_pair_is_unchanged_by_the_lookbehind(duckdb_pgsql):
    assert duckdb_pgsql.strip_schema("CREATE INDEX i ON cd.bookings (x);") == \
        "CREATE INDEX i ON bookings (x);"
    assert duckdb_pgsql.strip_schema("REFERENCES public.city(id)") == \
        "REFERENCES city(id)"


# --- PGSQL_DROP_VIEWS: views, and the comments that hang off them ---------
#
# DuckDB has views, so this is never about the syntax: it is for dumps whose
# view bodies need PostgreSQL semantics the rest of the conversion has taken
# away (airlines' three views want `AT TIME ZONE`, the range operator `@>` and
# a dropped PL/pgSQL function). Comments have to go with them, unlike on
# SQLite, because here COMMENT ON survives and a comment on a missing view is a
# Catalog Error.

def test_drop_views_default_off(duckdb_pgsql):
    text = "CREATE VIEW v AS SELECT 1;\nSELECT 1;"
    assert _convert(duckdb_pgsql, text) == text + "\n"


def test_drop_views_knob_drops_single_line(duckdb_pgsql, knob_env):
    knob_env(PGSQL_DROP_VIEWS="1")
    assert _convert(duckdb_pgsql, "CREATE VIEW v AS SELECT 1;\nSELECT 1;") == \
        "SELECT 1;\n"


def test_drop_views_knob_drops_multi_line_and_materialized(duckdb_pgsql, knob_env):
    knob_env(PGSQL_DROP_VIEWS="1")
    out = _convert(duckdb_pgsql,
                   "CREATE MATERIALIZED VIEW v AS\n"
                   " SELECT a,\n"
                   "    b\n"
                   "   FROM t;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_drop_views_knob_drops_the_views_comments(duckdb_pgsql, knob_env):
    # "Catalog Error: View with name airplanes does not exist!"
    knob_env(PGSQL_DROP_VIEWS="1")
    out = _convert(duckdb_pgsql,
                   "CREATE VIEW airplanes AS SELECT model FROM airplanes_data;\n"
                   "COMMENT ON VIEW airplanes IS 'Airplanes';\n"
                   "COMMENT ON COLUMN airplanes.model IS 'Airplane model';\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_drop_views_knob_keeps_table_comments(duckdb_pgsql, knob_env):
    # The point of dropping only the view's comments: DuckDB supports
    # COMMENT ON TABLE/COLUMN, so the surviving tables keep their docs. Note
    # `airplanes_data` starts with the dropped view's whole name.
    knob_env(PGSQL_DROP_VIEWS="1")
    out = _convert(duckdb_pgsql,
                   "CREATE VIEW airplanes AS SELECT model FROM airplanes_data;\n"
                   "COMMENT ON TABLE airplanes_data IS 'Airplanes (raw)';\n"
                   "COMMENT ON COLUMN airplanes_data.model IS 'Airplane model';\n")
    assert out == ("COMMENT ON TABLE airplanes_data IS 'Airplanes (raw)';\n"
                   "COMMENT ON COLUMN airplanes_data.model IS 'Airplane model';\n"
                   "\n")


def test_drop_views_knob_resolves_the_schema_qualifier(duckdb_pgsql, knob_env):
    # The view is declared `bookings.airplanes` and its comments say
    # `bookings.airplanes.model`; both have to be matched after flattening.
    knob_env(PGSQL_DROP_VIEWS="1", PGSQL_EXTRA_SCHEMAS="bookings")
    out = _convert(duckdb_pgsql,
                   "CREATE VIEW bookings.airplanes AS SELECT 1;\n"
                   "COMMENT ON COLUMN bookings.airplanes.model IS 'x';\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_view_name_and_comment_target(duckdb_pgsql):
    assert duckdb_pgsql.view_name('CREATE OR REPLACE VIEW "Airplanes" AS') == \
        "airplanes"
    assert duckdb_pgsql.comment_target("COMMENT ON VIEW airplanes IS 'x';") == \
        "airplanes"
    assert duckdb_pgsql.comment_target(
        "COMMENT ON COLUMN airplanes.model IS 'x';") == "airplanes"
    # A table comment names no view, so it can never be matched by accident.
    assert duckdb_pgsql.comment_target("COMMENT ON TABLE airplanes IS 'x';") is None


# --- PGSQL_TYPE_MAP: column types DuckDB has no equivalent for ------------

def test_type_map_default_off(duckdb_pgsql):
    text = "CREATE TABLE t (\n    model jsonb NOT NULL\n);"
    assert _convert(duckdb_pgsql, text) == text + "\n"


def test_type_map_knob_rewrites_column_types(duckdb_pgsql, knob_env):
    knob_env(PGSQL_TYPE_MAP="jsonb=json point=text tstzrange=text")
    out = _convert(duckdb_pgsql,
                   "CREATE TABLE t (\n"
                   "    model jsonb NOT NULL,\n"
                   "    coordinates point NOT NULL,\n"
                   "    validity tstzrange NOT NULL\n"
                   ");")
    assert out == ("CREATE TABLE t (\n"
                   "    model json NOT NULL,\n"
                   "    coordinates text NOT NULL,\n"
                   "    validity text NOT NULL\n"
                   ");\n")


def test_type_map_knob_matches_array_spelling(duckdb_pgsql, knob_env):
    # "Conversion Error: Type VARCHAR with value '{1,2,3}' can't be cast to the
    # destination type INTEGER[]" -- the type exists, the literal will not go
    # into it, so the column keeps the literal as text.
    knob_env(PGSQL_TYPE_MAP="integer[]=text")
    out = _convert(duckdb_pgsql,
                   "CREATE TABLE t (\n"
                   "    days_of_week integer[] NOT NULL,\n"
                   "    spaced integer [ ] NOT NULL\n"
                   ");")
    assert "integer" not in out
    assert out.count("text NOT NULL") == 2


def test_type_map_knob_is_scoped_to_create_table(duckdb_pgsql, knob_env):
    # A value, an index or a comment that happens to say `point` is not a
    # column declaration.
    knob_env(PGSQL_TYPE_MAP="point=text")
    for line in ("COMMENT ON COLUMN t.c IS 'a point on the map';",
                 "CREATE INDEX i ON t (point_id);"):
        assert _convert(duckdb_pgsql, line) == line + "\n", line


# --- PGSQL_COPY_CSV: COPY blocks out to sidecar CSV files ------------------
#
# The airlines demo is 10.7M rows; as INSERT text that is ~700 MB for DuckDB's
# SQL parser to walk one statement at a time, where its CSV reader is
# vectorized. The knob only changes how the rows travel, never which rows.

def test_copy_csv_default_off(duckdb_pgsql, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = _convert(duckdb_pgsql, "COPY foo (id, name) FROM stdin;\n1\ta\n\\.\n")
    assert out.startswith("INSERT INTO foo")
    assert not list(tmp_path.glob("*.csv"))


def test_copy_csv_knob_writes_a_sidecar_and_a_copy(duckdb_pgsql, knob_env,
                                                   tmp_path, monkeypatch):
    knob_env(PGSQL_COPY_CSV="1")
    monkeypatch.chdir(tmp_path)
    out = _convert(duckdb_pgsql,
                   "COPY public.foo (id, name) FROM stdin;\n"
                   "1\talice\n"
                   "2\tbob\n"
                   "\\.\n"
                   "SELECT 1;")
    assert out == (
        "COPY foo (id, name) FROM 'foo.csv' ({});\n"
        "SELECT 1;\n".format(duckdb_pgsql.CSV_OPTIONS))
    assert (tmp_path / "foo.csv").read_text(encoding="utf-8") == \
        "1,alice\n2,bob\n"


def test_copy_csv_knob_writes_beside_the_sql_file(duckdb_pgsql, knob_env,
                                                  tmp_path, monkeypatch):
    # main() passes the SQL file's own directory, so the relative path the
    # emitted COPY carries resolves from the build dir the loader runs in.
    knob_env(PGSQL_COPY_CSV="1")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    out = io.StringIO()
    duckdb_pgsql.convert_file("COPY foo (id) FROM stdin;\n1\n\\.\n", out, "sub")
    assert "FROM 'sub/foo.csv'" in out.getvalue()
    assert (tmp_path / "sub" / "foo.csv").read_text(encoding="utf-8") == "1\n"


def test_copy_csv_knob_honours_delimiter(duckdb_pgsql, knob_env, tmp_path,
                                         monkeypatch):
    knob_env(PGSQL_COPY_CSV="1")
    monkeypatch.chdir(tmp_path)
    _convert(duckdb_pgsql, "COPY foo (a, b) FROM stdin DELIMITER '|';\n1|x\n\\.\n")
    assert (tmp_path / "foo.csv").read_text(encoding="utf-8") == "1,x\n"


# --- csv_field: NULL and the empty string must stay distinguishable --------

def test_csv_field_null_sentinel_is_a_bare_empty_field(duckdb_pgsql):
    # Read back as NULL by `NULLSTR ''`.
    assert duckdb_pgsql.csv_field("\\N") == ""


def test_csv_field_empty_string_is_quoted(duckdb_pgsql):
    # Read back as '' by `ALLOW_QUOTED_NULLS false` -- with the DuckDB default
    # (true) this would arrive as NULL, which is the whole reason the option is
    # spelled out in CSV_OPTIONS.
    assert duckdb_pgsql.csv_field("") == '""'


def test_csv_field_quotes_only_when_it_has_to(duckdb_pgsql):
    assert duckdb_pgsql.csv_field("alice") == "alice"
    assert duckdb_pgsql.csv_field("a,b") == '"a,b"'
    assert duckdb_pgsql.csv_field('he said "hi"') == '"he said ""hi"""'


def test_csv_field_unescapes_and_then_quotes_control_characters(duckdb_pgsql):
    # COPY writes a tab/newline/CR inside a field as \t / \n / \r; the CSV has
    # to carry the real character, and a newline or CR forces quoting.
    assert duckdb_pgsql.csv_field("a\\tb") == "a\tb"
    assert duckdb_pgsql.csv_field("a\\nb") == '"a\nb"'
    assert duckdb_pgsql.csv_field("a\\rb") == '"a\rb"'
    assert duckdb_pgsql.csv_field("a\\\\b") == "a\\b"


def test_csv_field_leaves_a_single_quote_alone(duckdb_pgsql):
    # Unlike copy_value(), which is building a SQL literal.
    assert duckdb_pgsql.csv_field("it's") == "it's"


# --- CREATE FUNCTION: both terminator shapes ------------------------------

def test_convert_file_drops_sql_standard_body_function(duckdb_pgsql):
    # PostgreSQL 14+'s body form has no `LANGUAGE <x>;` terminator at all, so
    # a hook looking only for one swallows the rest of the dump -- which is
    # exactly what happened to the airlines demo's three functions.
    out = _convert(duckdb_pgsql,
                   "CREATE FUNCTION bookings.now() RETURNS timestamp with time zone\n"
                   "    LANGUAGE sql IMMUTABLE\n"
                   "    RETURN '2025-12-01 00:00:00+00'::timestamp with time zone;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_keeps_a_return_inside_a_quoted_body(duckdb_pgsql):
    # The RETURN terminator is gated on the function having no AS body, so
    # dellstore's PL/pgSQL body cannot end its own block early and take the
    # `LANGUAGE plpgsql;` line -- and the schema after it -- with it.
    out = _convert(duckdb_pgsql,
                   "CREATE FUNCTION f() RETURNS int AS $$\n"
                   "BEGIN\n"
                   "RETURN 1;\n"
                   "END;\n"
                   "$$ LANGUAGE plpgsql;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_keeps_a_return_inside_a_body_opened_later(duckdb_pgsql):
    # `AS $$` on a continuation line still counts as a body.
    out = _convert(duckdb_pgsql,
                   "CREATE FUNCTION f()\n"
                   "RETURNS integer\n"
                   "AS $$\n"
                   "RETURN 1;\n"
                   "$$ LANGUAGE plpgsql;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"
