#!/bin/sh
# Entrypoint for aa8y/mysql-dataset (Alpine MariaDB).
#
# On first start (empty /var/lib/mysql) it initialises the data directory,
# sets the root password, creates $MYSQL_DATABASE and imports every
# /docker-entrypoint-initdb.d/*.sql and *.sql.gz file. It then execs the
# server. Later starts skip initialisation.
#
# Supported variables: MYSQL_ROOT_PASSWORD (empty means generate one and print
# it) and MYSQL_DATABASE.
set -eu

DATADIR=/var/lib/mysql
INITDIR=/docker-entrypoint-initdb.d

# Double single quotes so the value is safe inside a SQL string literal.
# Backslash is also escaped, because it is an escape character by default.
sql_quote() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e "s/'/''/g"
}

# Stop the temporary server and empty the data directory that this init run
# created. Otherwise a later `docker start` sees $DATADIR/mysql, skips init,
# and serves a half-imported database.
abort_init() {
    echo "[e] $1" >&2
    if [ -n "${pid:-}" ]; then
        kill "$pid" 2> /dev/null || true
        wait "$pid" 2> /dev/null || true
    fi
    find "$DATADIR" -mindepth 1 -delete 2> /dev/null || true
    exit 1
}

mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld

if [ -d "$DATADIR/mysql" ]; then
    echo "[i] DB data directory already present, skipping creation"
    chown -R mysql:mysql "$DATADIR"
else
    echo "[i] DB data directory not found, creating initial DBs"
    chown -R mysql:mysql "$DATADIR"
    mariadb-install-db --user=mysql --datadir="$DATADIR" > /dev/null ||
        abort_init "mariadb-install-db failed"

    MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
    MYSQL_DATABASE="${MYSQL_DATABASE:-}"

    if [ -z "$MYSQL_ROOT_PASSWORD" ]; then
        MYSQL_ROOT_PASSWORD=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)
        echo "[i] Root Password: $MYSQL_ROOT_PASSWORD"
    fi
    pw=$(sql_quote "$MYSQL_ROOT_PASSWORD")

    tfile=$(mktemp)
    trap 'rm -f "$tfile"' EXIT
    cat > "$tfile" <<SQL
FLUSH PRIVILEGES;
ALTER USER 'root'@'localhost' IDENTIFIED BY '$pw';
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '$pw';
ALTER USER 'root'@'%' IDENTIFIED BY '$pw';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
DROP DATABASE IF EXISTS test;
FLUSH PRIVILEGES;
SQL
    if [ -n "$MYSQL_DATABASE" ]; then
        db=$(printf '%s' "$MYSQL_DATABASE" | sed 's/`/``/g')
        echo "[i] Creating database: $MYSQL_DATABASE"
        echo "[i] with character set: 'utf8' and collation: 'utf8_general_ci'"
        echo "CREATE DATABASE IF NOT EXISTS \`$db\` CHARACTER SET utf8 COLLATE utf8_general_ci;" >> "$tfile"
    fi

    mariadbd --user=mysql --bootstrap --verbose=0 --skip-name-resolve \
        --skip-networking=0 < "$tfile" || abort_init "Bootstrap SQL failed"
    rm -f "$tfile"
    trap - EXIT

    if [ -n "$MYSQL_DATABASE" ] && [ -n "$(ls -A "$INITDIR" 2>/dev/null)" ]; then
        echo
        echo "Preparing to process the contents of $INITDIR/"
        echo

        # Temporary server on the socket only (no TCP) for the import.
        mariadbd --user=mysql --skip-name-resolve --skip-networking &
        pid=$!

        # The password goes through the environment, not the command line.
        MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
        export MYSQL_PWD

        i=0
        until mariadb-admin --user=root ping --silent > /dev/null 2>&1; do
            i=$((i + 1))
            if [ "$i" -gt 300 ] || ! kill -0 "$pid" 2> /dev/null; then
                abort_init "Temporary server did not become ready"
            fi
            sleep 1
        done

        for f in "$INITDIR"/*; do
            case "$f" in
                *.sql)
                    echo "  $0: running $f"
                    mariadb --user=root "$MYSQL_DATABASE" < "$f" ||
                        abort_init "Import failed: $f"
                    ;;
                *.sql.gz)
                    echo "  $0: running $f"
                    gunzip -c "$f" | mariadb --user=root "$MYSQL_DATABASE" ||
                        abort_init "Import failed: $f"
                    ;;
            esac
        done

        mariadb-admin --user=root shutdown
        wait "$pid"
        unset MYSQL_PWD
        echo "Completed processing seed files."
    fi

    echo
    echo 'DB init process done. Ready for start up.'
    echo
fi

exec mariadbd --user=mysql --console --skip-name-resolve --skip-networking=0 "$@"
