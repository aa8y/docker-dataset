-- sample dump
CREATE TABLE `items` (
  `id` Int32,
  `name` Nullable(String),
  `price` Nullable(Decimal(8, 2)),
  `note` Nullable(String),
  `created` Nullable(DateTime64(6))
) ENGINE = MergeTree ORDER BY (`id`);
INSERT INTO `items` (`id`, `name`, `price`, `note`) VALUES
('1', 'Widget', '9.99', 'plain'),
('2', 'Gadget', NULL, 'it''s fine');

