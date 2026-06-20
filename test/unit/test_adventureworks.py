"""Unit tests for postgres/scripts/adventureworks/transform.

The hook reframes Microsoft's CSV bundle (pipe-delimited records with embedded
multi-line XML, and tab files with stray quotes) into the tab+CSV-quoted layout
install.sql expects. The risk is byte-level: a mis-handled newline or quote
silently corrupts a field. These pin the framing rules; the golden test asserts
whole-file output stays byte-identical.
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "adventureworks"


# --- csv_escape: quote only when needed, double embedded quotes -----------

def test_csv_escape_plain_unquoted(adventureworks):
    assert adventureworks.csv_escape("plain") == "plain"


@pytest.mark.parametrize("raw, out", [
    ('a"b', '"a""b"'),
    ("a\tb", '"a\tb"'),
    ("a\nb", '"a\nb"'),
    ("a\rb", '"a\rb"'),
])
def test_csv_escape_quotes_when_special(adventureworks, raw, out):
    assert adventureworks.csv_escape(raw) == out


# --- each_line: split only on \n, keep the terminator ---------------------

@pytest.mark.parametrize("text, lines", [
    ("a\nb\n", ["a\n", "b\n"]),
    ("a\nb", ["a\n", "b"]),
    ("a\rb\n", ["a\rb\n"]),   # embedded CR stays in the line
    ("", []),
])
def test_each_line(adventureworks, text, lines):
    assert list(adventureworks.each_line(text)) == lines


# --- chomp: strip one trailing record separator ---------------------------

@pytest.mark.parametrize("line, out", [
    ("x\r\n", "x"),
    ("x\n", "x"),
    ("x\r", "x"),
    ("x", "x"),
])
def test_chomp(adventureworks, line, out):
    assert adventureworks.chomp(line) == out


# --- reformat: branch selection + framing ---------------------------------

def test_reformat_pipe_basic(adventureworks):
    assert adventureworks.reformat("1+|a+|b&|\n", "Person") == "1\ta\tb\n"


def test_reformat_pipe_strips_nul(adventureworks):
    # A literal NUL is the NULL placeholder; it must vanish, not quote the field.
    assert adventureworks.reformat("1+|a\x00b&|\n", "Person") == "1\tab\n"


def test_reformat_pipe_multiline_record_is_quoted(adventureworks):
    # A record spans physical lines until one ends in `&|`; the embedded newline
    # forces the field to be CSV-quoted.
    assert adventureworks.reformat("1+|<x>\nmore</x>&|\n", "Person") == \
        '1\t"<x>\nmore</x>"\n'


def test_reformat_pipe_keeps_trailing_empty_field(adventureworks):
    assert adventureworks.reformat("1+|a+|&|\n", "Person") == "1\ta\t\n"


def test_reformat_productreview_multiline(adventureworks):
    # ProductReview has 8 columns; a record is complete once 7 tabs are buffered.
    out = adventureworks.reformat(
        "1\t2\t3\t4\ta\nb\t6\t7\t8\n", "ProductReview")
    assert out == '1\t2\t3\t4\t"a\nb"\t6\t7\t8\n'


def test_reformat_singleline_tab_with_quote(adventureworks):
    assert adventureworks.reformat('1\ta 2" plank\n', "ProductDescription") == \
        '1\t"a 2"" plank"\n'


def test_reformat_plain_tab_untouched(adventureworks):
    # No pipe header, not ProductReview, no quote -> leave the file alone.
    assert adventureworks.reformat("1\tplain\n", "Address") is None


def test_reformat_empty_untouched(adventureworks):
    assert adventureworks.reformat("", "Whatever") is None


# --- golden: full main() run over a bundle --------------------------------

def test_golden_bundle(adventureworks, tmp_path, monkeypatch):
    work = tmp_path / "AdventureWorks-for-Postgres"
    work.mkdir()
    inputs = sorted((FIXTURES / "input").glob("*.csv"))
    for src in inputs:
        (work / src.name).write_bytes(src.read_bytes())

    monkeypatch.chdir(tmp_path)
    adventureworks.main()

    for src in inputs:
        expected = (FIXTURES / "expected" / src.name).read_bytes()
        assert (work / src.name).read_bytes() == expected, src.name
