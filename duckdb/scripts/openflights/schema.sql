-- OpenFlights: airports, airlines and the routes that connect them.
-- https://github.com/jpatokal/openflights/tree/master/data
--
-- The DuckDB counterpart of ../../../postgres/scripts/openflights/schema.sql.
-- OpenFlights publishes only comma-separated data files (no SQL), so this
-- schema is authored here and staged into the build dir by the openflights
-- transform hook, which appends the `COPY <table> FROM '<file>.dat'` statements
-- that bulk-load them. The column order matches each file so the positional
-- load lines up; column names follow the field names in the upstream data
-- dictionary.
--
-- latitude/longitude/timezone are decimal rather than the postgres flavour's
-- unconstrained `numeric`, because DuckDB has no unconstrained DECIMAL: a bare
-- `decimal` is decimal(18, 3), which would round every coordinate to three
-- decimal places. The scales are the mysql flavour's
-- (../../../mysql/scripts/openflights/schema.sql), so the two images hold the
-- same rounded values; the upstream coordinates are float64 round-trips
-- carrying up to eighteen meaningless trailing digits.
--
-- No foreign keys. `routes` is compiled from published timetables and refers to
-- airports and airlines that are not all in the other two files (a route may
-- name an airport by a code with no matching row, and ~479 routes carry \N for
-- the airline), so the natural references dangle. Declaring them would reject
-- rows the upstream dataset deliberately keeps -- and DuckDB validates a
-- reference per row as it loads, so it would reject them one at a time.
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
  latitude   decimal(11, 7),
  longitude  decimal(11, 7),
  altitude   integer,        -- feet
  timezone   decimal(4, 2),  -- hours offset from UTC; fractional for e.g. +05:30
  dst        text,
  tz         text,           -- tz database name, e.g. Europe/London
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
  active     text            -- 'Y' if the airline still flies scheduled service
);

CREATE TABLE routes (
  airline                text,
  airline_id             integer,
  source_airport         text,
  source_airport_id      integer,
  destination_airport    text,
  destination_airport_id integer,
  codeshare              text,    -- 'Y' if the flight is operated by another carrier
  stops                  integer,
  equipment              text     -- space-separated aircraft type codes
);
