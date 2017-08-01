PostgreSQL Dataset
==================

Docker image of a populated postgres database with sample tables and data.

You can start it by running:
```
docker run -d --name pg-ds-all aa8y/postgres-dataset:latest
docker exec -it pg-ds-all psql -d <dn_name>
```
where `<db_name>` is the database name. Possible values are `dellstore`, `iso3166`,  `sportsdb`, `usda` and `world`.
