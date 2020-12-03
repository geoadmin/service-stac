# service-stac

| Branch | Status |
|--------|-----------|
| develop | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiaE1nOXJ6Zk5YYWZRWGd5MlY3SGZCUUV6c0pIVEM1Z0lmWHdpYWFxZzdKOW1LbTJ1YUZXT0lpaUVzUVZrZ0dTNlhDdDlUYm0rSE9yNmE5TlcrZ3RoclNZPSIsIml2UGFyYW1ldGVyU3BlYyI6Ii8rdldNQUt5MnZDdHpMT0siLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=develop) |
| master | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiaE1nOXJ6Zk5YYWZRWGd5MlY3SGZCUUV6c0pIVEM1Z0lmWHdpYWFxZzdKOW1LbTJ1YUZXT0lpaUVzUVZrZ0dTNlhDdDlUYm0rSE9yNmE5TlcrZ3RoclNZPSIsIml2UGFyYW1ldGVyU3BlYyI6Ii8rdldNQUt5MnZDdHpMT0siLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=master) |

## Table of Content

- [Summary of the project](#summary-of-the-project)
- [Specs](spec/README.md)
- [Local development](#local-development)
  - [Dependencies](#dependencies)
  - [Setup local db](#setup-local-db)
  - [Setup app](#setup-app)
  - [Starting dev server](#starting-dev-server)
  - [Running test](#running-test)
  - [Using Django shell](#using-django-shell)
  - [Linting and formatting your work](#linting-and-formatting-your-work)
- [Deploying the project and continuous integration](#deploying-the-project-and-continuous-integration)
- [Docker](#docker)
- [Deployment configuration](#deployment-configuration)

## Summary of the project

`service-stac` provides and manages access to packaged geospatial data and their metadata. It implements and extends the **STAC API** specification version 0.9.0 [radiantearth/stac-spec/tree/v0.9.0/api-spec](https://github.com/radiantearth/stac-spec/tree/v0.9.0/api-spec). Currently the **STAC API** has been split from the main **STAC SPEC** repository into [radiantearth/stac-api-spec](https://github.com/radiantearth/stac-api-spec), which is under active development until the release 1.0-beta.

## Local development

### Dependencies

Prerequisites for development:

- python version 3.7
- pipenv
- a local postgres (>= 12.0) running
- postgis extension installed (>= 3.0)

Prerequisite for testing the build/CI stages

- `docker` and `docker-compose`

### Setup local db

Create a new superuser (required to create/destroy the test-databases) and a new database.

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
psql> CREATE DATABASE service_stac WITH OWNER service_stac ENCODING 'UTF8' TEMPLATE template0;
```

The PostGIS extension will be installed automatically by Django.

**Note: this is a local development setup and not suitable for production!**

### Setup app

These steps you need to do once to setup the project.

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

### Starting dev server

```bash
# enable first your virtual environment and make sure that `APP_ENV=local` is set
pipenv shell
cd app
./manage.py runserver
```

### Running test

```bash
./manage.py test
```

you can choose to create a new test-db on every run or to keep the db, which speeds testing up:

```bash
./manage.py test --keepdb
```

**NOTE:** by default logging is disabled during tests, you can enable it by setting the `TEST_ENABLE_LOGGING=1` environment variable:

```bash
TEST_ENABLE_LOGGING=1 ./manage.py test
```

**NOTE:** the environment variable can also be set in the `.venv.local` file.

### Using Django shell

Django shell can be use for development purpose (see [Django: Playing with the API](https://docs.djangoproject.com/en/3.1/intro/tutorial02/#playing-with-the-api))

```bash
./manage.py shell
```

You can disable totally logging while playing with the shell as follow:

```bash
DISABLE_LOGGING=1 ./manage.py shell
```

**NOTE:** the environment variable can also be set in the `.venv.local` file.

#### Migrate DB with Django shell
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
2. Following command will generate a new migration script:
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

### Deployment configuration

The service is configured by Environment Variable:

| Env         | Default               | Description                            |
|-------------|-----------------------|----------------------------------------|
| LOGGING_CFG | logging-cfg-local.yml | Logging configuration file             |
