-- StackExchange data dump, converted from XML at build time.
-- See duckdb/scripts/stackexchange/transform.

BEGIN;

CREATE TABLE "Users" (
  "Id" INTEGER PRIMARY KEY,
  "Reputation" INTEGER,
  "CreationDate" TIMESTAMP,
  "DisplayName" TEXT,
  "LastAccessDate" TIMESTAMP,
  "WebsiteUrl" TEXT,
  "Location" TEXT,
  "AboutMe" TEXT,
  "Views" INTEGER,
  "UpVotes" INTEGER,
  "DownVotes" INTEGER,
  "ProfileImageUrl" TEXT,
  "Age" INTEGER,
  "AccountId" INTEGER
);
INSERT INTO "Users" ("Id", "Reputation", "CreationDate", "DisplayName", "LastAccessDate", "WebsiteUrl", "Location", "AboutMe", "Views", "UpVotes", "DownVotes", "ProfileImageUrl", "Age", "AccountId") VALUES
(1, 100, '2014-01-21T20:26:05.043', 'Alice', NULL, NULL, NULL, 'line1
it''s "great"', NULL, 5, NULL, NULL, NULL, NULL),
(2, NULL, NULL, 'Bob', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

CREATE INDEX "users_account_id_idx" ON "Users" ("AccountId");
CREATE INDEX "users_display_name_idx" ON "Users" ("DisplayName");
CREATE INDEX "users_up_votes_idx" ON "Users" ("UpVotes");
CREATE INDEX "users_down_votes_idx" ON "Users" ("DownVotes");
CREATE INDEX "users_creation_date_idx" ON "Users" ("CreationDate");

COMMIT;
