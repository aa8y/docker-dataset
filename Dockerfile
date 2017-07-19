FROM postgres:alpine

MAINTAINER Arun Allamsetty <arun.allamsetty@gmail.com>

# Separate the installation as we can cache it as a layer.
RUN apk add --update wget && \
    rm -rf /var/cache/apk/*

# Data Sources.
# PG Foundry: http://pgfoundry.org/frs/?group_id=1000150
# SportsDB:   http://www.sportsdb.org/sd/samples
ARG DELLSTORE_URL=http://pgfoundry.org/frs/download.php/543/dellstore2-normal-1.0.tar.gz
ARG DELLSTORE_SQL=dellstore2-normal-1.0/dellstore2-normal-1.0.sql
ARG ISO3166_URL=http://pgfoundry.org/frs/download.php/711/iso-3166-1.0.tar.gz
ARG ISO3166_SQL=iso-3166/iso-3166.sql
ARG SPORTSDB_URL=http://www.sportsdb.org/modules/sd/assets/downloads/sportsdb_sample_postgresql.zip
ARG SPORTSDB_SQL=sportsdb_sample_postgresql_20080304.sql
ARG USDA_URL=http://pgfoundry.org/frs/download.php/555/usda-r18-1.0.tar.gz
ARG USDA_SQL=usda-r18-1.0/usda.sql
ARG WORLD_URL=http://pgfoundry.org/frs/download.php/527/world-1.0.tar.gz
ARG WORLD_SQL=dbsamples-0.1/world/world.sql

ARG PG_USER=postgres
ARG PG_HOME=/home/$PG_USER

# Enable psql history.
RUN mkdir -p $PG_HOME && \
    touch $PG_HOME/.psql_history && \
    chown -R $PG_USER:$PG_USER $PG_HOME

ARG DATASET=world
ENV POSTGRES_USER docker
ENV POSTGRES_PASSWORD docker
ENV POSTGRES_DB $DATASET

# Set dataset parameters. Defaults to 'world'. Also, separate populating the database from
# installation as we want to separate the layer. `export` does not persist across images. So we
# need to make the conditional statements part of this layer.
WORKDIR /tmp
RUN if [ $DATASET == "dellstore" ]; then \
      export DATASET_URL=$DELLSTORE_URL && \
      export DATASET_SQL=$DELLSTORE_SQL; \
    elif [ $DATASET == "iso3166" ]; then \
      export DATASET_URL=$ISO3166_URL && \
      export DATASET_SQL=$ISO3166_SQL; \
    elif [ $DATASET == "sportsdb" ]; then \
      export DATASET_URL=$SPORTSDB_URL && \
      export DATASET_SQL=$SPORTSDB_SQL; \
    elif [ $DATASET == "usda" ]; then \
      export DATASET_URL=$USDA_URL && \
      export DATASET_SQL=$USDA_SQL; \
    else \
      export DATASET_URL=$WORLD_URL && \
      export DATASET_SQL=$WORLD_SQL; \
    fi && \
    wget -qO- $DATASET_URL | \
      if [ `echo $DATASET_URL | rev | cut -c-7 | rev` == .tar.gz ]; then \
        tar -C . -xzf -; \
      else \
        unzip -d . -; \
      fi && \
    cp $DATASET_SQL /docker-entrypoint-initdb.d/ && \
    rm -rf *

USER $PG_USER
WORKDIR $PG_HOME
