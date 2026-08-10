-- airlines-style dump (postgrespro demo database, in miniature): the upstream
-- pg_dump manages its own `demo` database, qualifies everything to the
-- `bookings` schema, declares SQL-standard-body functions, jsonb columns,
-- ANY(ARRAY[...]) CHECK constraints and convenience views.
SET statement_timeout = 0;
SELECT pg_catalog.set_config('search_path', '', false);

DROP DATABASE demo;
CREATE DATABASE demo WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE = 'en_US.UTF-8';
\connect demo

ALTER DATABASE demo SET "bookings.lang" TO 'en';
ALTER DATABASE demo SET search_path TO 'bookings', '$user', 'public';

CREATE SCHEMA bookings;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;
COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';

CREATE FUNCTION bookings.now() RETURNS timestamp with time zone
    LANGUAGE sql IMMUTABLE
    RETURN '2025-12-01 00:00:00+00'::timestamp with time zone;

CREATE TABLE bookings.airplanes_data (
    airplane_code character(3) NOT NULL,
    model jsonb NOT NULL,
    range integer NOT NULL,
    CONSTRAINT airplanes_data_range_check CHECK ((range > 0))
);

CREATE TABLE bookings.flights (
    flight_id integer NOT NULL,
    status text NOT NULL,
    CONSTRAINT flight_status_check CHECK ((status = ANY (ARRAY['Scheduled'::text, 'On Time'::text, 'Cancelled'::text])))
);

ALTER TABLE bookings.flights ALTER COLUMN flight_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME bookings.flights_flight_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE VIEW bookings.airplanes AS
 SELECT airplane_code,
    (model ->> bookings.lang()) AS model,
    range
   FROM bookings.airplanes_data;

COPY bookings.airplanes_data (airplane_code, model, range) FROM stdin;
32N	{"en": "Aerobus A320neo", "ru": "Аэробус A320neo"}	6500
773	{"en": "Boeing 777-300", "ru": "Боинг 777-300"}	11100
\.

COPY bookings.flights (flight_id, status) FROM stdin;
1	Scheduled
2	On Time
\.

SELECT pg_catalog.setval('bookings.flights_flight_id_seq', 2, true);

ALTER TABLE ONLY bookings.airplanes_data
    ADD CONSTRAINT airplanes_data_pkey PRIMARY KEY (airplane_code);

CREATE INDEX flights_status_idx ON bookings.flights USING btree (status, lower(status));
