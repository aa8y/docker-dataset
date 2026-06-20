"""Unit tests for the StackExchange XML -> SQL transforms (both dialects).

postgres/scripts/stackexchange/transform emits COPY TEXT; the MySQL counterpart
emits batched INSERTs. They share one schema and column mapping, adapted from
stackexchange-dump-to-postgres, and differ only in the emitted dialect. The
cross-dialect test guards the shared schema from drifting; the rest pin each
dialect's value rendering and the golden tests pin whole-file output.
"""
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
