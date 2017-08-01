#!/bin/sh

PUSH=$1
DATASETS=(dellstore iso3166 sportsdb usda world)

for DATASET in "${DATASETS[@]}"; do
  docker build -t aa8y/postgres-dataset:"$DATASET" --build-arg DATASETS="$DATASET" .
done
docker build -t aa8y/postgres-dataset:latest .

if [ "$PUSH" == "-p" ]; then
  for DATASET in "${DATASETS[@]}"; do
    docker push aa8y/postgres-dataset:"$DATASET"
  done
  docker push aa8y/postgres-dataset:latest
fi
