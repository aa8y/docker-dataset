-- GeoNames cities15000: every city on Earth with a population above 15,000.
-- https://download.geonames.org/export/dump/
--
-- The Apache Druid counterpart of ../../../cockroach/scripts/geonames/schema.sql.
-- GeoNames publishes only a tab-separated export (no SQL), so this schema is
-- authored here and the geonames transform hook staples the export onto it as a
-- `COPY ... FROM stdin` block -- which is exactly the format the export already
-- is -- and hands the result to the shared scripts/pgsql hook. So this file is
-- read for column names, types and NOT NULL flags, not executed: nothing here
-- ever reaches a SQL engine, it only tells the hook that `population` is a long
-- dimension and `latitude` a double one.
--
-- The 19 columns, in order, are the ones documented in the export's readme.txt;
-- the order matches the file so the positional COPY lines up.
--
-- modification_date is declared NOT NULL on purpose: the export always carries
-- it, so it becomes each row's Druid primary timestamp (`__time`) while staying
-- a dimension in its own right -- which makes this the one dataset here whose
-- __time means something. If a future export ever leaves it blank the hook
-- notices at build time and falls back to the constant timestamp rather than
-- letting Druid drop the row.
--
-- Upstream refreshes the dump daily, so row counts drift between builds and the
-- smoke test records floors rather than exact counts.

CREATE TABLE cities (
  geonameid         integer NOT NULL,
  name              text,
  asciiname         text,
  alternatenames    text,
  latitude          double precision,
  longitude         double precision,
  feature_class     text,
  feature_code      text,
  country_code      text,
  cc2               text,
  admin1_code       text,
  admin2_code       text,
  admin3_code       text,
  admin4_code       text,
  population        bigint,
  elevation         integer,
  dem               integer,
  timezone          text,
  modification_date date NOT NULL
);
