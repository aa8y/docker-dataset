-- GeoNames cities15000: every city on Earth with a population above 15,000.
-- https://download.geonames.org/export/dump/
--
-- The CockroachDB counterpart of ../../../postgres/scripts/geonames/schema.sql.
-- GeoNames publishes only a tab-separated export (no SQL), so this schema is
-- authored here and staged into the build dir by the geonames transform hook,
-- which appends the IMPORT INTO that bulk-loads the export. The 19 columns, in
-- order, are the ones documented in the export's readme.txt; the column order
-- matches the file so the positional import lines up.
--
-- CockroachDB creates the database (COCKROACH_DATABASE) and runs this script
-- against it, so there is no CREATE DATABASE header.
--
-- Upstream refreshes the dump daily, so row counts drift between builds and the
-- smoke test records floors rather than exact counts.

CREATE TABLE cities (
  geonameid         int,
  name              text,
  asciiname         text,
  alternatenames    text,
  latitude          decimal,
  longitude         decimal,
  feature_class     text,
  feature_code      text,
  country_code      text,
  cc2               text,
  admin1_code       text,
  admin2_code       text,
  admin3_code       text,
  admin4_code       text,
  population        int,
  elevation         int,
  dem               int,
  timezone          text,
  modification_date text
);
