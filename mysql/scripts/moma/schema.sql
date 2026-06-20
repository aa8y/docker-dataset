-- The Museum of Modern Art (MoMA) research collection dataset, MySQL flavour.
-- https://github.com/MuseumofModernArt/collection
--
-- The MySQL counterpart of ../../../postgres/scripts/moma/schema.sql. MoMA
-- publishes only CSV/JSON (no SQL), so this schema is authored here and staged
-- into the build dir by the moma transform hook. Every column is text: the
-- published CSVs carry free-form values (approximate dates like "c. 1950",
-- blank measurements, multi-valued ConstituentID) that don't map onto stricter
-- types. The column order matches the CSV header order so the positional bulk
-- load below lines up.
--
-- Data is bulk-loaded at container start with server-side LOAD DATA INFILE; the
-- CSVs ship in the moma/ subdir alongside this init script (see the moma load
-- hook). IGNORE 1 LINES skips the header; OPTIONALLY ENCLOSED BY '"' with
-- ESCAPED BY '' selects RFC4180 quoting (doubled "" quotes, no backslash
-- escapes) to match the CSVs.

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

LOAD DATA INFILE '/docker-entrypoint-initdb.d/moma/Artists.csv'
  INTO TABLE artists
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY ''
  LINES TERMINATED BY '\n'
  IGNORE 1 LINES;

LOAD DATA INFILE '/docker-entrypoint-initdb.d/moma/Artworks.csv'
  INTO TABLE artworks
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY ''
  LINES TERMINATED BY '\n'
  IGNORE 1 LINES;
