-- GeoNames cities15000: every city on Earth with a population above 15,000.
-- https://download.geonames.org/export/dump/
--
-- The Pinot counterpart of ../../../cockroach/scripts/geonames/schema.sql.
-- GeoNames publishes only a tab-separated export (no SQL), so this schema is
-- authored here; the geonames transform hook parses it with the same
-- CREATE TABLE reader the scripts/pgsql hook uses on real dumps, so the
-- PostgreSQL types below are mapped to Pinot data types by exactly one piece of
-- code and this file stays a plain, reviewable DDL rather than hand-written
-- JSON. The 19 columns, in order, are the ones documented in the export's
-- readme.txt; the column order matches the file so the positional load lines up.
--
-- `latitude`/`longitude` are `decimal`, which maps to Pinot DOUBLE -- the same
-- mapping every `numeric` column in the pgFoundry datasets gets, and enough
-- precision for coordinates published to five decimal places.
-- `modification_date` stays text, matching the CockroachDB and PostgreSQL
-- schemas for this dataset rather than becoming a Pinot TIMESTAMP, so the three
-- engines report the same column shape.
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
