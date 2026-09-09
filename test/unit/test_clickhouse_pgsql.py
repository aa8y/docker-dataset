"""Unit tests for clickhouse/scripts/pgsql/transform (PostgreSQL dump -> ClickHouse).

Where the mysql/sqlite/duckdb hooks *filter* a dump, this one rebuilds it: it
parses every ``CREATE TABLE`` into columns and constraints and re-emits it with
ClickHouse types, a MergeTree engine and a sorting key. So the tests here are
shaped a little differently from test_duckdb_pgsql.py -- alongside the shared
COPY / statement-scanning cases they pin the three pieces that are new and where
a bug is invisible to a row-count integration test:

* the **type map**, including the two decisions that are not one-to-one
  (unconstrained ``numeric`` -> Float64 vs ``numeric(p,s)`` -> Decimal, and
  date/timestamp -> the 32/64 variants that reach back before 1970);
* the **nullability and sorting-key rules** -- a column is Nullable unless it
  says NOT NULL, *except* a sorting-key column, which MergeTree refuses to let
  be Nullable, and a table with no primary key anywhere gets ORDER BY tuple();
* the **backslash doubling**, which has no counterpart in any other dialect
  here: PostgreSQL reads a backslash in a literal as itself and ClickHouse reads
  it as an escape, so every emitted and passed-through literal has to be
  rewritten or values silently change meaning.
"""
import io
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pgsql"


# --- identifiers: PostgreSQL folding, ClickHouse quoting -------------------

def test_parse_ident_folds_unquoted(clickhouse_pgsql):
    # PostgreSQL lower-cases unquoted names; ClickHouse folds nothing, so the
    # hook has to do it or frenchtowns' `CREATE TABLE Regions` and its
    # `COPY regions` end up naming different tables.
    assert clickhouse_pgsql.parse_ident("Regions (") == ("regions", " (")


def test_parse_ident_keeps_quoted_case(clickhouse_pgsql):
    assert clickhouse_pgsql.parse_ident('"InvoiceLine" (')[0] == "InvoiceLine"


def test_parse_ident_drops_schema_qualifier(clickhouse_pgsql):
    # ClickHouse's namespace *is* the database and each image holds one dataset,
    # so public./cd. qualifiers are flattened away.
    assert clickhouse_pgsql.parse_ident("public.Items (")[0] == "items"
    assert clickhouse_pgsql.parse_ident('cd."Bookings" (')[0] == "Bookings"


def test_quote_uses_backticks(clickhouse_pgsql):
    # usda has columns called `min`, `max` and "year"; quoting every identifier
    # keeps them from ever being read as function names or keywords.
    assert clickhouse_pgsql.quote("min") == "`min`"


def test_split_ident_list_folds_each(clickhouse_pgsql):
    assert clickhouse_pgsql.split_ident_list('countrycode, "language"') == \
        ["countrycode", "language"]


# --- type map --------------------------------------------------------------

def test_map_type_integers(clickhouse_pgsql):
    assert clickhouse_pgsql.map_type("smallint") == "Int16"
    assert clickhouse_pgsql.map_type("integer") == "Int32"
    assert clickhouse_pgsql.map_type("bigint") == "Int64"


def test_map_type_serial_is_its_underlying_integer(clickhouse_pgsql):
    # ClickHouse has no serial pseudo-type and no sequences; the dumps supply
    # every id explicitly, so a plain integer column is faithful.
    assert clickhouse_pgsql.map_type("serial") == "Int32"
    assert clickhouse_pgsql.map_type("bigserial") == "Int64"
    assert clickhouse_pgsql.map_type("smallserial") == "Int16"


def test_map_type_floats(clickhouse_pgsql):
    assert clickhouse_pgsql.map_type("real") == "Float32"
    assert clickhouse_pgsql.map_type("double precision") == "Float64"


def test_map_type_numeric_split(clickhouse_pgsql):
    # A declared precision becomes a Decimal; bare `numeric` (pgexercises' money
    # columns) cannot, because ClickHouse's Decimal has no default precision.
    assert clickhouse_pgsql.map_type("numeric(10,2)") == "Decimal(10, 2)"
    assert clickhouse_pgsql.map_type("numeric(12)") == "Decimal(12, 0)"
    assert clickhouse_pgsql.map_type("numeric") == "Float64"


def test_map_type_strings(clickhouse_pgsql):
    for spelling in ("text", "character varying(40)", "character(3)", "varchar"):
        assert clickhouse_pgsql.map_type(spelling) == "String", spelling


def test_map_type_boolean(clickhouse_pgsql):
    assert clickhouse_pgsql.map_type("boolean") == "Bool"


def test_map_type_dates_use_the_wide_variants(clickhouse_pgsql):
    # Date and DateTime both start at 1970-01-01; chinook's Employee.BirthDate
    # is 1947-1973, so the 32/64 variants are the only faithful mapping (and
    # DateTime64(6) also matches PostgreSQL timestamp's microsecond resolution).
    assert clickhouse_pgsql.map_type("date") == "Date32"
    assert clickhouse_pgsql.map_type("timestamp without time zone") == "DateTime64(6)"
    assert clickhouse_pgsql.map_type("TIMESTAMP") == "DateTime64(6)"


def test_map_type_falls_back_to_string(clickhouse_pgsql):
    for spelling in ("interval", "time without time zone", "bytea", "uuid"):
        assert clickhouse_pgsql.map_type(spelling) == "String", spelling


# --- literals: backslashes are escapes in ClickHouse, not in PostgreSQL ----

def test_escape_backslashes_inside_literals(clickhouse_pgsql):
    # chinook: 'Cavalleria Rusticana \ Act \ Intermezzo Sinfonico'.
    assert clickhouse_pgsql.escape_backslashes("VALUES ('a \\ b');") == \
        "VALUES ('a \\\\ b');"


def test_escape_backslashes_leaves_code_outside_literals(clickhouse_pgsql):
    assert clickhouse_pgsql.escape_backslashes("SELECT 1;") == "SELECT 1;"


def test_escape_backslashes_respects_the_doubled_quote(clickhouse_pgsql):
    # '' is an escaped quote in both dialects and must not be read as a close.
    assert clickhouse_pgsql.escape_backslashes("('it''s \\ fine', 2)") == \
        "('it''s \\\\ fine', 2)"


def test_copy_value_null_sentinel(clickhouse_pgsql):
    assert clickhouse_pgsql.copy_value("\\N") == "NULL"


def test_copy_value_doubles_single_quote(clickhouse_pgsql):
    assert clickhouse_pgsql.copy_value("it's") == "'it''s'"


def test_copy_value_reescapes_control_characters(clickhouse_pgsql):
    # COPY writes a tab as \t; ClickHouse reads \t as a tab, so the escape can
    # travel as-is rather than being expanded into a raw control character --
    # which also keeps every emitted row on one line.
    assert clickhouse_pgsql.copy_value("a\\tb") == "'a\\tb'"
    assert clickhouse_pgsql.copy_value("a\\nb") == "'a\\nb'"


def test_copy_value_doubles_backslash(clickhouse_pgsql):
    # COPY's \\ is one literal backslash, which ClickHouse needs doubled again.
    assert clickhouse_pgsql.copy_value("a\\\\b") == "'a\\\\b'"


def test_split_copy_row_plain(clickhouse_pgsql):
    assert clickhouse_pgsql.split_copy_row("a\tb\tc", "\t") == ["a", "b", "c"]


def test_split_copy_row_keeps_escaped_delimiter(clickhouse_pgsql):
    assert clickhouse_pgsql.split_copy_row("a\\\tb", "\t") == ["a\\\tb"]


def test_split_copy_row_honours_a_custom_delimiter(clickhouse_pgsql):
    # iso3166's COPY blocks are pipe-delimited.
    assert clickhouse_pgsql.split_copy_row("a|b", "|") == ["a", "b"]


# --- CREATE TABLE: body splitting -----------------------------------------

def test_split_body_ignores_commas_in_nested_parens(clickhouse_pgsql):
    parts = clickhouse_pgsql.split_body("a numeric(10,2), b integer")
    assert [p.strip() for p in parts] == ["a numeric(10,2)", "b integer"]


def test_split_body_ignores_commas_in_comments(clickhouse_pgsql):
    # frenchtowns: `capital VARCHAR(10) NOT NULL, -- REFERENCES Towns (code),`
    parts = clickhouse_pgsql.split_body(
        "a text, -- REFERENCES Towns (code),\n   b text")
    assert len(parts) == 2


def test_split_body_ignores_commas_in_literals(clickhouse_pgsql):
    parts = clickhouse_pgsql.split_body("a text DEFAULT 'x,y', b text")
    assert [p.strip() for p in parts] == ["a text DEFAULT 'x,y'", "b text"]


# --- CREATE TABLE: parse + render -----------------------------------------

def _render(mod, sql, alter_keys=None):
    table, columns, pk = mod.parse_create_table(sql)
    return mod.render_create_table(
        table, columns, pk or (alter_keys or {}).get(table, []))


def test_render_nullable_unless_not_null(clickhouse_pgsql):
    # PostgreSQL columns are nullable by default, ClickHouse's are the opposite.
    out = _render(clickhouse_pgsql,
                  "CREATE TABLE t (\n  a integer NOT NULL,\n  b text\n);")
    assert "`a` Int32" in out and "`b` Nullable(String)" in out


def test_render_without_a_primary_key_orders_by_tuple(clickhouse_pgsql):
    # frenchtowns declares only UNIQUE; usda's footnote nothing at all.
    out = _render(clickhouse_pgsql, "CREATE TABLE t (\n  a integer\n);")
    assert out.rstrip().endswith("ENGINE = MergeTree ORDER BY tuple();")


def test_render_inline_primary_key_becomes_the_sorting_key(clickhouse_pgsql):
    # iso3166: `two_letter TEXT PRIMARY KEY`.
    out = _render(clickhouse_pgsql,
                  "CREATE TABLE t (\n  two_letter TEXT PRIMARY KEY,\n  n text\n);")
    assert out.rstrip().endswith("ENGINE = MergeTree ORDER BY (`two_letter`);")


def test_render_table_constraint_primary_key(clickhouse_pgsql):
    # chinook: `CONSTRAINT "PK_PlaylistTrack" PRIMARY KEY ("PlaylistId", "TrackId")`.
    out = _render(clickhouse_pgsql,
                  'CREATE TABLE "PlaylistTrack" (\n'
                  '  "PlaylistId" INT NOT NULL,\n'
                  '  "TrackId" INT NOT NULL,\n'
                  '  CONSTRAINT "PK_PlaylistTrack" PRIMARY KEY ("PlaylistId", "TrackId")\n'
                  ');')
    assert out.rstrip().endswith(
        "ENGINE = MergeTree ORDER BY (`PlaylistId`, `TrackId`);")


def test_render_sorting_key_column_is_never_nullable(clickhouse_pgsql):
    # "Sorting key contains nullable columns, but merge tree setting
    # `allow_nullable_key` is disabled" (code 44). A PostgreSQL primary key
    # implies NOT NULL anyway, so forcing it loses nothing.
    out = _render(clickhouse_pgsql,
                  "CREATE TABLE t (\n  a integer PRIMARY KEY,\n  b text\n);")
    assert "`a` Int32,\n" in out and "Nullable(Int32)" not in out


def test_render_uses_an_alter_table_primary_key(clickhouse_pgsql):
    # world/usda/dellstore declare their keys *after* the data, so the key has
    # to be carried in from the collecting pass.
    out = _render(clickhouse_pgsql,
                  "CREATE TABLE city (\n  id integer NOT NULL,\n  name text NOT NULL\n);",
                  {"city": ["id"]})
    assert out.rstrip().endswith("ENGINE = MergeTree ORDER BY (`id`);")


def test_render_drops_constraints_clickhouse_has_no_form_for(clickhouse_pgsql):
    out = _render(clickhouse_pgsql,
                  "CREATE TABLE t (\n"
                  "  a integer NOT NULL,\n"
                  "  b integer REFERENCES u(b),\n"
                  "  CONSTRAINT c CHECK ((a > 0)),\n"
                  "  UNIQUE (a, b),\n"
                  "  FOREIGN KEY (a) REFERENCES u(a)\n"
                  ");")
    for gone in ("REFERENCES", "CHECK", "UNIQUE", "FOREIGN KEY"):
        assert gone not in out, gone
    assert "`a` Int32" in out and "`b` Nullable(Int32)" in out


def test_render_drops_defaults(clickhouse_pgsql):
    # `DEFAULT nextval(...)` has no ClickHouse equivalent, and every dump writes
    # its id values explicitly.
    out = _render(clickhouse_pgsql,
                  "CREATE TABLE t (\n"
                  "  id integer DEFAULT nextval('s'::regclass),\n"
                  "  n text DEFAULT 'x'\n"
                  ");")
    assert "DEFAULT" not in out and "nextval" not in out


def test_render_folds_unquoted_table_and_column_names(clickhouse_pgsql):
    out = _render(clickhouse_pgsql, "CREATE TABLE Regions (\n  Id integer\n);")
    assert "CREATE TABLE `regions`" in out and "`id`" in out


# --- collecting the primary keys pg_dump emits after the data -------------

def test_collect_alter_primary_keys_multi_line(clickhouse_pgsql):
    keys = clickhouse_pgsql.collect_alter_primary_keys([
        "ALTER TABLE ONLY public.countrylanguage\n"
        "    ADD CONSTRAINT countrylanguage_pkey PRIMARY KEY (countrycode, \"language\");\n"])
    assert keys == {"countrylanguage": ["countrycode", "language"]}


def test_collect_alter_primary_keys_ignores_foreign_keys(clickhouse_pgsql):
    keys = clickhouse_pgsql.collect_alter_primary_keys([
        "ALTER TABLE ONLY country\n"
        "    ADD CONSTRAINT country_capital_fkey FOREIGN KEY (capital) REFERENCES city(id);\n"])
    assert keys == {}


# --- ends_statement: quote-aware statement termination --------------------

def test_ends_statement_plain(clickhouse_pgsql):
    assert clickhouse_pgsql.ends_statement("SELECT 1;", False) == (False, True)


def test_ends_statement_semicolon_inside_literal(clickhouse_pgsql):
    assert clickhouse_pgsql.ends_statement("(1, 'a;b'),", False) == (False, False)


def test_ends_statement_carries_open_literal_across_lines(clickhouse_pgsql):
    in_string, done = clickhouse_pgsql.ends_statement("(1, 'multi", False)
    assert in_string and not done
    assert clickhouse_pgsql.ends_statement("line');", in_string) == (False, True)


# --- convert_file: the COPY / statement state machine ---------------------

def _convert(mod, text, alter_keys=None):
    out = io.StringIO()
    mod.convert_file(text, out, alter_keys or {})
    return out.getvalue()


def test_convert_file_copy_block_to_insert(clickhouse_pgsql):
    out = _convert(clickhouse_pgsql,
                   "COPY public.Foo (id, name) FROM stdin;\n"
                   "1\talice\n"
                   "2\t\\N\n"
                   "\\.\n")
    # The trailing blank line is the dump's own final newline, passed through.
    assert out == (
        "INSERT INTO `foo` (`id`, `name`) VALUES\n"
        "('1', 'alice'),\n"
        "('2', NULL);\n"
        "\n")


def test_convert_file_copy_honours_delimiter(clickhouse_pgsql):
    out = _convert(clickhouse_pgsql,
                   "COPY foo (a, b) FROM stdin DELIMITER '|';\n1|x\n\\.\n")
    assert "('1', 'x')" in out


def test_convert_file_copy_batches_at_limit(clickhouse_pgsql, monkeypatch):
    # Every INSERT into a MergeTree table writes a part, which is why this hook
    # batches at all -- and why it batches larger than the other engines do.
    monkeypatch.setattr(clickhouse_pgsql, "BATCH", 2)
    rows = "".join("{}\tn\n".format(i) for i in range(3))
    out = _convert(clickhouse_pgsql, "COPY foo (id, name) FROM stdin;\n" + rows + "\\.\n")
    assert out.count("INSERT INTO `foo`") == 2


def test_convert_file_coalesces_single_row_inserts(clickhouse_pgsql):
    # chinook ships 15,607 one-row INSERTs; a part apiece would be ruinous.
    out = _convert(clickhouse_pgsql,
                   'INSERT INTO "Genre" ("GenreId", "Name") VALUES (1, \'Rock\');\n'
                   'INSERT INTO "Genre" ("GenreId", "Name") VALUES (2, \'Jazz\');\n')
    assert out == ("INSERT INTO `Genre` (`GenreId`, `Name`) VALUES\n"
                   "(1, 'Rock'),\n"
                   "(2, 'Jazz');\n"
                   "\n")


def test_convert_file_flushes_when_the_column_list_changes(clickhouse_pgsql):
    # chinook's Track rows omit Composer when it is unknown, which changes the
    # INSERT prefix; rows may only be batched under the prefix they belong to.
    out = _convert(clickhouse_pgsql,
                   'INSERT INTO "T" ("a", "b") VALUES (1, 2);\n'
                   'INSERT INTO "T" ("a") VALUES (3);\n')
    assert out.count("INSERT INTO `T`") == 2


def test_convert_file_escapes_backslashes_in_coalesced_rows(clickhouse_pgsql):
    out = _convert(clickhouse_pgsql,
                   'INSERT INTO "T" ("a") VALUES (\'Rusticana \\ Act\');\n')
    assert "'Rusticana \\\\ Act'" in out


def test_convert_file_passes_multi_row_insert_through(clickhouse_pgsql):
    # pgexercises ships its data this way. Only the prefix is rewritten; the
    # rows travel untouched apart from the backslash doubling.
    out = _convert(clickhouse_pgsql,
                   "INSERT INTO cd.facilities (facid, name) VALUES\n"
                   "(0, 'Tennis Court 1'),\n"
                   "(1, 'Tennis Court 2');\n")
    assert out == ("INSERT INTO `facilities` (`facid`, `name`) VALUES\n"
                   "(0, 'Tennis Court 1'),\n"
                   "(1, 'Tennis Court 2');\n"
                   "\n")


def test_convert_file_drops_noise_lines(clickhouse_pgsql):
    # Each of these is a ClickHouse error: unknown settings, a transaction
    # spelling it does not have, statements it does not implement.
    for line in ("SET search_path = public;",
                 "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE;",
                 "BEGIN;", "COMMIT;", "ANALYZE city;",
                 "SELECT pg_catalog.setval('s', 1, true);",
                 "GRANT ALL ON TABLE foo TO postgres;",
                 "REVOKE ALL ON TABLE foo FROM public;",
                 "CREATE SCHEMA cd;",
                 "\\connect mydb"):
        assert _convert(clickhouse_pgsql, line) == "", line


def test_convert_file_drops_multi_line_blocks(clickhouse_pgsql):
    # pgexercises wraps each CREATE INDEX over four lines, and dellstore's
    # CREATE SEQUENCE over three, so these have to be read to their ';'.
    out = _convert(clickhouse_pgsql,
                   'CREATE INDEX "bookings.memid_facid"\n'
                   "  ON cd.bookings\n"
                   "  USING btree\n"
                   "  (memid, facid);\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_alter_table_entirely(clickhouse_pgsql):
    # The PRIMARY KEY form has already been consumed into the sorting key, and
    # ClickHouse cannot add one after the fact.
    out = _convert(clickhouse_pgsql,
                   "ALTER TABLE ONLY city\n"
                   "    ADD CONSTRAINT city_pkey PRIMARY KEY (id);\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_function_block(clickhouse_pgsql):
    # dellstore's new_customer: a ~60-line body inside one quoted string.
    out = _convert(clickhouse_pgsql,
                   "CREATE FUNCTION f() RETURNS int AS '\n"
                   "BEGIN RETURN 1; END;\n"
                   "'\n"
                   "    LANGUAGE plpgsql;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


# --- transcode: encoding fallback -----------------------------------------

def test_transcode_utf8(clickhouse_pgsql, tmp_path):
    p = tmp_path / "u.sql"
    p.write_bytes("café\n".encode("utf-8"))
    assert clickhouse_pgsql.transcode(str(p)) == "café\n"


def test_transcode_latin1_fallback(clickhouse_pgsql, tmp_path):
    # world / usda / dellstore ship Latin-1. ClickHouse stores String as raw
    # bytes, so without this the mojibake would be silent rather than an error.
    p = tmp_path / "l.sql"
    p.write_bytes("café\n".encode("latin-1"))
    assert clickhouse_pgsql.transcode(str(p)) == "café\n"


# --- main(): file selection and the cross-file key pass -------------------

def test_main_exits_without_sql_files(clickhouse_pgsql, tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_FILES", "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        clickhouse_pgsql.main()


def test_main_collects_primary_keys_across_files(clickhouse_pgsql, tmp_path,
                                                 monkeypatch):
    # pgexercises splits DDL and data across two files; a dump could equally
    # split the CREATE TABLE from its ALTER TABLE ... ADD PRIMARY KEY, so the
    # collecting pass reads every file before any is rewritten.
    ddl = tmp_path / "a.sql"
    keys = tmp_path / "b.sql"
    ddl.write_text("CREATE TABLE city (\n  id integer NOT NULL\n);\n", encoding="utf-8")
    keys.write_text("ALTER TABLE ONLY city\n"
                    "    ADD CONSTRAINT city_pkey PRIMARY KEY (id);\n", encoding="utf-8")
    monkeypatch.setenv("SQL_FILES", "{} {}".format(ddl, keys))
    monkeypatch.chdir(tmp_path)
    clickhouse_pgsql.main()
    assert "ENGINE = MergeTree ORDER BY (`id`);" in ddl.read_text(encoding="utf-8")
    assert keys.read_text(encoding="utf-8").strip() == ""


# --- golden: full main() run, in place -------------------------------------

def test_golden_dump(clickhouse_pgsql, tmp_path, monkeypatch):
    # Same input dump as test_pgsql.py / test_sqlite_pgsql.py / the DuckDB
    # golden, so the four dialects' whole-file output can be diffed by eye.
    work = tmp_path / "work.sql"
    work.write_bytes((FIXTURES / "dump.sql").read_bytes())
    monkeypatch.setenv("SQL_FILES", str(work))
    monkeypatch.chdir(tmp_path)
    clickhouse_pgsql.main()
    assert work.read_text(encoding="utf-8") == \
        (FIXTURES / "dump.expected_clickhouse.sql").read_text(encoding="utf-8")
