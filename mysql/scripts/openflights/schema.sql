-- OpenFlights: airports, airlines and the routes that connect them.
-- https://github.com/jpatokal/openflights/tree/master/data
--
-- The MySQL counterpart of ../../../postgres/scripts/openflights/schema.sql.
-- OpenFlights publishes only comma-separated data files (no SQL), so this
-- schema is authored here and staged into the build dir by the openflights
-- transform hook. The column order matches each file so the positional bulk
-- load below lines up; column names follow the field names in the upstream data
-- dictionary.
--
-- Data is bulk-loaded at container start with server-side LOAD DATA INFILE; the
-- files ship in the openflights/ subdir alongside this init script (see the
-- openflights load hook). The files carry no header row and quote their string
-- fields RFC4180-style, and a missing value is written as an unquoted \N --
-- which MySQL's default escape character reads as NULL, so no per-column
-- rewriting is needed. (The same escaping turns the handful of upstream names
-- that carry a literal backslash, e.g. "Compagnie Africaine d\\'Aviation", into
-- their unescaped form.) Every table is utf8mb4: the base image's entrypoint
-- creates the dataset database with the legacy utf8mb3 charset, which cannot
-- hold the non-BMP characters some airport names carry.
--
-- No foreign keys. `routes` is compiled from published timetables and refers to
-- airports and airlines that are not all in the other two files (a route may
-- name an airport by a code with no matching row, and ~479 routes carry \N for
-- the airline), so the natural references dangle. Declaring them would reject
-- rows the upstream dataset deliberately keeps.
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
  latitude   decimal(11, 7),
  longitude  decimal(11, 7),
  altitude   int,             -- feet
  timezone   decimal(4, 2),   -- hours offset from UTC; fractional for e.g. +05:30
  dst        text,
  tz         text,            -- tz database name, e.g. Europe/London
  type       text,
  source     text
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE airlines (
  airline_id int,
  name       text,
  alias      text,
  iata       text,
  icao       text,
  callsign   text,
  country    text,
  active     text  -- 'Y' if the airline still flies scheduled service
) DEFAULT CHARSET = utf8mb4;

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
) DEFAULT CHARSET = utf8mb4;

LOAD DATA INFILE '/docker-entrypoint-initdb.d/openflights/airports.dat'
  INTO TABLE airports
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n';

LOAD DATA INFILE '/docker-entrypoint-initdb.d/openflights/airlines.dat'
  INTO TABLE airlines
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n';

LOAD DATA INFILE '/docker-entrypoint-initdb.d/openflights/routes.dat'
  INTO TABLE routes
  CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
  LINES TERMINATED BY '\n';
