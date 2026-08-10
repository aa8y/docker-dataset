# Dataset attribution and licenses

This repository's own contents — the Dockerfiles, transform hooks, manifest, and
tests — are [MIT licensed](../LICENSE) as *software and packaging*. That license
covers the packaging only: **every bundled dataset remains under its own upstream
license**, listed below. If you redistribute an image, the upstream terms for the
dataset it carries still apply to you.

Licenses marked *(verified)* were checked against the linked upstream on the date
shown. Where an upstream publishes no license statement, this file says
**See upstream** rather than guessing — check the source before relying on it.

## Stack Exchange attribution

The `stackexchange-*` images contain content from the
[Stack Exchange Network](https://stackexchange.com/), © Stack Exchange, Inc. and
its contributors, licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Attribution is
**required** by that license, and this file provides it for the data shipped in
these images. If you redistribute or publish derivations of that data you must
carry the same license, keep the attribution, and — for internet use — link back
to the original question on the source site (each post's `Id` resolves to
`https://<site>.stackexchange.com/questions/<Id>`).

## Sources

| Dataset(s) | Upstream source | License | Attribution / notes | Pinned or volatile |
| --- | --- | --- | --- | --- |
| `world`, `iso3166`, `frenchtowns`, `usda`, `dellstore` (all engines) | [pgFoundry dbsamples](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) on ftp.postgresql.org | See upstream — no license statement is published alongside the tarballs (checked 2026-08-09) | Historical PostgreSQL sample databases from the retired pgFoundry project, still mirrored on the PostgreSQL FTP site. | Pinned — versioned tarballs (`world-1.0`, `iso-3166-1.0`, `usda-r18-1.0`, `dellstore2-normal-1.0`, `french-towns-communes-francaises-1.0`). |
| `yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-pgexercises`, `yugabyte-sportsdb` / `sportsdb`, and the CockroachDB `chinook`, `northwind`, `pgexercises`, `sportsdb` built from the same dumps | [yugabyte/yugabyte-db `sample/`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | Apache-2.0 for the repository *(verified 2026-08-09)*. The separate `managed/` tree is Polyform Free Trial 1.0.0 and is not used here. | Yugabyte redistributes ports of third-party samples, each with its own origin: Chinook (see its own row below), `clubdata` from [PGExercises](https://pgexercises.com/) (site content is CC BY-SA 3.0; the dataset itself carries no separate statement — see upstream), Northwind from Microsoft's Access sample, and SportsDB from sportsdb.org (**see upstream** — the site no longer resolves as of 2026-08-09). | Volatile — fetched from an unpinned `master`. |
| `stackexchange-beer`, `-chess`, `-coffee`, `-cooking`, `-poker`, `-woodworking` (all engines) | [archive.org/download/stackexchange](https://archive.org/download/stackexchange) | **CC BY-SA 4.0** *(verified 2026-08-09)* | **Attribution required** — see [Stack Exchange attribution](#stack-exchange-attribution) above. © Stack Exchange, Inc. and contributors. Derivative use must remain under CC BY-SA 4.0. | Volatile — archive.org publishes new dumps periodically; the build tracks the current dump and fingerprints it via archive.org's metadata API. |
| `moma` (all engines) | [MuseumofModernArt/collection](https://github.com/MuseumofModernArt/collection) | CC0 1.0 *(verified 2026-08-09)* | Public-domain dedication. MoMA nonetheless asks to be acknowledged where possible and asks that modified data be marked as changed — the schema here is authored in-repo and the CSVs are loaded unmodified. Row counts are recorded as floors because MoMA refreshes its exports. | Volatile — CSVs pulled from the unpinned `main` branch; floor counts drift upward. |
| `chinook` (MySQL, SQLite) | [lerocha/chinook-database](https://github.com/lerocha/chinook-database) | MIT *(verified 2026-08-09)* | Copyright (c) 2008-2024 Luis Rocha. | Pinned — release `v1.4.5` (`Chinook_MySql.sql`, `Chinook_Sqlite.sql`). |
| `sakila` (MySQL) | [MySQL Sakila](https://dev.mysql.com/doc/sakila/en/), `downloads.mysql.com/docs/sakila-db.tar.gz` | New BSD *(verified 2026-08-09)* | Oracle licenses `sakila-schema.sql` and `sakila-data.sql` under the New BSD license; the accompanying documentation is **not** open-licensed and is not redistributed in these images. | Stable — unversioned but long-lived download URL. |
| `world` (MySQL) | [MySQL world](https://dev.mysql.com/doc/world-setup/en/), `downloads.mysql.com/docs/world-db.tar.gz` | See upstream — Oracle publishes no explicit license for the world sample files (checked 2026-08-09) | © Oracle. Distinct from the pgFoundry `world` used by the other engines, though row counts match. | Stable — unversioned but long-lived download URL. |
| `airlines` (PostgreSQL, SQLite) | [postgrespro demo database](https://postgrespro.com/community/demodb) | MIT *(verified 2026-08-09)* | Postgres Professional's flight-bookings demo database. The SQLite tag is built from the same dump, hand-translated at build time (views dropped, `jsonb` shipped as JSON text). | Pinned — snapshot `demo-20250901-3m`. If postgrespro retires the file the URL needs bumping. |
| `adventureworks` (PostgreSQL) | [lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres), which pulls Microsoft's [AdventureWorks OLTP script](https://github.com/microsoft/sql-server-samples) | MIT for the PostgreSQL port *(verified 2026-08-09)*; MIT for microsoft/sql-server-samples *(verified 2026-08-09)* | AdventureWorks is a Microsoft SQL Server sample; the port reformats Microsoft's CSV bundle for PostgreSQL at build time. | Volatile — the port is cloned from its default branch; Microsoft's release asset is a stable download. |
| `omdb` (PostgreSQL) | [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql), data from [omdb.org](https://www.omdb.org/) | GPL-2.0-or-later for the import scripts *(verified 2026-08-09)*; the omdb.org data is CC BY 2.0 DE *(verified 2026-08-09)* | The GPL covers df7cb's loader tooling, not the movie data; the data requires attribution to omdb.org. | Volatile — repo cloned from its default branch and CSVs fetched live from omdb.org at build time (counts recorded as floors). |
| `pagila` (PostgreSQL) | [devrimgunduz/pagila](https://github.com/devrimgunduz/pagila) | PostgreSQL License *(verified 2026-08-09)* | A PostgreSQL port of MySQL's Sakila; upstream states "The pagila database is made available under PostgreSQL license." | Volatile — cloned from its default branch; upstream periodically shifts sample dates to the current year. |
| `northwind` (MySQL) | [dalers/mywind](https://github.com/dalers/mywind) | BSD-2-Clause *(verified 2026-08-09)* | A MySQL port of Microsoft's Access Northwind sample. | Volatile — cloned from its default branch. |
| `northwind` (SQLite) | [jpwhite3/northwind-SQLite3](https://github.com/jpwhite3/northwind-SQLite3) | MIT *(verified 2026-08-09)* | The prebuilt `dist/northwind.db` is shipped as-is; it is the port's *expanded* edition, so `Orders` / `"Order Details"` are much larger than the classic sample. | Volatile — fetched from the unpinned `main` branch. |
| `sakila` (SQLite) | [bradleygrant/sakila-sqlite3](https://github.com/bradleygrant/sakila-sqlite3) | BSD-3-Clause for the repository *(verified 2026-08-09)*; the database definition files remain under MySQL Sakila's New BSD license | The prebuilt `sakila_master.db` is shipped as-is. See the MySQL `sakila` row for the original upstream. | Volatile — fetched from the unpinned `main` branch. |

## Corrections

If any license above is wrong or out of date, or an upstream wants different
attribution, please open an issue at
[aa8y/docker-dataset](https://github.com/aa8y/docker-dataset/issues).
