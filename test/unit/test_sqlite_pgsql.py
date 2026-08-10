"""Unit tests for sqlite/scripts/pgsql/transform (PostgreSQL dump -> SQLite).

The SQLite counterpart of mysql/scripts/pgsql/transform, and the same class of
hook: regex line-rewriting plus a COPY->INSERT state machine. It differs in what
it drops rather than what it converts -- SQLite keeps the Postgres column
spellings (type affinity) but cannot ALTER TABLE ... ADD CONSTRAINT, has no
sequences/domains/types, and no ``::`` casts -- so the failure modes are a
dropped statement swallowing a line it shouldn't, or an escape rule corrupting a
value. Both load fine and slip past the row-count integration test.
"""
import io
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pgsql"


# --- copy_value: one COPY TEXT field -> SQLite literal --------------------

def test_copy_value_null_sentinel(sqlite_pgsql):
    assert sqlite_pgsql.copy_value("\\N") == "NULL"


def test_copy_value_doubles_single_quote(sqlite_pgsql):
    # SQLite has no backslash escapes in string literals; a quote is doubled and
    # everything else travels literally.
    assert sqlite_pgsql.copy_value("it's") == "'it''s'"


def test_copy_value_unescapes_tab_newline(sqlite_pgsql):
    # COPY encodes tab/newline as \t / \n; the literal must carry the real
    # control character (SQLite would read a backslash pair verbatim).
    assert sqlite_pgsql.copy_value("a\\tb") == "'a\tb'"
    assert sqlite_pgsql.copy_value("a\\nb") == "'a\nb'"
    assert sqlite_pgsql.copy_value("a\\rb") == "'a\rb'"


def test_copy_value_collapses_escaped_backslash(sqlite_pgsql):
    assert sqlite_pgsql.copy_value("a\\\\b") == "'a\\b'"


# --- split_copy_row: split on unescaped delimiter only --------------------

def test_split_copy_row_plain(sqlite_pgsql):
    assert sqlite_pgsql.split_copy_row("a\tb\tc", "\t") == ["a", "b", "c"]


def test_split_copy_row_keeps_escaped_delimiter(sqlite_pgsql):
    # `\<tab>` is an escaped tab inside a field, not a column separator.
    assert sqlite_pgsql.split_copy_row("a\\\tb", "\t") == ["a\\\tb"]


def test_split_copy_row_escaped_backslash_then_delimiter(sqlite_pgsql):
    # `\\` is a literal backslash; the following tab *is* a real delimiter.
    assert sqlite_pgsql.split_copy_row("a\\\\\tb", "\t") == ["a\\\\", "b"]


# --- clean_ddl: per-line DDL fixes ----------------------------------------

def test_clean_ddl_strips_type_casts(sqlite_pgsql):
    # SQLite has no `::` cast operator; the value must survive it, whether the
    # cast target carries parameters or not.
    assert sqlite_pgsql.clean_ddl("    region character varying DEFAULT 'Asia'::text,") == \
        "    region character varying DEFAULT 'Asia',"
    assert sqlite_pgsql.clean_ddl("    p numeric DEFAULT 0::numeric(8,2),") == \
        "    p numeric DEFAULT 0,"


def test_clean_ddl_drops_default_nextval(sqlite_pgsql):
    # SQLite has no sequences; the column keeps its type and loses the default.
    assert sqlite_pgsql.clean_ddl("    id integer DEFAULT nextval('s'::regclass),") == \
        "    id integer ,"


def test_clean_ddl_alter_table_only(sqlite_pgsql):
    assert sqlite_pgsql.clean_ddl("ALTER TABLE ONLY Foo") == "ALTER TABLE foo"


def test_clean_ddl_strips_schema_qualifiers(sqlite_pgsql):
    assert sqlite_pgsql.clean_ddl("CREATE TABLE public.Foo (") == "CREATE TABLE foo ("
    assert sqlite_pgsql.clean_ddl("    REFERENCES cd.Bookings") == "    REFERENCES bookings"


def test_clean_ddl_strips_access_method(sqlite_pgsql):
    # SQLite indexes have no access-method clause.
    for method in ("btree", "hash", "lsm"):
        out = sqlite_pgsql.clean_ddl(
            "    CONSTRAINT pk PRIMARY KEY USING {} (id)".format(method))
        assert method not in out, method
        assert "PRIMARY KEY" in out and "(id)" in out


def test_clean_ddl_lowercases_table_identifiers(sqlite_pgsql):
    # A dump that defines `Regions` but loads `regions` (Postgres folds unquoted
    # names, SQLite does not) must resolve to one spelling.
    assert sqlite_pgsql.clean_ddl("CREATE TABLE Regions (") == "CREATE TABLE regions ("
    assert sqlite_pgsql.clean_ddl("CREATE INDEX ix ON Regions (id);") == \
        "CREATE INDEX ix ON regions (id);"


# --- convert_file: the COPY / drop-block state machine ---------------------

def _convert(mod, text):
    out = io.StringIO()
    mod.convert_file(text, out)
    return out.getvalue()


def test_convert_file_copy_block_to_insert(sqlite_pgsql):
    out = _convert(sqlite_pgsql,
                   "COPY public.Foo (id, name) FROM stdin;\n"
                   "1\talice\n"
                   "2\t\\N\n"
                   "\\.\n")
    # The table name is de-qualified and lower-cased; values are quoted literals
    # (SQLite type affinity coerces '1' into an INTEGER column).
    assert out == (
        "INSERT INTO foo (id, name) VALUES\n"
        "('1', 'alice'),\n"
        "('2', NULL);\n"
        "\n")


def test_convert_file_copy_honours_delimiter(sqlite_pgsql):
    out = _convert(sqlite_pgsql, "COPY foo (a, b) FROM stdin DELIMITER '|';\n"
                                 "1|x\n\\.\n")
    assert "('1', 'x')" in out


def test_convert_file_copy_batches_at_limit(sqlite_pgsql, monkeypatch):
    monkeypatch.setattr(sqlite_pgsql, "BATCH", 2)
    rows = "".join("{}\tn\n".format(i) for i in range(3))
    out = _convert(sqlite_pgsql, "COPY foo (id, name) FROM stdin;\n" + rows + "\\.\n")
    assert out.count("INSERT INTO foo") == 2


def test_convert_file_drops_single_line_alter_table(sqlite_pgsql):
    # SQLite cannot add constraints via ALTER TABLE, so these go wholesale --
    # and the *next* statement must survive.
    out = _convert(sqlite_pgsql,
                   "ALTER TABLE foo ADD CONSTRAINT pk PRIMARY KEY (id);\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_multi_line_alter_table(sqlite_pgsql):
    out = _convert(sqlite_pgsql,
                   "ALTER TABLE ONLY public.foo\n"
                   "    ADD CONSTRAINT pk PRIMARY KEY (id);\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_block_statements(sqlite_pgsql):
    # SQLite has none of these; each is dropped whether it ends on its own line
    # or spans several, and the following statement must survive either way.
    for head in ("CREATE SEQUENCE foo_seq", "ALTER SEQUENCE foo_seq",
                 "CREATE DOMAIN d AS integer", "CREATE TYPE mood AS ENUM"):
        assert _convert(sqlite_pgsql, head + ";\nSELECT 1;") == "SELECT 1;\n", head
        assert _convert(sqlite_pgsql,
                        head + "\n    OWNED BY foo.id;\nSELECT 1;") == \
            "SELECT 1;\n", head


def test_convert_file_drops_function_block(sqlite_pgsql):
    out = _convert(sqlite_pgsql,
                   "CREATE OR REPLACE FUNCTION f() RETURNS int AS $$\n"
                   "BEGIN RETURN 1; END;\n"
                   "$$ LANGUAGE plpgsql;\n"
                   "SELECT 1;")
    assert out == "SELECT 1;\n"


def test_convert_file_drops_noise_lines(sqlite_pgsql):
    for line in ("SET search_path = public;",
                 "SELECT pg_catalog.setval('s', 1, true);",
                 "GRANT ALL ON TABLE foo TO postgres;",
                 "REVOKE ALL ON TABLE foo FROM public;",
                 "COMMENT ON TABLE foo IS 'x';",
                 "WITHOUT OIDS;",
                 "CREATE SCHEMA cd;",
                 "\\connect mydb"):
        assert _convert(sqlite_pgsql, line) == "", line


def test_convert_file_passes_through_comments_and_inserts(sqlite_pgsql):
    # An INSERT is only de-qualified -- never run through clean_ddl, so its data
    # keeps any `::`-looking or mixed-case content.
    text = "-- a comment\nINSERT INTO public.foo VALUES ('A::B');"
    assert _convert(sqlite_pgsql, text) == \
        "-- a comment\nINSERT INTO foo VALUES ('A::B');\n"


# --- transcode: encoding fallback -----------------------------------------

def test_transcode_utf8(sqlite_pgsql, tmp_path):
    p = tmp_path / "u.sql"
    p.write_bytes("café\n".encode("utf-8"))
    assert sqlite_pgsql.transcode(str(p)) == "café\n"


def test_transcode_latin1_fallback(sqlite_pgsql, tmp_path):
    # Some pgFoundry dumps are Latin-1; bytes that aren't valid UTF-8 must fall
    # back rather than crash the build.
    p = tmp_path / "l.sql"
    p.write_bytes("café\n".encode("latin-1"))
    assert sqlite_pgsql.transcode(str(p)) == "café\n"


# --- main(): file selection and the once-per-run preamble ------------------

def test_main_exits_without_sql_files(sqlite_pgsql, tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_FILES", "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        sqlite_pgsql.main()


def test_main_writes_preamble_only_to_first_file(sqlite_pgsql, tmp_path, monkeypatch):
    # The files are cat'd into one sqlite3 session, so the PRAGMA preamble must
    # appear exactly once, at the top of the first file.
    first, second = tmp_path / "a.sql", tmp_path / "b.sql"
    for p in (first, second):
        p.write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.setenv("SQL_FILES", "{} {}".format(first, second))
    monkeypatch.chdir(tmp_path)
    sqlite_pgsql.main()
    assert first.read_text(encoding="utf-8").startswith(sqlite_pgsql.PREAMBLE)
    assert "PRAGMA" not in second.read_text(encoding="utf-8")


# --- golden: full main() run, in place -------------------------------------

def test_golden_dump(sqlite_pgsql, tmp_path, monkeypatch):
    # Same input dump as test_pgsql.py's golden, so the two dialects' whole-file
    # output can be diffed against each other by eye.
    work = tmp_path / "work.sql"
    work.write_bytes((FIXTURES / "dump.sql").read_bytes())
    monkeypatch.setenv("SQL_FILES", str(work))
    monkeypatch.chdir(tmp_path)
    sqlite_pgsql.main()
    assert work.read_text(encoding="utf-8") == \
        (FIXTURES / "dump.expected_sqlite.sql").read_text(encoding="utf-8")
