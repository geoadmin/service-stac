# service-stac

| Branch | Status |
|--------|-----------|
| develop | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiaE1nOXJ6Zk5YYWZRWGd5MlY3SGZCUUV6c0pIVEM1Z0lmWHdpYWFxZzdKOW1LbTJ1YUZXT0lpaUVzUVZrZ0dTNlhDdDlUYm0rSE9yNmE5TlcrZ3RoclNZPSIsIml2UGFyYW1ldGVyU3BlYyI6Ii8rdldNQUt5MnZDdHpMT0siLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=develop) |
| master | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiaE1nOXJ6Zk5YYWZRWGd5MlY3SGZCUUV6c0pIVEM1Z0lmWHdpYWFxZzdKOW1LbTJ1YUZXT0lpaUVzUVZrZ0dTNlhDdDlUYm0rSE9yNmE5TlcrZ3RoclNZPSIsIml2UGFyYW1ldGVyU3BlYyI6Ii8rdldNQUt5MnZDdHpMT0siLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=master) |

## Table of Content

- [Summary of the project](#summary-of-the-project)
- [Specs](#specs)
- [Local development](#local-development)
  - [Dependencies](#dependencies)
  - [Setup local db](#setup-local-db)
  - [Setup app](#setup-app)
  - [Starting dev server](#starting-dev-server)
  - [Running test](#running-test)
  - [Using Django shell](#using-django-shell)
  - [Linting and formatting your work](#linting-and-formatting-your-work)
- [Deploying the project and continuous integration](#deploying-the-project-and-continuous-integration)
- [Deployment configuration](#deployment-configuration)

## Summary of the project

`service-stac` provides and manages access to packaged geospatial data and their metadata. It implements and extends the **STAC API** specification version 0.9.0 [radiantearth/stac-spec/tree/v0.9.0/api-spec](https://github.com/radiantearth/stac-spec/tree/v0.9.0/api-spec). Currently the **STAC API** has been split from the main **STAC SPEC** repository into [radiantearth/stac-api-spec](https://github.com/radiantearth/stac-api-spec), which is under active development until the release 1.0-beta.

## Specs

The API of this service is based on the [STAC API Specification](https://github.com/radiantearth/stac-api-spec) in version `0.9.0`, which itself is based on the [STAC Specification](https://github.com/radiantearth/stac-spec/tree/v0.9.0) and the [_OGC API - Features_](https://github.com/opengeospatial/ogcapi-features) specification. The default STAC spec is amended by geoadmin-specific parts that are explicitly mentioned in the spec, as well as adapted examples that resemble geoadmin-specific usecases.

The spec is OpenAPI 3.0 compliant. The files are located in `spec/` and slightly splitted for better understanding. Two different versions of the spec can be compiled from these source files into `spec/static/` folder: an `openapi.yaml` file that contains the 'public' part with the REST endpoint and HTTP methods (mostly GET) defined in the standard spec, and an `openapitransactional.yaml` file that is intended for internal usage and contains info about the additional `/asset` endpoint and additional writing possibilities. 

The spec files can be compiled with 

```
make spec/openapi.yaml
make spec/openapitransactional.yaml
```

and previewed locally with the little html ReDoc wrappers `spec/static/api.html` and `spec/static/apitransactional.html`. The can be served locally by invoking

```
make serve-spec
```

which starts a simple http server that can be reached under `http://0.0.0.0:8000` (default port is `8000`, if you need another one, check the Makefile on how to do this).

The generated files along with html wrappers are also included as static targets and are available under `https://<host_env>/api/stac/v0.9/static/api.html`.


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

## Deploying the project and continuous integration

When creating a PR, terraform should run a codebuild job to test and build automatically your PR as a tagged container. This container will only be pushed to dockerhub when the PR is accepted and merged.

This service is to be deployed to the Kubernetes cluster once it is merged.

### Deployment configuration

The service is configured by Environment Variable:

| Env         | Default               | Description                            |
|-------------|-----------------------|----------------------------------------|
| LOGGING_CFG | logging-cfg-local.yml | Logging configuration file             |
