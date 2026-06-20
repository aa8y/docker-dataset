-- StackExchange data dump, converted from XML at build time.
-- See mysql/scripts/stackexchange/transform.

SET autocommit=0;
SET unique_checks=0;
SET foreign_key_checks=0;

CREATE TABLE `Users` (
  `Id` INT PRIMARY KEY,
  `Reputation` INT,
  `CreationDate` DATETIME(6),
  `DisplayName` MEDIUMTEXT,
  `LastAccessDate` DATETIME(6),
  `WebsiteUrl` MEDIUMTEXT,
  `Location` MEDIUMTEXT,
  `AboutMe` MEDIUMTEXT,
  `Views` INT,
  `UpVotes` INT,
  `DownVotes` INT,
  `ProfileImageUrl` MEDIUMTEXT,
  `Age` INT,
  `AccountId` INT
) DEFAULT CHARSET=utf8mb4;
INSERT INTO `Users` (`Id`, `Reputation`, `CreationDate`, `DisplayName`, `LastAccessDate`, `WebsiteUrl`, `Location`, `AboutMe`, `Views`, `UpVotes`, `DownVotes`, `ProfileImageUrl`, `Age`, `AccountId`) VALUES
(1, 100, '2014-01-21 20:26:05.043', 'Alice', NULL, NULL, NULL, 'line1\nit\'s "great"', NULL, 5, NULL, NULL, NULL, NULL),
(2, NULL, NULL, 'Bob', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

CREATE INDEX `users_account_id_idx` ON `Users` (`AccountId`);
CREATE INDEX `users_display_name_idx` ON `Users` (`DisplayName`(191));
CREATE INDEX `users_up_votes_idx` ON `Users` (`UpVotes`);
CREATE INDEX `users_down_votes_idx` ON `Users` (`DownVotes`);
CREATE INDEX `users_creation_date_idx` ON `Users` (`CreationDate`);

COMMIT;
SET foreign_key_checks=1;
SET unique_checks=1;
