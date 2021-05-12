# service-stac

| Branch | Status |
|--------|-----------|
| develop | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiaE1nOXJ6Zk5YYWZRWGd5MlY3SGZCUUV6c0pIVEM1Z0lmWHdpYWFxZzdKOW1LbTJ1YUZXT0lpaUVzUVZrZ0dTNlhDdDlUYm0rSE9yNmE5TlcrZ3RoclNZPSIsIml2UGFyYW1ldGVyU3BlYyI6Ii8rdldNQUt5MnZDdHpMT0siLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=develop) |
| master | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiaE1nOXJ6Zk5YYWZRWGd5MlY3SGZCUUV6c0pIVEM1Z0lmWHdpYWFxZzdKOW1LbTJ1YUZXT0lpaUVzUVZrZ0dTNlhDdDlUYm0rSE9yNmE5TlcrZ3RoclNZPSIsIml2UGFyYW1ldGVyU3BlYyI6Ii8rdldNQUt5MnZDdHpMT0siLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=master) |

## Table of Content

- [Table of Content](#table-of-content)
- [Summary of the project](#summary-of-the-project)
- [Local development](#local-development)
  - [Dependencies](#dependencies)
    - [Python3.7](#python37)
    - [pipenv](#pipenv)
  - [Using Postgres on local host](#using-postgres-on-local-host)
  - [Creating the local environment](#creating-the-local-environment)
  - [Setting up the local database](#setting-up-the-local-database)
  - [Using a local PostGres database instead of a container](#using-a-local-postgres-database-instead-of-a-container)
  - [Starting dev server](#starting-dev-server)
  - [Running tests](#running-tests)
    - [Unit test logging](#unit-test-logging)
  - [Using Django shell](#using-django-shell)
  - [Migrate DB with Django](#migrate-db-with-django)
  - [Linting and formatting your work](#linting-and-formatting-your-work)
- [Initial Setup up the RDS database and the user](#initial-setup-up-the-rds-database-and-the-user)
- [Deploying the project and continuous integration](#deploying-the-project-and-continuous-integration)
- [Docker](#docker)
  - [Configuration](#configuration)
    - [**General settings**](#general-settings)
    - [**Database settings**](#database-settings)
    - [**Asset Storage settings (AWS S3)**](#asset-storage-settings-aws-s3)
    - [**Development settings (only for local environment and DEV staging)**](#development-settings-only-for-local-environment-and-dev-staging)

## Summary of the project

`service-stac` provides and manages access to packaged geospatial data and their metadata. It implements and extends the **STAC API** specification version 0.9.0 [radiantearth/stac-spec/tree/v0.9.0/api-spec](https://github.com/radiantearth/stac-spec/tree/v0.9.0/api-spec). Currently the **STAC API** has been split from the main **STAC SPEC** repository into [radiantearth/stac-api-spec](https://github.com/radiantearth/stac-api-spec), which is under active development until the release 1.0-beta.

## Local development

### Dependencies

Prerequisites on host for development and build:

- python version 3.7
- libgdal-dev
- [pipenv](https://pipenv-fork.readthedocs.io/en/latest/install.html)
- `docker` and `docker-compose`

#### Python3.7

If your Ubuntu distribution is missing Python 3.7, you may use the `deadsnakes` PPA and install it:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.7
```

#### pipenv

Generally, all modern distribution have already a [pipenv](https://pipenv-fork.readthedocs.io) package. If no, install from hand.

The other services that are used (Postgres with PostGIS extension for metadata and [MinIO](https://www.min.io) as local S3 replacement) are wrapped in a docker compose.

Starting postgres and MinIO is done with a simple

```bash
docker-compose up
```

in the source root folder (this is automatically done if you `make setup`). Make sure to run `make setup` before to ensure the necessary folders `.volumes/*` are in place. These folders are mounted in the services and allow data persistency over restarts of the containers.

### Using Postgres on local host

If you wish to use a local postgres instance rather than the dockerised one, you'll also need the following :

- a local postgres (>= 12.0) running
- postgis extension installed (>= 3.0)

### Creating the local environment

These steps will ensure you have everything needed to start working locally.

- clone the repo

  ```bash
  git clone git@github.com:geoadmin/service-stac.git
  cd service-stac
  ```

- define the app environment (`APP_ENV=local` causes the settings to populate the env from `.env.local`, otherwise values are taken from the system ENV)

  ```bash
  export APP_ENV=local
  ```

- create and adapt your local copy of `.env.default` with the values defined when creating the database:

  ```bash
  cp .env.default .env.local
  ```

- and finally create your local copy of the `settings.py`, which is in the simplest case just a

  ```bash
  echo "from .settings_dev import *" > app/config/settings.py
  ```

- creating a virtualenv and installing dependencies

  ```bash
  pipenv install
  ```

An alternative to ```pipenv install``` is to use the ```make setup``` command, which will install the environment,
create the volumes needed by the Postgres and MinIO containers
and run those containers. ```Make setup``` assume a standard local installation with a dev environment.

### Setting up the local database

The service use two other services to run, Posgres with a PostGIS extension and S3.
For local development, we recommend using the services given through the [docker-compose.yml](docker-compose.yml) file, which will
instantiate a Postgres container and a [MinIO](https://www.min.io/) container which act as a local S3 replacement.

If you used the ```make setup``` command during the local environment creation, those two services
should be already be up. You can check with

  ```bash
  docker ps -a
  ```

which should give you a result like this :
  ```
  CONTAINER ID   IMAGE                  COMMAND                   CREATED        STATUS                      PORTS                     NAMES
  a63582388800   minio/mc               "/bin/sh -c '\n  set …"   39 hours ago   Exited (0) 40 seconds ago                             service-stac_s3-client_1
  33deededf690   minio/minio            "/usr/bin/docker-ent…"    39 hours ago   Up 41 seconds               0.0.0.0:9090->9000/tcp    service-stac_s3_1
  d158be863ac1   kartoza/postgis:12.0   "/bin/sh -c /docker-…"    39 hours ago   Up 41 seconds               0.0.0.0:15432->5432/tcp   service-stac_db_1
  ```

As you can see, MinIO is using two containers, one is the local S3 server, the other is a S3 client used to set the
download policy of the bucket which allows anonymous downloads, and exits once its job is done. You should also have a postGIS container.

`make setup` also creates some necessary directories : `.volumes/minio` and `.volumes/postgresql`, which are mounted to the
corresponding containers in order to allow data persistency.

Another way to start these containers (if, for example, they stopped) is with a simple

  ```bash
  docker-compose up
  ```

Lastly, once your databases have been set up, it is time to apply migrations (to have the latest model) and fill it with
some default values to be able to start working with it. (From the root)
  ```bash
  pipenv shell
  ./app/manage.py migrate
  ./app/manage.py populate_testdb
  ```

the ```pipenv shell``` command activate the virtual environment provided by pipenv.

### Using a local PostGres database instead of a container

To use a local postgres instance rather than a container, once you've ensured you've the needed dependencies, you should :

- Create a new superuser (required to create/destroy the test-databases) and a new database.

*Note: the user/password and database name in the example below can be changed if required, these names reflects the one in `.env.default`.*

```bash
sudo su - postgres
psql
# create a new user, for simplicity make it a superuser
# this allows the user to automatically create/destroy
# databases (used for testing)
psql> CREATE USER service_stac WITH PASSWORD 'service_stac';
psql> ALTER ROLE service_stac WITH SUPERUSER;
# We need a database with utf8 encoding (for jsonfield) and utf8 needs template0
psql> CREATE DATABASE service_stac_local WITH OWNER service_stac ENCODING 'UTF8' TEMPLATE template0;
```

The PostGIS extension will be installed automatically by Django.

**Note: this is a local development setup and not suitable for production!**

You might have to change your .env.local file especially the DB_PORT, if you're using this setup.

### Starting dev server

```bash
# enable first your virtual environment and make sure that `APP_ENV=local` is set
pipenv shell
cd app
./manage.py runserver
```

### Running tests

```bash
./manage.py test
```

You can choose to create a new test-db on every run or to keep the db, which speeds testing up:

```bash
./manage.py test --keepdb
```

You can uses `--parallel=20` which also speed up tests.

You can use `--failfast` to stop at the first error.

Alternatively you can use `make` to run the tests which will run all tests in parallel.

```bash
make test
```

or use the container environment like on the CI.

```bash
docker-compose -f docker-compose-ci.yml up --build --abort-on-container-exit
```

**NOTE:** the `--build` option is important otherwise the container will not be rebuild and you don't have the latest modification
of the code.

#### Unit test logging

By default only `WARNING` logs of the `tests` module is printed in the console during unit testing.
All logs are also added to two logs files; `app/tests/logs/unittest-json-logs.json` and `app/tests/logs/unittest-standard-logs.txt`.

Alternatively for a finer logging granularity during unit test, a new logging configuration base on `app/config/logging-cfg-unittest.yml` can be generated and set via `LOGGING_CFG` environment variable or logging can be completely disabled by setting `LOGGING_CFG=0`.

### Using Django shell

Django shell can be use for development purpose (see [Django: Playing with the API](https://docs.djangoproject.com/en/3.1/intro/tutorial02/#playing-with-the-api))

```bash
./manage.py shell
```

Logging is then redireted by default to the log files `logs/management-standard-logs.txt` and `logs/management-json-logs.json`. Only error logs are printed to the console. You can disable totally logging while playing with the shell as follow:

```bash
LOGGING_CFG=0 ./manage.py shell
```

**NOTE:** the environment variable can also be set in the `.venv.local` file.

For local development (or whenever you have a `*-dev` docker image deployed), there's `shell_plus` available (part of the package `django_extensions`), a shell on steroids that automatically pre-imports e.g. all model definitions and makes working with the Django API much easier

```bash
./manage.py shell_plus
```

### Migrate DB with Django

With the Django shell ist is possible to migrate the state of the database according to the code base. Please consider following principles:

In general, the code base to setup the according state of the database ist stored here:

```bash
stac_api/migrations/
├── 0001_initial.py
├── 0002_auto_20201016_1423.py
├── 0003_auto_20201022_1346.py
├── 0004_auto_20201028.py
```

Please make sure, that per PR only one migrations script gets generated (_if possible_).

**How to generate a db migrations script?**

1. First of all this will only happen, when a model has changed
1. Following command will generate a new migration script:

    ```bash
    ./manage.py makemigrations
    ```

**How to put the database to the state of a previous code base?**

With the following command of the Django shell a specific state of the database can be achieved:

```bash
.manage.py migrate stac_api 0003_auto_20201022_1346
```

**How to create a clean PR with a singe migration script?**

Under a clean PR, we mean that only one migration script comes along a PR.
This can be obtained with the following steps (_only if more than one migration script exist for this PR_):

```bash
# 1. migrate back to the state before the PR
./manage.py migrate stac_api 0016_auto_20201022_1346

# 2. remove the migration scripts that have to be put together
cd stac_api/migrations && rm 0017_har.py 0018_toto.py 0019_final.py
./manage.py makemigrations

# 3. add the generated migration script to git
git add stac_api/migrations 0017_the_new_one.py
```

**NOTE:** When going back to a certain migration step, you have to pay attention, that this also involves deleting fields, that have not been added yet.
Which, of course, involves that its content will be purged as well.

**How to get a working database when migrations scripts screw up?**

With the following commands it is possible to get a proper state of the database:

```bash
./manage.py reset_db
./manage.py migrate
```

**Warning:** ```reset_db``` a destructive command and will delete all structure and content of the database.

### Linting and formatting your work

In order to have a consistent code style the code should be formatted using `yapf`. Also to avoid syntax errors and non
pythonic idioms code, the project uses the `pylint` linter. Both formatting and linter can be manually run using the
following command:

```bash
make format
```

```bash
make lint
```

**Formatting and linting should be at best integrated inside the IDE, for this look at
[Integrate yapf and pylint into IDE](https://github.com/geoadmin/doc-guidelines/blob/master/PYTHON.md#yapf-and-pylint-ide-integration)**

<!--
#### gopass summon provider

For the DB connection, some makefile targets (`test`, `serve`, `gunicornserve`, ...) uses `summon -p gopass --up -e service-stac-$(ENV)` to gets the credentials as environment variables.

This __summon__ command requires to have a `secrets.yml` file located higher up in the project folder hierarchy (e.g in `${HOME}/secrets.yml` if the project has been cloned in `${HOME}` or in a sub folder). This `secrets.yml` file must have two sections as follow:

```yaml
service-stac-dev:
    DB_USER: !var path-to-the-db-user-variable
    DB_PW: !var path-to-the-db-user-password
    DB_HOST: !var path-to-the-db-host
```

-->

## Initial Setup up the RDS database and the user

Right now the initial setup on the RDS database for the stagings _dev_, _int_ and _prod_ can be obtained
with the helper script `scripts/setup_rds_db.sh`. The credentials come from `gopass`. To
setup the RDS database on int, run following command:

```bash
    summon -p `which summon-gopass` -D APP_ENV=int scripts/setup_rds_db.sh
```

**Note:** The script won't delete the existing database.

## Deploying the project and continuous integration

When creating a PR, terraform should run a codebuild job to test and build automatically your PR as a tagged container. This container will only be pushed to dockerhub when the PR is accepted and merged.

This service is to be deployed to the Kubernetes cluster once it is merged.

## Docker

The service is encapsulated in a Docker image. Images are pushed on the public [Dockerhub](https://hub.docker.com/r/swisstopo/service-stac/tags) registry. From each github PR that are merged into develop branch, two Docker images are built and pushed with the following tags:

- develop.latest (prod image)
- develop.latest-dev (dev image)

From each github PR that are merged into master, one Docker image is built an pushed with the following tag:

- master.GIT_HASH

Each images contains the following metadata:

- author
- target
- git.branch
- git.hash
- git.dirty
- version

These metadata can be seen directly on the dockerhub registry in the image layers or can be read with the following command

```bash
# NOTE: jq is only used for pretty printing the json output,
# you can install it with `apt install jq` or simply enter the command without it
docker image inspect --format='{{json .Config.Labels}}' swisstopo/service-stac:develop.latest-dev | jq
```

You can also check these metadata on a running container as follow

```bash
docker ps --format="table {{.ID}}\t{{.Image}}\t{{.Labels}}"d
```

### Configuration

The service is configured by Environment Variable:

#### **General settings**

| Env         | Default               | Description                            |
|-------------|-----------------------|----------------------------------------|
| APP_ENV | `'local'` | Determine the application environment (local|dev|int|prod) |
| LOGGING_CFG | `'logging-cfg-local.yml'` | Logging configuration file or '0' to disable logging             |
| SECRET_KEY | - | Secret key for django |
| ALLOWED_HOSTS | `''` | See django ALLOWED_HOSTS. On local development and DEV staging this is overwritten with `'*'` |
| THIS_POD_IP | No default | The IP of the POD the service is running on |
| HTTP_CACHE_SECONDS | `600` | Sets the `Cache-Control: max-age` and `Expires` headers of the GET and HEAD requests to the api views. |
| HTTP_STATIC_CACHE_SECONDS | `3600` | Sets the `Cache-Control: max-age` header of GET, HEAD requests to the static files. |
| STORAGE_ASSETS_CACHE_SECONDS | `7200` | Sets the `Cache-Control: max-age` and `Expires` headers of the GET and HEAD on the assets file uploaded via admin page. |
| DJANGO_STATIC_HOST | `''` | See [Whitenoise use CDN](http://whitenoise.evans.io/en/stable/django.html#use-a-content-delivery-network). |
| TEST_ENABLE_LOGGING | `False` | Enable logging in unittest |
| PAGE_SIZE | `100` | Default page size |
| PAGE_SIZE_LIMIT | `100` | Maximum page size allowed |

#### **Database settings**

| Env         | Default               | Description                            |
|-------------|-----------------------|----------------------------------------|
| DB_NAME | service_stac | Database name |
| DB_USER | service_stac | Database user (used by django for DB connection) |
| DB_PW | service_stac | Database password (used by django for DB connection) |
| DB_HOST | service_stac | Database host |
| DB_PORT | 5432 | Database port |
| DB_NAME_TEST | test_service_stac | Database name used for unittest |

#### **Asset Storage settings (AWS S3)**

| Env         | Default               | Description                            |
|-------------|-----------------------|----------------------------------------|
| AWS_ACCESS_KEY_ID | - | |
| AWS_SECRET_ACCESS_KEY | - | |
| AWS_STORAGE_BUCKET_NAME | - | |
| AWS_S3_REGION_NAME | - | |
| AWS_S3_ENDPOINT_URL | `None` | |
| AWS_S3_CUSTOM_DOMAIN | `None` | |
| AWS_PRESIGNED_URL_EXPIRES | 3600 | AWS presigned url for asset upload expire time in seconds | 

#### **Development settings (only for local environment and DEV staging)**

These settings are read from `settings_dev.py`

| Env         | Default               | Description                            |
|-------------|-----------------------|----------------------------------------|
| DEBUG | `False` | Set django DEBUG flag |
| DEBUG_PROPAGATE_API_EXCEPTIONS | `False` | When `True` the API exception are treated as in production, using a JSON response. Otherwise in DEBUG mode the API exception returns an HTML response with backtrace. |
