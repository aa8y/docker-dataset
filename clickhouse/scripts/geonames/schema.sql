-- GeoNames cities15000: every city on Earth with a population above 15,000.
-- https://download.geonames.org/export/dump/
--
-- The ClickHouse counterpart of ../../../postgres/scripts/geonames/schema.sql.
-- GeoNames publishes only a tab-separated export (no SQL), so this schema is
-- authored here and staged into the build dir by the geonames transform hook,
-- which appends the load for the export unpacked by the extract hook. The 19
-- columns, in order, are the ones documented in the export's readme.txt, with
-- the same names and the same (int / numeric / text) split the other engines
-- use; the column order matches the file so the positional load lines up.
--
-- Types are those spellings in ClickHouse: int -> Int32, unconstrained numeric
-- -> Float64 (ClickHouse's Decimal needs a declared precision, and the
-- export's coordinates have no fixed scale), text -> String.
--
-- `geonameid` is the sorting key and so cannot be Nullable -- MergeTree rejects
-- a nullable key -- which costs nothing: it is the export's own identifier and
-- is present on every row. Every other column is Nullable, matching the other
-- engines' schemas, where nothing is declared NOT NULL. The export is dense in
-- practice but `elevation` is blank on most rows and the admin codes on many.
--
-- Upstream refreshes the dump daily, so row counts drift between builds and the
-- smoke test records floors rather than exact counts.

CREATE TABLE `cities` (
  `geonameid`         Int32,
  `name`              Nullable(String),
  `asciiname`         Nullable(String),
  `alternatenames`    Nullable(String),
  `latitude`          Nullable(Float64),
  `longitude`         Nullable(Float64),
  `feature_class`     Nullable(String),
  `feature_code`      Nullable(String),
  `country_code`      Nullable(String),
  `cc2`               Nullable(String),
  `admin1_code`       Nullable(String),
  `admin2_code`       Nullable(String),
  `admin3_code`       Nullable(String),
  `admin4_code`       Nullable(String),
  `population`        Nullable(Int32),
  `elevation`         Nullable(Int32),
  `dem`               Nullable(Int32),
  `timezone`          Nullable(String),
  `modification_date` Nullable(String)
) ENGINE = MergeTree ORDER BY (`geonameid`);
