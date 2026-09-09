-- StackExchange data dump, converted from XML at build time.
-- See clickhouse/scripts/stackexchange/transform.

CREATE TABLE `Users` (
  `Id` Int32,
  `Reputation` Nullable(Int32),
  `CreationDate` Nullable(DateTime64(3)),
  `DisplayName` Nullable(String),
  `LastAccessDate` Nullable(DateTime64(3)),
  `WebsiteUrl` Nullable(String),
  `Location` Nullable(String),
  `AboutMe` Nullable(String),
  `Views` Nullable(Int32),
  `UpVotes` Nullable(Int32),
  `DownVotes` Nullable(Int32),
  `ProfileImageUrl` Nullable(String),
  `Age` Nullable(Int32),
  `AccountId` Nullable(Int32)
) ENGINE = MergeTree ORDER BY (`Id`);
INSERT INTO `Users` (`Id`, `Reputation`, `CreationDate`, `DisplayName`, `LastAccessDate`, `WebsiteUrl`, `Location`, `AboutMe`, `Views`, `UpVotes`, `DownVotes`, `ProfileImageUrl`, `Age`, `AccountId`) VALUES
(1, 100, '2014-01-21T20:26:05.043', 'Alice', NULL, NULL, NULL, 'line1\nit''s "great"', NULL, 5, NULL, NULL, NULL, NULL),
(2, NULL, NULL, 'Bob', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

