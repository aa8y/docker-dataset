-- StackExchange data dump, converted from XML at build time.
-- See postgres/scripts/stackexchange/transform.

CREATE TABLE Users (
    Id int PRIMARY KEY,
    Reputation int,
    CreationDate timestamp,
    DisplayName text,
    LastAccessDate timestamp,
    WebsiteUrl text,
    Location text,
    AboutMe text,
    Views int,
    UpVotes int,
    DownVotes int,
    ProfileImageUrl text,
    Age int,
    AccountId int
);
COPY Users (Id, Reputation, CreationDate, DisplayName, LastAccessDate, WebsiteUrl, Location, AboutMe, Views, UpVotes, DownVotes, ProfileImageUrl, Age, AccountId) FROM stdin;
1	100	2014-01-21T20:26:05.043	Alice	\N	\N	\N	line1\nit's "great"	\N	5	\N	\N	\N	\N
2	\N	\N	Bob	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
\.

CREATE INDEX users_account_id_idx ON Users USING hash (AccountId);
CREATE INDEX users_display_name_idx ON Users USING hash (DisplayName);
CREATE INDEX users_up_votes_idx ON Users (UpVotes);
CREATE INDEX users_down_votes_idx ON Users (DownVotes);
CREATE INDEX users_creation_date_idx ON Users (CreationDate);
