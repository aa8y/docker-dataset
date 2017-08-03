#!/bin/sh

PUSH=$1

# Datasets
DATASETS=(dellstore iso3166 pagila sportsdb usda world)
# Non-dataset tags
TAGS=(all latest)

# Build images for pushing/use.
# Images with single datasets and hence dataset-specific tags.
for DATASET in "${DATASETS[@]}"; do
  docker build -t aa8y/postgres-dataset:"$DATASET" --build-arg DATASETS="$DATASET" .
done
# Images with all datasets and hence non-dataset-specific tags.
for TAG in "${TAGS[@]}"; do
  docker build -t aa8y/postgres-dataset:"$TAG" .
done

# Update TAGS to contain all tags.
for TAG in "${DATASETS[@]}"; do
  TAGS+=($TAG)
done
# If the push flag is set, push all tags.
if [ "$PUSH" == "-p" ]; then
  for TAG in "${TAGS[@]}"; do
    docker push aa8y/postgres-dataset:"$TAG"
  done
fi
