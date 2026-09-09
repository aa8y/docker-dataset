-- The Museum of Modern Art (MoMA) research collection dataset.
-- https://github.com/MuseumofModernArt/collection
--
-- The Pinot counterpart of ../../../cockroach/scripts/moma/schema.sql, with the
-- same two tables, the same column names and the same all-`text` typing. MoMA
-- publishes only CSV/JSON (no SQL), and the published CSVs carry free-form
-- values -- approximate dates like "c. 1950", blank measurements, multi-valued
-- ConstituentID -- that do not map cleanly onto stricter types. On Pinot that
-- matters more than elsewhere: a value a column's data type cannot parse does
-- not land as an error, it lands as the type's default value, so a speculative
-- INT column here would quietly fill with Integer.MIN_VALUE.
--
-- The moma transform hook parses this file with the same CREATE TABLE reader
-- the scripts/pgsql hook uses on real dumps, so `text` becomes Pinot STRING
-- through the same type map as every other tag.
--
-- Counts drift as MoMA refreshes its exports, so the smoke test records floors
-- rather than exact counts.

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
