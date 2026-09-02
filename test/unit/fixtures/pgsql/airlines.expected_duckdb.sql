-- airlines-style dump (postgrespro demo database, in miniature): the upstream
-- pg_dump manages its own `demo` database, qualifies everything to the
-- `bookings` schema, declares SQL-standard-body functions, jsonb columns,
-- ANY(ARRAY[...]) CHECK constraints and convenience views.





CREATE TABLE airplanes_data (
    airplane_code character(3) NOT NULL,
    model json NOT NULL,
    range integer NOT NULL,
    CONSTRAINT airplanes_data_range_check CHECK ((range > 0))
);

CREATE TABLE flights (
    flight_id integer NOT NULL,
    status text NOT NULL,
    CONSTRAINT flight_status_check CHECK ((status IN ('Scheduled'::text, 'On Time'::text, 'Cancelled'::text)))
);



COPY airplanes_data (airplane_code, model, range) FROM 'airplanes_data.csv' (FORMAT CSV, HEADER false, NULLSTR '', ALLOW_QUOTED_NULLS false, QUOTE '"', ESCAPE '"');

COPY flights (flight_id, status) FROM 'flights.csv' (FORMAT CSV, HEADER false, NULLSTR '', ALLOW_QUOTED_NULLS false, QUOTE '"', ESCAPE '"');


ALTER TABLE ONLY airplanes_data
    ADD CONSTRAINT airplanes_data_pkey PRIMARY KEY (airplane_code);

CREATE INDEX flights_status_idx ON flights  (status, lower(status));

