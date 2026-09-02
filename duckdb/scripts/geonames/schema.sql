-- GeoNames cities15000: every city on Earth with a population above 15,000.
-- https://download.geonames.org/export/dump/
--
-- The DuckDB counterpart of ../../../postgres/scripts/geonames/schema.sql.
-- GeoNames publishes only a tab-separated export (no SQL), so this schema is
-- authored here and staged into the build dir by the geonames transform hook,
-- which appends the `COPY cities FROM '<file>.txt'` that bulk-loads the export
-- unpacked by the extract hook. The 19 columns, in order, are the ones
-- documented in the export's readme.txt; the column order matches the file so
-- the positional load lines up.
--
-- latitude/longitude are decimal(11, 7) rather than the postgres flavour's
-- unconstrained `numeric`, because DuckDB has no unconstrained DECIMAL: a bare
-- `decimal` is decimal(18, 3), which would round every coordinate to three
-- decimal places. The scale is the mysql flavour's
-- (../../../mysql/scripts/geonames/schema.sql), and comfortably exact for this
-- export, which publishes at most five decimals and never more than three
-- digits of longitude.
--
-- Upstream refreshes the dump daily, so row counts drift between builds and the
-- smoke test records floors rather than exact counts.

CREATE TABLE cities (
  geonameid         integer,
  name              text,
  asciiname         text,
  alternatenames    text,
  latitude          decimal(11, 7),
  longitude         decimal(11, 7),
  feature_class     text,
  feature_code      text,
  country_code      text,
  cc2               text,
  admin1_code       text,
  admin2_code       text,
  admin3_code       text,
  admin4_code       text,
  population        integer,
  elevation         integer,
  dem               integer,
  timezone          text,
  modification_date text
);
