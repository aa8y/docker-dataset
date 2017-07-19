FROM postgres:9.6

MAINTAINER Arun Allamsetty <arun.allamsetty@gmail.com>

# Separate the installation as we can cache it as a layer.
RUN apt-get update && \
    apt-get install -y wget && \
    rm -rf /var/lib/apt/lists/*

# Source: http://pgfoundry.org/frs/?group_id=1000150
ARG DELLSTORE_URL=http://pgfoundry.org/frs/download.php/543/dellstore2-normal-1.0.tar.gz
ARG DELLSTORE_SQL=dellstore2-normal-1.0/dellstore2-normal-1.0.sql
ARG USDA_URL=http://pgfoundry.org/frs/download.php/555/usda-r18-1.0.tar.gz
ARG USDA_SQL=usda-r18-1.0/usda.sql
ARG WORLD_URL=http://pgfoundry.org/frs/download.php/527/world-1.0.tar.gz
ARG WORLD_SQL=dbsamples-0.1/world/world.sql

RUN mkdir -p /home/postgres && \
    touch /home/postgres/.psql_history && \
    chown -R postgres:postgres /home/postgres

ARG DATASET=world
ARG DATASET_URL=$WORLD_URL
ARG DATASET_SQL=$WORLD_SQL

# Set dataset parameters. Defaults to 'world'.
# RUN if [ $DATASET=="dellstore2" ]; then \
#       export DATASET_URL=$DELLSTORE_URL && \
#       export DATASET_FILENAME=$DELLSTORE_FILENAME; \
#     elif [ $DATASET=="usda" ]; then \
#       export DATASET_URL=$USDA_URL && \
#       export DATASET_FILENAME=$USDA_FILENAME; \
#     else \
#       echo $WORLD_URL && \
#       export DATASET_URL=$WORLD_URL && \
#       export DATASET_FILENAME=$WORLD_FILENAME; \
#     fi

ENV POSTGRES_USER docker
ENV POSTGRES_PASSWORD docker
ENV POSTGRES_DB $DATASET

# Separate populating the database from installation as we want to separate the layer.
WORKDIR /tmp
RUN wget -qO- $DATASET_URL | tar -C . -xzf - && \
    cp $DATASET_SQL /docker-entrypoint-initdb.d/ && \
    rm -rf *
