SET sql_mode='ANSI_QUOTES,NO_BACKSLASH_ESCAPES';
SET foreign_key_checks=0;
SET unique_checks=0;

-- sample dump
CREATE TABLE items (
    id int NOT NULL,
    name varchar(40),
    price decimal(8,2),
    note varchar(255),
    created datetime 
);
INSERT INTO items (id, name, price, note) VALUES
('1', 'Widget', '9.99', 'plain'),
('2', 'Gadget', NULL, 'it''s fine');
ALTER TABLE items
    ADD CONSTRAINT items_pkey PRIMARY KEY (id);


SET foreign_key_checks=1;
SET unique_checks=1;
