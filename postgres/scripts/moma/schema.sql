-- The Museum of Modern Art (MoMA) research collection dataset.
-- https://github.com/MuseumofModernArt/collection
--
-- MoMA publishes only CSV/JSON (no SQL), so this schema is authored here and
-- staged into the build dir by the moma transform hook. Every column is text:
-- the published CSVs carry free-form values (e.g. approximate dates like
-- "c. 1950", blank measurements, multi-valued ConstituentID) that don't map
-- cleanly onto stricter types. Data is loaded with \copy at container start;
-- the CSVs ship alongside this script (see cdDir in manifest.yml), and HEADER
-- true skips each file's header row (and its UTF-8 BOM).

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

\copy artists FROM 'Artists.csv' WITH (FORMAT csv, HEADER true)
\copy artworks FROM 'Artworks.csv' WITH (FORMAT csv, HEADER true)
