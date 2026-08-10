PRAGMA synchronous=OFF;
PRAGMA journal_mode=MEMORY;

-- airlines-style dump (postgrespro demo database, in miniature): the upstream
-- pg_dump manages its own `demo` database, qualifies everything to the
-- `bookings` schema, declares SQL-standard-body functions, jsonb columns,
-- ANY(ARRAY[...]) CHECK constraints and convenience views.





CREATE TABLE airplanes_data (
    airplane_code character(3) NOT NULL,
    model jsonb NOT NULL,
    range integer NOT NULL,
    CONSTRAINT airplanes_data_range_check CHECK ((range > 0))
);

CREATE TABLE flights (
    flight_id integer NOT NULL,
    status text NOT NULL,
    CONSTRAINT flight_status_check CHECK ((status IN ('Scheduled', 'On Time', 'Cancelled')))
);



INSERT INTO airplanes_data (airplane_code, model, range) VALUES
('32N', '{"en": "Aerobus A320neo", "ru": "Аэробус A320neo"}', '6500'),
('773', '{"en": "Boeing 777-300", "ru": "Боинг 777-300"}', '11100');

INSERT INTO flights (flight_id, status) VALUES
('1', 'Scheduled'),
('2', 'On Time');



CREATE INDEX flights_status_idx ON flights  (status, lower(status));

