

# Docker Dataset

[![CI](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/aa8y/docker-dataset/actions/workflows/ci.yml)

**Bases de datos de ejemplo pre pobladas como imágenes de Docker** — contenedores listos para ejecutar [PostgreSQL](https://www.postgresql.org/), [MySQL](https://www.mysql.com/), [CockroachDB](https://www.cockroachlabs.com/) y [SQLite](https://www.sqlite.org/) cargados con datos de ejemplo reales y válidos (Chinook, Northwind, Sakila/Pagila, World, AdventureWorks, Stack Exchange y más).

¿Necesitabas alguna vez una base de datos ya poblada con datos válidos — para practicar SQL, ejecutar pruebas, hacer una demo de una aplicación o realizar un benchmark — sin tener que crear filas a mano o buscar un volcado utilizable? Cada imagen entrega exactamente un conjunto de datos en su propia base de datos, por lo que solo tienes que ejecutar `docker run` y conectar.

## Contenido

* [Matriz de soporte de conjuntos de datos](#dataset-support-matrix)
* [Bases de datos](#databases)
* [Imágenes de PostgreSQL](#postgresql-images)
* [Imágenes de MySQL](#mysql-images)
* [Imágenes de CockroachDB](#cockroachdb-images)
* [Imágenes de SQLite](#sqlite-images)
* [Uso](#usage)
* [Imágenes personalizadas](#custom-images)
* [Pruebas](#testing)
* [Caché de compilación](#build-caching)
* [Trabajos Futuros](#future-work)

## Matriz de soporte de conjuntos de datos

Cada celda contiene la etiqueta de imagen para extraer (`pull`) ese conjunto de datos en ese motor; **—** significa que no se distribuye allí (aún). El nombre del conjunto de datos enlaza a su fuente original cuando todos los motores lo extraen del mismo lugar; cuando los motores usan fuentes distintas, el enlace a la fuente se coloca en la etiqueta individual en su lugar. Todas las imágenes se publican para `linux/amd64` y `linux/arm64`.

| Conjunto de datos | [PostgreSQL](#postgresql-images) | [MySQL](#mysql-images) | [CockroachDB](#cockroachdb-images) | [SQLite](#sqlite-images) |
| --- | --- | --- | --- | --- |
| [AdventureWorks](https://github.com/lorint/AdventureWorks-for-Postgres) | `adventureworks` | — | — | — |
| [Airlines](https://postgrespro.com/education/demodb) | `airlines` | — | — | — |
| Chinook | [`yugabyte-chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) | [`chinook`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`chinook`](https://github.com/lerocha/chinook-database) |
| [Dell DVD Store](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `dellstore` | `dellstore` | `dellstore` | `dellstore` |
| [French Towns](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `frenchtowns` | `frenchtowns` | `frenchtowns` | `frenchtowns` |
| [ISO 3166](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `iso3166` | `iso3166` | `iso3166` | `iso3166` |
| [MoMA](https://github.com/MuseumofModernArt/collection) | `moma` | `moma` | `moma` | `moma` |
| Northwind | [`yugabyte-northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/dalers/mywind) | [`northwind`](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | [`northwind`](https://github.com/jpwhite3/northwind-SQLite3) |
| [OMDb](https://github.com/df7cb/omdb-postgresql) | `omdb` | — | — | — |
| [PGExercises](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `yugabyte-pgexercises` | `pgexercises` | `pgexercises` | `pgexercises` |
| Sakila / Pagila | [`pagila`](https://github.com/devrimgunduz/pagila) | [`sakila`](https://dev.mysql.com/doc/sakila/en/) | — | [`sakila`](https://github.com/bradleygrant/sakila-sqlite3) |
| [SportsDB](https://github.com/yugabyte/yugabyte-db/tree/master/sample) | `sportsdb`, `yugabyte-sportsdb` | `sportsdb` | `sportsdb` | `sportsdb` |
| [Stack Exchange](https://archive.org/details/stackexchange)¹ | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` | `stackexchange-<site>` |
| [USDA](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | `usda` | `usda` | `usda` | `usda` |
| World | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://dev.mysql.com/doc/world-setup/en/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) | [`world`](https://www.postgresql.org/ftp/projects/pgFoundry/dbsamples/) |

¹ `<site>` es uno de `beer`, `coffee`, `poker`, `woodworking`, `chess`, `cooking` (p. ej. `stackexchange-chess`).

Cada motor también publica una etiqueta `latest`: sigue a `world` en PostgreSQL y MySQL, y a `chinook` en CockroachDB y SQLite.

## Bases de datos

Actualmente se soportan cuatro motores de bases de datos, cada uno publicado como su propio repositorio de imágenes. [ClickHouse](https://clickhouse.com/), [DuckDB](https://duckdb.org/), [Apache Druid](https://druid.apache.org/) y [Apache Pinot](https://pinot.apache.org/) están planificados — consulte [Trabajos Futuros](#future-work).

* [PostgreSQL](https://www.postgresql.org/) como [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset). Usamos la versión `alpine` de la imagen oficial como imagen base para mantener nuestra imagen ligera.
* [MySQL](https://www.mysql.com/) como [`aa8y/mysql-dataset`](https://hub.docker.com/r/aa8y/mysql-dataset). No existe una imagen oficial de Alpine para Oracle MySQL (la imagen oficial `mysql` se basa en Oracle Linux / Debian) y los propios repositorios de paquetes de Alpine distribuyen [MariaDB](https://mariadb.org/) en lugar de MySQL, por lo que, para mantener el objetivo de "ligera y basada en Alpine", compilamos sobre la imagen comunitaria [`yobasystems/alpine-mariadb`](https://hub.docker.com/r/yobasystems/alpine-mariadb). MariaDB es el sustituto de MySQL para Alpine, y su punto de entrada cumple con las mismas variables de entorno `MYSQL_*` y la convención `/docker-entrypoint-initdb.d/*.sql` que la imagen oficial de PostgreSQL, por lo que el patrón de conjuntos de datos se mantiene sin cambios.
* [CockroachDB](https://www.cockroachlabs.com/) como [`aa8y/cockroach-dataset`](https://hub.docker.com/r/aa8y/cockroach-dataset). No existe una imagen oficial de Alpine (la imagen oficial [`cockroachdb/cockroach`](https://hub.docker.com/r/cockroachdb/cockroach) es UBI-minimal), pero es ligera (~170 MB) y multiarquitectura, y su punto de entrada cumple la misma convención `/docker-entrypoint-initdb.d/*.sql` que la imagen oficial de PostgreSQL (más la variable de entorno `COCKROACH_DATABASE`) cuando el contenedor se inicia con `start-single-node`. CockroachDB es compatible a nivel de cable y SQL con PostgreSQL, por lo que el patrón de conjuntos de datos se mantiene y estos reutilizan los mismos volcados de ejemplo del dialecto PostgreSQL.
* [SQLite](https://www.sqlite.org/) como [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset). SQLite es sin servidor — una base de datos es solo un archivo — por lo que no hay servidor que iniciar ni scripts de inicialización; la compilación ensambla el archivo de base de datos y la imagen lo distribuye. Usamos la imagen Alpine, vinculada estáticamente [`keinos/sqlite3`](https://hub.docker.com/r/keinos/sqlite3) (multiarquitectura) como base, manteniendo la imagen genuinamente ligera y basada en Alpine.

## Imágenes de PostgreSQL

Las imágenes originales: cada imagen [`aa8y/postgres-dataset`](https://hub.docker.com/r/aa8y/postgres-dataset) contiene exactamente un conjunto de datos, cargado en una base de datos con el nombre del conjunto, y se compila mediante un [Dockerfile](postgres/Dockerfile) de Extracción -> Transformación -> Carga impulsado por `manifest.yml`. (Las fuentes están en la [matriz](#dataset-support-matrix); las notas a continuación son específicas de PostgreSQL.)

* `yugabyte-chinook` (bd `chinook`): 11 tablas en el esquema `public`, identificadores en CamelCase entre comillas (p. ej. `"Track"`, `"InvoiceLine"`).
* `yugabyte-pgexercises` (bd `pgexercises`): 3 tablas en un esquema dedicado `cd` (no `public`).
* `sportsdb` / `yugabyte-sportsdb`: se crean las 107 tablas, pero solo las tablas de infraestructura genérica más las de fútbol americano, béisbol, baloncesto y hockey sobre hielo contienen datos — automovilismo, fútbol, tenis, apuestas y clima son solo esquema.
* `pagila`: la tabla `payment` está particionada por rango mensual (`payment_p2022_NN`), por lo que las cuentas de filas se dividen entre la tabla padre y sus particiones; la fuente original cambia periódicamente las fechas de ejemplo al año actual, por lo que las fechas absolutas cambian entre recompilaciones.
* `omdb`: los CSV se obtienen en tiempo de compilación y se incluyen en la imagen para que `\copy` se resuelva al inicio; el script de inicialización crea la extensión `tsm_system_rows` en la que dependen las vistas de la fuente original. Pesado (~150 MB de CSV + índices).
* `adventureworks`: la portabilidad de la fuente extrae el paquete CSV de Microsoft y ejecuta un reformateo en Python antes de cargar (68 tablas en 5 esquemas). Pesado (~90 MB de CSV).
* `airlines`: 9 tablas en un esquema `bookings` (`search_path` lo toma como predeterminado). La fuente original distribuye un único `pg_dump` comprimido en gzip de su propia base de datos `demo`, por lo que la compilación lo descomprime y elimina las directivas `DROP/CREATE DATABASE` / `\connect` para que se cargue en la base de datos `airlines`. El conjunto de datos más pesado (varios millones de filas en línea); la URL de instantánea tiene marca de tiempo y puede necesitar actualización si postgrespro retira el archivo fijado.
* `moma`: MoMA solo distribuye CSV/JSON, por lo que el esquema se escribe en el repositorio (`postgres/scripts/moma/schema.sql`, cada columna `text`) y los CSV se distribuyen junto con el script de inicialización; las cuentas fluctúan a medida que MoMA actualiza sus exportaciones (registradas como límites mínimos).
* `stackexchange-<site>` (bd = nombre simple del sitio): el volcado solo distribuye XML por tabla, por lo que un gancho de compilación compartido (`postgres/scripts/stackexchange/transform`) lo convierte a `CREATE TABLE` + `COPY` en línea + índices en tiempo de compilación (8 tablas en `public`). Cada sitio comparte un esquema y se compila a través de ese gancho, por lo que agregar un sitio es solo otra etiqueta; las cuentas se registran como límites mínimos. `cooking` es el más grande (~500k votos, ~230k filas de historial de publicaciones).

### Nomenclatura de etiquetas

La base de datos dentro de cada imagen es el nombre simple del conjunto de datos: la etiqueta menos cualquier prefijo `yugabyte-`/`stackexchange-`. Esos prefijos de fuente existen para que un conjunto de datos pueda distribuirse desde un segundo espejo en el futuro; `sportsdb` y `yugabyte-sportsdb` son la misma imagen hoy, con el `sportsdb` sin prefijo mantenido como un alias compatible con versiones anteriores.

### Historial

Ya no existe la imagen `all` de múltiples conjuntos de datos: cada imagen es un conjunto; para usar varios a la vez, ejecute un contenedor por conjunto (p. ej. mediante `docker-compose`). `pagila` fue [eliminada en 2019](https://github.com/aa8y/docker-dataset/issues/1) debido a una ruptura en la fuente original y ha vuelto como una etiqueta regular, ya que el [fork](https://github.com/devrimgunduz/pagila) se carga correctamente en PostgreSQL moderno y un conjunto ya no puede romper a los demás.

## Imágenes de MySQL

Las imágenes de MySQL reflejan las de PostgreSQL: un conjunto por imagen, mismo [Dockerfile](mysql/Dockerfile) ETL impulsado por `manifest.yml`. El motor es MariaDB (consulte [Bases de datos](#databases) para saber por qué); es compatible a nivel de cable y SQL con MySQL para estas muestras. Dado que cada imagen contiene un único conjunto de datos, la compilación elimina cualquier DDL a nivel de base de datos que distribuya el volcado original (`CREATE`/`DROP DATABASE`/`SCHEMA`, `USE`) y carga todo en una única base de datos con el nombre del conjunto.

Inicie un contenedor y conéctese con el cliente `mariadb` (compatible con MySQL):
```
docker run -d --name my-ds-<tag> aa8y/mysql-dataset:<tag>
docker exec -it my-ds-<tag> mariadb -uroot -pmysql <db_name>
```
donde `<tag>` es una de las etiquetas en la columna de MySQL de la [matriz](#dataset-support-matrix) y `<db_name>` es el nombre del conjunto de datos correspondiente (la etiqueta en sí, menos cualquier prefijo `stackexchange-`). La contraseña de root es `mysql`.

### Conjuntos de datos de MySQL

Fuentes nativas de MySQL, usadas directamente (fuentes en la [matriz](#dataset-support-matrix); las notas a continuación son específicas de MySQL):

* `sakila`: sustituye a `pagila` de PostgreSQL (que es en sí un puerto de Sakila); 16 tablas base. `film_text` se pobla mediante un disparador `AFTER INSERT` en `film` en lugar de con datos en lote, y a diferencia de `pagila`, la tabla `payment` no está particionada.
* `world`: `world` nativo de MySQL — `city`, `country`, `countrylanguage` (3 tablas), con cuentas de filas idénticas al `world` de PostgreSQL.
* `chinook`: el `Chinook_MySql.sql` específico de MySQL del proveedor (versión `v1.4.5`); identificadores en CamelCase (p. ej. `` `Track` ``), con el `CREATE DATABASE Chinook` del script eliminado para que se cargue en la base de datos `chinook` en minúsculas.
* `northwind`: el puerto dalers/mywind del ejemplo de Access de Microsoft (snake_case, 20 tablas) — una conversión más grande que el `yugabyte-northwind` de PostgreSQL de 14 tablas.
* `moma`: esquema escrito en el repositorio (`mysql/scripts/moma/schema.sql`, cada columna `text`); CSV cargados en lote al inicio con `LOAD DATA INFILE` del lado del servidor. Las cuentas fluctúan a medida que MoMA actualiza sus exportaciones (registradas como límites mínimos).
* `stackexchange-<site>`: XML por tabla convertido en tiempo de compilación por un gancho compartido (`mysql/scripts/stackexchange`) a `CREATE TABLE` + `INSERT`s por lotes + índices (identificadores en CamelCase). Mapea `int`/`timestamp`/`text` de PostgreSQL a `INT`/`DATETIME(6)`/`MEDIUMTEXT` y agrega una longitud de prefijo de clave a los índices de columnas de texto (MySQL no puede indexar un `TEXT` completo). `cooking` es el más grande; las cuentas se registran como límites mínimos.

Los conjuntos de datos restantes no tienen fuente nativa de MySQL, pero sus volcados de PostgreSQL son DDL + datos simples, por lo que se traducen manualmente en tiempo de compilación a través de un gancho de transformación compartido `mysql/scripts/pgsql`. Convierte bloques `COPY` a `INSERT`s por lotes, reescribe los tipos de PostgreSQL a sus equivalentes de MySQL (`character varying`→`varchar`, `timestamp`→`datetime`, `double precision`→`double`, `numeric` sin adornos→`decimal`, y `text`→`varchar(255)` para que una columna de texto pueda servir como clave, lo cual MySQL prohíbe para `TEXT`), elimina el ruido exclusivo de PostgreSQL (secuencias, `OWNER TO`, `GRANT`/`REVOKE`, `USING btree`/`hash`/`lsm`, calificadores de esquema), convierte identificadores de tablas a minúsculas, transcodifica volcados Latin-1 a UTF-8 y elimina cualquier función almacenada PL/pgSQL (sin traducción mecánica a MySQL: el esquema y todos los datos aún se cargan). Las cuentas de filas coinciden exactamente con los conjuntos de PostgreSQL.

* `iso3166`: la clave primaria de país `two_letter` (referenciada por `subcountry`) se convierte en `varchar` para que pueda ser una clave.
* `frenchtowns`: el volcado declara tablas en CamelCase pero carga en minúsculas, lo que el gancho reconcilia convirtiendo los nombres de tabla a minúsculas; los nombres de comunas con acentos se mantienen (la fuente es UTF-8).
* `usda`: el archivo tar de pgFoundry es Latin-1, por lo que el gancho lo transcodifica a UTF-8 antes de cargar.
* `pgexercises`: la fuente original vive en un esquema dedicado `cd`; el gancho elimina el calificador `cd.` para que se cargue en la única base de datos `pgexercises`.
* `sportsdb`: además de las correcciones habituales, el gancho elimina el método de acceso a índice `USING lsm` de Yugabyte y un `CREATE DOMAIN` no utilizado; las 96 restricciones únicas y 137 claves foráneas sobreviven la traducción.
* `dellstore`: el volcado distribuye una función PL/pgSQL `new_customer` (un auxiliar de aplicación no utilizado); el gancho la elimina — el esquema, las claves y todos los datos aún se cargan.

### Conjuntos de datos no portados a MySQL

Los conjuntos de datos restantes de PostgreSQL provienen de fuentes exclusivas de PostgreSQL o dependen de características específicas de PostgreSQL (PL/pgSQL, extensiones, internos de `pg_dump`) que no se pueden traducir manualmente sin divergir del conjunto original. Los volcados simples de DDL + datos en su lugar se traducen manualmente (consulte el grupo anterior); estos son los que permanecen exclusivos de PostgreSQL:

* `pagila`: no omitida sino *reemplazada* — `pagila` es un puerto de Sakila a PostgreSQL, y MySQL usa el Sakila original directamente (etiqueta `sakila`, arriba).
* `adventureworks`: el único puerto abierto mantenido ([lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres)) apunta a PostgreSQL. AdventureWorks es un ejemplo de Microsoft SQL Server sin un puerto compatible y mantenido para MySQL, y su compilación depende de un reformateo en Python más múltiples esquemas y vistas materializadas — demasiado mecanismo específico de PostgreSQL para traducir manualmente con fidelidad.
* `airlines`: la [demo de postgrespro](https://postgrespro.com/education/demodb) se distribuye como un `pg_dump` de PostgreSQL casi binario y depende de características de PostgreSQL (`jsonb`, varios millones de filas en línea); es exclusivo de PostgreSQL.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) es específico de PostgreSQL — sus vistas dependen de la extensión `tsm_system_rows` (sin equivalente en MySQL), por lo que un puerto tendría que eliminarlas y ya no sería el conjunto de la fuente original.
* `yugabyte-chinook`, `yugabyte-northwind`, `yugabyte-sportsdb`: reemplazados en MySQL por las etiquetas nativas/portadas `chinook`, `northwind` y `sportsdb` anteriores (el SQL de Yugabyte es dialecto PostgreSQL; `sportsdb` se traduce manualmente desde el mismo volcado, por lo que la etiqueta con prefijo no se duplica aquí).

## Imágenes de CockroachDB

Las imágenes de CockroachDB reflejan las de PostgreSQL: un conjunto por imagen, mismo [Dockerfile](cockroach/Dockerfile) ETL impulsado por `manifest.yml`. El motor es [CockroachDB](https://www.cockroachlabs.com/) (consulte [Bases de datos](#databases) para la elección de la imagen base); es compatible a nivel de cable y SQL con PostgreSQL, por lo que estas reutilizan los mismos volcados del dialecto PostgreSQL que usan las etiquetas de PostgreSQL de Yugabyte. El punto de entrada oficial `cockroachdb/cockroach` crea la base de datos nombrada por la variable de entorno `COCKROACH_DATABASE` y ejecuta cada script `/docker-entrypoint-initdb.d/*.sql` contra ella (bajo `start-single-node`), por lo que — a diferencia de las imágenes de postgres — la compilación no emite un encabezado `CREATE DATABASE`; la base de datos es el nombre simple del conjunto.

Las imágenes ejecutan un clúster de nodo único en modo inseguro (estas son imágenes desechables para prácticas/pruebas, reflejando las credenciales triviales que usan las imágenes de postgres/mysql), lo que mantiene la conexión simple. Inicie un contenedor y conéctese con el cliente `cockroach sql` integrado:
```
docker run -d --name cr-ds-<tag> aa8y/cockroach-dataset:<tag>
docker exec -it cr-ds-<tag> cockroach sql --insecure --database <db_name>
```
donde `<tag>` es una de las etiquetas en la columna de CockroachDB de la [matriz](#dataset-support-matrix) y `<db_name>` es el nombre del conjunto correspondiente (la etiqueta menos cualquier prefijo `stackexchange-`, p. ej. `stackexchange-beer` → `beer`).

### Conjuntos de datos de CockroachDB

Las fuentes están en la [matriz](#dataset-support-matrix); las notas a continuación son específicas de CockroachDB:

* `chinook`, `northwind`: mismos volcados del dialecto PostgreSQL de Yugabyte que las etiquetas postgres `yugabyte-chinook` / `yugabyte-northwind` (identificadores en CamelCase entre comillas para chinook; snake_case para northwind).
* `world`, `iso3166`, `frenchtowns`, `usda`, `dellstore`: volcados DDL + datos de pgFoundry PostgreSQL, transcodificados de Latin-1 a UTF-8, eliminados de configuraciones de sesión de Postgres y llamadas `setval` que CockroachDB no necesita, con bloques `COPY` reescritos a `INSERT`s por lotes en tiempo de compilación (`cockroach/scripts/pgfoundry`; el `COPY` de entrada estándar en tiempo de inicialización de CRDB es mucho más lento que Postgres para bloques grandes). Se elimina la función auxiliar PL/pgSQL de dellstore (el esquema y los datos aún se cargan con fidelidad).
* `pgexercises`: el ejemplo `clubdata` de Yugabyte (3 tablas en un esquema dedicado `cd`).
* `sportsdb`: el espejo sportsdb de Yugabyte (se crean 107 tablas; solo infraestructura genérica más fútbol americano, béisbol, baloncesto y hockey sobre hielo contienen datos). Los índices `USING lsm` de Yugabyte se reescriben a `btree` en tiempo de compilación; se elimina un `CREATE DOMAIN` no utilizado.
* `moma`: esquema escrito en el repositorio (`cockroach/scripts/moma/schema.sql`, cada columna `text`); las exportaciones CSV se leen en tiempo de compilación y se integran en el script de inicialización como `INSERT`s por lotes (el cliente SQL de CockroachDB no admite ni `\copy` ni `COPY FROM '<archivo>'`). Las cuentas fluctúan a medida que MoMA actualiza sus exportaciones (registradas como límites mínimos).
* `stackexchange-<site>` (bd = nombre simple del sitio): XML por tabla convertido en tiempo de compilación por el gancho compartido de stackexchange de cockroach a `CREATE TABLE` + `INSERT`s por lotes + índices (8 tablas en `public`); el gancho de Postgres emite `COPY` en su lugar, pero el `COPY` de entrada estándar en tiempo de inicialización de CRDB es mucho más lento para bloques grandes. Las cuentas se registran como límites mínimos. `cooking` es el más grande.

### Conjuntos de datos no portados a CockroachDB

Los conjuntos de datos restantes provienen de fuentes exclusivas de PostgreSQL o dependen de características específicas de PostgreSQL que CockroachDB no soporta con fidelidad:

* `pagila`: no omitida sino *reemplazada* — `pagila` es un puerto de Sakila a PostgreSQL con tablas particionadas por rango; MySQL y SQLite usan puertos nativos de Sakila directamente (etiqueta `sakila`).
* `adventureworks`: el único puerto abierto mantenido apunta a PostgreSQL; su compilación depende de un reformateo en Python más múltiples esquemas y vistas materializadas — demasiado mecanismo específico de PostgreSQL para cargar en CockroachDB sin divergencia.
* `airlines`: la [demo de postgrespro](https://postgrespro.com/education/demodb) se distribuye como un `pg_dump` de PostgreSQL casi binario y depende de características de PostgreSQL (`jsonb`, varios millones de filas en línea).
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) depende de la extensión `tsm_system_rows` (sin equivalente en CockroachDB), por lo que un puerto tendría que eliminar las vistas de la fuente original.

## Imágenes de SQLite

Las imágenes de SQLite siguen el mismo modelo de un conjunto por imagen, pero dado que SQLite es sin servidor, la compilación se invierte: en lugar de distribuir scripts de inicialización que se ejecutan al iniciar el contenedor, la compilación ensambla el archivo de base de datos y la imagen final lo lleva. Cada imagen [`aa8y/sqlite-dataset`](https://hub.docker.com/r/aa8y/sqlite-dataset) contiene exactamente un conjunto como `/data/<dataset>.db`, construido a través del [Dockerfile](sqlite/Dockerfile) impulsado por `manifest.yml`: un conjunto se describe mediante un script SQL nativo de SQLite (alimentado al CLI `sqlite3` para construir la base de datos) o mediante un archivo de base de datos SQLite precompilado (distribuido tal cual).

Inicie un contenedor y abra la base de datos con la shell `sqlite3` incluida:
```
docker run -it --rm aa8y/sqlite-dataset:<tag>
```
lo que abre `/data/<db_name>.db` directamente. También puede ejecutar una consulta única:
```
docker run --rm aa8y/sqlite-dataset:<tag> /usr/bin/sqlite3 /data/<db_name>.db "SELECT count(*) FROM ..."
```
donde `<tag>` es una de las etiquetas en la columna de SQLite de la [matriz](#dataset-support-matrix) y `<db_name>` es el nombre del conjunto correspondiente.

### Conjuntos de datos de SQLite

Las fuentes están en la [matriz](#dataset-support-matrix); las notas a continuación son específicas de SQLite:

* `chinook`: construido en tiempo de compilación de imagen a partir del script nativo `Chinook_Sqlite.sql` del proveedor (versión `v1.4.5`); identificadores en CamelCase (`Track`, `InvoiceLine`), con cuentas de filas que coinciden exactamente con las otras etiquetas `chinook`.
* `northwind`: la base de datos jpwhite3/northwind-SQLite3 precompilada distribuida tal cual — la edición *expandida* del puerto, cuyas tablas `Orders` y especialmente `"Order Details"` contienen muchas más filas que la muestra clásica, por lo que esta imagen es más pesada que las demás.
* `world`: el volcado `world` de PostgreSQL de pgFoundry traducido manualmente en tiempo de compilación a través del gancho de transformación compartido `sqlite/scripts/pgsql` (`COPY` → `INSERT`s por lotes, ruido exclusivo de Postgres eliminado); tres tablas (`city`, `country`, `countrylanguage`) con cuentas de filas que coinciden exactamente con las otras etiquetas `world`.
* `iso3166`, `frenchtowns`, `usda`, `pgexercises`, `dellstore`, `sportsdb`: mismo gancho compartido `sqlite/scripts/pgsql` que `world` — volcados simples de DDL + datos de PostgreSQL reescritos para SQLite en tiempo de compilación. SQLite no puede agregar restricciones mediante `ALTER TABLE`, por lo que las restricciones PK/FK/únicas del volcado se eliminan; las tablas y cuentas de filas aún se cargan con fidelidad (coincidiendo con las etiquetas de MySQL para estos conjuntos).
* `sakila`: el `sakila_master.db` precompilado del puerto bradleygrant/sakila-sqlite3 distribuido tal cual — sustituye a `pagila` de PostgreSQL (16 tablas base, cuentas de filas compatibles con MySQL).
* `moma`: esquema escrito en el repositorio (`sqlite/scripts/moma/schema.sql`, cada columna `text`); CSV cargados en lote en tiempo de compilación con el comando punto `.import` del CLI sqlite3. Las cuentas fluctúan a medida que MoMA actualiza sus exportaciones (registradas como límites mínimos).
* `stackexchange-<site>`: XML por tabla convertido en tiempo de compilación por un gancho compartido (`sqlite/scripts/stackexchange`) a `CREATE TABLE` + `INSERT`s por lotes + índices (identificadores en CamelCase entre comillas dobles). `cooking` es el más grande; las cuentas se registran como límites mínimos.

### Conjuntos de datos no portados a SQLite

Los conjuntos de datos restantes provienen de fuentes exclusivas de PostgreSQL o dependen de características específicas de PostgreSQL que no se pueden traducir manualmente sin divergir del conjunto original. Los volcados simples de DDL + datos en su lugar se traducen manualmente (consulte el grupo anterior); estos son los que permanecen exclusivos de PostgreSQL:

* `pagila`: no omitida sino *reemplazada* — `pagila` es un puerto de Sakila a PostgreSQL, y SQLite usa un puerto nativo de Sakila directamente (etiqueta `sakila`, arriba).
* `adventureworks`: el único puerto abierto mantenido apunta a PostgreSQL; AdventureWorks es un ejemplo de Microsoft SQL Server sin un puerto compatible y mantenido para SQLite, y su compilación depende de un reformateo en Python más múltiples esquemas y vistas materializadas — demasiado mecanismo específico de PostgreSQL para traducir manualmente con fidelidad.
* `airlines`: la [demo de postgrespro](https://postgrespro.com/education/demodb) se distribuye como un `pg_dump` de PostgreSQL casi binario y depende de características de PostgreSQL (`jsonb`, varios millones de filas en línea); es exclusivo de PostgreSQL.
* `omdb`: [df7cb/omdb-postgresql](https://github.com/df7cb/omdb-postgresql) es específico de PostgreSQL — sus vistas dependen de la extensión `tsm_system_rows` (sin equivalente en SQLite), por lo que un puerto tendría que eliminarlas y ya no sería el conjunto de la fuente original.

## Uso

Puede iniciar el contenedor ejecutando:
```
docker run -d --name pg-ds-<tag> aa8y/postgres-dataset:<tag>
```
y acceder a él mediante:
```
docker exec -it pg-ds-<tag> psql -d <db_name>
```
donde `<tag>` es una de las etiquetas de la [matriz](#dataset-support-matrix) y `<db_name>` es el conjunto de datos integrado en ella: la etiqueta en sí, menos cualquier prefijo `yugabyte-`/`stackexchange-` (p. ej. `yugabyte-chinook` → `chinook`, `stackexchange-beer` → `beer`). También puede usarlas con `docker-compose`. Consulte [este ejemplo](https://github.com/aa8y/data-dude/blob/master/docker-compose.yml) para obtener información sobre cómo usarlas.

## Imágenes personalizadas

Cada imagen contiene un conjunto de datos, seleccionado con el arg de compilación `DATASET` junto con las fuentes de ese conjunto (declaradas por etiqueta en `manifest.yml`). La forma más sencilla de compilar una etiqueta es a través de `dave`:
```
dave build -c postgres -t dellstore
```
La forma recomendada de agregar o cambiar un conjunto de datos es declarar su `extractUrl`, `sqlFiles` y cualquier elemento extra (`extraPrereqs`, `dbExtension`, `cdDir`) bajo una nueva etiqueta en `manifest.yml`: el [Dockerfile ETL](postgres/Dockerfile) los lee como args de compilación. También puede invocar `docker build` directamente pasando esos mismos argumentos, p. ej.:
```
docker build -t aa8y/postgres-dataset:world postgres \
  --build-arg DATASET=world \
  --build-arg EXTRACT_URL=https://ftp.postgresql.org/pub/projects/pgFoundry/dbsamples/world/world-1.0/world-1.0.tar.gz \
  --build-arg SQL_FILES=dbsamples-0.1/world/world.sql
```
y luego siguiendo los mismos pasos [mencionados anteriormente](#usage) para usar su imagen personalizada.

## Pruebas

Hay dos capas de pruebas.

**Pruebas de estructura** son configuraciones estáticas de [container-structure-test][cst] bajo
`test/config/`: un `common.yaml` compartido más un archivo por conjunto. Realizan
aserciones sobre el sistema de archivos de la imagen y los scripts de inicialización distribuidos sin iniciar Postgres.
Las configuraciones a aplicar por etiqueta se declaran en `manifest.yml` bajo
`structureTest:` y se ejecutan nativamente con `dave structure-test`.

**Pruebas de integración (smoke)** realmente inician cada imagen y consultan la base
de datos en vivo. Para cada conjunto distribuido en una etiqueta, `test/integration/run.sh`:

1. espera a que Postgres termine de inicializarse (listo por TCP, para que todos los scripts
   de inicialización se completen),
2. lista las tablas base y asegura que el conjunto coincida exactamente con el esperado
   (sin tablas faltantes, sin extras inesperados), y
3. ejecuta `SELECT count(*)` en cada tabla y asegura que las cuentas de filas coincidan.

Las tablas y cuentas esperadas viven por conjunto como JSON bajo `test/expected/`,
p. ej. `test/expected/iso3166.json`:

```json
{
  "public.country": 242,
  "public.subcountry": 3995
}
```

con clave el nombre de la tabla calificada por esquema, con valores autoritativos de `count(*)`.
Un valor normalmente es una cuenta exacta. Para conjuntos cuyos datos se obtienen de una
fuente en vivo en tiempo de compilación y por lo tanto varían entre compilaciones (`omdb` de
`www.omdb.org`, `moma` de las exportaciones CSV de MoMA y `beer` del
volcado de datos de Stack Exchange), el valor en su lugar es un límite mínimo como
`">=59274"` y la prueba asegura `count(*) >=` ese número. `--update` escribe
los límites automáticamente para dichos conjuntos.

Estos están cableados en `dave test` a través de la plantilla `test:` en `manifest.yml`,
que se renderiza por etiqueta y pasa la etiqueta de imagen más el único conjunto integrado en
ella (`run.sh` aún acepta una lista separada por comas, por lo que sigue funcionando si se
reintroduce una imagen de múltiples conjuntos). El script necesita `docker` y `jq`
en el host; `psql` se ejecuta dentro del contenedor.

```sh
brew install container-structure-test jq     # una sola vez

dave build
dave structure-test                           # comprobaciones estáticas
dave test                                      # pruebas en vivo (inicia imágenes)

# limitar a etiquetas específicas localmente (nota: -c postgres es obligatorio con -t):
dave test -c postgres -t iso3166 -t dellstore
```

Para (re)generar un archivo esperado después de un cambio intencional en el conjunto, ejecute el
script en modo de actualización contra una imagen recién compilada:

```sh
test/integration/run.sh --update iso3166 iso3166   # <tag> <datasets-csv>
```

CI ejecuta los tres comandos; consulte `.github/workflows/ci.yml`.

[cst]: https://github.com/GoogleContainerTools/container-structure-test

## Caché de compilación

Cada etiqueta usa un [caché de compilación de registro](https://docs.docker.com/build/cache/backends/registry/)
para que la capa costosa `EXTRACT` (la descarga de la fuente) y las
capas `TRANSFORM`/`LOAD` posteriores se reutilicen entre compilaciones en lugar de
redarse desde cero en cada ejecución de CI. El caché se lee en `dave build`
(`--cache-from`) y se escribe en `dave push` (`--cache-to ... mode=max`),
almacenado por etiqueta como `<repository>:buildcache-<tag>`. Una referencia de caché faltante es un
fallo de caché, no un error, por lo que la primera compilación de una nueva etiqueta simplemente lo pobla.

La corrección depende del contenido real de la fuente del conjunto. Antes de cada
compilación, `bin/dataset-checksum` calcula una huella digital barata y estable de la(s)
fuente(s) de la etiqueta: el SHA HEAD de `git ls-remote` para fuentes `*.git`, el
`md5`/`sha1` real de la [API de metadatos JSON de archive.org](https://archive.org/developers/md-read.html)
(vía `jq`) para los volcados de Stack Exchange, o el
`ETag`/`Last-Modified`/`Content-Length` de un `HEAD` HTTP (con una recuperación ranged-GET)
para otras URLs de archivos — sin descargar los datos. La huella digital se
pasa a la compilación como el arg de compilación `DATASET_CHECKSUM`, que el compilador
referencia justo antes de `EXTRACT`:

* cuando la fuente no ha cambiado, la huella es idéntica y las capas en caché
  se reutilizan (rápido);
* cuando la fuente cambia, la huella cambia, invalidando `EXTRACT` y
  propagando una recompilación a través de `TRANSFORM` y `LOAD` (nuevo).

La huella se registra en la imagen final como la
etiqueta `org.opencontainers.image.revision` (`docker inspect`). El cálculo
es de fallo abierto: una fuente que no expone metadatos utilizables (o es momentáneamente
inalcanzable) colapsa a un marcador estable y se almacena en caché como antes en lugar de
forzar una recompilación completa espuria. El script necesita `curl`, `jq` y `git` en
el host (todos presentes en los ejecutores de CI; `jq` ya es requerido por las
pruebas de integración).

## Trabajos Futuros

* Más conjuntos de datos de MySQL: portar conjuntos adicionales de PostgreSQL donde exista una fuente nativa de MySQL o la fuente sea lo suficientemente neutral en formato como para traducir manualmente con fidelidad (consulte [Conjuntos de datos no portados a MySQL](#datasets-not-ported-to-mysql)).
* Imágenes de [ClickHouse](https://clickhouse.com/): distribuir los mismos conjuntos de ejemplo en ClickHouse: un motor columnar OLAP cuyo dialecto SQL y modelo de carga masiva (`MergeTree`, `INSERT`/`CSV`) difieren lo suficiente de PostgreSQL que la mayoría de los conjuntos necesitarían transformaciones específicas del motor en lugar de reutilizar los volcados de postgres textualmente.
* Imágenes de [DuckDB](https://duckdb.org/): distribuir los mismos conjuntos de ejemplo en DuckDB: una base de datos analítica embebida (como SQLite, un archivo de base de datos en lugar de un servidor que iniciar) con fuerte compatibilidad con PostgreSQL para muchos volcados simples de DDL + datos, por lo que varios conjuntos pueden portarse con pocos cambios.
* Imágenes de [Apache Druid](https://druid.apache.org/): distribuir los mismos conjuntos de ejemplo en Druid: un almacén de datos OLAP en tiempo real construido alrededor de segmentos inmutables e ingestión por lotes/flujo en lugar de DDL + `INSERT`/`COPY` convencional, por lo que cada conjunto necesitaría una pipeline de ingestión dedicada y mapeo de esquema.
* Imágenes de [Apache Pinot](https://pinot.apache.org/): distribuir los mismos conjuntos de ejemplo en Pinot: un motor OLAP distribuido orientado a tablas analíticas de esquema estrella y trabajos de ingestión offline/online, por lo que los volcados relacionales de ejemplo necesitarían transformaciones similares por conjunto y rutas de carga en lugar de cargar SQL de postgres tal cual.
* Buscar y agregar más fuentes de datos gratuitas.
