--
-- Hand-written miniature of a pgFoundry dump (world/dellstore shape): a
-- client_encoding declaration, a BEGIN/COMMIT wrapper, a PL/pgSQL helper with
-- no data dependency, a COPY block whose data deliberately contains rows
-- starting with the very words the statement filter drops, and the trailing
-- setval/ANALYZE maintenance.
--
SET search_path = public, pg_catalog;


CREATE TABLE public.keywords (
    id integer NOT NULL,
    word character varying(40)
);


INSERT INTO public.keywords (id, word) VALUES
('1', 'BEGIN'),
('2', 'ANALYZE'),
('3', 'VACUUM'),
('4', 'it''s a \ tab:	here'),
('5', NULL);



