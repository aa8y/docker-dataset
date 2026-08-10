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
                 "GRANT ALL ON TABLE foo TO postgres;",
                 "REVOKE ALL ON TABLE foo FROM public;",
                 "WITHOUT OIDS;",
                 "  USING btree",
                 "CREATE SCHEMA cd;",
                 "\\connect mydb"):
        assert _convert(duckdb_pgsql, line) == "", line


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


# --- transcode: encoding fallback -----------------------------------------

def test_transcode_utf8(duckdb_pgsql, tmp_path):
    p = tmp_path / "u.sql"
    p.write_bytes("café\n".encode("utf-8"))
    assert duckdb_pgsql.transcode(str(p)) == "café\n"


def test_transcode_latin1_fallback(duckdb_pgsql, tmp_path):
    # world / usda / dellstore ship Latin-1; DuckDB validates UTF-8 and would
    # abort on the first accented value.
    p = tmp_path / "l.sql"
    p.write_bytes("café\n".encode("latin-1"))
    assert duckdb_pgsql.transcode(str(p)) == "café\n"


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
