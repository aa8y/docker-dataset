#!/bin/sh
#
# Single-container supervisor for an aa8y/druid-dataset image.
#
# Apache Druid is a cluster of cooperating services, not one server process, and
# it has no DDL + INSERT/COPY load path: data enters through an ingestion task
# that writes immutable segments. So unlike the other server engines here --
# where the official entrypoint boots one process and runs *.sql against it --
# this script has to do three things:
#
#   1. bring up a whole single-node Druid (ZooKeeper + five services) from the
#      distribution's own bundled `nano-quickstart` profile,
#   2. submit the per-table ingestion specs the build shipped and wait until
#      every segment is published, loaded, *and* visible to SQL,
#   3. print one unmistakable ready marker and keep supervising.
#
# The marker is what the smoke test waits for (test/integration/run-druid.sh);
# nothing may print it before every datasource actually answers a query.
#
# Services are started the way the official apache/druid image starts them --
# `bin/run-java` (which supplies the --add-exports/--add-opens flags Java 17+
# needs) with the profile's own jvm.config and a `_common` + per-service
# classpath -- so what you know about that image still applies here. The one
# deliberate difference: where the official druid.sh rewrites runtime.properties
# files under /tmp/conf before launching, this passes the same settings as `-D`
# system properties, which Druid reads at higher precedence than the property
# files. That keeps the shipped conf/ pristine and this script short enough to
# read in one sitting.
#
# Logging. Druid's own log4j2 config already writes one rolling file per service
# (var/log/<service>.log); this only adds var/log/<service>.out for whatever the
# JVM prints before log4j is up (bad flags, OOM killer notices). `docker logs`
# is deliberately left to this script's own progress lines -- Druid emits
# thousands of startup lines per service, which would bury the ready marker --
# and any failure below dumps the tail of the log that explains it.
#
# Environment knobs (the first two mirror the official image):
#   DRUID_SINGLE_NODE_CONF   conf/druid/single-server profile to run
#                            (default nano-quickstart)
#   druid_*                  any Druid property, e.g.
#                            druid_processing_numThreads=2 ->
#                            -Ddruid.processing.numThreads=2. `__` escapes a
#                            literal underscore, exactly as in druid.sh. Values
#                            must not contain spaces (they are passed on the
#                            command line, not written to a file).
#   DRUID_INGEST_TIMEOUT     seconds allowed for all ingestion tasks (1800)
set -eu

DRUID_HOME=/opt/druid
cd "$DRUID_HOME"

CONF_PROFILE="${DRUID_SINGLE_NODE_CONF:-nano-quickstart}"
CONF="${DRUID_HOME}/conf/druid/single-server/${CONF_PROFILE}"
COMMON_CONF="${CONF}/_common"
DATASET_DIR="${DRUID_HOME}/dataset"
LOG_DIR="${DRUID_HOME}/var/log"

# Services, in start order, each with the port whose /status/health says it is
# up. The name is the profile's conf directory, which is also what this script
# calls a service everywhere (log files, node type, diagnostics).
SERVICES="coordinator-overlord:8081 historical:8083 middleManager:8091 broker:8082 router:8888"

# ... and the name `org.apache.druid.cli.Main server` knows it by, which differs
# for exactly one of them: the single-server profiles put the Coordinator and
# the Overlord in one JVM and one conf directory, but the CLI has no
# `coordinator-overlord` command -- `server coordinator` starts both, because
# the profile sets druid.coordinator.asOverlord.enabled. The official druid.sh
# maps the other way (service `coordinator` -> conf dir `coordinator-overlord`);
# same table, read from the other end.
svc_cli() {
  case "$1" in
    coordinator-overlord) echo coordinator ;;
    *)                    echo "$1" ;;
  esac
}
OVERLORD=http://localhost:8081
ROUTER=http://localhost:8888

say() { printf 'druid-dataset: %s\n' "$*"; }
warn() { printf 'druid-dataset: %s\n' "$*" >&2; }

# --- memory -----------------------------------------------------------------
# The stock nano-quickstart profile is sized for a 4 GB machine and, once the
# ingestion peon is counted, asks for ~1.9 GB of heap plus ~1.2 GB of direct
# memory -- more than a CI runner shard can spare next to a Docker daemon. These
# overrides cut that to ~1.2 GB heap + ~0.6 GB direct (plus one 256 MB peon
# while ingesting), which is what these datasets actually need: the largest is a
# few hundred thousand rows in a single segment.
#
# Direct memory is not a free knob: Druid refuses to start unless
# MaxDirectMemorySize >= (numMergeBuffers + numThreads + 1) * buffer.sizeBytes.
# With the processing settings below that is 4 * 25 MiB = 100 MiB, so every
# figure here keeps headroom over the minimum.
#
# Passed after the profile's own jvm.config on the command line, and HotSpot
# takes the last occurrence of -Xmx/-Xms/-XX:MaxDirectMemorySize, so these win
# without editing a single file.
svc_jvm() {
  case "$1" in
    coordinator-overlord) echo "-Xms256m -Xmx256m" ;;
    historical)           echo "-Xms384m -Xmx384m -XX:MaxDirectMemorySize=192m" ;;
    middleManager)        echo "-Xms64m -Xmx64m" ;;
    broker)               echo "-Xms256m -Xmx256m -XX:MaxDirectMemorySize=160m" ;;
    router)               echo "-Xms128m -Xmx128m -XX:MaxDirectMemorySize=128m" ;;
  esac
}

# The extensions to load, as a JSON array with no spaces (see common_props).
# dataset/loadList, when the build wrote one, names the extensions that
# dataset's ingestion needs; anything it names that the engine stage trimmed
# away is a build bug, so it is reported rather than silently dropped.
load_list() {
  list=""
  if [ -f "${DATASET_DIR}/loadList" ]; then
    for ext in $(cat "${DATASET_DIR}/loadList"); do
      if [ ! -d "${DRUID_HOME}/extensions/${ext}" ]; then
        warn "dataset needs extension ${ext}, which is not in this image"
        exit 1
      fi
      list="${list}${list:+,}\"${ext}\""
    done
  fi
  printf '[%s]' "$list"
}

# Properties applied to every Druid service. No value may contain a space: they
# are word-split deliberately so each becomes its own argv entry.
#
#   extensions.loadList  the profile's stock list names four extensions the
#                        build trimmed away (HDFS, Kafka, datasketches,
#                        Parquet); Druid fails to start on a missing extension,
#                        so the list is rebuilt from what the dataset asked for.
#   processing.*         pinned small, and pinned at all: numThreads defaults to
#                        (cores - 1), so on a 16-core host the broker would
#                        demand 17 * 50 MiB of direct memory and refuse to boot.
#   worker.capacity      one ingestion task at a time, so peak memory does not
#                        depend on how many tables a dataset has.
#   indexer.runner.*     the peon's JVM, sized like the services above. The
#                        middleManager passes every druid.* property it holds
#                        down to the peons it forks, so these reach them too.
common_props() {
  echo "-Ddruid.extensions.loadList=$(load_list)"
  echo "-Ddruid.processing.numThreads=1"
  echo "-Ddruid.processing.numMergeBuffers=2"
  echo "-Ddruid.processing.buffer.sizeBytes=25MiB"
  echo "-Ddruid.worker.capacity=1"
  echo '-Ddruid.indexer.runner.javaOptsArray=["-server","-Xms256m","-Xmx256m","-XX:MaxDirectMemorySize=160m","-Duser.timezone=UTC","-Dfile.encoding=UTF-8","-XX:+ExitOnOutOfMemoryError","-Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager"]'
}

# Druid properties from the environment, mirroring the official druid.sh:
# druid_a_b=c -> -Ddruid.a.b=c, with `__` escaping a literal underscore. The
# %UNDERSCORE% pivot is druid.sh's own, and avoids relying on `\n` in a sed
# replacement (BusyBox and GNU sed disagree about that).
env_props() {
  env | sed -n 's/^druid_//p' | while IFS= read -r kv; do
    key=$(printf '%s' "${kv%%=*}" |
          sed -e 's/__/%UNDERSCORE%/g' -e 's/_/./g' -e 's/%UNDERSCORE%/_/g')
    printf -- '-Ddruid.%s=%s\n' "$key" "${kv#*=}"
  done
}

# --- process supervision ----------------------------------------------------
NAMES=""

dump_log() {
  # dump_log <service> -- the tail of whatever that service last said, from
  # log4j's file and from the raw JVM output, whichever exist.
  for suffix in log out; do
    [ -s "${LOG_DIR}/$1.${suffix}" ] || continue
    warn "--- tail of var/log/$1.${suffix} ---"
    tail -40 "${LOG_DIR}/$1.${suffix}" >&2
  done
}

die() {
  # die <message> [service] -- report, dump that service's log, and stop.
  warn "$1"
  if [ $# -gt 1 ]; then dump_log "$2"; fi
  exit 1
}

# Forward SIGTERM (docker stop) to every child and wait for them, so nothing is
# killed mid-write.
#
# Note that six Druid JVMs do not all finish inside `docker stop`'s 10-second
# default grace period, so an ordinary `docker stop` still ends in SIGKILL and
# exit code 137 (measured). Nothing is lost when that happens -- var/ lives in
# the container and every dataset is re-ingested from the shipped specs on the
# next start -- but `docker stop -t 60` is the way to see a clean 143.
shutdown() {
  trap - TERM INT
  say "shutting down"
  for entry in $NAMES; do kill -TERM "${entry#*:}" 2>/dev/null || true; done
  for entry in $NAMES; do wait "${entry#*:}" 2>/dev/null || true; done
  exit 143
}
trap shutdown TERM INT

start() {
  # start <name> <command...> -- launch one JVM and remember its pid. The
  # redirect catches only what the JVM prints outside log4j; log4j itself
  # writes var/log/<name>.log (see -Ddruid.log.path below).
  name="$1"; shift
  "$@" >"${LOG_DIR}/${name}.out" 2>&1 &
  NAMES="${NAMES} ${name}:$!"
}

# check_children -- fail loudly the moment any supervised JVM exits. Called from
# every wait loop below, so a service that dies during startup (an unsatisfiable
# memory setting, a port clash) surfaces immediately with its own log rather
# than as an opaque readiness timeout minutes later.
check_children() {
  for entry in $NAMES; do
    kill -0 "${entry#*:}" 2>/dev/null && continue
    die "${entry%:*} exited unexpectedly" "${entry%:*}"
  done
}

poll() {
  # poll <seconds> <command...> -- run the command every second until it
  # succeeds, checking the children each time. Returns 1 on timeout.
  budget="$1"; shift
  deadline=$(( $(date +%s) + budget ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    check_children
    "$@" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

# --- boot -------------------------------------------------------------------
# The dirs every service expects to be able to write (the same set the official
# druid.sh creates), plus ZooKeeper's data dir and the log dir.
mkdir -p var/tmp var/log var/zk var/druid/segments var/druid/indexing-logs \
         var/druid/task var/druid/segment-cache var/druid/processing

[ -d "$CONF" ] || die "no such conf profile: ${CONF_PROFILE}"

EXTRA_PROPS="$(common_props) $(env_props)"

# ZooKeeper, from the distribution's own bundled jars -- the same class and
# config bin/run-zk uses. Druid needs it for service discovery and for handing
# tasks to the middleManager; running it in-container keeps the image to one
# process tree with no external dependency.
say "starting zookeeper"
start zookeeper bin/run-java -Xms128m -Xmx128m -Duser.timezone=UTC \
  "-Ddruid.log.path=${LOG_DIR}" -Dzookeeper.jmx.log4j.disable=true \
  -cp "lib/*:${DRUID_HOME}/conf/zk" \
  org.apache.zookeeper.server.quorum.QuorumPeerMain "${DRUID_HOME}/conf/zk/zoo.cfg"

for entry in $SERVICES; do
  svc="${entry%:*}"
  say "starting ${svc}"
  # shellcheck disable=SC2046  # deliberate word splitting: each flag is one argv entry
  start "$svc" bin/run-java $(xargs < "${CONF}/${svc}/jvm.config") \
    $(svc_jvm "$svc") $EXTRA_PROPS \
    "-Ddruid.node.type=${svc}" "-Ddruid.log.path=${LOG_DIR}" \
    -cp "${COMMON_CONF}:${CONF}/${svc}:lib/*" \
    org.apache.druid.cli.Main server "$(svc_cli "$svc")"
done

for entry in $SERVICES; do
  svc="${entry%:*}"; port="${entry#*:}"
  poll 300 curl -fsS "http://localhost:${port}/status/health" ||
    die "${svc} did not become healthy in 300s" "$svc"
done
say "cluster up"

# --- ingest -----------------------------------------------------------------
# One native batch task per table, submitted to the Overlord and polled to
# completion. Tasks are submitted up front and the Overlord queues them;
# druid.worker.capacity=1 means exactly one runs at a time, so peak memory is
# independent of how many tables the dataset has.
TASKS=""
DATASOURCES=""
for spec in "${DATASET_DIR}"/specs/*.json; do
  [ -e "$spec" ] || die "no ingestion specs in ${DATASET_DIR}/specs"
  table="$(basename "$spec" .json)"
  # The Overlord answers `{"task":"index_parallel_<table>_<suffix>"}`.
  id="$(curl -fsS -H 'Content-Type: application/json' \
          --data-binary "@${spec}" "${OVERLORD}/druid/indexer/v1/task" |
        sed -n 's/.*"task"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  [ -n "$id" ] || die "could not submit the ${table} ingestion task" coordinator-overlord
  TASKS="${TASKS} ${table}=${id}"
  DATASOURCES="${DATASOURCES} ${table}"
done
say "submitted $(set -- $TASKS; echo $#) ingestion task(s)"

# A task's status payload carries "statusCode":"RUNNING"|"SUCCESS"|"FAILED".
task_state() {
  curl -fsS "${OVERLORD}/druid/indexer/v1/task/$1/status" |
    sed -n 's/.*"statusCode"[[:space:]]*:[[:space:]]*"\([A-Z_]*\)".*/\1/p'
}

INGEST_TIMEOUT="${DRUID_INGEST_TIMEOUT:-1800}"
ingest_deadline=$(( $(date +%s) + INGEST_TIMEOUT ))
for task in $TASKS; do
  table="${task%%=*}"; id="${task#*=}"
  while :; do
    check_children
    state="$(task_state "$id" || true)"
    case "$state" in
      SUCCESS) say "ingested ${table}"; break ;;
      FAILED)
        warn "ingestion of ${table} FAILED (task ${id})"
        curl -fsS "${OVERLORD}/druid/indexer/v1/task/${id}/log" 2>/dev/null | tail -60 >&2
        exit 1 ;;
    esac
    [ "$(date +%s)" -lt "$ingest_deadline" ] ||
      die "ingestion of ${table} did not finish in ${INGEST_TIMEOUT}s (task ${id}, state ${state:-unknown})" \
          coordinator-overlord
    sleep 2
  done
done

# --- wait for the data to be queryable --------------------------------------
# A successful task means the segments were *published*, not that anyone can
# read them: the Coordinator still has to assign each one to the historical, the
# historical has to load it, and the broker has to notice. loadstatus reports
# the first two as a per-datasource percentage; the SQL check after it covers
# the third, and is the same query the smoke test runs.
loaded() {
  status="$(curl -fsS "${OVERLORD}/druid/coordinator/v1/loadstatus")" || return 1
  for ds in $DATASOURCES; do
    printf '%s' "$status" | grep -q "\"${ds}\"[[:space:]]*:[[:space:]]*100" || return 1
  done
}
poll 600 loaded || die "segments did not finish loading in 600s" historical

sql() {
  curl -fsS -H 'Content-Type: application/json' \
    --data-binary "{\"query\":$1}" "${ROUTER}/druid/v2/sql"
}
queryable() {
  tables="$(sql '"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '"'"'druid'"'"'"')" || return 1
  for ds in $DATASOURCES; do
    printf '%s' "$tables" | grep -q "\"${ds}\"" || return 1
  done
}
poll 300 queryable || die "datasources did not become queryable in 300s" broker

# The one line the smoke test waits for. Everything above must have succeeded
# for it to be printed.
say "${DATASET} ready ($(set -- $DATASOURCES; echo $#) datasources)"

# --- supervise --------------------------------------------------------------
# Stay in the foreground so the container lives, and take the whole container
# down if any service dies -- a half-dead Druid answers some queries and not
# others, which is worse than a restart.
#
# A trap only runs once the current foreground command returns, so this interval
# is also how long a `docker stop` waits before the shutdown handler above even
# starts -- keep it short.
while :; do
  check_children
  sleep 5
done
