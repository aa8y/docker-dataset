-- sample dump
SET search_path = public;
CREATE TABLE public.Items (
    id serial NOT NULL,
    name character varying(40),
    price numeric(8,2),
    note text,
    created timestamp without time zone DEFAULT nextval('x'::regclass)
);
CREATE SEQUENCE items_id_seq
    START WITH 1
    INCREMENT BY 1;
COPY public.Items (id, name, price, note) FROM stdin;
1	Widget	9.99	plain
2	Gadget	\N	it's fine
\.
ALTER TABLE ONLY public.Items
    ADD CONSTRAINT items_pkey PRIMARY KEY (id);
