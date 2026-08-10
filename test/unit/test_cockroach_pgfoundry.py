"""Unit tests for cockroach/scripts/pgfoundry/transform.

The hook strips what CockroachDB cannot run from a pgFoundry dump (client_encoding,
the BEGIN/COMMIT wrapper, a bare ANALYZE, a PL/pgSQL helper) and rewrites COPY
blocks into batched INSERTs. The dangerous interaction is between those two jobs:
the drop patterns match on words -- BEGIN, ANALYZE, VACUUM -- that are also
perfectly ordinary *data*, so the hook keeps an in_copy flag and passes COPY
bodies through untouched. A regression there deletes rows silently and still
loads, so the row-count integration test would only catch it if the count moved.
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pgfoundry"


def _transform(mod, tmp_path, text, name="t.sql"):
    """Run transform_file over `text` in place and return the result."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    mod.transform_file(str(path))
    return path.read_text(encoding="utf-8")


# --- the headline case: COPY data must not be read as statements -----------

def test_copy_data_rows_survive_the_statement_filter(pgfoundry, tmp_path):
    # Each of these first fields is a word DROP_LINE_RE matches at line start.
    # Inside a COPY body they are data and must reach the INSERT intact.
    out = _transform(pgfoundry, tmp_path,
                     "COPY public.log (id, word) FROM stdin;\n"
                     "1\tBEGIN\n"
                     "2\tANALYZE\n"
                     "3\tCOMMIT\n"
                     "4\tVACUUM\n"
                     "\\.\n")
    assert out == ("INSERT INTO public.log (id, word) VALUES\n"
                   "('1', 'BEGIN'),\n"
                   "('2', 'ANALYZE'),\n"
                   "('3', 'COMMIT'),\n"
                   "('4', 'VACUUM');\n")


def test_statement_filter_resumes_after_the_copy_body(pgfoundry, tmp_path):
    # The in_copy flag must clear on `\.` -- a COMMIT after the block is a
    # statement again, not data.
    out = _transform(pgfoundry, tmp_path,
                     "COPY t (a) FROM stdin;\n"
                     "BEGIN\n"
                     "\\.\n"
                     "COMMIT;\n"
                     "SELECT 1;\n")
    assert out == "INSERT INTO t (a) VALUES\n('BEGIN');\nSELECT 1;\n"


# --- statement dropping ----------------------------------------------------

def test_set_client_encoding_dropped_but_search_path_kept(pgfoundry, tmp_path):
    # Only client_encoding is unsupported (crdb #35882); other SET statements
    # are left alone rather than blanket-dropped.
    out = _transform(pgfoundry, tmp_path,
                     "SET client_encoding = 'LATIN1';\n"
                     "SET search_path = public, pg_catalog;\n"
                     "SET standard_conforming_strings = off;\n")
    assert out == ("SET search_path = public, pg_catalog;\n"
                   "SET standard_conforming_strings = off;\n")


def test_transaction_and_maintenance_statements_dropped(pgfoundry, tmp_path):
    for line in ("BEGIN;", "COMMIT;", "START TRANSACTION;", "ANALYZE;",
                 "VACUUM ANALYZE;",
                 "SELECT pg_catalog.setval('s', 1, true);"):
        assert _transform(pgfoundry, tmp_path, line + "\nSELECT 1;\n") == \
            "SELECT 1;\n", line


def test_function_block_dropped_through_language_terminator(pgfoundry, tmp_path):
    # The body contains BEGIN/ANALYZE too; the whole block goes as one unit.
    out = _transform(pgfoundry, tmp_path,
                     "CREATE FUNCTION public.new_customer() RETURNS void AS $$\n"
                     "BEGIN\n"
                     "    ANALYZE;\n"
                     "END;\n"
                     "$$ LANGUAGE plpgsql;\n"
                     "SELECT 1;\n")
    assert out == "SELECT 1;\n"


def test_single_line_function_dropped(pgfoundry, tmp_path):
    out = _transform(pgfoundry, tmp_path,
                     "CREATE OR REPLACE FUNCTION f() RETURNS int AS "
                     "'select 1' LANGUAGE sql;\n"
                     "SELECT 1;\n")
    assert out == "SELECT 1;\n"


# --- COPY -> INSERT --------------------------------------------------------

def test_copy_keeps_the_table_name_verbatim(pgfoundry, tmp_path):
    # Deliberately unlike the mysql/sqlite pgsql hooks, which de-qualify and
    # lower-case: CockroachDB is PostgreSQL-compatible, so the dump's own
    # spelling (schema qualifier, mixed case) is the correct one.
    out = _transform(pgfoundry, tmp_path,
                     "COPY public.MixedCase (a) FROM stdin;\n1\n\\.\n")
    assert out.startswith("INSERT INTO public.MixedCase (a) VALUES\n")


def test_copy_batches_at_limit(pgfoundry, tmp_path, monkeypatch):
    monkeypatch.setattr(pgfoundry, "BATCH", 2)
    out = _transform(pgfoundry, tmp_path,
                     "COPY foo (id) FROM stdin;\n1\n2\n3\n\\.\n")
    assert out == ("INSERT INTO foo (id) VALUES\n('1'),\n('2');\n"
                   "INSERT INTO foo (id) VALUES\n('3');\n")


def test_copy_honours_delimiter_clause(pgfoundry, tmp_path):
    out = _transform(pgfoundry, tmp_path,
                     "COPY t (a, b) FROM stdin DELIMITER '|';\n"
                     "1|x\ty\n\\.\n")
    # With '|' as the delimiter, an embedded tab is just part of the field.
    assert out == "INSERT INTO t (a, b) VALUES\n('1', 'x\ty');\n"


# --- field-level escaping ---------------------------------------------------

def test_copy_value_null_and_escapes(pgfoundry):
    assert pgfoundry.copy_value("\\N") == "NULL"
    assert pgfoundry.copy_value("it's") == "'it''s'"
    assert pgfoundry.copy_value("a\\tb") == "'a\tb'"
    assert pgfoundry.copy_value("a\\\\b") == "'a\\b'"


def test_split_copy_row_keeps_escaped_delimiter(pgfoundry):
    assert pgfoundry.split_copy_row("a\\\tb", "\t") == ["a\\\tb"]
    assert pgfoundry.split_copy_row("a\\\\\tb", "\t") == ["a\\\\", "b"]


# --- encoding ---------------------------------------------------------------

def test_latin1_dumps_are_rewritten_as_utf8(pgfoundry, tmp_path):
    # The reason this hook exists: these dumps declare LATIN1 and ship Latin-1
    # bytes, which CockroachDB will not accept.
    assert pgfoundry.decode_raw("café\n".encode("utf-8")) == "café\n"
    assert pgfoundry.decode_raw("café\n".encode("latin-1")) == "café\n"
    path = tmp_path / "l.sql"
    path.write_bytes("SELECT 'café';\n".encode("latin-1"))
    pgfoundry.transform_file(str(path))
    assert path.read_text(encoding="utf-8") == "SELECT 'café';\n"


# --- main() -----------------------------------------------------------------

def test_main_exits_on_empty_sql_files(pgfoundry, monkeypatch):
    monkeypatch.setenv("SQL_FILES", "")
    with pytest.raises(SystemExit):
        pgfoundry.main()


def test_main_transforms_every_listed_file(pgfoundry, tmp_path, monkeypatch):
    paths = []
    for name in ("a.sql", "b.sql"):
        p = tmp_path / name
        p.write_text("BEGIN;\nSELECT 1;\n", encoding="utf-8")
        paths.append(p)
    monkeypatch.setenv("SQL_FILES", " ".join(str(p) for p in paths))
    pgfoundry.main()
    for p in paths:
        assert p.read_text(encoding="utf-8") == "SELECT 1;\n"


# --- golden -----------------------------------------------------------------

def test_golden_dump(pgfoundry, tmp_path):
    # dump.expected.sql was generated by this hook from dump.sql and read
    # through before committing.
    work = tmp_path / "dump.sql"
    work.write_bytes((FIXTURES / "dump.sql").read_bytes())
    pgfoundry.transform_file(str(work))
    assert work.read_text(encoding="utf-8") == \
        (FIXTURES / "dump.expected.sql").read_text(encoding="utf-8")
