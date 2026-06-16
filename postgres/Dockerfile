FROM postgres:18-alpine

LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="PostgreSQL images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/postgres-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/postgres-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASETS=dellstore,frenchtowns,iso3166,sportsdb,usda,world
ARG PG_USER=postgres
ARG PG_HOME=/home/$PG_USER
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
# Don't override this value. Do not use this value for `POSTGRES_USER`. We're making this change to
# to make sure the default database created by the `postgres` base image does not interfere with
# our database creation while populating data.
ENV POSTGRES_DB=donotuse

# Enable psql history.
RUN mkdir -p $PG_HOME && \
    touch $PG_HOME/.psql_history && \
    chown -R $PG_USER:$PG_USER $PG_HOME

WORKDIR /tmp
# Data Sources.
# PG Foundry: http://pgfoundry.org/frs/?group_id=1000150
# SportsDB:   https://github.com/yugabyte/yugabyte-db/tree/master/sample
#             (Yugabyte's mirror of the original SportsDB sample; the
#             upstream www.sportsdb.org download is no longer available.)
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
      [frenchtowns]="(french-towns-communes-francaises.sql)" \
      [iso3166]="(iso-3166/iso-3166.sql)" \
      [sportsdb]="(sportsdb_tables.sql sportsdb_inserts.sql sportsdb_indexes.sql sportsdb_constraints.sql sportsdb_fks.sql)" \
      [usda]="(usda-r18-1.0/usda.sql)" \
      [world]="(dbsamples-0.1/world/world.sql)" \
    ) && \
    declare -A URL=( \
      [dellstore]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/dellstore2/dellstore2-normal-1.0/dellstore2-normal-1.0.tar.gz \
      [frenchtowns]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/french-towns-communes-francais/french-towns-communes-francaises-1.0/french-towns-communes-francaises-1.0.tar.gz \
      [iso3166]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/iso-3166/iso-3166-1.0/iso-3166-1.0.tar.gz \
      [sportsdb]="https://raw.githubusercontent.com/yugabyte/yugabyte-db/master/sample/sportsdb_tables.sql https://raw.githubusercontent.com/yugabyte/yugabyte-db/master/sample/sportsdb_inserts.sql https://raw.githubusercontent.com/yugabyte/yugabyte-db/master/sample/sportsdb_indexes.sql https://raw.githubusercontent.com/yugabyte/yugabyte-db/master/sample/sportsdb_constraints.sql https://raw.githubusercontent.com/yugabyte/yugabyte-db/master/sample/sportsdb_fks.sql" \
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
        elif [[ $DATASET_URL == *.sql* ]]; then \
          for u in $DATASET_URL; do wget -q "$u"; done; \
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
