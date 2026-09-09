-- The Museum of Modern Art (MoMA) research collection dataset, ClickHouse flavour.
-- https://github.com/MuseumofModernArt/collection
--
-- MoMA publishes only CSV/JSON (no SQL), so this schema is authored here and
-- staged into the build dir by the moma transform hook, which appends the
-- `INSERT ... FROM INFILE` statements that load the CSVs fetched by
-- EXTRACT_URL at container start. Same two tables and same column order as the
-- postgres/sqlite/duckdb flavours (../../../postgres/scripts/moma/schema.sql),
-- so the images are queried identically.
--
-- Every column is String: the published CSVs carry free-form values
-- (approximate dates like "c. 1950", blank measurements, multi-valued
-- ConstituentID) that don't map onto stricter types. Non-nullable String rather
-- than Nullable(String), because there is no distinction worth keeping here
-- between an absent value and an empty one, and a blank CSV field lands as an
-- empty string either way.
--
-- ORDER BY tuple() -- MergeTree always needs a sorting key and neither table
-- has one: `artists.constituent_id` looks like a key but the artworks table
-- reuses the name for a comma-separated *list* of ids, and MoMA renumbers
-- rows between exports. tuple() is ClickHouse's documented "no sorting key",
-- which leaves the data in insertion (i.e. file) order.

CREATE TABLE `artists` (
  `constituent_id` String,
  `display_name`   String,
  `artist_bio`     String,
  `nationality`    String,
  `gender`         String,
  `begin_date`     String,
  `end_date`       String,
  `wiki_qid`       String,
  `ulan`           String
) ENGINE = MergeTree ORDER BY tuple();

CREATE TABLE `artworks` (
  `title`            String,
  `artist`           String,
  `constituent_id`   String,
  `artist_bio`       String,
  `nationality`      String,
  `begin_date`       String,
  `end_date`         String,
  `gender`           String,
  `date`             String,
  `medium`           String,
  `dimensions`       String,
  `credit_line`      String,
  `accession_number` String,
  `classification`   String,
  `department`       String,
  `date_acquired`    String,
  `cataloged`        String,
  `object_id`        String,
  `url`              String,
  `image_url`        String,
  `on_view`          String,
  `circumference_cm` String,
  `depth_cm`         String,
  `diameter_cm`      String,
  `height_cm`        String,
  `length_cm`        String,
  `weight_kg`        String,
  `width_cm`         String,
  `seat_height_cm`   String,
  `duration_sec`     String
) ENGINE = MergeTree ORDER BY tuple();
