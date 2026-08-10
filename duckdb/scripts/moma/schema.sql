-- The Museum of Modern Art (MoMA) research collection dataset, DuckDB flavour.
-- https://github.com/MuseumofModernArt/collection
--
-- MoMA publishes only CSV/JSON (no SQL), so this schema is authored here and
-- staged into the build dir by the moma transform hook, which appends the
-- `COPY ... FROM '<file>.csv'` statements that bulk-load the CSVs fetched by
-- EXTRACT_URL. Same two tables and same column order as the sqlite flavour
-- (../../../sqlite/scripts/moma/schema.sql), so the two images are queried
-- identically.
--
-- Every column is text: the published CSVs carry free-form values (approximate
-- dates like "c. 1950", blank measurements, multi-valued ConstituentID) that
-- don't map onto stricter types. Declaring them keeps DuckDB's CSV sniffer out
-- of it -- left to its own devices it would infer types per refresh, so a
-- column could silently change shape when upstream publishes a new row.

CREATE TABLE artists (
  constituent_id text,
  display_name   text,
  artist_bio     text,
  nationality    text,
  gender         text,
  begin_date     text,
  end_date       text,
  wiki_qid       text,
  ulan           text
);

CREATE TABLE artworks (
  title            text,
  artist           text,
  constituent_id   text,
  artist_bio       text,
  nationality      text,
  begin_date       text,
  end_date         text,
  gender           text,
  date             text,
  medium           text,
  dimensions       text,
  credit_line      text,
  accession_number text,
  classification   text,
  department       text,
  date_acquired    text,
  cataloged        text,
  object_id        text,
  url              text,
  image_url        text,
  on_view          text,
  circumference_cm text,
  depth_cm         text,
  diameter_cm      text,
  height_cm        text,
  length_cm        text,
  weight_kg        text,
  width_cm         text,
  seat_height_cm   text,
  duration_sec     text
);
