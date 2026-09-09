"""Unit tests for druid/scripts/pgdump.py (CSV -> the PostgreSQL dump it lacked).

The three CSV-only Druid datasets (geonames, openflights, moma) do not
reimplement the Druid half of the pipeline: their hooks assemble the dump their
upstream never shipped -- an authored `CREATE TABLE` plus a `COPY ... FROM
stdin` block per file -- and hand it to the shared scripts/pgsql hook, which
turns DDL + COPY into ingestion specs and is tested separately. This module is
the seam between the two, so what matters here is that a value survives the
round trip unchanged.

The round-trip tests below therefore run the *real* pair: pgdump writes a dump,
the pgsql hook reads it, and the resulting Druid CSV is compared against the
input. A one-sided test of the escaping would pass happily while the two halves
disagreed about, say, what a backslash means.
"""
import csv
import io
import json

import pytest


# --- copy_escape: one CSV field -> one COPY TEXT field --------------------

def test_copy_escape_passes_plain_text_through(pgdump):
    assert pgdump.copy_escape("Andorra la Vella") == "Andorra la Vella"


def test_copy_escape_escapes_the_backslash_first(pgdump):
    # Order matters: escaping the tab first and the backslash second would
    # turn a literal backslash-t into a real tab on the way back.
    assert pgdump.copy_escape("a\\tb") == "a\\\\tb"


def test_copy_escape_escapes_control_characters(pgdump):
    assert pgdump.copy_escape("a\tb") == "a\\tb"
    assert pgdump.copy_escape("a\nb") == "a\\nb"
    assert pgdump.copy_escape("a\rb") == "a\\rb"


def test_copy_escape_maps_the_source_null_spelling(pgdump):
    # OpenFlights writes a literal \N for a missing value; MoMA leaves it empty.
    assert pgdump.copy_escape("\\N", "\\N") == "\\N"
    assert pgdump.copy_escape("", "") == "\\N"


def test_copy_escape_leaves_empty_alone_when_that_is_not_the_null_spelling(pgdump):
    assert pgdump.copy_escape("", "\\N") == ""


# --- copy_block ------------------------------------------------------------

def test_copy_block_writes_a_single_line_header(pgdump):
    # The shared hook matches the header with one regex on one line; a wrapped
    # header would leave the block unrecognised and the table silently empty.
    out = io.StringIO()
    pgdump.copy_block(out, "cities", ["a", "b"], [["1", "2"]])
    header = [ln for ln in out.getvalue().split("\n") if ln.startswith("COPY")]
    assert header == ["COPY cities (a, b) FROM stdin;"]


def test_copy_block_terminates_the_block(pgdump):
    out = io.StringIO()
    pgdump.copy_block(out, "t", ["a"], [["1"]])
    assert out.getvalue().rstrip("\n").endswith("\\.")


def test_copy_block_pads_short_rows(pgdump):
    # MoMA's exports are genuinely ragged; a short row must keep its values in
    # their own columns rather than shifting the ones after it.
    out = io.StringIO()
    pgdump.copy_block(out, "t", ["a", "b", "c"], [["1", "2"]])
    assert "1\t2\t\n" in out.getvalue()


def test_copy_block_truncates_long_rows(pgdump):
    out = io.StringIO()
    pgdump.copy_block(out, "t", ["a", "b"], [["1", "2", "3"]])
    assert "1\t2\n" in out.getvalue()


def test_copy_block_reports_the_row_count(pgdump):
    out = io.StringIO()
    assert pgdump.copy_block(out, "t", ["a"], [["1"], ["2"], ["3"]]) == 3


# --- csv_rows --------------------------------------------------------------

def test_csv_rows_skips_the_header_when_asked(pgdump, tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert list(pgdump.csv_rows(str(path), skip_header=True)) == [["1", "2"]]
    assert list(pgdump.csv_rows(str(path))) == [["a", "b"], ["1", "2"]]


def test_csv_rows_reads_quoted_fields(pgdump, tmp_path):
    path = tmp_path / "x.csv"
    path.write_text('"Smith, John","said ""hi""","line\none"\n', encoding="utf-8")
    assert list(pgdump.csv_rows(str(path))) == \
        [["Smith, John", 'said "hi"', "line\none"]]


# --- round trip: pgdump -> the shared pgsql hook -> the Druid CSV ---------

def round_trip(pgdump, druid_pgsql, tmp_path, monkeypatch, columns, rows,
               null_sentinel=None):
    """Write `rows` as CSV, run both hooks, and read back the Druid CSV rows."""
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "specs").mkdir(exist_ok=True)
    monkeypatch.setattr(druid_pgsql, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(druid_pgsql, "SPEC_DIR", str(tmp_path / "specs"))

    source = tmp_path / "source.csv"
    with open(source, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)

    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE t (\n{}\n);\n".format(
        ",\n".join("  {} text".format(c) for c in columns)), encoding="utf-8")

    dump = tmp_path / "dump.sql"
    pgdump.build(str(schema), str(dump),
                 [(str(source), "t", columns, False, null_sentinel)])

    monkeypatch.setenv("SQL_FILES", str(dump))
    monkeypatch.chdir(tmp_path)
    druid_pgsql.main()
    with open(tmp_path / "data" / "t.csv", newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def test_round_trip_preserves_ordinary_values(pgdump, druid_pgsql, tmp_path,
                                              monkeypatch):
    rows = [["Andorra la Vella", "AD", "20430"]]
    assert round_trip(pgdump, druid_pgsql, tmp_path, monkeypatch,
                      ["name", "code", "population"], rows) == rows


def test_round_trip_preserves_commas_quotes_and_backslashes(pgdump, druid_pgsql,
                                                            tmp_path, monkeypatch):
    # Each of these is escaped by one hook and unescaped by the other; if the
    # two disagreed, the value would come back mangled or split in two.
    rows = [['Smith, John', 'said "hi"', "C:\\path\\to"]]
    assert round_trip(pgdump, druid_pgsql, tmp_path, monkeypatch,
                      ["a", "b", "c"], rows) == rows


def test_round_trip_preserves_tabs(pgdump, druid_pgsql, tmp_path, monkeypatch):
    # A tab in a value would otherwise become a COPY field separator and shift
    # every column after it.
    rows = [["before\tafter", "next"]]
    assert round_trip(pgdump, druid_pgsql, tmp_path, monkeypatch,
                      ["a", "b"], rows) == rows


def test_round_trip_flattens_newlines_without_losing_columns(pgdump, druid_pgsql,
                                                             tmp_path, monkeypatch):
    # The documented lossy edge: Druid's CSV reader splits input into lines
    # before parsing, so an embedded newline cannot round-trip and is flattened
    # to a space. What must NOT happen is the row splitting in two -- ~11,000
    # MoMA values take this path.
    out = round_trip(pgdump, druid_pgsql, tmp_path, monkeypatch,
                     ["a", "b"], [["line\none", "kept"]])
    assert out == [["line one", "kept"]]


def test_round_trip_maps_the_null_sentinel_through(pgdump, druid_pgsql, tmp_path,
                                                   monkeypatch):
    # OpenFlights' \N becomes COPY's \N becomes an empty Druid CSV field, which
    # Druid reads as null -- the same result as the other engines' nullif.
    out = round_trip(pgdump, druid_pgsql, tmp_path, monkeypatch,
                     ["a", "b"], [["\\N", "kept"]], null_sentinel="\\N")
    assert out == [["", "kept"]]


def test_round_trip_spec_lists_the_authored_columns(pgdump, druid_pgsql, tmp_path,
                                                    monkeypatch):
    round_trip(pgdump, druid_pgsql, tmp_path, monkeypatch,
               ["name", "code"], [["Andorra", "AD"]])
    spec = json.loads((tmp_path / "specs" / "t.json").read_text(encoding="utf-8"))
    assert spec["spec"]["ioConfig"]["inputFormat"]["columns"] == ["name", "code"]
    assert spec["spec"]["dataSchema"]["dataSource"] == "t"
