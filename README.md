# service-stac

| Branch | Status |
|--------|-----------|
| develop | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiZ1BGZFcwU0lITG8zTEo2UlBMRXlwRkNHMU13RUlrYVV4S1BBYWsyYk85T3Q1U3diT3dsNjJ6SlhFeHQvNG04eVBkKzlZWVY2Y1RRTzFvWFhFYzRhMGlNPSIsIml2UGFyYW1ldGVyU3BlYyI6IlA0SFZ5SDJDSEwzZE01QngiLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=develop) |
| master | ![Build Status](https://codebuild.eu-central-1.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiZ1BGZFcwU0lITG8zTEo2UlBMRXlwRkNHMU13RUlrYVV4S1BBYWsyYk85T3Q1U3diT3dsNjJ6SlhFeHQvNG04eVBkKzlZWVY2Y1RRTzFvWFhFYzRhMGlNPSIsIml2UGFyYW1ldGVyU3BlYyI6IlA0SFZ5SDJDSEwzZE01QngiLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=master) |

## Table of Content

- [Summary of the project](#summary-of-the-project)
- [Links](#links)
- [Local development](#local-development)
  - [Dependencies](#dependencies)
  - [Setting up to work](#setting-up-to-work)
  - [Linting and formatting your work](#linting-and-formatting-your-work)
  - [Test your work](#test-your-work)
- [Deploying the project and continuous integration](#deploying-the-project-and-continuous-integration)
- [Deployment configuration](#deployment-configuration)

## Summary of the project

`service-stac` provides and manages access to packaged geospatial data and their metadata. It implements and extends the **STAC API** specification version 0.9.0 [radiantearth/stac-spec/tree/v0.9.0/api-spec](https://github.com/radiantearth/stac-spec/tree/v0.9.0/api-spec). Currently the **STAC API** has been splitted from the main **STAC SPEC** repository into [radiantearth/stac-api-spec](https://github.com/radiantearth/stac-api-spec), which is under active development until the release 1.0-beta.

## Links

- [STAC Specification version 0.9.0](https://github.com/radiantearth/stac-spec/tree/v0.9.0)
- [STAC API Specification version 0.9.0](https://stacspec.org/STAC-api.html)
- [STAC Lint](https://staclint.com/)
- [data.geo.admin.ch STAC API Specification](https://data.geo.admin.ch/api/stac/v0.9/api.html)
- [geoadmin/doc-api-specs](https://github.com/geoadmin/doc-api-specs/)

## Local development

### Dependencies

<!--The **Make** targets assume you have **bash**, **curl**, **tar**, **gopass**, **summon**, **gopass summon provider**, **docker** and **docker-compose** installed.-->
Prerequisites for development:
- a recent python version (>= 3.7) (check with `python -V`)
- a local postgres (>= 12.0) running
- postgis extension installed (>= 3.0)

Prerequisite for testing the build/CI stages
- `docker` and `docker-compose`

### Setup local db
Create a new superuser (required to create/destroy the test-databases) and a new database
```
sudo su - postgres
psql
# create a new user, for simplicity make it a superuser
# this allows the user to automatically create/destroy
# databases (used for testing)
psql> CREATE USER <db_user> WITH PASSWORD '<db_pw>';
psql> ALTER ROLE <db_user> WITH SUPERUSER;
# We need a database with utf8 encoding (for jsonfield) and utf8 needs template0
psql> CREATE DATABASE <db_name> WITH OWNER <db_user> ENCODING 'UTF8' TEMPLATE template0;
```

The PostGIS extension will be installed automatically by Django.

**Note:** this is a local development setup and not suitable for production!

### Setup app
These steps you need to do once to setup the project.
- clone the repo
```
git clone git@github.com:geoadmin/service-stac.git
cd service-stac
```
- define the app environment (`APP_ENV=local` causes the settings to populate the env from `.env.local`, otherwise values are taken from the system ENV)
```
export APP_ENV=local
```
- create and adapt your local copy of `.env.default` with the values defined when creating the database:
```
cp .env.default .env.local
```
- and finally create your local copy of the `settings.py`, which is in the simplest case just a
```
echo "from .settings_dev import *" > app/config/settings.py
```
- creating a virtualenv and installing dependencies
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_dev.txt
```

### Starting dev server
```
cd app
# make sure you have the virtualenv activated and `APP_ENV=local` set
./manage.py runserver
```

### Running test
```
./manage.py test
```
you can choose to create a new test-db on every run or to keep the db, which speeds testing up:
```
./manage.py test --keepdb
```
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

### Setting up to work

First, you'll need to clone the repo

```bash
git clone git@github.com:geoadmin/service-stac.git
```

Then, you can run the `dev` target to ensure you have everything needed to develop, test and serve locally

```bash
make dev
```

That's it, you're ready to work.

For more help you can use

```bash
make help
```

### Linting and formatting your work

In order to have a consistent code style the code should be formatted using `yapf`. Also to avoid syntax errors and non
pythonic idioms code, the project uses the `pylint` linter. Both formatting and linter can be manually run using the
following command:

```bash
make format-lint
```

**Formatting and linting should be at best integrated inside the IDE, for this look at
[Integrate yapf and pylint into IDE](https://github.com/geoadmin/doc-guidelines/blob/master/PYTHON.md#yapf-and-pylint-ide-integration)**

### Test your work

Testing if what you developed work is made simple. You have four targets at your disposal. **test, serve, gunicornserve, dockerrun**

```bash
make test
```

This command run the integration and unit tests.

```bash
make serve
```

This will serve the application through Django Server without any wsgi in front.

```bash
make gunicornserve
```

This will serve the application with the Gunicorn layer in front of the application

```bash
make dockerrun
```

This will serve the application with the wsgi server, inside a container. To stop serving through container press `CTRL^C`.

To stop the container run,

```bash
make shutdown
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
