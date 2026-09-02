-- OpenFlights: airports, airlines and the routes that connect them.
-- https://github.com/jpatokal/openflights/tree/master/data
--
-- The Pinot counterpart of ../../../cockroach/scripts/openflights/schema.sql.
-- OpenFlights publishes only comma-separated data files (no SQL), so this
-- schema is authored here and parsed by the openflights transform hook with the
-- same CREATE TABLE reader the scripts/pgsql hook uses on real dumps -- so the
-- PostgreSQL types below reach Pinot through exactly one type map. The column
-- order matches each file so the positional load lines up; column names follow
-- the field names in the upstream data dictionary.
--
-- No foreign keys, and not only because Pinot has none to declare: `routes` is
-- compiled from published timetables and refers to airports and airlines that
-- are not all in the other two files, so the natural references dangle by
-- design.
--
-- The files are refreshed in place upstream, so row counts drift between builds
-- and the smoke test records floors rather than exact counts.

CREATE TABLE airports (
  airport_id int,
  name       text,
  city       text,
  country    text,
  iata       text,
  icao       text,
  latitude   decimal,
  longitude  decimal,
  altitude   int,      -- feet
  timezone   decimal,  -- hours offset from UTC; fractional for e.g. +05:30
  dst        text,
  tz         text,     -- tz database name, e.g. Europe/London
  type       text,
  source     text
);

CREATE TABLE airlines (
  airline_id int,
  name       text,
  alias      text,
  iata       text,
  icao       text,
  callsign   text,
  country    text,
  active     text      -- 'Y' if the airline still flies scheduled service
);

CREATE TABLE routes (
  airline                text,
  airline_id             int,
  source_airport         text,
  source_airport_id      int,
  destination_airport    text,
  destination_airport_id int,
  codeshare              text,  -- 'Y' if the flight is operated by another carrier
  stops                  int,
  equipment              text   -- space-separated aircraft type codes
);
