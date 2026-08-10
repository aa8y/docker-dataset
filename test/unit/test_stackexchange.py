"""Unit tests for the StackExchange XML -> SQL transforms (both dialects).

postgres/scripts/stackexchange/transform emits COPY TEXT; the MySQL counterpart
emits batched INSERTs. They share one schema and column mapping, adapted from
stackexchange-dump-to-postgres, and differ only in the emitted dialect. The
cross-dialect test guards the shared schema from drifting; the rest pin each
dialect's value rendering and the golden tests pin whole-file output.
"""
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "stackexchange"


# --- shared schema: the two hooks must stay column-for-column in sync ------

def _schema(mod):
    cat = {mod.INT: "INT", mod.TS: "TS", mod.TXT: "TXT"}
    return [(xml_file, table, [(xa, col, cat[ct]) for xa, col, ct in cols])
            for xml_file, table, cols, _ in mod.TABLES]


def test_schema_matches_across_dialects(se_postgres, se_mysql):
    # Same tables, same XML-attribute -> column mapping, same type categories.
    assert _schema(se_postgres) == _schema(se_mysql)


def test_posthistory_text_column_renamed(se_postgres, se_mysql):
    # PostHistory's XML attribute "Text" maps to a column named PostText.
    for mod in (se_postgres, se_mysql):
        ph = next(cols for _, table, cols, _ in mod.TABLES if table == "PostHistory")
        assert ("Text", "PostText") in [(xa, col) for xa, col, _ in ph]


# --- shared schema, all four dialects --------------------------------------
#
# _schema() above keys type categories off the dialect's own INT/TS/TXT
# constants, which only works while the three are distinct strings. They are not
# for SQLite -- INT, TS, TXT = "INTEGER", "TEXT", "TEXT" -- so building that dict
# there silently collapses TS and TXT onto one key. The parity checks below
# therefore split into two: the attribute -> column mapping, which every dialect
# shares verbatim, and the type categories, compared only where the constants
# stay distinguishable (SQLite gets its own coarser check).

def _mapping(mod):
    """(xml_file, table, [(xml_attribute, sql_column), ...]) per table."""
    return [(xml_file, table, [(xa, col) for xa, col, _ in cols])
            for xml_file, table, cols, _ in mod.TABLES]


def _all_dialects(request):
    return [request.getfixturevalue("se_" + d)
            for d in ("postgres", "mysql", "sqlite", "cockroach")]


def test_column_mapping_matches_across_all_dialects(request):
    # Same tables in the same order, same XML-attribute -> column mapping.
    postgres, *others = _all_dialects(request)
    for mod in others:
        assert _mapping(mod) == _mapping(postgres), mod.__name__


def test_schema_matches_for_cockroach(se_postgres, se_cockroach):
    # CockroachDB keeps Postgres' own int/timestamp/text spellings, so the
    # category trick works verbatim here.
    assert _schema(se_cockroach) == _schema(se_postgres)


def test_sqlite_integer_columns_match_postgres_int(se_postgres, se_sqlite):
    # SQLite maps both timestamp and text onto TEXT (timestamps are stored as
    # ISO 8601 strings), so only the INT/non-INT split is comparable.
    pg = [[ct == se_postgres.INT for _, _, ct in cols]
          for _, _, cols, _ in se_postgres.TABLES]
    lite = [[ct == se_sqlite.INT for _, _, ct in cols]
            for _, _, cols, _ in se_sqlite.TABLES]
    assert lite == pg
    # Guard the premise: TS and TXT really are the same string for SQLite.
    assert se_sqlite.TS == se_sqlite.TXT == "TEXT"


_INDEX_RE = re.compile(
    r"CREATE INDEX (\w+) ON (\w+)(?: USING \w+)? \(([^)]*)\);")


def _indexes(mod):
    """(table, index_name, [column, ...]) per index, whatever the source form.

    Postgres and CockroachDB carry indexes as raw CREATE INDEX strings (the
    Postgres ones with a USING clause); MySQL and SQLite carry (name, [columns])
    tuples. Normalize to compare.
    """
    out = []
    for _, table, _, indexes in mod.TABLES:
        for index in indexes:
            if isinstance(index, str):
                m = _INDEX_RE.match(index)
                assert m, index
                assert m.group(2) == table, index
                out.append((table, m.group(1),
                            [c.strip() for c in m.group(3).split(",")]))
            else:
                name, cols = index
                out.append((table, name, list(cols)))
    return out


def test_index_parity_across_all_dialects(request):
    # Every dialect indexes the same columns under the same names; only the
    # access method (Postgres `USING hash`) and the MySQL key prefix differ, and
    # neither is part of the shared schema.
    postgres, *others = _all_dialects(request)
    for mod in others:
        assert _indexes(mod) == _indexes(postgres), mod.__name__


def test_posthistory_text_column_renamed_in_new_dialects(se_sqlite, se_cockroach):
    for mod in (se_sqlite, se_cockroach):
        ph = next(cols for _, table, cols, _ in mod.TABLES if table == "PostHistory")
        assert ("Text", "PostText") in [(xa, col) for xa, col, _ in ph]


# --- postgres dialect: COPY TEXT ------------------------------------------

def test_pg_escape(se_postgres):
    assert se_postgres.escape("a\tb") == "a\\tb"
    assert se_postgres.escape("a\nb") == "a\\nb"
    assert se_postgres.escape("a\rb") == "a\\rb"
    assert se_postgres.escape("a\\b") == "a\\\\b"


def test_pg_field_null_for_missing(se_postgres):
    assert se_postgres.field({}, "X", se_postgres.INT) == "\\N"


def test_pg_field_empty_numeric_is_null(se_postgres):
    assert se_postgres.field({"X": ""}, "X", se_postgres.INT) == "\\N"


def test_pg_field_empty_text_is_empty(se_postgres):
    # An empty TEXT attribute is a real empty string, not NULL.
    assert se_postgres.field({"X": ""}, "X", se_postgres.TXT) == ""


def test_pg_ddl(se_postgres):
    out = se_postgres.ddl("Users", [
        ("Id", "Id", se_postgres.INT), ("Name", "Name", se_postgres.TXT)])
    assert out == ("CREATE TABLE Users (\n"
                   "    Id int PRIMARY KEY,\n"
                   "    Name text\n"
                   ");\n")


# --- mysql dialect: INSERT ------------------------------------------------

def test_my_sql_str_escapes(se_mysql):
    assert se_mysql.sql_str("a'b") == "'a\\'b'"
    assert se_mysql.sql_str("a\nb") == "'a\\nb'"
    assert se_mysql.sql_str("a\\b") == "'a\\\\b'"


def test_my_value_null_for_missing(se_mysql):
    assert se_mysql.value({}, "X", se_mysql.INT) == "NULL"


def test_my_value_empty_numeric_is_null(se_mysql):
    assert se_mysql.value({"X": ""}, "X", se_mysql.INT) == "NULL"


def test_my_value_int_unquoted(se_mysql):
    assert se_mysql.value({"X": "42"}, "X", se_mysql.INT) == "42"


def test_my_value_timestamp_space_separator(se_mysql):
    # ISO 8601 "T" must become a space for MariaDB DATETIME.
    assert se_mysql.value({"X": "2014-01-21T20:26:05.043"}, "X", se_mysql.TS) == \
        "'2014-01-21 20:26:05.043'"


def test_my_ddl(se_mysql):
    out = se_mysql.ddl("Users", [
        ("Id", "Id", se_mysql.INT), ("Name", "Name", se_mysql.TXT)])
    assert out == ("CREATE TABLE `Users` (\n"
                   "  `Id` INT PRIMARY KEY,\n"
                   "  `Name` MEDIUMTEXT\n"
                   ") DEFAULT CHARSET=utf8mb4;\n")


def test_my_index_ddl_text_gets_key_prefix(se_mysql):
    out = se_mysql.index_ddl("Users", "name_idx", ["Name"], {"Name": se_mysql.TXT})
    assert out == "CREATE INDEX `name_idx` ON `Users` (`Name`(191));\n"


def test_my_index_ddl_scalar_no_prefix(se_mysql):
    out = se_mysql.index_ddl("Users", "acct_idx", ["AccountId"],
                             {"AccountId": se_mysql.INT})
    assert out == "CREATE INDEX `acct_idx` ON `Users` (`AccountId`);\n"


# --- sqlite dialect: INSERT, double-quoted identifiers ---------------------

def test_sqlite_sql_str_doubles_quote_only(se_sqlite):
    # SQLite string literals have no backslash escapes: a quote is doubled and
    # everything else -- backslashes, real newlines -- travels literally.
    assert se_sqlite.sql_str("a'b") == "'a''b'"
    assert se_sqlite.sql_str("a\\b") == "'a\\b'"
    assert se_sqlite.sql_str("a\nb") == "'a\nb'"


def test_sqlite_value_null_rules(se_sqlite):
    # Missing attribute and empty non-text both mean NULL; an empty TEXT
    # attribute is a real empty string.
    assert se_sqlite.value({}, "X", se_sqlite.INT) == "NULL"
    assert se_sqlite.value({"X": ""}, "X", se_sqlite.INT) == "NULL"
    assert se_sqlite.value({"X": ""}, "X", se_sqlite.TXT) == "''"


def test_sqlite_value_rendering_per_type(se_sqlite):
    # Ints unquoted; timestamps quoted and, unlike MariaDB DATETIME, keeping the
    # ISO 8601 "T" (SQLite stores them as text).
    assert se_sqlite.value({"X": "42"}, "X", se_sqlite.INT) == "42"
    assert se_sqlite.value({"X": "2014-01-21T20:26:05.043"}, "X", se_sqlite.TS) == \
        "'2014-01-21T20:26:05.043'"


def test_sqlite_ddl(se_sqlite):
    out = se_sqlite.ddl("Users", [
        ("Id", "Id", se_sqlite.INT), ("Name", "Name", se_sqlite.TXT)])
    assert out == ('CREATE TABLE "Users" (\n'
                   '  "Id" INTEGER PRIMARY KEY,\n'
                   '  "Name" TEXT\n'
                   ');\n')


def test_sqlite_index_ddl_needs_no_key_prefix(se_sqlite):
    # SQLite indexes a TEXT column in full, so (unlike MySQL) there is no
    # per-column length and index_ddl takes no type map.
    assert se_sqlite.index_ddl("Users", "name_idx", ["Name"]) == \
        'CREATE INDEX "name_idx" ON "Users" ("Name");\n'


# --- cockroach dialect: CSV + IMPORT INTO ----------------------------------

def test_cockroach_field_null_rules(se_cockroach):
    # The CSV carries a `\N` sentinel (matched by IMPORT's `WITH nullif`) for a
    # missing attribute and for an empty numeric/timestamp. An empty TEXT
    # attribute stays an empty string, which the writer emits as an unquoted
    # empty field -- distinct from the sentinel.
    assert se_cockroach.field({}, "X", se_cockroach.TXT) == se_cockroach.NULL
    assert se_cockroach.field({"X": ""}, "X", se_cockroach.INT) == se_cockroach.NULL
    assert se_cockroach.field({"X": ""}, "X", se_cockroach.TS) == se_cockroach.NULL
    assert se_cockroach.field({"X": ""}, "X", se_cockroach.TXT) == ""


def test_cockroach_field_passes_values_through(se_cockroach):
    # No escaping here: csv.writer quotes what needs quoting downstream.
    assert se_cockroach.field({"X": "a,b\"c"}, "X", se_cockroach.TXT) == "a,b\"c"
    assert se_cockroach.field({"X": "42"}, "X", se_cockroach.INT) == "42"


def test_cockroach_ddl(se_cockroach):
    out = se_cockroach.ddl("Users", [
        ("Id", "Id", se_cockroach.INT), ("Name", "Name", se_cockroach.TXT)])
    assert out == ("CREATE TABLE Users (\n"
                   "    Id int PRIMARY KEY,\n"
                   "    Name text\n"
                   ");\n")


def test_cockroach_write_csv(se_cockroach, tmp_path):
    xml = tmp_path / "Users.xml"
    xml.write_text('<users><row Id="1" Name="a,b" /><row Name="" /></users>\n',
                   encoding="utf-8")
    out = tmp_path / "Users.csv"
    se_cockroach.write_csv(str(xml), [("Id", "Id", se_cockroach.INT),
                                      ("Name", "Name", se_cockroach.TXT)], str(out))
    # Row 2: Id is missing -> sentinel; Name is empty TEXT -> empty field.
    assert out.read_text(encoding="utf-8") == '1,"a,b"\n\\N,\n'


# --- golden: full main() run per dialect -----------------------------------

@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
def test_golden(request, dialect, tmp_path, monkeypatch):
    mod = request.getfixturevalue("se_" + dialect)
    (tmp_path / "Users.xml").write_bytes((FIXTURES / "Users.xml").read_bytes())
    monkeypatch.setenv("DATASET", "site")
    monkeypatch.chdir(tmp_path)
    mod.main()
    expected = (FIXTURES / "expected_{}.sql".format(dialect)).read_text(encoding="utf-8")
    assert (tmp_path / "site.sql").read_text(encoding="utf-8") == expected


def test_golden_sqlite(se_sqlite, tmp_path, monkeypatch):
    # expected_sqlite.sql was generated by this hook from Users.xml and read
    # through before committing.
    (tmp_path / "Users.xml").write_bytes((FIXTURES / "Users.xml").read_bytes())
    monkeypatch.setenv("DATASET", "site")
    monkeypatch.chdir(tmp_path)
    se_sqlite.main()
    assert (tmp_path / "site.sql").read_text(encoding="utf-8") == \
        (FIXTURES / "expected_sqlite.sql").read_text(encoding="utf-8")


def test_golden_cockroach(se_cockroach, tmp_path, monkeypatch):
    # expected_cockroach.sql / expected_cockroach_Users.csv were generated by
    # this hook from Users.xml and read through before committing. CSV_DIR is
    # bound at import, so it is patched on the module, not via the environment.
    (tmp_path / "Users.xml").write_bytes((FIXTURES / "Users.xml").read_bytes())
    csv_dir = tmp_path / "csv"
    monkeypatch.setattr(se_cockroach, "CSV_DIR", str(csv_dir))
    monkeypatch.setenv("DATASET", "site")
    monkeypatch.chdir(tmp_path)
    se_cockroach.main()
    assert (tmp_path / "site.sql").read_text(encoding="utf-8") == \
        (FIXTURES / "expected_cockroach.sql").read_text(encoding="utf-8")
    assert (csv_dir / "Users.csv").read_bytes() == \
        (FIXTURES / "expected_cockroach_Users.csv").read_bytes()
