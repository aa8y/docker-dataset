"""Unit tests for mysql/scripts/pgsql/transform (PostgreSQL dump -> MySQL).

The hook is almost entirely regex line-rewriting plus a small COPY->INSERT state
machine, so the failure modes are quiet ones (a regex matching a substring it
shouldn't, an escape rule corrupting a value) that load fine and so slip past
the row-count integration test. These lock the conversions down.
"""
import io
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pgsql"


# --- convert_type: Postgres type -> MySQL type ----------------------------

@pytest.mark.parametrize("pg, my", [
    ("character varying(40)", "varchar(40)"),
    ("character varying", "varchar"),
    ("character(2)", "char(2)"),
    ("timestamp without time zone", "datetime"),
    ("timestamp with time zone", "datetime"),
    ("timestamp(6) without time zone", "datetime"),
    ("timestamp", "datetime"),
    ("double precision", "double"),
    ("bigserial", "bigint"),
    ("serial", "int"),
    ("boolean", "tinyint(1)"),
    ("numeric", "decimal(20,6)"),
    ("numeric(5,2)", "decimal(5,2)"),
    ("text", "varchar(255)"),
])
def test_convert_type_maps_each_type(pgsql, pg, my):
    assert pgsql.convert_type("  col {} NOT NULL,".format(pg)) == \
        "  col {} NOT NULL,".format(my)


@pytest.mark.parametrize("ident", ["context", "serial_number", "subtext"])
def test_convert_type_respects_word_boundaries(pgsql, ident):
    # A column whose *name* contains a type keyword as a substring must be left
    # alone (e.g. `text` inside `context`, `serial` inside `serial_number`).
    assert pgsql.convert_type("  {} integer,".format(ident)) == \
        "  {} integer,".format(ident)


# --- copy_value: one COPY TEXT field -> MySQL literal (NO_BACKSLASH_ESCAPES) -

def test_copy_value_null_sentinel(pgsql):
    assert pgsql.copy_value("\\N") == "NULL"


def test_copy_value_plain(pgsql):
    assert pgsql.copy_value("hello") == "'hello'"


def test_copy_value_doubles_single_quote(pgsql):
    assert pgsql.copy_value("it's") == "'it''s'"


def test_copy_value_unescapes_tab_newline(pgsql):
    # COPY encodes tab/newline as \t / \n; under NO_BACKSLASH_ESCAPES the literal
    # must carry the real control character, not the backslash pair.
    assert pgsql.copy_value("a\\tb") == "'a\tb'"
    assert pgsql.copy_value("a\\nb") == "'a\nb'"


def test_copy_value_collapses_escaped_backslash(pgsql):
    # COPY encodes a literal backslash as `\\`; it must end up as one backslash.
    assert pgsql.copy_value("a\\\\b") == "'a\\b'"


# --- split_copy_row: split on unescaped delimiter only --------------------

def test_split_copy_row_plain(pgsql):
    assert pgsql.split_copy_row("a\tb\tc", "\t") == ["a", "b", "c"]


def test_split_copy_row_keeps_escaped_delimiter(pgsql):
    # `\<tab>` is an escaped tab inside a field, not a column separator.
    assert pgsql.split_copy_row("a\\\tb", "\t") == ["a\\\tb"]


def test_split_copy_row_escaped_backslash_then_delimiter(pgsql):
    # `\\` is a literal backslash; the following tab *is* a real delimiter.
    assert pgsql.split_copy_row("a\\\\\tb", "\t") == ["a\\\\", "b"]


# --- clean_ddl: per-line DDL fixes ----------------------------------------

def test_clean_ddl_alter_table_only(pgsql):
    assert pgsql.clean_ddl("ALTER TABLE ONLY Foo") == "ALTER TABLE foo"


def test_clean_ddl_drops_default_nextval(pgsql):
    assert pgsql.clean_ddl("    id integer DEFAULT nextval('s'::regclass),") == \
        "    id integer ,"


def test_clean_ddl_strips_schema_qualifiers(pgsql):
    assert pgsql.clean_ddl("ALTER TABLE public.foo") == "ALTER TABLE foo"
    assert pgsql.clean_ddl("    REFERENCES cd.bookings") == "    REFERENCES bookings"


def test_clean_ddl_lowercases_table_identifiers(pgsql):
    assert pgsql.clean_ddl("CREATE TABLE Regions (").startswith("CREATE TABLE regions")
    assert "regions" in pgsql.clean_ddl("REFERENCES Regions (id)")


def test_clean_ddl_strips_access_method(pgsql):
    assert "btree" not in pgsql.clean_ddl("    CONSTRAINT pk PRIMARY KEY USING btree (id)")


# --- convert_file: the COPY/function/sequence state machine ----------------

def _convert(pgsql, text):
    out = io.StringIO()
    pgsql.convert_file(text, out)
    return out.getvalue()


def test_convert_file_copy_block_to_insert(pgsql):
    out = _convert(pgsql,
                   "COPY public.foo (id, name) FROM stdin;\n"
                   "1\talice\n"
                   "2\tbob\n"
                   "\\.\n")
    # COPY values are rendered as quoted literals (MySQL coerces '1' into the
    # INT column). The trailing blank line is the input's final newline echoed.
    assert out == (
        "INSERT INTO foo (id, name) VALUES\n"
        "('1', 'alice'),\n"
        "('2', 'bob');\n"
        "\n")


def test_convert_file_copy_batches_at_limit(pgsql, monkeypatch):
    monkeypatch.setattr(pgsql, "BATCH", 2)
    rows = "".join("{}\tn\n".format(i) for i in range(3))
    out = _convert(pgsql, "COPY foo (id, name) FROM stdin;\n" + rows + "\\.\n")
    # 3 rows, batch of 2 -> two INSERT statements.
    assert out.count("INSERT INTO foo") == 2


def test_convert_file_drops_function_block(pgsql):
    out = _convert(pgsql,
                   "CREATE FUNCTION f() RETURNS int AS $$\n"
                   "BEGIN RETURN 1; END;\n"
                   "$$ LANGUAGE plpgsql;\n"
                   "SELECT 1;\n")
    assert "FUNCTION" not in out
    assert "BEGIN" not in out


def test_convert_file_drops_sequence_block(pgsql):
    out = _convert(pgsql, "CREATE SEQUENCE foo_seq\n  START WITH 1;\n")
    assert out.strip() == ""


def test_convert_file_drops_set_lines(pgsql):
    assert _convert(pgsql, "SET search_path = public;\n").strip() == ""


def test_convert_file_passes_through_comments_and_inserts(pgsql):
    # No trailing newline, so there is no echoed blank final line.
    text = "-- a comment\nINSERT INTO foo VALUES (1);"
    assert _convert(pgsql, text) == text + "\n"


# --- transcode: encoding fallback -----------------------------------------

def test_transcode_utf8(pgsql, tmp_path):
    p = tmp_path / "u.sql"
    p.write_bytes("café\n".encode("utf-8"))
    assert pgsql.transcode(str(p)) == "café\n"


def test_transcode_latin1_fallback(pgsql, tmp_path):
    # Some pgFoundry dumps are Latin-1; bytes that aren't valid UTF-8 must fall
    # back rather than crash the build.
    p = tmp_path / "l.sql"
    p.write_bytes("café\n".encode("latin-1"))
    assert pgsql.transcode(str(p)) == "café\n"


# --- golden: full main() run, in place, with preamble/postamble -----------

def test_golden_dump(pgsql, tmp_path, monkeypatch):
    work = tmp_path / "work.sql"
    work.write_bytes((FIXTURES / "dump.sql").read_bytes())
    monkeypatch.setenv("SQL_FILES", str(work))
    monkeypatch.chdir(tmp_path)
    pgsql.main()
    assert work.read_text(encoding="utf-8") == \
        (FIXTURES / "dump.expected.sql").read_text(encoding="utf-8")
