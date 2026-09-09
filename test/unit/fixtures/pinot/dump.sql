-- A miniature PostgreSQL dump carrying, in one file, every shape the six
-- pgFoundry/Yugabyte dumps behind the pinot pgsql tags actually contain. Not a
-- copy of test/unit/fixtures/pgsql/dump.sql: that one is shared by the three
-- dialect-rewriting hooks, whose output is SQL, while this hook's output is
-- CSV + JSON and the interesting inputs are different ones.
--
-- What each part is here to exercise:
--   Regions       a mixed-case declared name loaded through a lower-case COPY
--                 (frenchtowns), plus inline `--` comments between columns, one
--                 of which is a commented-out REFERENCES with a trailing comma.
--   country       a CHECK constraint whose body contains commas and quoted
--                 literals (world), a `numeric(p,s)`, a `real`, a boolean
--                 written as COPY's t/f, and a \N NULL.
--   "measure"     a quoted reserved-word column (usda's "year"), a
--                 pipe-delimited COPY (iso3166), and a value containing the
--                 default multi-value delimiter.
--   members       INSERT-sourced data (pgexercises) in a schema, with a NULL
--                 keyword, an embedded comma, a doubled quote, and a timestamp.
--   empties       a table whose COPY block has no rows at all (dellstore's
--                 reorder).
--   audit_log     a PL/pgSQL function that must not be mistaken for a table.
BEGIN;

SET client_encoding = 'LATIN1';

CREATE SCHEMA cd;
SET search_path = cd, pg_catalog;

-- Regions / Régions
CREATE TABLE Regions (
   id SERIAL UNIQUE NOT NULL,
   code VARCHAR(4) UNIQUE NOT NULL, -- Not always numeric, for instance 2A
                                    -- and 2B
   capital VARCHAR(10) NOT NULL, -- REFERENCES Towns (code),
   name TEXT UNIQUE NOT NULL
);

CREATE TABLE public.country (
    code character(3) NOT NULL,
    name text NOT NULL,
    surfacearea real,
    indepyear smallint,
    gnp numeric(10,2),
    isofficial boolean NOT NULL,
    founded date,
    CONSTRAINT country_continent_check CHECK ((((name = 'Asia'::text) OR (name = 'Europe'::text)) OR (name = 'Oceania'::text))),
    PRIMARY KEY (code)
);

CREATE TABLE measure (
    ndb_no character(5) NOT NULL,
    "year" integer,
    seq bigint,
    amount double precision,
    note text
);

CREATE TABLE members (
    memid integer NOT NULL PRIMARY KEY,
    surname character varying(200) NOT NULL,
    address character varying(300) NOT NULL,
    recommendedby integer,
    joindate timestamp without time zone NOT NULL,
    FOREIGN KEY (recommendedby) REFERENCES members(memid) ON DELETE SET NULL
);

CREATE TABLE empties (
    prod_id integer,
    date_low date
);

CREATE FUNCTION audit_log(name_in character varying, OUT id_out integer) RETURNS integer
    AS $$
DECLARE
BEGIN
    id_out := 1;
END
$$
    LANGUAGE plpgsql;

CREATE INDEX regions_code ON Regions USING btree (code);

COPY regions (id, code, capital, name) FROM stdin;
1	01	97105	Guadeloupe
2	02	97209	Martinique
\.

COPY public.country (code, name, surfacearea, indepyear, gnp, isofficial, founded) FROM stdin;
AFG	Afghanistan	652090	1919	5976.00	t	1919-08-19
ATA	Antarctica	13120000	\N	0.00	f	\N
\.

COPY measure (ndb_no, "year", seq, amount, note) FROM stdin DELIMITER '|';
01001|2005|9223372036854775807|6.38|Bone 24.92%; Cartilage 9.79%
01002|\N|1|-0.01|tab\there
\.

COPY empties (prod_id, date_low) FROM stdin;
\.

INSERT INTO cd.members (memid, surname, address, recommendedby, joindate) VALUES
(0, 'GUEST', 'GUEST', NULL, '2012-07-01 00:00:00'),
(1, 'O''Brien', '8 Bloomsbury Close, Boston', 0, '2012-07-02 12:02:05');

GRANT SELECT ON TABLE public.country TO PUBLIC;

COMMIT;
