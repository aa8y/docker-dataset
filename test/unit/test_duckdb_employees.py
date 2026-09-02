"""Unit tests for duckdb/scripts/employees/transform.

The hook turns datacharmer/test_db's MySQL-flavoured dumps into per-table CSVs
and its PostgreSQL-port schema into DuckDB DDL. Both halves can fail quietly
rather than loudly: a mis-parsed quote or a dropped tuple shifts data into the
wrong columns instead of erroring, and a schema rewrite that misses a construct
DuckDB rejects only shows up as a build failure much later. So the tuple parser
is tested against the escape forms MySQL dumps use (which this dataset happens
not to contain), and main() is tested end to end against a golden bundle built
from a miniature of the real clone.

The dump -> CSV half of the hook is shared byte for byte with the cockroach
copy; test_cockroach_employees.py owns the test that keeps the two in step.
"""
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "employees"


# --- read_string ------------------------------------------------------------

def test_read_string_handles_both_quote_escapes(duckdb_employees):
    # SQL's doubled quote and MySQL's backslash escape mean the same thing.
    value, i = duckdb_employees.read_string("'O''Hara',", 0)
    assert (value, i) == ("O'Hara", 9)
    value, i = duckdb_employees.read_string(r"'Bam\'ford')", 0)
    assert (value, i) == ("Bam'ford", 11)


def test_read_string_decodes_backslash_escapes(duckdb_employees):
    value, _ = duckdb_employees.read_string(r"'Line\nTwo\tTabbed\\Back'", 0)
    assert value == "Line\nTwo\tTabbed\\Back"


def test_read_string_exits_when_unterminated(duckdb_employees):
    with pytest.raises(SystemExit):
        duckdb_employees.read_string("'no closing quote", 0)


# --- read_tuple -------------------------------------------------------------

def test_read_tuple_reads_numbers_strings_and_null(duckdb_employees):
    text = "(10002,'Staff',NULL,'1996-08-03'),"
    values, i = duckdb_employees.read_tuple(text, 0)
    assert values == ["10002", "Staff", None, "1996-08-03"]
    assert text[i] == ","


def test_read_tuple_tolerates_whitespace_and_newlines(duckdb_employees):
    values, _ = duckdb_employees.read_tuple("(\n  1 ,\n  'a'\n)", 0)
    assert values == ["1", "a"]


def test_read_tuple_keeps_a_quoted_null_as_text(duckdb_employees):
    # Only an *unquoted* NULL is the SQL keyword; 'NULL' is the four-letter
    # string and must survive as one.
    values, _ = duckdb_employees.read_tuple("('NULL',NULL)", 0)
    assert values == ["NULL", None]


def test_read_tuple_keeps_separators_inside_strings(duckdb_employees):
    values, _ = duckdb_employees.read_tuple("('R&D, Advanced','a)b')", 0)
    assert values == ["R&D, Advanced", "a)b"]


def test_read_tuple_exits_when_unterminated(duckdb_employees):
    with pytest.raises(SystemExit):
        duckdb_employees.read_tuple("(1,2", 0)


# --- dump_to_csv ------------------------------------------------------------

def test_dump_to_csv_writes_every_tuple_of_every_statement(
        duckdb_employees, tmp_path):
    import csv
    out = tmp_path / "out.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        rows = duckdb_employees.dump_to_csv(
            str(FIXTURES / "test_db" / "load_employees.dump"),
            csv.writer(fh, lineterminator="\n"), 6)
    # Two INSERT statements in that fixture, three tuples between them.
    assert rows == 3
    assert out.read_text(encoding="utf-8").splitlines()[1] == \
        "10002,1964-06-02,Bezalel,O'Neil,F,1985-11-21"


def test_dump_to_csv_exits_on_an_arity_mismatch(duckdb_employees, tmp_path):
    # Padding a short tuple would load the data into shifted columns; the hook
    # must fail the build instead.
    import csv
    src = tmp_path / "short.dump"
    src.write_text("INSERT INTO `t` VALUES (1,'a');\n", encoding="utf-8")
    with (tmp_path / "out.csv").open("w", newline="", encoding="utf-8") as fh:
        with pytest.raises(SystemExit):
            duckdb_employees.dump_to_csv(str(src), csv.writer(fh), 4)


# --- table_columns ----------------------------------------------------------

def test_table_columns_skips_constraint_lines(duckdb_employees):
    ddl = (FIXTURES / "test_db" / "postgresql" / "employees.sql").read_text(
        encoding="utf-8")
    # departments' block ends with PRIMARY KEY and UNIQUE lines; employees'
    # gender column carries an inline CHECK. Neither may leak into the list.
    assert duckdb_employees.table_columns(ddl, "departments") == \
        ["dept_no", "dept_name"]
    assert duckdb_employees.table_columns(ddl, "employees") == \
        ["emp_no", "birth_date", "first_name", "last_name", "gender",
         "hire_date"]
    # titles is the one table whose FOREIGN KEY sits between columns and PK.
    assert duckdb_employees.table_columns(ddl, "titles") == \
        ["emp_no", "title", "from_date", "to_date"]


def test_table_columns_exits_on_a_missing_table(duckdb_employees):
    with pytest.raises(SystemExit):
        duckdb_employees.table_columns("CREATE TABLE a (\n  x INT\n);\n", "b")


def test_every_dumped_table_is_in_the_schema(duckdb_employees):
    ddl = (FIXTURES / "test_db" / "postgresql" / "employees.sql").read_text(
        encoding="utf-8")
    for table, _ in duckdb_employees.DUMPS:
        assert duckdb_employees.table_columns(ddl, table)


# --- stage_schema -----------------------------------------------------------

def test_stage_schema_drops_what_duckdb_rejects(duckdb_employees, monkeypatch):
    monkeypatch.chdir(FIXTURES)
    ddl = duckdb_employees.stage_schema()
    # Database management: ours, not the dump's.
    assert "DROP DATABASE" not in ddl
    assert "CREATE DATABASE" not in ddl
    assert "\\connect" not in ddl
    # "Can only drop one object at a time".
    assert "DROP TABLE" not in ddl
    # "FOREIGN KEY constraints cannot use CASCADE, ..." plus per-row validation.
    assert "FOREIGN KEY" not in ddl
    # Everything DuckDB does support survives.
    assert ddl.count("CREATE TABLE ") == 6
    assert ddl.count("CREATE OR REPLACE VIEW ") == 2
    assert "CHECK (gender IN ('M','F'))" in ddl
    assert "PRIMARY KEY (emp_no, from_date)" in ddl
    assert "UNIQUE  (dept_name)" in ddl
    # No CREATE TABLE may be left with a comma dangling before its `);`.
    assert ",\n);" not in ddl


def test_stage_schema_repairs_a_trailing_foreign_key(
        duckdb_employees, tmp_path, monkeypatch):
    # Upstream always ends a CREATE TABLE with PRIMARY KEY, so dropping an FK
    # line never strands a comma today. Guard the reflow anyway: DuckDB would
    # fail with a parse error on `,\n);`.
    schema = tmp_path / "test_db" / "postgresql"
    schema.mkdir(parents=True)
    (schema / "employees.sql").write_text(
        "CREATE TABLE t (\n"
        "    a INT NOT NULL,\n"
        "    PRIMARY KEY (a),\n"
        "    FOREIGN KEY (a) REFERENCES u (a) ON DELETE CASCADE\n"
        ");\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert duckdb_employees.stage_schema() == \
        "CREATE TABLE t (\n    a INT NOT NULL,\n    PRIMARY KEY (a)\n);\n"


# --- main() -----------------------------------------------------------------

def test_main_exits_when_a_dump_is_missing(
        duckdb_employees, tmp_path, monkeypatch):
    shutil.copytree(FIXTURES / "test_db", tmp_path / "test_db")
    (tmp_path / "test_db" / "load_titles.dump").unlink()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        duckdb_employees.main()


def test_golden_bundle(duckdb_employees, tmp_path, monkeypatch):
    # The expected/ files were generated by this hook from the fixture clone
    # and read through before committing. The fixture's schema is upstream's
    # verbatim; its dumps are miniatures in the same shape, carrying the
    # escapes and the NULL the real ones do not.
    shutil.copytree(FIXTURES / "test_db", tmp_path / "test_db")
    monkeypatch.chdir(tmp_path)
    duckdb_employees.main()

    assert (tmp_path / "employees.sql").read_text(encoding="utf-8") == \
        (FIXTURES / "expected" / "duckdb" / "employees.sql").read_text(
            encoding="utf-8")
    for csv_file in sorted((FIXTURES / "expected" / "csv").iterdir()):
        assert (tmp_path / csv_file.name).read_bytes() == \
            csv_file.read_bytes(), csv_file.name
