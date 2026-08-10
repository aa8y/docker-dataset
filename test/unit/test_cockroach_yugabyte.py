"""Unit tests for cockroach/scripts/yugabyte/transform.

The hook coalesces consecutive single-row INSERTs that share an
``INSERT INTO <table> (<cols>)`` prefix into batched multi-row statements, so
tens of thousands of Raft commits collapse into a few hundred. Everything rides
on the run key: coalescing two *different* tables' rows under one prefix would
load the wrong data, and failing to flush before a non-INSERT line would reorder
statements. Both produce a dump that still executes, so these are the checks the
integration row counts cannot make.
"""


def _transform(mod, tmp_path, text, name="t.sql"):
    """Run transform_file over `text` in place and return the result."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    mod.transform_file(str(path))
    return path.read_text(encoding="utf-8")


# --- coalescing ------------------------------------------------------------

def test_same_prefix_run_becomes_one_statement(yugabyte, tmp_path):
    out = _transform(yugabyte, tmp_path,
                     "INSERT INTO t (a, b) VALUES (1, 'x');\n"
                     "INSERT INTO t (a, b) VALUES (2, 'y');\n"
                     "INSERT INTO t (a, b) VALUES (3, 'z');\n")
    assert out == ("INSERT INTO t (a, b) VALUES\n"
                   "(1, 'x'),\n"
                   "(2, 'y'),\n"
                   "(3, 'z');\n")


def test_run_flushes_at_batch_limit(yugabyte, tmp_path, monkeypatch):
    monkeypatch.setattr(yugabyte, "BATCH", 2)
    out = _transform(yugabyte, tmp_path,
                     "INSERT INTO t (a) VALUES (1);\n"
                     "INSERT INTO t (a) VALUES (2);\n"
                     "INSERT INTO t (a) VALUES (3);\n")
    assert out == ("INSERT INTO t (a) VALUES\n(1),\n(2);\n"
                   "INSERT INTO t (a) VALUES\n(3);\n")


def test_prefix_change_starts_a_new_statement(yugabyte, tmp_path):
    out = _transform(yugabyte, tmp_path,
                     "INSERT INTO t (a) VALUES (1);\n"
                     "INSERT INTO u (a) VALUES (2);\n")
    assert out == ("INSERT INTO t (a) VALUES\n(1);\n"
                   "INSERT INTO u (a) VALUES\n(2);\n")


def test_differing_column_lists_are_distinct_keys(yugabyte, tmp_path):
    # Same table, different column list: coalescing these would misalign values.
    out = _transform(yugabyte, tmp_path,
                     "INSERT INTO t (a) VALUES (1);\n"
                     "INSERT INTO t (a, b) VALUES (2, 'x');\n")
    assert out == ("INSERT INTO t (a) VALUES\n(1);\n"
                   "INSERT INTO t (a, b) VALUES\n(2, 'x');\n")


def test_quoted_and_schema_qualified_prefixes_are_distinct(yugabyte, tmp_path):
    # The prefix is compared as raw text, so "Track" and public.Track never
    # merge -- and each keeps its own spelling.
    out = _transform(yugabyte, tmp_path,
                     'INSERT INTO "Track" ("a") VALUES (1);\n'
                     "INSERT INTO public.Track (a) VALUES (2);\n")
    assert out == ('INSERT INTO "Track" ("a") VALUES\n(1);\n'
                   "INSERT INTO public.Track (a) VALUES\n(2);\n")


def test_non_insert_line_flushes_the_run(yugabyte, tmp_path):
    # A comment/DDL line must not be hoisted above the rows that precede it.
    out = _transform(yugabyte, tmp_path,
                     "INSERT INTO t (a) VALUES (1);\n"
                     "CREATE INDEX ix ON t (a);\n"
                     "INSERT INTO t (a) VALUES (2);\n")
    assert out == ("INSERT INTO t (a) VALUES\n(1);\n"
                   "CREATE INDEX ix ON t (a);\n"
                   "INSERT INTO t (a) VALUES\n(2);\n")


def test_final_run_flushes_at_eof(yugabyte, tmp_path):
    # Last statement, no trailing newline: the batch must still be written.
    out = _transform(yugabyte, tmp_path, "INSERT INTO t (a) VALUES (1);")
    assert out == "INSERT INTO t (a) VALUES\n(1);\n"


def test_multi_row_insert_still_matches_and_batches(yugabyte, tmp_path):
    # Some dumps already emit a few rows per statement. NOTE current behavior:
    # BATCH counts *statements*, not rows, so such a line contributes one entry
    # to the run however many tuples it carries.
    out = _transform(yugabyte, tmp_path,
                     "INSERT INTO t (a) VALUES (1),(2);\n"
                     "INSERT INTO t (a) VALUES (3);\n")
    assert out == "INSERT INTO t (a) VALUES\n(1),(2),\n(3);\n"


def test_insert_without_column_list_passes_through(yugabyte, tmp_path):
    # No column list means no coalescing key; the statement is left verbatim.
    text = "INSERT INTO t VALUES (1);\n"
    assert _transform(yugabyte, tmp_path, text) == text


# --- CREATE DOMAIN ----------------------------------------------------------

def test_single_line_domain_dropped_and_run_flushed(yugabyte, tmp_path):
    # CockroachDB has no CREATE DOMAIN (crdb #27796). Dropping it must also
    # close the INSERT run that preceded it.
    out = _transform(yugabyte, tmp_path,
                     "INSERT INTO t (a) VALUES (1);\n"
                     "CREATE DOMAIN primary_id AS integer;\n"
                     "INSERT INTO t (a) VALUES (2);\n")
    assert out == ("INSERT INTO t (a) VALUES\n(1);\n"
                   "INSERT INTO t (a) VALUES\n(2);\n")


def test_multi_line_domain_dropped(yugabyte, tmp_path):
    out = _transform(yugabyte, tmp_path,
                     "CREATE DOMAIN primary_id AS integer\n"
                     "    NOT NULL\n"
                     "    DEFAULT 0;\n"
                     "INSERT INTO t (a) VALUES (2);\n")
    assert out == "INSERT INTO t (a) VALUES\n(2);\n"


# --- main() -----------------------------------------------------------------

def test_main_transforms_every_listed_file(yugabyte, tmp_path, monkeypatch):
    paths = []
    for name in ("a.sql", "b.sql"):
        p = tmp_path / name
        p.write_text("INSERT INTO t (a) VALUES (1);\n"
                     "INSERT INTO t (a) VALUES (2);\n", encoding="utf-8")
        paths.append(p)
    monkeypatch.setenv("SQL_FILES", " ".join(str(p) for p in paths))
    yugabyte.main()
    for p in paths:
        assert p.read_text(encoding="utf-8") == \
            "INSERT INTO t (a) VALUES\n(1),\n(2);\n"
