-- The Museum of Modern Art (MoMA) research collection dataset, SQLite flavour.
-- https://github.com/MuseumofModernArt/collection
--
-- MoMA publishes only CSV/JSON (no SQL), so this schema is authored here and
-- staged into the build dir by the moma transform hook. Every column is text:
-- the published CSVs carry free-form values (approximate dates like "c. 1950",
-- blank measurements, multi-valued ConstituentID) that don't map onto stricter
-- types. Data is bulk-loaded by the sqlite3 CLI's .import dot-command; the CSVs
-- are fetched alongside this script by EXTRACT_URL.

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
