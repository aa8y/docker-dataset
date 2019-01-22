FROM postgres:11-alpine

MAINTAINER Arun Allamsetty <arun.allamsetty@gmail.com>

ARG DATASETS=dellstore,iso3166,sportsdb,usda,world
ARG PG_USER=postgres
ARG PG_HOME=/home/$PG_USER
ENV POSTGRES_USER postgres
ENV POSTGRES_PASSWORD postgres
# Don't override this value. Do not use this value for `POSTGRES_USER`. We're making this change to
# to make sure the default database created by the `postgres` base image does not interfere with
# our database creation while populating data.
ENV POSTGRES_DB donotuse

# Enable psql history.
RUN mkdir -p $PG_HOME && \
    touch $PG_HOME/.psql_history && \
    chown -R $PG_USER:$PG_USER $PG_HOME

WORKDIR /tmp
# Data Sources.
# PG Foundry: http://pgfoundry.org/frs/?group_id=1000150
# SportsDB:   http://www.sportsdb.org/sd/samples
#
# `export` does not persist across images. So we need to make the conditional statements part of
# this layer.
RUN apk add --update \
      bash \
      ca-certificates \
      git \
      wget && \
    bash -c ' \
    declare -A SQL=( \
      [dellstore]="(dellstore2-normal-1.0/dellstore2-normal-1.0.sql)" \
      [iso3166]="(iso-3166/iso-3166.sql)" \
      [sportsdb]="(sportsdb_sample_postgresql_20080304.sql)" \
      [usda]="(usda-r18-1.0/usda.sql)" \
      [world]="(dbsamples-0.1/world/world.sql)" \
    ) && \
    declare -A URL=( \
      [dellstore]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/dellstore2/dellstore2-normal-1.0/dellstore2-normal-1.0.tar.gz \
      [iso3166]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/iso-3166/iso-3166-1.0/iso-3166-1.0.tar.gz \
      [sportsdb]=http://www.sportsdb.org/modules/sd/assets/downloads/sportsdb_sample_postgresql.zip \
      [usda]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/usda/usda-r18-1.0/usda-r18-1.0.tar.gz \
      [world]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/world/world-1.0/world-1.0.tar.gz \
    ) && \
    for DATASET in "${!SQL[@]}"; do \
      export DATASET_URL="${URL[$DATASET]}" && \
      declare -a DATASET_SQL="${SQL[$DATASET]}" && \
      if [[ $DATASETS == *"$DATASET"* ]]; then \
        echo "Populating dataset: ${DATASET}" && \
        if [[ $DATASET_URL == *.tar.gz ]]; then \
          wget -qO- $DATASET_URL | tar -C . -xzf -; \
        elif [[ $DATASET_URL == *.zip ]]; then \
          wget $DATASET_URL -O tmp.zip && \
          unzip -d . tmp.zip; \
          rm tmp.zip; \
        elif [[ $DATASET_URL == *.git ]]; then \
          git clone $DATASET_URL; \
        fi && \
        echo "CREATE DATABASE $DATASET;" >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
        echo "\c $DATASET;" >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
        for i in "${!DATASET_SQL[@]}"; do \
          cat "${DATASET_SQL[i]}" >> "/docker-entrypoint-initdb.d/${DATASET}.sql"; \
        done && \
        rm -rf *; \
      fi; \
    done' && \
    apk del --purge \
      bash \
      ca-certificates \
      git \
      wget && \
    rm -rf /var/cache/apk/*

USER $PG_USER
WORKDIR $PG_HOME
