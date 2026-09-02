"""Unit tests for duckdb/scripts/airlines/transform (postgrespro demo dump).

The hook is a pre-processor: it rewrites the dump in place, exports four knobs
and ``exec``s duckdb/scripts/pgsql/transform, so main() never returns and the
tests drive ``convert()`` directly (as test_duckdb_sakila.py does).

Its whole job is the handful of things no knob covers -- the statements DuckDB
cannot parse at all (``CREATE EXTENSION``, ``ALTER DATABASE``, the comments on
extensions and functions), the ``ANY(ARRAY[...])`` spelling DuckDB rejects only
inside a CHECK constraint, and the one index whose meaning the type mapping
would silently change. Two properties matter enough to have a test each: the
rewrites must never reach a COPY data row (they are data, not SQL, and the
``ANY`` rewrite is not anchored), and the knobs it exports must be the ones the
shared hook actually reads.
"""
import io
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pgsql"


def _convert(mod, text):
    out = io.StringIO()
    mod.convert(io.StringIO(text), out)
    return out.getvalue()


# --- statements DuckDB cannot parse ---------------------------------------

@pytest.mark.parametrize("line", [
    "CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;",
    "DROP EXTENSION cube;",
    "COMMENT ON EXTENSION btree_gist IS 'support for indexing';",
    'ALTER DATABASE demo SET "bookings.lang" TO \'en\';',
    "ALTER DATABASE demo SET search_path TO 'bookings', '$user', 'public';",
    "COMMENT ON FUNCTION bookings.lang() IS 'Language code';",
    "COMMENT ON SCHEMA bookings IS 'x';",
    "COMMENT ON DATABASE demo IS 'x';",
])
def test_drops_unparseable_statements(duckdb_airlines, line):
    # Each is a Parser Error in DuckDB 1.5.5; see the hook's docstring.
    assert _convert(duckdb_airlines, line + "\nSELECT 1;\n") == "SELECT 1;\n"


def test_keeps_the_comments_duckdb_supports(duckdb_airlines):
    # COMMENT ON TABLE / COLUMN work, and they are the dump's documentation.
    text = ("COMMENT ON TABLE bookings.routes IS 'Routes';\n"
            "COMMENT ON COLUMN bookings.routes.validity IS 'Period of validity';\n")
    assert _convert(duckdb_airlines, text) == text


# --- ANY(ARRAY[...]) -> IN (...), on CHECK constraints only ---------------

def test_rewrites_any_array_in_a_check(duckdb_airlines):
    # "Parser Error: subqueries prohibited in CHECK constraints" -- DuckDB's
    # binder reads the ARRAY as a subquery. IN means the same and binds.
    line = ("    CONSTRAINT flight_status_check CHECK ((status = ANY "
            "(ARRAY['Scheduled'::text, 'Cancelled'::text])))\n")
    assert _convert(duckdb_airlines, line) == (
        "    CONSTRAINT flight_status_check CHECK ((status IN "
        "('Scheduled'::text, 'Cancelled'::text)))\n")


def test_leaves_any_array_alone_outside_a_check(duckdb_airlines):
    # DuckDB accepts the ANY form in an ordinary expression, so rewriting it
    # everywhere would be a gratuitous change to something that already works.
    line = "CREATE VIEW v AS SELECT * FROM t WHERE a = ANY (ARRAY['x']);\n"
    assert _convert(duckdb_airlines, line) == line


# --- the lower(<range>) index -------------------------------------------

def test_drops_an_index_over_a_range_bound(duckdb_airlines):
    # `lower(validity)` is the range's lower bound in PostgreSQL; on the text
    # column PGSQL_TYPE_MAP leaves behind it is lower-casing, so the index
    # would quietly index something else.
    text = ("CREATE TABLE bookings.routes (\n"
            "    route_no text NOT NULL,\n"
            "    validity tstzrange NOT NULL\n"
            ");\n"
            "CREATE INDEX routes_departure_airport_lower_idx ON bookings.routes"
            " USING btree (departure_airport, lower(validity));\n"
            "CREATE INDEX routes_route_no_idx ON bookings.routes"
            " USING btree (route_no);\n")
    out = _convert(duckdb_airlines, text)
    assert "routes_departure_airport_lower_idx" not in out
    assert "routes_route_no_idx" in out


def test_keeps_lower_over_an_ordinary_column(duckdb_airlines):
    # `lower()` on text means the same thing in both engines; only a column the
    # dump declared as a range type is affected.
    text = ("CREATE TABLE t (\n    status text NOT NULL\n);\n"
            "CREATE INDEX i ON t USING btree (status, lower(status));\n")
    assert _convert(duckdb_airlines, text) == text


# --- COPY bodies are data, not SQL ----------------------------------------

def test_copy_body_passes_through_untouched(duckdb_airlines):
    # A passenger name or a JSON value that reads like DDL must survive: the
    # ANY rewrite is not anchored to the start of a line, and the shared hook
    # is what turns these rows into CSV.
    text = ("COPY bookings.tickets (ticket_no, note) FROM stdin;\n"
            "0005432000000\tCOMMENT ON EXTENSION cube IS 'x';\n"
            "0005432000001\tCHECK (a = ANY (ARRAY['x']))\n"
            "\\.\n"
            "SELECT 1;\n")
    assert _convert(duckdb_airlines, text) == text


def test_copy_body_ends_at_its_terminator(duckdb_airlines):
    # ...and rewriting resumes after the `\.`, or the DDL that follows the data
    # (every ALTER TABLE and index in a pg_dump) would go unconverted.
    text = ("COPY t (a) FROM stdin;\n"
            "1\n"
            "\\.\n"
            "CREATE EXTENSION cube;\n"
            "SELECT 1;\n")
    assert _convert(duckdb_airlines, text) == \
        "COPY t (a) FROM stdin;\n1\n\\.\nSELECT 1;\n"


# --- the knobs handed to the shared hook ----------------------------------

def test_knobs_are_read_by_the_shared_hook(duckdb_airlines, duckdb_pgsql,
                                           monkeypatch):
    # A typo in a knob name would be silent: the shared hook would just do
    # nothing and the build would fail much later, on a jsonb column.
    for key, value in duckdb_airlines.KNOBS.items():
        monkeypatch.setenv(key, value)
    duckdb_pgsql.configure()
    assert duckdb_pgsql.DROP_VIEWS and duckdb_pgsql.COPY_CSV
    assert duckdb_pgsql.strip_schema("bookings.flights") == "flights"
    assert [replacement for _, replacement in duckdb_pgsql.TYPE_MAP] == \
        ["json", "text", "text", "text"]
    for key in duckdb_airlines.KNOBS:
        monkeypatch.delenv(key)
    duckdb_pgsql.configure()


# --- golden: the miniature dump, pre-hook then shared hook ----------------

def test_golden_dump(duckdb_airlines, duckdb_pgsql, tmp_path, monkeypatch):
    # The same fixture test_sqlite_pgsql.py runs, so the two dialects' whole
    # -file output can be diffed against each other by eye. Driven from the
    # build dir with a relative SQL_FILES, exactly as the Dockerfile runs it,
    # so the CSV path the COPY carries is the relative one.
    work = tmp_path / "airlines.sql"
    with (FIXTURES / "airlines.sql").open(encoding="utf-8", newline="\n") as src, \
            work.open("w", encoding="utf-8", newline="\n") as out:
        duckdb_airlines.convert(src, out)

    for key, value in duckdb_airlines.KNOBS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SQL_FILES", "airlines.sql")
    monkeypatch.chdir(tmp_path)
    duckdb_pgsql.main()
    for key in duckdb_airlines.KNOBS:
        monkeypatch.delenv(key)
    duckdb_pgsql.configure()

    assert work.read_text(encoding="utf-8") == \
        (FIXTURES / "airlines.expected_duckdb.sql").read_text(encoding="utf-8")
    # The rows leave through the sidecars, so they are part of the golden too:
    # a jsonb object full of commas and quotes is the case that would break a
    # naive writer.
    assert (tmp_path / "airplanes_data.csv").read_text(encoding="utf-8") == (
        '32N,"{""en"": ""Aerobus A320neo"", ""ru"": ""Аэробус A320neo""}",6500\n'
        '773,"{""en"": ""Boeing 777-300"", ""ru"": ""Боинг 777-300""}",11100\n')
    assert (tmp_path / "flights.csv").read_text(encoding="utf-8") == \
        "1,Scheduled\n2,On Time\n"
