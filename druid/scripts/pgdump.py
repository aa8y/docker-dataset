"""Write the PostgreSQL dump a CSV-only dataset never shipped.

Three of this engine's datasets -- geonames, openflights and moma -- publish
delimited text and no SQL, so their schema is authored in-repo (each dataset's
``schema.sql``) and their transform hook has to get from "a CSV file and a
CREATE TABLE" to "a Druid ingestion spec and a data file".

Rather than a second implementation of that -- typed dimensions, the explicit
column list, the ``__time`` decision and its build-time validation all have to
match -- those hooks assemble an ordinary PostgreSQL dump (the authored DDL
plus a ``COPY ... FROM stdin`` block) and hand it to the shared
``scripts/pgsql/transform``, which already does the Druid part and is covered by
unit tests. This module is the one piece that needs writing for that: the CSV
-> COPY TEXT conversion, and specifically its escaping, which is the only part
where a subtle bug would corrupt data rather than fail the build.

geonames does not need this module at all -- its published export *is* COPY
TEXT already -- which is what makes the approach worth taking: the conversion
here exists only for the two datasets that publish RFC 4180 CSV.
"""
import csv
import sys

# COPY TEXT's escapes, in the order they must be applied: the backslash first,
# or it would re-escape the backslashes the later replacements introduce.
_ESCAPES = (("\\", "\\\\"), ("\t", "\\t"), ("\n", "\\n"), ("\r", "\\r"))


def copy_escape(value, null_sentinel=None):
    """Render one parsed CSV field as a COPY TEXT field.

    `null_sentinel` is the source's own spelling of a missing value -- the
    OpenFlights data dictionary uses a literal ``\\N``, MoMA just leaves the
    cell empty -- and is mapped onto COPY's ``\\N``, which the shared hook reads
    as NULL and writes to the Druid CSV as an empty field.
    """
    if null_sentinel is not None and value == null_sentinel:
        return "\\N"
    for raw, escaped in _ESCAPES:
        value = value.replace(raw, escaped)
    return value


def copy_block(out, table, columns, rows, null_sentinel=None):
    """Append one ``COPY <table> (<columns>) FROM stdin`` block to `out`.

    The header goes on a single line because that is what pg_dump writes and
    what the shared hook matches -- a wrapped header would leave the block
    unrecognised and the table silently empty.
    """
    out.write("\nCOPY {} ({}) FROM stdin;\n".format(table, ", ".join(columns)))
    written = 0
    for row in rows:
        # Pad or truncate to the schema's width, so a refreshed upstream that
        # grew or lost a trailing column still loads (MoMA's exports are
        # genuinely ragged) rather than shifting every value one place.
        row = (list(row) + [""] * len(columns))[:len(columns)]
        out.write("\t".join(copy_escape(v, null_sentinel) for v in row) + "\n")
        written += 1
    out.write("\\.\n")
    return written


def csv_rows(path, skip_header=False):
    """Yield the rows of an RFC 4180 CSV file, optionally without its header."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        if skip_header:
            next(reader, None)  # also swallows a UTF-8 BOM, if present
        for row in reader:
            yield row


def build(schema_path, dump_path, tables):
    """Write `dump_path`: the authored schema, then one COPY block per table.

    `tables` is a list of (csv path, table name, columns, skip_header,
    null_sentinel). Row counts are reported on stdout, matching what the shared
    hook prints for the datasets that ship real dumps.
    """
    with open(schema_path, encoding="utf-8") as fh:
        schema = fh.read()
    with open(dump_path, "w", encoding="utf-8") as out:
        out.write(schema)
        if not schema.endswith("\n"):
            out.write("\n")
        for path, table, columns, skip_header, null_sentinel in tables:
            rows = copy_block(out, table, columns,
                              csv_rows(path, skip_header), null_sentinel)
            print("druid pgdump: {} -> {} rows from {}".format(
                table, rows, path), file=sys.stderr)
