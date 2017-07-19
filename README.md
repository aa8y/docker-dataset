PostgreSQL Dataset
==================

Docker image of a populated postgres database with sample tables and data.

You can start it by running:
```
docker run -d --name pgds aa8y/docker-pg-dataset:latest
docker exec -it pgds psql -d world
```
where `world` is the database name (it is the default).
