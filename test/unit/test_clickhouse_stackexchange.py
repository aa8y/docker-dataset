"""Unit tests for clickhouse/scripts/stackexchange/transform (XML -> ClickHouse).

The cross-dialect parity checks -- same tables, same XML-attribute -> column
mapping, same index set -- live in test_stackexchange.py, which compares every
dialect against the postgres hook and would catch this one drifting from the
shared schema. What is pinned here is the part that is ClickHouse's alone:

* every table names an engine and a sorting key, because ClickHouse has neither
  by default, and the sorting-key column is the only one that may not be
  Nullable;
* backslashes are doubled, because ClickHouse reads escape sequences inside
  string literals where SQLite and DuckDB do not -- a post body full of code is
  exactly where that bites;
* no ``CREATE INDEX`` and no ``BEGIN``/``COMMIT``, neither of which ClickHouse
  has in the form the other dialects emit.
"""
import re
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "stackexchange"


# --- shared schema: this dialect must not drift from the others ------------
#
# test_stackexchange.py runs the same comparison across the five older
# dialects; the equivalent for this one lives here rather than there so the
# ClickHouse hook can be added without touching the shared suite.

def _mapping(mod):
    """(xml_file, table, [(xml_attribute, sql_column), ...]) per table."""
    return [(xml_file, table, [(xa, col) for xa, col, _ in cols])
            for xml_file, table, cols, _ in mod.TABLES]


def test_column_mapping_matches_postgres(se_clickhouse, se_postgres):
    # Same tables in the same order, same XML-attribute -> column mapping.
    assert _mapping(se_clickhouse) == _mapping(se_postgres)


def test_type_categories_match_postgres(se_clickhouse, se_postgres):
    # The spellings differ (Int32/DateTime64(3)/String vs int/timestamp/text)
    # but the int/timestamp/text split must not: this is what pins the
    # timestamp columns to the same set every other engine types as timestamps.
    def categories(mod):
        cat = {mod.INT: "INT", mod.TS: "TS", mod.TXT: "TXT"}
        return [[cat[ct] for _, _, ct in cols] for _, _, cols, _ in mod.TABLES]
    assert categories(se_clickhouse) == categories(se_postgres)


_INDEX_RE = re.compile(r"CREATE INDEX (\w+) ON (\w+)(?: USING \w+)? \(([^)]*)\);")


def test_index_list_matches_postgres(se_clickhouse, se_postgres):
    # Nothing is emitted from it -- ClickHouse has no equivalent object -- but
    # the list is carried so this comparison keeps the shared schema honest and
    # documents what the sorting key is standing in for.
    out = []
    for _, table, _, indexes in se_postgres.TABLES:
        for index in indexes:
            m = _INDEX_RE.match(index)
            assert m, index
            out.append((table, m.group(1), [c.strip() for c in m.group(3).split(",")]))
    mine = [(table, name, list(cols))
            for _, table, _, indexes in se_clickhouse.TABLES
            for name, cols in indexes]
    assert mine == out


def test_posthistory_text_column_renamed(se_clickhouse):
    ph = next(cols for _, table, cols, _ in se_clickhouse.TABLES
              if table == "PostHistory")
    assert ("Text", "PostText") in [(xa, col) for xa, col, _ in ph]


# --- value rendering -------------------------------------------------------

def test_sql_str_escapes_quote_and_backslash(se_clickhouse):
    # The quote is doubled (shared with every other dialect); the backslash is
    # doubled too, which is this dialect's own requirement -- ClickHouse would
    # otherwise read `\n` in a post body as a newline.
    assert se_clickhouse.sql_str("a'b") == "'a''b'"
    assert se_clickhouse.sql_str("a\\b") == "'a\\\\b'"


def test_sql_str_keeps_rows_on_one_line(se_clickhouse):
    # AboutMe and Body routinely contain newlines; escaping them keeps each
    # emitted row a single line, which ClickHouse reads back identically.
    assert se_clickhouse.sql_str("line1\nline2") == "'line1\\nline2'"
    assert se_clickhouse.sql_str("a\tb") == "'a\\tb'"


def test_value_null_rules(se_clickhouse):
    # A missing attribute is NULL; an empty numeric/timestamp is NULL (an empty
    # string would not cast); an empty text attribute is a real empty string.
    assert se_clickhouse.value({}, "X", se_clickhouse.INT) == "NULL"
    assert se_clickhouse.value({"X": ""}, "X", se_clickhouse.INT) == "NULL"
    assert se_clickhouse.value({"X": ""}, "X", se_clickhouse.TS) == "NULL"
    assert se_clickhouse.value({"X": ""}, "X", se_clickhouse.TXT) == "''"


def test_value_int_unquoted(se_clickhouse):
    assert se_clickhouse.value({"X": "42"}, "X", se_clickhouse.INT) == "42"


def test_value_timestamp_keeps_the_iso_t(se_clickhouse):
    # Unlike the MySQL hook there is no separator rewrite: ClickHouse's
    # DateTime64 text parser accepts the dumps' ISO-8601 `T` form directly.
    assert se_clickhouse.value({"X": "2014-01-21T20:26:05.043"}, "X",
                               se_clickhouse.TS) == "'2014-01-21T20:26:05.043'"


# --- DDL -------------------------------------------------------------------

def test_ddl_declares_engine_and_sorting_key(se_clickhouse):
    out = se_clickhouse.ddl("Users", [
        ("Id", "Id", se_clickhouse.INT),
        ("CreationDate", "CreationDate", se_clickhouse.TS),
        ("Name", "Name", se_clickhouse.TXT)])
    assert out == ("CREATE TABLE `Users` (\n"
                   "  `Id` Int32,\n"
                   "  `CreationDate` Nullable(DateTime64(3)),\n"
                   "  `Name` Nullable(String)\n"
                   ") ENGINE = MergeTree ORDER BY (`Id`);\n")


def test_ddl_leaves_only_the_sorting_key_non_nullable(se_clickhouse):
    # "Sorting key contains nullable columns, but merge tree setting
    # `allow_nullable_key` is disabled" -- everything else is optional in these
    # dumps and so has to be Nullable.
    out = se_clickhouse.ddl("Posts", [
        ("Id", "Id", se_clickhouse.INT),
        ("Score", "Score", se_clickhouse.INT)])
    assert "`Id` Int32," in out
    assert "`Score` Nullable(Int32)" in out


def test_types_are_the_clickhouse_spellings(se_clickhouse):
    assert (se_clickhouse.INT, se_clickhouse.TS, se_clickhouse.TXT) == \
        ("Int32", "DateTime64(3)", "String")


# --- whole-file output -----------------------------------------------------

def _run(mod, tmp_path, monkeypatch):
    (tmp_path / "Users.xml").write_bytes((FIXTURES / "Users.xml").read_bytes())
    monkeypatch.setenv("DATASET", "site")
    monkeypatch.chdir(tmp_path)
    mod.main()
    return (tmp_path / "site.sql").read_text(encoding="utf-8")


def test_emits_no_indexes_or_transaction(se_clickhouse, tmp_path, monkeypatch):
    # ClickHouse's CREATE INDEX declares a data-skipping index, not the lookup
    # index the other dialects emit, and a bare `BEGIN;` is a syntax error
    # ("Expected TRANSACTION").
    out = _run(se_clickhouse, tmp_path, monkeypatch)
    assert "CREATE INDEX" not in out
    assert "BEGIN;" not in out and "COMMIT;" not in out
    assert "PRAGMA" not in out


def test_golden(se_clickhouse, tmp_path, monkeypatch):
    # expected_clickhouse.sql was generated by this hook from the shared
    # Users.xml and read through before committing; diffing it against
    # expected_duckdb.sql shows the whole fork -- the engine clause, the
    # Nullable columns, the escaped newline and the missing indexes.
    assert _run(se_clickhouse, tmp_path, monkeypatch) == \
        (FIXTURES / "expected_clickhouse.sql").read_text(encoding="utf-8")
