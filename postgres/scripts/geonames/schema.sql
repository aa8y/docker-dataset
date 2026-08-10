-- GeoNames cities15000: every city on Earth with a population above 15,000.
-- https://download.geonames.org/export/dump/
--
-- GeoNames publishes only a tab-separated export (no SQL), so this schema is
-- authored here and staged into the build dir by the geonames transform hook.
-- The 19 columns, in order, are the ones documented in the export's readme.txt;
-- the column order matches the file so the positional load below lines up.
--
-- The export carries no header row and no quoting at all -- a double quote in a
-- place name is a literal character -- so the load below reads it as CSV with a
-- tab delimiter and a QUOTE character that cannot occur in the data (backspace).
-- CSV mode is what makes an empty field NULL, which the nullable integer columns
-- (`elevation` is blank for most rows) need; COPY's TEXT format would reject
-- them. Data is loaded with \copy at container start; the export ships alongside
-- this script (see cdDir in manifest.yml).
--
-- Upstream refreshes the dump daily, so row counts drift between builds and the
-- smoke test records floors rather than exact counts.

CREATE TABLE cities (
  geonameid         int,
  name              text,
  asciiname         text,
  alternatenames    text,
  latitude          numeric,
  longitude         numeric,
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

\copy cities FROM 'cities15000.txt' WITH (FORMAT csv, DELIMITER E'\t', QUOTE E'\b')
