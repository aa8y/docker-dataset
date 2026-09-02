"""Unit tests for duckdb/scripts/sakila/transform.

The hook is a pre-processor: it removes or maps the constructs the jOOQ
PostgreSQL Sakila port carries that the shared duckdb/scripts/pgsql hook does
not handle, then execs that hook. Its ``main()`` therefore never returns, so
everything here exercises ``convert()`` and the helpers it is built from.

Two of those helpers carry the real risk. The statement scanner has to be
dollar-quote aware: the dump's eight function bodies are ``$_$`` quoted and
contain both ``;`` and the word LANGUAGE, and three of them end with a
qualifier after the language name (``LANGUAGE sql IMMUTABLE;``) that the
shared hook's end-of-function regex does not match -- which is precisely why
the functions must be removed *here*, and why a scanner that stopped at the
first ``;`` inside a body would leave a dangling half-statement behind. And
``apply_domains`` re-expresses a dropped ``CREATE DOMAIN``'s CHECK as a column
constraint, so a regression there silently loses a range the upstream enforced.
"""
import pytest


# --- scan_line / read_statement: dollar-quote-aware statement boundaries ---

def test_scan_line_reports_semicolon_outside_quotes(duckdb_sakila):
    assert duckdb_sakila.scan_line("SELECT 1;", None) == (None, True)


def test_scan_line_ignores_semicolon_inside_a_string(duckdb_sakila):
    assert duckdb_sakila.scan_line("SELECT 'a;b'", None) == (None, False)


def test_scan_line_handles_doubled_quote_escape(duckdb_sakila):
    # '' is an escaped quote, not the end of the literal, so the ';' that
    # follows is still inside the string.
    assert duckdb_sakila.scan_line("SELECT 'it''s; fine'", None) == (None, False)


def test_scan_line_ignores_semicolon_in_a_comment(duckdb_sakila):
    assert duckdb_sakila.scan_line("-- a comment; not a statement", None) == (
        None, False)


def test_scan_line_enters_and_leaves_a_dollar_quote(duckdb_sakila):
    state, ends = duckdb_sakila.scan_line("    AS $_$", None)
    assert (state, ends) == ("$_$", False)
    # Inside the body a ';' is text, not a terminator.
    state, ends = duckdb_sakila.scan_line("SELECT 1; SELECT 2;", state)
    assert (state, ends) == ("$_$", False)
    state, ends = duckdb_sakila.scan_line("$_$", state)
    assert (state, ends) == (None, False)


def test_read_statement_spans_a_dollar_quoted_function_body(duckdb_sakila):
    lines = [
        "CREATE FUNCTION _group_concat(text, text) RETURNS text",
        "    AS $_$",
        "SELECT CASE WHEN $2 IS NULL THEN $1 ELSE $1 || ', ' || $2 END;",
        "$_$",
        "    LANGUAGE sql IMMUTABLE;",
        "SELECT 'after';",
    ]
    statement, nxt = duckdb_sakila.read_statement(lines, 0)
    assert statement.endswith("LANGUAGE sql IMMUTABLE;")
    assert nxt == 5


def test_read_statement_stops_at_end_of_unterminated_input(duckdb_sakila):
    statement, nxt = duckdb_sakila.read_statement(["CREATE TABLE t ("], 0)
    assert statement == "CREATE TABLE t ("
    assert nxt == 1


# --- parse_domain / apply_domains: the dropped domain's CHECK survives -----

DOMAIN = ("CREATE DOMAIN year AS integer\n"
          "\tCONSTRAINT year_check CHECK (((VALUE >= 1901) AND (VALUE <= 2155)));")


def test_parse_domain_splits_name_base_type_and_check(duckdb_sakila):
    name, base, check = duckdb_sakila.parse_domain(DOMAIN)
    assert name == "year"
    assert base == "integer"
    assert check == "(((VALUE >= 1901) AND (VALUE <= 2155)))"


def test_parse_domain_without_a_check(duckdb_sakila):
    assert duckdb_sakila.parse_domain("CREATE DOMAIN primary_id AS integer;") == (
        "primary_id", "integer", None)


def test_apply_domains_rewrites_type_and_binds_value_to_the_column(duckdb_sakila):
    out = duckdb_sakila.apply_domains(
        "CREATE TABLE film (\n    release_year year,\n    title text\n);",
        {"year": ("integer", "(((VALUE >= 1901) AND (VALUE <= 2155)))")})
    assert ("release_year integer CHECK "
            "(((release_year >= 1901) AND (release_year <= 2155)))") in out


def test_apply_domains_leaves_a_column_named_like_the_domain_alone(duckdb_sakila):
    # `year` in *name* position is a column, not a type: only the type slot
    # may be rewritten.
    out = duckdb_sakila.apply_domains(
        "CREATE TABLE t (\n    year integer\n);",
        {"year": ("integer", None)})
    assert out == "CREATE TABLE t (\n    year integer\n);"


# --- type mapping, sequence and index fixes --------------------------------

def test_map_types_demotes_tsvector_to_text(duckdb_sakila):
    assert duckdb_sakila.map_types("    fulltext tsvector NOT NULL") == (
        "    fulltext text NOT NULL")


def test_map_types_demotes_text_array_to_text(duckdb_sakila):
    assert duckdb_sakila.map_types("    special_features text[]") == (
        "    special_features text")


def test_strip_cache_removes_the_clause_but_keeps_the_terminator(duckdb_sakila):
    out = duckdb_sakila.strip_cache(
        "CREATE SEQUENCE s\n    INCREMENT BY 1\n    NO MINVALUE\n    CACHE 1;")
    assert out == "CREATE SEQUENCE s\n    INCREMENT BY 1\n    NO MINVALUE;"


def test_strip_gist_removes_only_the_access_method(duckdb_sakila):
    assert duckdb_sakila.strip_gist(
        "CREATE INDEX film_fulltext_idx ON film USING gist (fulltext);") == (
        "CREATE INDEX film_fulltext_idx ON film (fulltext);")


def test_bare_unqualifies_and_unquotes(duckdb_sakila):
    assert duckdb_sakila.bare('public."Payment_P2007_01"') == "payment_p2007_01"


# --- convert(): the whole-file rules ---------------------------------------

def test_convert_drops_procedural_language_and_schema_comment(duckdb_sakila):
    out = duckdb_sakila.convert(
        "COMMENT ON SCHEMA public IS 'Standard public schema';\n"
        "CREATE OR REPLACE PROCEDURAL LANGUAGE plpgsql;\n"
        "ALTER PROCEDURAL LANGUAGE plpgsql OWNER TO postgres;\n"
        "CREATE TABLE t (a integer);\n")
    assert "PROCEDURAL LANGUAGE" not in out
    assert "COMMENT ON SCHEMA" not in out
    assert "CREATE TABLE t (a integer);" in out


def test_convert_drops_a_function_whose_terminator_the_shared_hook_misses(
        duckdb_sakila):
    # `LANGUAGE sql IMMUTABLE;` does not match the shared hook's
    # `LANGUAGE <x>;` end-of-function regex -- left in place it would make that
    # hook swallow everything up to the next function. Nothing after the block
    # may be lost here.
    out = duckdb_sakila.convert(
        "CREATE FUNCTION _group_concat(text, text) RETURNS text\n"
        "    AS $_$\n"
        "SELECT CASE WHEN $2 IS NULL THEN $1 ELSE $1 || ', ' || $2 END;\n"
        "$_$\n"
        "    LANGUAGE sql IMMUTABLE;\n"
        "CREATE TABLE keep_me (a integer);\n")
    assert "_group_concat" not in out
    assert "CREATE TABLE keep_me (a integer);" in out


def test_convert_drops_aggregate_trigger_and_rule(duckdb_sakila):
    out = duckdb_sakila.convert(
        "CREATE AGGREGATE group_concat(text) (\n"
        "    SFUNC = _group_concat,\n"
        "    STYPE = text\n"
        ");\n"
        "ALTER AGGREGATE public.group_concat(text) OWNER TO postgres;\n"
        "CREATE TRIGGER last_updated\n"
        "    BEFORE UPDATE ON actor\n"
        "    FOR EACH ROW\n"
        "    EXECUTE PROCEDURE last_updated();\n"
        "CREATE RULE payment_insert_p2007_01 AS ON INSERT TO payment "
        "DO INSTEAD INSERT INTO payment_p2007_01 VALUES (1);\n"
        "CREATE TABLE keep_me (a integer);\n")
    for gone in ("CREATE AGGREGATE", "ALTER AGGREGATE", "CREATE TRIGGER",
                 "CREATE RULE"):
        assert gone not in out
    assert "CREATE TABLE keep_me (a integer);" in out


def test_convert_drops_inherits_children_and_their_indexes(duckdb_sakila):
    out = duckdb_sakila.convert(
        "CREATE TABLE payment (payment_id integer);\n"
        "CREATE TABLE payment_p2007_01 (CONSTRAINT c CHECK (payment_id > 0))\n"
        "INHERITS (payment);\n"
        "CREATE INDEX idx_fk_payment_p2007_01_staff_id "
        "ON payment_p2007_01 USING btree (staff_id);\n"
        "ALTER TABLE ONLY payment_p2007_01\n"
        "    ADD CONSTRAINT payment_p2007_01_pkey PRIMARY KEY (payment_id);\n"
        "CREATE INDEX idx_fk_staff_id ON payment USING btree (staff_id);\n")
    assert "payment_p2007_01" not in out
    # The parent and its own index are untouched.
    assert "CREATE TABLE payment (payment_id integer);" in out
    assert "CREATE INDEX idx_fk_staff_id ON payment USING btree (staff_id);" in out


def test_convert_maps_the_film_columns_duckdb_cannot_type(duckdb_sakila):
    out = duckdb_sakila.convert(
        "CREATE DOMAIN year AS integer\n"
        "\tCONSTRAINT year_check CHECK (((VALUE >= 1901) AND (VALUE <= 2155)));\n"
        "ALTER DOMAIN public.year OWNER TO postgres;\n"
        "CREATE TABLE film (\n"
        "    release_year year,\n"
        "    special_features text[],\n"
        "    fulltext tsvector NOT NULL\n"
        ");\n"
        "CREATE INDEX film_fulltext_idx ON film USING gist (fulltext);\n")
    assert "CREATE DOMAIN" not in out
    assert "ALTER DOMAIN" not in out
    assert "release_year integer CHECK" in out
    assert "special_features text,\n" in out
    assert "fulltext text NOT NULL" in out
    assert "CREATE INDEX film_fulltext_idx ON film (fulltext);" in out


def test_convert_passes_a_copy_body_through_untouched(duckdb_sakila):
    # COPY rows are data, not statements: they carry no ';', so running the
    # statement reader over them would swallow the block whole. They must
    # reach the shared hook verbatim for it to convert them to INSERTs.
    body = ("COPY public.film (film_id, special_features) FROM stdin;\n"
            "1\t{Trailers,\"Behind the Scenes\"}\n"
            "2\tCREATE TRIGGER not really\n"
            "\\.\n")
    out = duckdb_sakila.convert(body + "CREATE TABLE keep_me (a integer);\n")
    assert body in out
    assert "CREATE TABLE keep_me (a integer);" in out


def test_convert_keeps_the_ordinary_schema_intact(duckdb_sakila):
    # A sanity net around the drop patterns: the everyday statements the shared
    # hook is responsible for must arrive there unchanged.
    src = ("CREATE TABLE actor (\n"
           "    actor_id integer DEFAULT nextval('actor_actor_id_seq'::regclass) "
           "NOT NULL\n"
           ");\n"
           "CREATE TYPE mpaa_rating AS ENUM (\n"
           "    'G',\n"
           "    'R'\n"
           ");\n"
           "CREATE VIEW staff_list AS\n"
           "    SELECT s.staff_id AS id FROM staff s;\n"
           "ALTER TABLE ONLY actor\n"
           "    ADD CONSTRAINT actor_pkey PRIMARY KEY (actor_id);\n"
           "CREATE INDEX idx_actor_last_name ON actor USING btree (last_name);\n")
    out = duckdb_sakila.convert(src)
    for kept in ("CREATE TABLE actor", "::regclass", "CREATE TYPE mpaa_rating",
                 "CREATE VIEW staff_list", "ADD CONSTRAINT actor_pkey",
                 "USING btree"):
        assert kept in out
