#!/bin/sh

docker build -t aa8y/postgres-dataset:dellstore --build-arg DATASETS=dellstore .
docker build -t aa8y/postgres-dataset:iso3166 --build-arg DATASETS=iso3166 .
docker build -t aa8y/postgres-dataset:sportsdb --build-arg DATASETS=sportsdb .
docker build -t aa8y/postgres-dataset:usda --build-arg DATASETS=usda .
docker build -t aa8y/postgres-dataset:world --build-arg DATASETS=world .
docker build -t aa8y/postgres-dataset:latest .
