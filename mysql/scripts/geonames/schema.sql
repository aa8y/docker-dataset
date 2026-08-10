-- GeoNames cities15000: every city on Earth with a population above 15,000.
-- https://download.geonames.org/export/dump/
--
-- The MySQL counterpart of ../../../postgres/scripts/geonames/schema.sql.
-- GeoNames publishes only a tab-separated export (no SQL), so this schema is
-- authored here and staged into the build dir by the geonames transform hook.
-- The 19 columns, in order, are the ones documented in the export's readme.txt;
-- the column order matches the file so the positional bulk load below lines up.
--
-- Data is bulk-loaded at container start with server-side LOAD DATA INFILE; the
-- export ships in the geonames/ subdir alongside this init script (see the
-- geonames load hook). The export has no header row, no quoting (a double quote
-- in a place name is a literal character) and no backslash escapes, so
-- ESCAPED BY '' with no enclosing character reads it verbatim. Blank fields
-- would otherwise be stored as 0 in the nullable integer columns (`elevation` is
-- blank for most rows), so those three are read into user variables and NULLIFed.
--
-- Both the table and the load pin utf8mb4 explicitly. The base image's
-- entrypoint creates the dataset database with the legacy utf8mb3 charset, and
-- `alternatenames` carries names outside the BMP (e.g. Gothic script), which
-- utf8mb3 cannot store and whose bytes it cannot even parse -- the load aborts
-- with "Incorrect string value" unless both ends are told the data is utf8mb4.
--
-- Upstream refreshes the dump daily, so row counts drift between builds and the
-- smoke test records floors rather than exact counts.

CREATE TABLE cities (
  geonameid         int,
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
  population        int,
  elevation         int,
  dem               int,
  timezone          text,
  modification_date text
) DEFAULT CHARSET = utf8mb4;

LOAD DATA INFILE '/docker-entrypoint-initdb.d/geonames/cities15000.txt'
  INTO TABLE cities
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY '\t' ESCAPED BY ''
  LINES TERMINATED BY '\n'
  (geonameid, name, asciiname, alternatenames, latitude, longitude,
   feature_class, feature_code, country_code, cc2, admin1_code, admin2_code,
   admin3_code, admin4_code, @population, @elevation, @dem, timezone,
   modification_date)
  SET population = nullif(@population, ''),
      elevation  = nullif(@elevation, ''),
      dem        = nullif(@dem, '');
