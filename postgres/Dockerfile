FROM postgres:18-alpine

LABEL org.opencontainers.image.authors="https://github.com/aa8y" \
      org.opencontainers.image.description="PostgreSQL images pre-populated with sample datasets for practice and testing." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/aa8y/docker-dataset" \
      org.opencontainers.image.title="aa8y/postgres-dataset" \
      org.opencontainers.image.url="https://hub.docker.com/r/aa8y/postgres-dataset" \
      org.opencontainers.image.vendor="https://github.com/aa8y"

ARG DATASETS=adventureworks,dellstore,frenchtowns,iso3166,omdb,sportsdb,usda,world
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
COPY preprocess-adventureworks.rb /usr/local/lib/preprocess-adventureworks.rb

# Data Sources.
# PG Foundry: http://pgfoundry.org/frs/?group_id=1000150
# SportsDB:   https://github.com/yugabyte/yugabyte-db/tree/master/sample
#             (Yugabyte's mirror of the original SportsDB sample; the
#             upstream www.sportsdb.org download is no longer available.)
# OMDB:       https://github.com/df7cb/omdb-postgresql
#             (CSV data is fetched from www.omdb.org at build time and
#             shipped alongside the init script so psql \copy resolves it.)
# AdventureWorks:
#             https://github.com/lorint/AdventureWorks-for-Postgres
#             (CSVs come from Microsoft's AdventureWorks 2014 OLTP zip,
#             reformatted via the upstream Ruby script, and shipped next
#             to the init script.)
#
# `export` does not persist across images. So we need to make the conditional statements part of
# this layer.
RUN apk add --update \
      bash \
      bzip2 \
      ca-certificates \
      git \
      ruby \
      unzip \
      wget && \
    bash -c ' \
    declare -A SQL=( \
      [adventureworks]="(AdventureWorks-for-Postgres/install.sql)" \
      [dellstore]="(dellstore2-normal-1.0/dellstore2-normal-1.0.sql)" \
      [frenchtowns]="(french-towns-communes-francaises.sql)" \
      [iso3166]="(iso-3166/iso-3166.sql)" \
      [omdb]="(omdb-postgresql/00-drop-tables.sql omdb-postgresql/12-kind.sql omdb-postgresql/13-schema.sql omdb-postgresql/20-import.sql omdb-postgresql/30-duplicates.sql omdb-postgresql/31-primary-keys.sql omdb-postgresql/40-clean-orphans.sql omdb-postgresql/41-foreign-keys.sql omdb-postgresql/50-views.sql omdb-postgresql/52-category-en.sql omdb-postgresql/55-purge_dirty.sql omdb-postgresql/60-log.sql)" \
      [sportsdb]="(sportsdb_tables.sql sportsdb_inserts.sql sportsdb_indexes.sql sportsdb_constraints.sql sportsdb_fks.sql)" \
      [usda]="(usda-r18-1.0/usda.sql)" \
      [world]="(dbsamples-0.1/world/world.sql)" \
    ) && \
    declare -A URL=( \
      [adventureworks]=https://github.com/lorint/AdventureWorks-for-Postgres.git \
      [dellstore]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/dellstore2/dellstore2-normal-1.0/dellstore2-normal-1.0.tar.gz \
      [frenchtowns]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/french-towns-communes-francais/french-towns-communes-francaises-1.0/french-towns-communes-francaises-1.0.tar.gz \
      [iso3166]=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/iso-3166/iso-3166-1.0/iso-3166-1.0.tar.gz \
      [omdb]=https://github.com/df7cb/omdb-postgresql.git \
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
          if [[ "$DATASET" == "omdb" ]]; then \
            (cd omdb-postgresql && \
              ./download && \
              bunzip2 --force www.omdb.org/data/*.bz2 && \
              mkdir -p /docker-entrypoint-initdb.d/www.omdb.org && \
              mv www.omdb.org/data /docker-entrypoint-initdb.d/www.omdb.org/data); \
          elif [[ "$DATASET" == "adventureworks" ]]; then \
            (cd AdventureWorks-for-Postgres && \
              wget -q -O ms.zip https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks-oltp-install-script.zip && \
              unzip -q -o ms.zip && \
              rm ms.zip && \
              ruby /usr/local/lib/preprocess-adventureworks.rb && \
              mkdir -p /docker-entrypoint-initdb.d/adventureworks && \
              mv *.csv /docker-entrypoint-initdb.d/adventureworks/); \
          fi; \
        elif [[ $DATASET_URL == *.sql* ]]; then \
          for u in $DATASET_URL; do wget -q "$u"; done; \
        fi && \
        echo "CREATE DATABASE $DATASET;" >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
        echo "\c $DATASET;" >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
        if [[ "$DATASET" == "omdb" ]]; then \
          echo "CREATE EXTENSION IF NOT EXISTS tsm_system_rows;" >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
          echo "\cd /docker-entrypoint-initdb.d" >> "/docker-entrypoint-initdb.d/${DATASET}.sql"; \
        elif [[ "$DATASET" == "adventureworks" ]]; then \
          echo "\cd /docker-entrypoint-initdb.d/adventureworks" >> "/docker-entrypoint-initdb.d/${DATASET}.sql"; \
        fi && \
        for i in "${!DATASET_SQL[@]}"; do \
          cat "${DATASET_SQL[i]}" >> "/docker-entrypoint-initdb.d/${DATASET}.sql"; \
        done && \
        rm -rf *; \
      fi; \
    done' && \
    apk del --purge \
      bash \
      bzip2 \
      ca-certificates \
      git \
      ruby \
      unzip \
      wget && \
    rm -rf /var/cache/apk/* /usr/local/lib/preprocess-adventureworks.rb

USER $PG_USER
WORKDIR $PG_HOME
