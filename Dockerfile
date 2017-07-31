FROM postgres:alpine

MAINTAINER Arun Allamsetty <arun.allamsetty@gmail.com>

# Separate the installation as we can cache it as a layer.
RUN apk add --update \
      bash \
      wget && \
    rm -rf /var/cache/apk/*

# Data Sources.
# PG Foundry: http://pgfoundry.org/frs/?group_id=1000150
# SportsDB:   http://www.sportsdb.org/sd/samples
ARG DATASETS=dellstore,iso3166,sportsdb,usda,world
ARG PG_USER=postgres
ARG PG_HOME=/home/$PG_USER

# Enable psql history.
RUN mkdir -p $PG_HOME && \
    touch $PG_HOME/.psql_history && \
    chown -R $PG_USER:$PG_USER $PG_HOME
ENV POSTGRES_USER docker
ENV POSTGRES_PASSWORD docker
ENV POSTGRES_DB $DATASET

# Set dataset parameters. Defaults to 'world'. Also, separate populating the database from
# installation as we want to separate the layer. `export` does not persist across images. So we
# need to make the conditional statements part of this layer.
WORKDIR /tmp
RUN bash -c ' \
    export ALL_DATASETS=(dellstore iso3166 sportsdb usda world) && \
    export SQL=( \
      dellstore2-normal-1.0/dellstore2-normal-1.0.sql \
      iso-3166/iso-3166.sql \
      sportsdb_sample_postgresql_20080304.sql \
      usda-r18-1.0/usda.sql \
      dbsamples-0.1/world/world.sql \
    ) && \
    export URL=( \
      http://pgfoundry.org/frs/download.php/543/dellstore2-normal-1.0.tar.gz \
      http://pgfoundry.org/frs/download.php/711/iso-3166-1.0.tar.gz \
      http://www.sportsdb.org/modules/sd/assets/downloads/sportsdb_sample_postgresql.zip \
      http://pgfoundry.org/frs/download.php/555/usda-r18-1.0.tar.gz \
      http://pgfoundry.org/frs/download.php/527/world-1.0.tar.gz \
    ) && \
    for i in "${!ALL_DATASETS[@]}"; do \
      export DATASET="${ALL_DATASETS[$i]}" && \
      export DATASET_URL="${URL[$i]}" && \
      export DATASET_SQL="${SQL[$i]}" && \
      if [[ $DATASETS == *"$DATASET"* ]]; then \
        echo "Populating dataset: ${DATASET}" && \
        if [ `echo $DATASET_URL | rev | cut -c-7 | rev` == .tar.gz ]; then \
          wget -qO- $DATASET_URL | tar -C . -xzf -; \
        else \
          wget $DATASET_URL -O tmp.zip && \
          unzip -d . tmp.zip; \
          rm tmp.zip; \
        fi && \
        echo "CREATE DATABASE $DATASET;" >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
        echo "\c $DATASET;" >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
        cat $DATASET_SQL >> "/docker-entrypoint-initdb.d/${DATASET}.sql" && \
        rm -rf *; \
      fi; \
    done'

USER $PG_USER
WORKDIR $PG_HOME
