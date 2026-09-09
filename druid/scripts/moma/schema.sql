-- The Museum of Modern Art (MoMA) research collection dataset.
-- https://github.com/MuseumofModernArt/collection
--
-- The Apache Druid counterpart of ../../../cockroach/scripts/moma/schema.sql.
-- MoMA publishes only CSV/JSON (no SQL), so this schema is authored here and
-- the moma transform hook turns the exports into `COPY ... FROM stdin` blocks
-- underneath it, handing the assembled dump to the shared scripts/pgsql hook.
-- So this file is read for column names and types rather than executed.
--
-- Every column is text, exactly as on the other engines: the published CSVs
-- carry free-form values (approximate dates like "c. 1950", blank measurements,
-- multi-valued ConstituentID) that don't map onto stricter types. Declaring
-- them all as text also keeps the Druid dimensions stable across refreshes --
-- with schema discovery a column could silently change type when upstream
-- publishes a new row.
--
-- No primary timestamp: `date_acquired` looks like one but is blank for a large
-- share of the collection and free-form where it is not, so every row gets the
-- constant `__time` the shared hook falls back to. (Declaring it as a date
-- would only make the hook discover the same thing at build time and demote it
-- anyway -- and if it ever stopped discovering it, Druid would drop the blank
-- rows and the counts would drift.)
--
-- Same two tables and same column order as the other engines, so the images are
-- queried identically. Counts drift as MoMA refreshes its exports, so the smoke
-- test records floors.

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
