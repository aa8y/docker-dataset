-- OpenFlights: airports, airlines and the routes that connect them.
-- https://github.com/jpatokal/openflights/tree/master/data
--
-- The Apache Druid counterpart of
-- ../../../cockroach/scripts/openflights/schema.sql. OpenFlights publishes only
-- comma-separated data files (no SQL), so this schema is authored here and the
-- openflights transform hook turns the files into `COPY ... FROM stdin` blocks
-- underneath it, handing the assembled dump to the shared scripts/pgsql hook.
-- So this file is read for column names, types and NOT NULL flags rather than
-- executed: nothing here ever reaches a SQL engine, it only tells the hook that
-- `altitude` is a long dimension and `latitude` a double one.
--
-- The column order matches each file so the positional COPY lines up; column
-- names follow the field names in the upstream data dictionary.
--
-- No foreign keys, and no primary timestamp: none of the three files carries a
-- date, so every row gets the constant `__time` the shared hook falls back to.
--
-- The files are refreshed in place upstream, so row counts drift between builds
-- and the smoke test records floors rather than exact counts.

CREATE TABLE airports (
  airport_id integer,
  name       text,
  city       text,
  country    text,
  iata       text,
  icao       text,
  latitude   double precision,
  longitude  double precision,
  altitude   integer,           -- feet
  timezone   double precision,  -- hours offset from UTC; fractional for e.g. +05:30
  dst        text,
  tz         text,              -- tz database name, e.g. Europe/London
  type       text,
  source     text
);

CREATE TABLE airlines (
  airline_id integer,
  name       text,
  alias      text,
  iata       text,
  icao       text,
  callsign   text,
  country    text,
  active     text                -- 'Y' if the airline still flies scheduled service
);

CREATE TABLE routes (
  airline                text,
  airline_id             integer,
  source_airport         text,
  source_airport_id      integer,
  destination_airport    text,
  destination_airport_id integer,
  codeshare              text,   -- 'Y' if the flight is operated by another carrier
  stops                  integer,
  equipment              text    -- space-separated aircraft type codes
);
