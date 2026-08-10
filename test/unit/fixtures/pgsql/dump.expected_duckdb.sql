-- sample dump
CREATE TABLE Items (
    id integer NOT NULL,
    name character varying(40),
    price numeric(8,2),
    note text,
    created timestamp without time zone DEFAULT nextval('x')
);
CREATE SEQUENCE items_id_seq
    START WITH 1
    INCREMENT BY 1;
INSERT INTO Items (id, name, price, note) VALUES
('1', 'Widget', '9.99', 'plain'),
('2', 'Gadget', NULL, 'it''s fine');
ALTER TABLE ONLY Items
    ADD CONSTRAINT items_pkey PRIMARY KEY (id);

