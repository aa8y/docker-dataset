-- Miniature stand-in for cockroach/scripts/moma/schema.sql: same shape (all
-- text columns, one CREATE TABLE per CSV_TABLES entry) but only a handful of
-- columns, so the golden stays readable. The real schema is parsed by
-- test_table_columns_matches_real_schema.

CREATE TABLE artists (
  constituent_id text,
  display_name   text,
  nationality    text
);

CREATE TABLE artworks (
  title            text,
  artist           text,
  date             text,
  accession_number text
);
