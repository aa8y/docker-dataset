-- OpenFlights: airports, airlines and the routes that connect them.
-- https://github.com/jpatokal/openflights/tree/master/data
--
-- The ClickHouse counterpart of
-- ../../../postgres/scripts/openflights/schema.sql. OpenFlights publishes only
-- comma-separated data files (no SQL), so this schema is authored here and
-- staged into the build dir by the openflights transform hook, which appends
-- the loads. The column order matches each file so the positional load lines
-- up; column names and the int/numeric/text split follow the other engines'
-- schemas, which in turn follow the upstream data dictionary.
--
-- Types: int -> Int32, unconstrained numeric -> Float64 (coordinates and the
-- fractional UTC offsets have no fixed scale, and ClickHouse's Decimal needs a
-- declared precision), text -> String.
--
-- Nullability mirrors those schemas, where nothing is declared NOT NULL, with
-- the one exception MergeTree forces: a sorting-key column cannot be Nullable.
-- `airports` and `airlines` are keyed on their upstream id, which is present on
-- every row; `routes` has no key of its own, so it takes ClickHouse's
-- documented "no sorting key", ORDER BY tuple(), and every column stays
-- Nullable.
--
-- No foreign keys -- ClickHouse has none to declare, and they would be wrong
-- here anyway: `routes` is compiled from published timetables and refers to
-- airports and airlines that are not all in the other two files (a route may
-- name an airport by a code with no matching row, and ~479 routes carry \N for
-- the airline), so the natural references dangle by design.
--
-- The files are refreshed in place upstream, so row counts drift between builds
-- and the smoke test records floors rather than exact counts.

CREATE TABLE `airports` (
  `airport_id` Int32,
  `name`       Nullable(String),
  `city`       Nullable(String),
  `country`    Nullable(String),
  `iata`       Nullable(String),
  `icao`       Nullable(String),
  `latitude`   Nullable(Float64),
  `longitude`  Nullable(Float64),
  `altitude`   Nullable(Int32),   -- feet
  `timezone`   Nullable(Float64), -- hours offset from UTC; fractional for e.g. +05:30
  `dst`        Nullable(String),
  `tz`         Nullable(String),  -- tz database name, e.g. Europe/London
  `type`       Nullable(String),
  `source`     Nullable(String)
) ENGINE = MergeTree ORDER BY (`airport_id`);

CREATE TABLE `airlines` (
  `airline_id` Int32,
  `name`       Nullable(String),
  `alias`      Nullable(String),
  `iata`       Nullable(String),
  `icao`       Nullable(String),
  `callsign`   Nullable(String),
  `country`    Nullable(String),
  `active`     Nullable(String)   -- 'Y' if the airline still flies scheduled service
) ENGINE = MergeTree ORDER BY (`airline_id`);

CREATE TABLE `routes` (
  `airline`                Nullable(String),
  `airline_id`             Nullable(Int32),
  `source_airport`         Nullable(String),
  `source_airport_id`      Nullable(Int32),
  `destination_airport`    Nullable(String),
  `destination_airport_id` Nullable(Int32),
  `codeshare`              Nullable(String), -- 'Y' if operated by another carrier
  `stops`                  Nullable(Int32),
  `equipment`              Nullable(String)  -- space-separated aircraft type codes
) ENGINE = MergeTree ORDER BY tuple();
