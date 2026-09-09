"""Unit tests for pinot/scripts/pgsql/transform (PostgreSQL dump -> Pinot).

This hook is the odd one out among the repo's dump translators. The others emit
SQL and can be checked by diffing a rewritten file; this one emits CSV plus two
JSON documents per table, so the tests assert on the *artifacts* -- the column
names and Pinot data types in the schema, the rows in the CSV, the row counts in
tables.tsv.

The cases below are weighted towards the failures that a row-count integration
test could never catch, because they lose or corrupt values while keeping the
count exactly right:

  * ``t``/``f`` reaching Pinot unnormalized, where the BOOLEAN parser turns
    *both* into false without an error anywhere;
  * an inline ``--`` comment being read as a column, which silently drops the
    columns on either side of it (frenchtowns);
  * a mixed-case ``CREATE TABLE Regions`` not folding to the lower-case name its
    ``COPY regions`` uses, which would leave every table empty;
  * a ``CHECK`` constraint or a table-level ``FOREIGN KEY`` being counted as a
    column;
  * the NULL sentinel not being written, which turns every NULL into a default
    value once Pinot substitutes for it.
"""
import csv
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pinot"


# --- fold: PostgreSQL identifier folding ----------------------------------

def test_fold_lowercases_unquoted(pinot_pgsql):
    # frenchtowns declares `Regions` and loads `COPY regions`; Pinot table names
    # are case-sensitive, so both spellings have to land on one name.
    assert pinot_pgsql.fold("Regions") == "regions"
    assert pinot_pgsql.fold("  Towns  ") == "towns"


def test_fold_keeps_quoted_verbatim(pinot_pgsql):
    assert pinot_pgsql.fold('"year"') == "year"
    assert pinot_pgsql.fold('"MixedCase"') == "MixedCase"


def test_fold_drops_schema_qualifier(pinot_pgsql):
    # Pinot has no schemas: a cluster is a flat namespace of tables.
    assert pinot_pgsql.fold("public.Country") == "country"
    assert pinot_pgsql.fold("cd.members") == "members"
    assert pinot_pgsql.fold('cd."Members"') == "Members"


# --- pinot_type: the PostgreSQL -> Pinot data type map --------------------

@pytest.mark.parametrize("pg,expected", [
    ("smallint", "INT"),
    ("integer NOT NULL", "INT"),
    ("int4", "INT"),
    ("serial UNIQUE NOT NULL", "INT"),
    ("smallserial", "INT"),
    ("bigint", "LONG"),
    ("bigserial", "LONG"),
    ("int8", "LONG"),
    ("real", "FLOAT"),
    ("float4", "FLOAT"),
    ("double precision", "DOUBLE"),
    ("numeric(10,2)", "DOUBLE"),
    ("numeric", "DOUBLE"),
    ("decimal(8,4)", "DOUBLE"),
    ("money", "DOUBLE"),
    ("boolean NOT NULL", "BOOLEAN"),
    ("bool", "BOOLEAN"),
    ("date", "TIMESTAMP"),
    ("timestamp without time zone NOT NULL", "TIMESTAMP"),
    ("timestamp with time zone", "TIMESTAMP"),
    ("timestamptz", "TIMESTAMP"),
    ("text", "STRING"),
    ("character(3) NOT NULL", "STRING"),
    ("character varying(200)", "STRING"),
    ("varchar(4)", "STRING"),
    ("uuid", "STRING"),
    ("bytea", "STRING"),
    ("text[]", "STRING"),
])
def test_pinot_type_map(pinot_pgsql, pg, expected):
    assert pinot_pgsql.pinot_type(pg) == expected


def test_pinot_type_bool_not_shadowed_by_prefix(pinot_pgsql):
    # `bool` must not match before `boolean` and leave the column a STRING.
    assert pinot_pgsql.pinot_type("boolean") == "BOOLEAN"


def test_pinot_type_double_precision_beats_double_prefix(pinot_pgsql):
    # Longest-prefix ordering: "double precision" must not be cut at "double".
    assert pinot_pgsql.pinot_type("double precision NOT NULL") == "DOUBLE"


def test_pinot_type_unknown_falls_back_to_string(pinot_pgsql):
    assert pinot_pgsql.pinot_type("some_domain_type") == "STRING"


# --- strip_line_comment ---------------------------------------------------

def test_strip_line_comment_removes_trailing_comment(pinot_pgsql):
    line = "   capital VARCHAR(10) NOT NULL, -- REFERENCES Towns (code),"
    assert pinot_pgsql.strip_line_comment(line, False) == \
        "   capital VARCHAR(10) NOT NULL, "


def test_strip_line_comment_keeps_dashes_inside_a_literal(pinot_pgsql):
    line = "  CHECK (name = 'a--b')"
    assert pinot_pgsql.strip_line_comment(line, False) == line


def test_strip_line_comment_keeps_dashes_inside_an_identifier(pinot_pgsql):
    line = '  "od--d" integer,'
    assert pinot_pgsql.strip_line_comment(line, False) == line


def test_strip_line_comment_honours_incoming_string_state(pinot_pgsql):
    # A literal opened on a previous line: everything here is still data.
    assert pinot_pgsql.strip_line_comment("still -- inside', x", True) == \
        "still -- inside', x"


# --- split_columns / parse_create_table -----------------------------------

def test_split_columns_keeps_precision_together(pinot_pgsql):
    items = pinot_pgsql.split_columns("a numeric(10,2), b integer")
    assert [i.strip() for i in items] == ["a numeric(10,2)", "b integer"]


def test_split_columns_keeps_check_constraint_whole(pinot_pgsql):
    body = ("code text, CONSTRAINT c CHECK (((n = 'Asia'::text) "
            "OR (n = 'Europe'::text))), name text")
    items = [i.strip() for i in pinot_pgsql.split_columns(body)]
    assert len(items) == 3
    assert items[1].startswith("CONSTRAINT c CHECK")


def test_split_column_def_handles_quoted_identifier(pinot_pgsql):
    assert pinot_pgsql.split_column_def('"year" integer') == ('"year"', "integer")


def test_parse_create_table_skips_table_level_constraints(pinot_pgsql):
    stmt = (
        "CREATE TABLE public.country (\n"
        "    code character(3) NOT NULL,\n"
        "    gnp numeric(10,2),\n"
        "    CONSTRAINT c CHECK ((name = 'Asia'::text)),\n"
        "    PRIMARY KEY (code),\n"
        "    UNIQUE (code),\n"
        "    FOREIGN KEY (code) REFERENCES other(code)\n"
        ");")
    table, columns = pinot_pgsql.parse_create_table(stmt)
    assert table == "country"
    assert columns == [("code", "STRING"), ("gnp", "DOUBLE")]


def test_parse_create_table_folds_the_table_name(pinot_pgsql):
    table, columns = pinot_pgsql.parse_create_table(
        "CREATE TABLE Regions (\n   id SERIAL,\n   name TEXT\n);")
    assert table == "regions"
    assert columns == [("id", "INT"), ("name", "STRING")]


def test_parse_create_table_ignores_a_non_table_statement(pinot_pgsql):
    assert pinot_pgsql.parse_create_table("CREATE INDEX ix ON t (a);") == (None, [])


# --- COPY decoding --------------------------------------------------------

def test_split_copy_row_plain(pinot_pgsql):
    assert pinot_pgsql.split_copy_row("a\tb\tc", "\t") == ["a", "b", "c"]


def test_split_copy_row_alternate_delimiter(pinot_pgsql):
    # iso3166 ships `FROM stdin DELIMITER '|'`.
    assert pinot_pgsql.split_copy_row("Afghanistan|AF|4", "|") == \
        ["Afghanistan", "AF", "4"]


def test_split_copy_row_keeps_escaped_delimiter(pinot_pgsql):
    assert pinot_pgsql.split_copy_row("a\\\tb", "\t") == ["a\\\tb"]


def test_copy_field_null_sentinel(pinot_pgsql):
    assert pinot_pgsql.copy_field("\\N") is None


def test_copy_field_unescapes_control_characters(pinot_pgsql):
    assert pinot_pgsql.copy_field("a\\tb") == "a\tb"
    assert pinot_pgsql.copy_field("a\\nb") == "a\nb"
    assert pinot_pgsql.copy_field("a\\\\b") == "a\\b"


def test_copy_field_keeps_a_plain_value(pinot_pgsql):
    assert pinot_pgsql.copy_field("it's fine") == "it's fine"


# --- INSERT decoding ------------------------------------------------------

def test_split_tuples_finds_each_group(pinot_pgsql):
    assert pinot_pgsql.split_tuples(" (1, 'a'), (2, 'b');") == \
        ["1, 'a'", "2, 'b'"]


def test_split_tuples_ignores_parens_inside_a_literal(pinot_pgsql):
    assert pinot_pgsql.split_tuples("(1, 'a) (b')") == ["1, 'a) (b'"]


def test_split_values_keeps_a_comma_inside_a_literal(pinot_pgsql):
    # pgexercises has addresses like '8 Bloomsbury Close, Boston'.
    assert pinot_pgsql.split_values("1, '8 Bloomsbury Close, Boston', NULL") == \
        ["1", "'8 Bloomsbury Close, Boston'", "NULL"]


def test_split_values_keeps_a_doubled_quote(pinot_pgsql):
    assert pinot_pgsql.split_values("'O''Brien', 2") == ["'O''Brien'", "2"]


def test_insert_value_null_keyword(pinot_pgsql):
    assert pinot_pgsql.insert_value("NULL") is None
    assert pinot_pgsql.insert_value(" null ") is None


def test_insert_value_unquotes_and_unescapes(pinot_pgsql):
    assert pinot_pgsql.insert_value("'O''Brien'") == "O'Brien"


def test_insert_value_keeps_a_bare_number(pinot_pgsql):
    assert pinot_pgsql.insert_value(" 42 ") == "42"


# --- value rendering ------------------------------------------------------

def test_bool_literal_normalizes_copy_spelling(pinot_pgsql):
    # The whole point: Pinot's BOOLEAN parser reads `t` as *false*.
    assert pinot_pgsql.bool_literal("t") == "true"
    assert pinot_pgsql.bool_literal("f") == "false"


def test_bool_literal_accepts_the_other_spellings(pinot_pgsql):
    for truthy in ("true", "TRUE", "Y", "yes", "1"):
        assert pinot_pgsql.bool_literal(truthy) == "true", truthy
    for falsy in ("false", "FALSE", "n", "no", "0"):
        assert pinot_pgsql.bool_literal(falsy) == "false", falsy


def test_bool_literal_passes_through_the_unrecognized(pinot_pgsql):
    # Better a visibly wrong value than a silent false.
    assert pinot_pgsql.bool_literal("maybe") == "maybe"


def test_timestamp_literal_keeps_what_pinot_parses(pinot_pgsql):
    assert pinot_pgsql.timestamp_literal("2012-07-02 12:02:05") == \
        "2012-07-02 12:02:05"
    assert pinot_pgsql.timestamp_literal("2004-01-27") == "2004-01-27"
    assert pinot_pgsql.timestamp_literal("2012-07-02 12:02:05.123") == \
        "2012-07-02 12:02:05.123"


def test_timestamp_literal_strips_an_offset(pinot_pgsql):
    # Pinot's TIMESTAMP parser rejects an offset outright; none of the six dumps
    # has one, but losing the offset beats failing the whole ingest.
    assert pinot_pgsql.timestamp_literal("2013-05-19 16:05:10+01") == \
        "2013-05-19 16:05:10"
    assert pinot_pgsql.timestamp_literal("2013-05-19T16:05:10Z") == \
        "2013-05-19 16:05:10"


def test_render_writes_the_null_sentinel(pinot_pgsql):
    assert pinot_pgsql.render(None, "STRING") == pinot_pgsql.NULL_SENTINEL
    assert pinot_pgsql.render(None, "INT") == pinot_pgsql.NULL_SENTINEL


def test_render_applies_the_type_specific_normalizers(pinot_pgsql):
    assert pinot_pgsql.render("t", "BOOLEAN") == "true"
    assert pinot_pgsql.render("2013-05-19 16:05:10+01", "TIMESTAMP") == \
        "2013-05-19 16:05:10"
    assert pinot_pgsql.render("t", "STRING") == "t"


# --- the emitted JSON documents -------------------------------------------

def test_pinot_schema_puts_every_column_in_dimensions(pinot_pgsql):
    schema = pinot_pgsql.pinot_schema("city", [("id", "INT"), ("name", "STRING")])
    assert schema["schemaName"] == "city"
    assert schema["dimensionFieldSpecs"] == [
        {"name": "id", "dataType": "INT"},
        {"name": "name", "dataType": "STRING"},
    ]
    # A metric field would default a null to 0; a date-time field would force a
    # time column onto datasets that have no natural one.
    assert "metricFieldSpecs" not in schema
    assert "dateTimeFieldSpecs" not in schema


def test_pinot_table_config_is_offline_with_null_handling(pinot_pgsql):
    config = pinot_pgsql.pinot_table_config("city")
    assert config["tableName"] == "city"
    assert config["tableType"] == "OFFLINE"
    assert config["tableIndexConfig"]["nullHandlingEnabled"] is True
    assert config["segmentsConfig"] == {"replication": "1"}
    # An OFFLINE table needs no time column, and inventing one would add a
    # column the source dump never had.
    assert "timeColumnName" not in config["segmentsConfig"]


# --- TableWriter positional mapping ---------------------------------------

def test_table_writer_positions_by_the_statement_column_list(pinot_pgsql, tmp_path):
    # The dump's COPY/INSERT column list, not the CREATE TABLE order, decides
    # where a value goes -- and a column the statement omits must come out NULL,
    # not shift its neighbours along.
    writer = pinot_pgsql.TableWriter(
        str(tmp_path), "t", [("a", "STRING"), ("b", "INT"), ("c", "STRING")])
    writer.write(["c", "a"], ["see", "ay"])
    writer.close()
    rows = list(csv.reader((tmp_path / "t.csv").open(newline="", encoding="utf-8")))
    assert rows == [["a", "b", "c"], ["ay", pinot_pgsql.NULL_SENTINEL, "see"]]
    assert writer.rows == 1


# --- transcode ------------------------------------------------------------

def test_transcode_falls_back_to_latin1(pinot_pgsql, tmp_path):
    # world / usda / dellstore ship Latin-1 bytes; left undecoded they would be
    # invalid UTF-8 in the CSV and the ingest would fail on them.
    path = tmp_path / "l.sql"
    path.write_bytes("café\n".encode("latin-1"))
    assert pinot_pgsql.transcode(str(path)) == "café\n"


def test_transcode_prefers_utf8(pinot_pgsql, tmp_path):
    path = tmp_path / "u.sql"
    path.write_bytes("Régions\n".encode("utf-8"))
    assert pinot_pgsql.transcode(str(path)) == "Régions\n"


# --- main(): the whole conversion, against the fixture dump ---------------

@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    """Run the hook over fixtures/pinot/dump.sql once and hand back the output."""
    import importlib.machinery
    import importlib.util

    out = tmp_path_factory.mktemp("dataset")
    src = tmp_path_factory.mktemp("build") / "dump.sql"
    src.write_bytes((FIXTURES / "dump.sql").read_bytes())

    # Reloaded rather than reusing the session fixture: OUT_DIR is bound from
    # the environment at import time, so the env var has to be set first.
    import os
    prev = os.environ.get("PINOT_DATASET_DIR")
    prev_sql = os.environ.get("SQL_FILES")
    os.environ["PINOT_DATASET_DIR"] = str(out)
    os.environ["SQL_FILES"] = str(src)
    try:
        path = Path(__file__).resolve().parents[2] / "pinot/scripts/pgsql/transform"
        loader = importlib.machinery.SourceFileLoader("pinot_pgsql_main", str(path))
        spec = importlib.util.spec_from_loader("pinot_pgsql_main", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        module.main()
    finally:
        for key, value in (("PINOT_DATASET_DIR", prev), ("SQL_FILES", prev_sql)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return out


def read_csv(out, table):
    with (out / (table + ".csv")).open(newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def read_schema(out, table):
    return json.loads((out / (table + ".schema.json")).read_text(encoding="utf-8"))


def test_manifest_lists_every_table_with_its_row_count(converted):
    lines = (converted / "tables.tsv").read_text(encoding="utf-8").splitlines()
    assert [line.split("\t") for line in lines] == [
        ["country", "2"],
        ["empties", "0"],
        ["measure", "2"],
        ["members", "2"],
        ["regions", "2"],
    ]


def test_every_table_ships_a_full_artifact_set(converted):
    for table in ("country", "empties", "measure", "members", "regions"):
        for suffix in (".csv", ".schema.json", ".table.json"):
            assert (converted / (table + suffix)).is_file(), table + suffix


def test_the_plpgsql_function_did_not_become_a_table(converted):
    assert not (converted / "audit_log.csv").exists()


def test_mixed_case_ddl_and_lowercase_copy_land_in_one_table(converted):
    rows = read_csv(converted, "regions")
    assert rows[0] == ["id", "code", "capital", "name"]
    assert rows[1] == ["1", "01", "97105", "Guadeloupe"]
    assert len(rows) == 3


def test_inline_comments_do_not_eat_columns(converted):
    schema = read_schema(converted, "regions")
    names = [f["name"] for f in schema["dimensionFieldSpecs"]]
    assert names == ["id", "code", "capital", "name"]


def test_country_types_and_values(converted):
    schema = read_schema(converted, "country")
    assert schema["dimensionFieldSpecs"] == [
        {"name": "code", "dataType": "STRING"},
        {"name": "name", "dataType": "STRING"},
        {"name": "surfacearea", "dataType": "FLOAT"},
        {"name": "indepyear", "dataType": "INT"},
        {"name": "gnp", "dataType": "DOUBLE"},
        {"name": "isofficial", "dataType": "BOOLEAN"},
        {"name": "founded", "dataType": "TIMESTAMP"},
    ]
    rows = read_csv(converted, "country")
    assert rows[1] == ["AFG", "Afghanistan", "652090", "1919", "5976.00",
                       "true", "1919-08-19"]
    # Every NULL in the dump becomes the sentinel, not an empty cell, so Pinot
    # can tell it apart from a value.
    assert rows[2] == ["ATA", "Antarctica", "13120000", "\\N", "0.00",
                       "false", "\\N"]


def test_measure_honours_the_pipe_delimiter_and_quoted_column(converted):
    schema = read_schema(converted, "measure")
    assert [f["name"] for f in schema["dimensionFieldSpecs"]] == \
        ["ndb_no", "year", "seq", "amount", "note"]
    assert schema["dimensionFieldSpecs"][2]["dataType"] == "LONG"
    rows = read_csv(converted, "measure")
    assert rows[1] == ["01001", "2005", "9223372036854775807", "6.38",
                       "Bone 24.92%; Cartilage 9.79%"]
    assert rows[2][1] == "\\N"
    assert rows[2][4] == "tab\there"


def test_members_come_from_the_insert_path(converted):
    rows = read_csv(converted, "members")
    assert rows[0] == ["memid", "surname", "address", "recommendedby", "joindate"]
    assert rows[1] == ["0", "GUEST", "GUEST", "\\N", "2012-07-01 00:00:00"]
    assert rows[2] == ["1", "O'Brien", "8 Bloomsbury Close, Boston", "0",
                       "2012-07-02 12:02:05"]


def test_an_empty_copy_block_still_ships_a_header_only_csv(converted):
    # dellstore's `reorder`: Pinot needs a real 0-row segment for the table to
    # answer count(*) = 0 rather than nothing at all.
    rows = read_csv(converted, "empties")
    assert rows == [["prod_id", "date_low"]]


def test_main_exits_without_sql_files(pinot_pgsql, tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_FILES", "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        pinot_pgsql.main()


def test_main_exits_when_no_table_was_found(pinot_pgsql, tmp_path, monkeypatch):
    # A dump the hook cannot read at all must fail the build, not ship an image
    # that boots and serves nothing.
    src = tmp_path / "a.sql"
    src.write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.setenv("SQL_FILES", str(src))
    monkeypatch.setattr(pinot_pgsql, "OUT_DIR", str(tmp_path / "dataset"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        pinot_pgsql.main()
