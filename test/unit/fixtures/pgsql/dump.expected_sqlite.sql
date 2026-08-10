PRAGMA synchronous=OFF;
PRAGMA journal_mode=MEMORY;

-- sample dump
CREATE TABLE items (
    id serial NOT NULL,
    name character varying(40),
    price numeric(8,2),
    note text,
    created timestamp without time zone 
);
INSERT INTO items (id, name, price, note) VALUES
('1', 'Widget', '9.99', 'plain'),
('2', 'Gadget', NULL, 'it''s fine');

