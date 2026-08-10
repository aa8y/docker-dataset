--
-- Hand-written miniature of a pgFoundry dump (world/dellstore shape): a
-- client_encoding declaration, a BEGIN/COMMIT wrapper, a PL/pgSQL helper with
-- no data dependency, a COPY block whose data deliberately contains rows
-- starting with the very words the statement filter drops, and the trailing
-- setval/ANALYZE maintenance.
--
SET client_encoding = 'LATIN1';
SET search_path = public, pg_catalog;

BEGIN;

CREATE TABLE public.keywords (
    id integer NOT NULL,
    word character varying(40)
);

CREATE FUNCTION public.new_customer() RETURNS void AS $$
BEGIN
    ANALYZE;
END;
$$ LANGUAGE plpgsql;

COPY public.keywords (id, word) FROM stdin;
1	BEGIN
2	ANALYZE
3	VACUUM
4	it's a \\ tab:\there
5	\N
\.

SELECT pg_catalog.setval('public.keywords_id_seq', 5, true);

COMMIT;

ANALYZE;
