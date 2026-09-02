"""Unit tests for druid/scripts/pgsql/transform (PostgreSQL dump -> Druid).

This hook is the odd one out among the pgsql hooks: the others rewrite a dump
into SQL their engine can run, so a bug shows up as a load error. This one
*reads* the dump and emits CSV plus an ingestion spec, and its failure mode is
much quieter -- a mis-parsed COPY escape, a column mapped to the wrong Druid
type, or a timestamp format Druid cannot parse all produce a spec that ingests
cleanly and a datasource whose contents are subtly wrong. Two of those would
not even move the row count the integration test asserts.

So the tests below concentrate on the three places where a silent wrong answer
is possible:

  * the DDL reader -- column order, types and NOT NULL, across the two closing
    paren styles and the constraint clauses these dumps mix in;
  * the two data readers -- COPY TEXT escapes and the INSERT tokenizer, whose
    string literals contain the commas and parens a naive split would cut on;
  * the __time decision, which is the one place the hook can silently lose
    *rows*: Druid drops a row whose timestamp will not parse, so a nullable or
    unparseable column must demote the table to the constant fallback.
"""
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pgsql"


@pytest.fixture
def hook(druid_pgsql, tmp_path, monkeypatch):
    """The hook with its output directories pointed at a tmp dir.

    DATA_DIR / SPEC_DIR / RUNTIME_DATA_DIR are module constants bound from the
    environment at import time (the Dockerfile sets them), and conftest imports
    each hook once per session -- so they have to be patched on the module, not
    via monkeypatch.setenv.
    """
    (tmp_path / "data").mkdir()
    (tmp_path / "specs").mkdir()
    monkeypatch.setattr(druid_pgsql, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(druid_pgsql, "SPEC_DIR", str(tmp_path / "specs"))
    monkeypatch.setattr(druid_pgsql, "RUNTIME_DATA_DIR", "/opt/druid/dataset/data")
    return druid_pgsql


def run(hook, tmp_path, monkeypatch, sql, name="dump.sql"):
    """Run main() over `sql` and return {table: (csv text, spec dict)}."""
    work = tmp_path / name
    work.write_text(sql, encoding="utf-8")
    monkeypatch.setenv("SQL_FILES", str(work))
    monkeypatch.chdir(tmp_path)
    hook.main()
    out = {}
    for spec_path in sorted((tmp_path / "specs").glob("*.json")):
        table = spec_path.stem
        out[table] = (
            (tmp_path / "data" / (table + ".csv")).read_text(encoding="utf-8"),
            json.loads(spec_path.read_text(encoding="utf-8")),
        )
    return out


# --- fold: PostgreSQL identifier case rules -------------------------------

def test_fold_lowercases_unquoted(hook):
    # frenchtowns declares `Regions` and loads `regions`; PostgreSQL treats
    # those as one table, so the hook must too or the data lands nowhere.
    assert hook.fold("Regions") == "regions"
    assert hook.fold("public.Towns") == "towns"


def test_fold_keeps_quoted_case(hook):
    assert hook.fold('"Regions"') == "Regions"
    assert hook.fold('public."Year"') == "Year"


# --- dimension_type: the PostgreSQL -> Druid type map ---------------------

def test_dimension_type_integers_are_long(hook):
    for pg in ("smallint", "integer", "bigint", "serial", "bigserial", "int4"):
        assert hook.dimension_type(pg) == "long", pg


def test_dimension_type_reals_are_double(hook):
    # Druid has a float type too; double is used throughout so a numeric column
    # never loses precision relative to the PostgreSQL/DuckDB tags.
    for pg in ("real", "double precision", "numeric(10,2)", "decimal", "money"):
        assert hook.dimension_type(pg) == "double", pg


def test_dimension_type_everything_else_is_string(hook):
    # boolean included: Druid has no boolean dimension type, and COPY already
    # encodes the values as the strings t/f.
    for pg in ("text", "character(3)", "character varying(40)", "boolean",
               "date", "timestamp without time zone"):
        assert hook.dimension_type(pg) == "string", pg


def test_dimension_type_ignores_precision(hook):
    assert hook.dimension_type("numeric(8, 2)") == "double"


# --- parse_create_table ----------------------------------------------------

def test_parse_create_table_columns_types_and_not_null(hook):
    lines = ("CREATE TABLE city (\n"
             "    id integer NOT NULL,\n"
             "    name text NOT NULL,\n"
             "    population integer\n"
             ");").split("\n")
    table, columns, nxt = hook.parse_create_table(lines, 0)
    assert table == "city"
    assert columns == [("id", "integer", True),
                       ("name", "text", True),
                       ("population", "integer", False)]
    assert nxt == 5, "the index just past the closing paren"


def test_parse_create_table_accepts_an_indented_closing_paren(hook):
    # frenchtowns' Towns ends with "  );". Missing that terminator once made the
    # parser swallow the rest of the dump, including every COPY block.
    lines = ("CREATE TABLE towns (\n"
             "   id SERIAL UNIQUE NOT NULL,\n"
             "   UNIQUE (code, department)\n"
             "  );\n"
             "COPY towns (id) FROM stdin;").split("\n")
    table, columns, nxt = hook.parse_create_table(lines, 0)
    assert columns == [("id", "SERIAL", True)]
    assert lines[nxt].startswith("COPY")


def test_parse_create_table_skips_constraint_clauses(hook):
    lines = ("CREATE TABLE country (\n"
             "    code character(3) NOT NULL,\n"
             "    capital integer,\n"
             "    CONSTRAINT country_continent_check CHECK ((continent = 'Asia'::text)),\n"
             "    PRIMARY KEY (code),\n"
             "    FOREIGN KEY (capital) REFERENCES city(id)\n"
             ");").split("\n")
    _, columns, _ = hook.parse_create_table(lines, 0)
    assert [c[0] for c in columns] == ["code", "capital"]


def test_parse_create_table_strips_inline_column_constraints_from_the_type(hook):
    # frenchtowns spells a column `region VARCHAR(4) NOT NULL REFERENCES ...`,
    # and the trailing REFERENCES must not end up inside the type.
    lines = ("CREATE TABLE departments (\n"
             "   region VARCHAR(4) NOT NULL REFERENCES Regions (code),\n"
             "   capital VARCHAR(10) UNIQUE NOT NULL, -- REFERENCES Towns (code),\n"
             ");").split("\n")
    _, columns, _ = hook.parse_create_table(lines, 0)
    assert columns == [("region", "VARCHAR(4)", True),
                       ("capital", "VARCHAR(10)", True)]


def test_parse_create_table_folds_quoted_column_names(hook):
    # usda has a `"year"` column and dellstore a `"password"` one.
    lines = 'CREATE TABLE t (\n    "year" integer\n);'.split("\n")
    _, columns, _ = hook.parse_create_table(lines, 0)
    assert columns[0][0] == "year"


# --- COPY TEXT decoding ----------------------------------------------------

def test_copy_value_null_sentinel(hook):
    # None becomes an empty CSV field, which Druid reads as null.
    assert hook.copy_value("\\N") is None


def test_copy_value_unescapes_control_characters(hook):
    assert hook.copy_value("a\\tb") == "a\tb"
    assert hook.copy_value("a\\nb") == "a\nb"
    assert hook.copy_value("a\\rb") == "a\rb"
    assert hook.copy_value("a\\\\b") == "a\\b"


def test_copy_value_unescapes_octal(hook):
    assert hook.copy_value("\\101") == "A"


def test_split_copy_row_keeps_escaped_delimiter(hook):
    assert hook.split_copy_row("a\\\tb", "\t") == ["a\\\tb"]


def test_split_copy_row_honours_a_custom_delimiter(hook):
    # iso3166's COPY blocks are pipe-separated.
    assert hook.split_copy_row("a|b|c", "|") == ["a", "b", "c"]


# --- INSERT tokenizing -----------------------------------------------------

def test_parse_insert_tuples_keeps_commas_inside_literals(hook):
    # pgexercises: '8 Bloomsbury Close, Boston' is one value, not two.
    rows = list(hook.parse_insert_tuples(
        "(1, '8 Bloomsbury Close, Boston', 4321)"))
    assert rows == [["1", "8 Bloomsbury Close, Boston", "4321"]]


def test_parse_insert_tuples_keeps_parens_inside_literals(hook):
    rows = list(hook.parse_insert_tuples("(1, '(000) 000-0000')"))
    assert rows == [["1", "(000) 000-0000"]]


def test_parse_insert_tuples_unescapes_doubled_quotes(hook):
    rows = list(hook.parse_insert_tuples("(1, 'it''s fine')"))
    assert rows == [["1", "it's fine"]]


def test_parse_insert_tuples_maps_bare_null_to_none(hook):
    # Quoted 'NULL' is the four-character string, not a null.
    rows = list(hook.parse_insert_tuples("(NULL, 'NULL')"))
    assert rows == [[None, "NULL"]]


def test_parse_insert_tuples_reads_every_tuple(hook):
    rows = list(hook.parse_insert_tuples("(1, 'a'),\n(2, 'b'),\n(3, 'c');"))
    assert [r[0] for r in rows] == ["1", "2", "3"]


# --- __time selection ------------------------------------------------------

DATED = ("CREATE TABLE orders (\n"
         "    orderid integer NOT NULL,\n"
         "    orderdate date NOT NULL\n"
         ");\n"
         "COPY orders (orderid, orderdate) FROM stdin;\n"
         "1\t2004-01-02\n"
         "\\.\n")


def test_time_column_is_used_when_every_value_parses(hook, tmp_path, monkeypatch):
    spec = run(hook, tmp_path, monkeypatch, DATED)["orders"][1]
    stamp = spec["spec"]["dataSchema"]["timestampSpec"]
    # An explicit Joda format, not "auto": pg_dump writes `2012-07-03 11:00:00`
    # for a timestamp column, which Druid's auto parser rejects.
    assert stamp == {"column": "orderdate", "format": "yyyy-MM-dd"}


def test_time_column_stays_a_dimension_in_its_own_right(hook, tmp_path, monkeypatch):
    # Druid keeps an explicitly declared dimension even when it is also the
    # timestamp input, so promoting a column costs nothing.
    spec = run(hook, tmp_path, monkeypatch, DATED)["orders"][1]
    names = [d["name"] for d in spec["spec"]["dataSchema"]["dimensionsSpec"]["dimensions"]]
    assert names == ["orderid", "orderdate"]


def test_unparseable_value_demotes_to_the_constant(hook, tmp_path, monkeypatch):
    # The point of the build-time check: Druid silently *drops* a row whose
    # timestamp will not parse, so one bad value must cost the whole table its
    # natural __time rather than costing the image a row.
    sql = DATED.replace("1\t2004-01-02\n", "1\t2004-01-02\n2\tnot-a-date\n")
    table = run(hook, tmp_path, monkeypatch, sql)["orders"]
    assert "missingValue" in table[1]["spec"]["dataSchema"]["timestampSpec"]
    assert table[0].count("\n") == 2, "both rows must still be written"


def test_nullable_time_column_is_never_promoted(hook, tmp_path, monkeypatch):
    sql = DATED.replace("orderdate date NOT NULL", "orderdate date")
    spec = run(hook, tmp_path, monkeypatch, sql)["orders"][1]
    assert "missingValue" in spec["spec"]["dataSchema"]["timestampSpec"]


def test_timestamp_columns_use_the_space_separated_format(hook, tmp_path, monkeypatch):
    sql = ("CREATE TABLE bookings (\n"
           "    starttime timestamp without time zone NOT NULL\n"
           ");\n"
           "INSERT INTO bookings (starttime) VALUES\n"
           "('2012-07-03 11:00:00');\n")
    spec = run(hook, tmp_path, monkeypatch, sql)["bookings"][1]
    assert spec["spec"]["dataSchema"]["timestampSpec"] == {
        "column": "starttime", "format": "yyyy-MM-dd HH:mm:ss"}


# --- the spec's non-negotiable settings ------------------------------------

def test_rollup_is_off_and_query_granularity_preserves_time(hook, tmp_path, monkeypatch):
    # rollup would merge identical rows, so COUNT(*) would stop counting rows;
    # queryGranularity ALL would truncate every __time to Druid's minimum
    # instant, throwing away both real timestamps and the readable constant.
    gran = run(hook, tmp_path, monkeypatch, DATED)["orders"][1] \
        ["spec"]["dataSchema"]["granularitySpec"]
    assert gran["rollup"] is False
    assert gran["queryGranularity"] == "NONE"
    assert gran["segmentGranularity"] == "ALL"


def test_input_format_lists_columns_in_ddl_order(hook, tmp_path, monkeypatch):
    # The CSV has no header, so the spec's column list *is* the schema; a
    # mismatch with the writer's order would shift every value one place.
    spec = run(hook, tmp_path, monkeypatch, DATED)["orders"][1]
    assert spec["spec"]["ioConfig"]["inputFormat"]["columns"] == \
        ["orderid", "orderdate"]


def test_input_source_points_at_the_runtime_data_dir(hook, tmp_path, monkeypatch):
    source = run(hook, tmp_path, monkeypatch, DATED)["orders"][1] \
        ["spec"]["ioConfig"]["inputSource"]
    assert source == {"type": "local", "baseDir": "/opt/druid/dataset/data",
                      "filter": "orders.csv"}


# --- row writing -----------------------------------------------------------

def test_copy_column_order_is_remapped_to_ddl_order(hook, tmp_path, monkeypatch):
    # A COPY header may list the columns in any order; the CSV must follow the
    # DDL, because that is what the spec's column list says.
    sql = ("CREATE TABLE t (\n    a integer,\n    b text\n);\n"
           "COPY t (b, a) FROM stdin;\n"
           "hello\t1\n"
           "\\.\n")
    assert run(hook, tmp_path, monkeypatch, sql)["t"][0] == "1,hello\n"


def test_values_with_newlines_are_flattened(hook, tmp_path, monkeypatch):
    # Druid's CSV reader splits on lines before parsing them, so an embedded
    # newline cannot round-trip; usda's deriv_cd has exactly one such value.
    sql = ("CREATE TABLE t (\n    a text\n);\n"
           "COPY t (a) FROM stdin;\n"
           "one\\ntwo\n"
           "\\.\n")
    assert run(hook, tmp_path, monkeypatch, sql)["t"][0] == "one two\n"


def test_zero_row_tables_ship_nothing(hook, tmp_path, monkeypatch):
    # Druid has no empty datasource: the task would succeed, produce no
    # segments, and the entrypoint would wait forever for a datasource that
    # cannot appear. dellstore's `reorder` is the real case.
    sql = ("CREATE TABLE full (\n    a integer\n);\n"
           "CREATE TABLE empty (\n    a integer\n);\n"
           "COPY full (a) FROM stdin;\n1\n\\.\n"
           "COPY empty (a) FROM stdin;\n\\.\n")
    out = run(hook, tmp_path, monkeypatch, sql)
    assert set(out) == {"full"}
    assert not (tmp_path / "data" / "empty.csv").exists()


def test_main_exits_when_no_table_has_rows(hook, tmp_path, monkeypatch):
    sql = "CREATE TABLE empty (\n    a integer\n);\n"
    with pytest.raises(SystemExit):
        run(hook, tmp_path, monkeypatch, sql)


def test_main_exits_without_sql_files(hook, tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_FILES", "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        hook.main()


# --- transcode: encoding fallback -----------------------------------------

def test_transcode_utf8(hook, tmp_path):
    p = tmp_path / "u.sql"
    p.write_bytes("café\n".encode("utf-8"))
    assert hook.transcode(str(p)) == "café\n"


def test_transcode_latin1_fallback(hook, tmp_path):
    # world / usda / dellstore ship Latin-1 bytes.
    p = tmp_path / "l.sql"
    p.write_bytes("café\n".encode("latin-1"))
    assert hook.transcode(str(p)) == "café\n"


# --- golden: full main() run ----------------------------------------------

def test_golden_dump(hook, tmp_path, monkeypatch):
    # The same input dump as test_pgsql.py / test_sqlite_pgsql.py /
    # test_duckdb_pgsql.py, so this engine's whole-file output can be compared
    # against the other three by eye. `Items` folds to `items`; the nullable
    # `created` column is absent from the COPY header, so every value is empty
    # and __time falls back to the constant.
    out = run(hook, tmp_path, monkeypatch,
              (FIXTURES / "dump.sql").read_text(encoding="utf-8"))
    assert set(out) == {"items"}
    csv_text, spec = out["items"]
    assert csv_text == (FIXTURES / "dump.expected_druid_items.csv") \
        .read_text(encoding="utf-8")
    assert spec == json.loads(
        (FIXTURES / "dump.expected_druid_items.json").read_text(encoding="utf-8"))
