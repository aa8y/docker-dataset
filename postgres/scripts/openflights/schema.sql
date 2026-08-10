-- OpenFlights: airports, airlines and the routes that connect them.
-- https://github.com/jpatokal/openflights/tree/master/data
--
-- OpenFlights publishes only comma-separated data files (no SQL), so this
-- schema is authored here and staged into the build dir by the openflights
-- transform hook. The files carry no header row, quote their string fields
-- RFC4180-style and write an unquoted \N for a missing value, which is why each
-- load below declares NULL '\N'. The column order matches each file so the
-- positional load lines up; column names follow the field names in the upstream
-- data dictionary. Data is loaded with \copy at container start; the files ship
-- alongside this script (see cdDir in manifest.yml).
--
-- No foreign keys. `routes` is compiled from published timetables and refers to
-- airports and airlines that are not all in the other two files (a route may
-- name an airport by a code with no matching row, and ~479 routes carry \N for
-- the airline), so the natural references dangle. Declaring them would reject
-- rows the upstream dataset deliberately keeps, so the join columns are plain
-- values and the dangling references are part of what makes this dataset
-- interesting to query.
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
  latitude   numeric,
  longitude  numeric,
  altitude   int,      -- feet
  timezone   numeric,  -- hours offset from UTC; fractional for e.g. +05:30
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

\copy airports FROM 'airports.dat' WITH (FORMAT csv, NULL '\N')
\copy airlines FROM 'airlines.dat' WITH (FORMAT csv, NULL '\N')
\copy routes FROM 'routes.dat' WITH (FORMAT csv, NULL '\N')
