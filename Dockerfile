FROM postgres:9.6

MAINTAINER Arun Allamsetty <arun.allamsetty@gmail.com>

# Separate the installation as we can cache it as a layer.
RUN apt-get update && \
    apt-get install -y wget && \
    rm -rf /var/lib/apt/lists/*

ARG DATASET=world

# Source: http://pgfoundry.org/frs/?group_id=1000150
ARG DELLSTORE_FILENAME=dellstore2-normal-1.0
ARG DELLSTORE_URL=http://pgfoundry.org/frs/download.php/543/${DELLSTORE_FILENAME}.tar.gz
ARG USDA_FILENAME=usda-r18-1.0
ARG USDA_URL=http://pgfoundry.org/frs/download.php/555/${USDA_FILENAME}.tar.gz
ARG WORLD_FILENAME=world-1.0
ARG WORLD_URL=http://pgfoundry.org/frs/download.php/527/${WORLD_FILENAME}.tar.gz

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

ARG DATASET_URL=$DELLSTORE_URL
ARG DATASET_FILENAME=$DELLSTORE_FILENAME
ENV POSTGRES_USER docker
ENV POSTGRES_PASSWORD docker
ENV POSTGRES_DB docker

# Separate populating the database from installation as we want to separate the layer.
WORKDIR /tmp

RUN wget -qO- $DATASET_URL | tar -C . -xzf - && \
    cp ${DATASET_FILENAME}/${DATASET_FILENAME}.sql /docker-entrypoint-initdb.d/ && \
    rm -rf /tmp/*

ENTRYPOINT ["postgres"]
