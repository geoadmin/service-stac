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

The **Make** targets assume you have **bash**, **curl**, **tar**, **docker** and **docker-compose** installed.

### Setting up to work

First, you'll need to clone the repo

    git clone git@github.com:geoadmin/service-stac.git

Then, you can run the `dev` target to ensure you have everything needed to develop, test and serve locally

    make dev

That's it, you're ready to work.

For more help you can use

    make help

### Linting and formatting your work

In order to have a consistent code style the code should be formatted using `yapf`. Also to avoid syntax errors and non
pythonic idioms code, the project uses the `pylint` linter. Both formatting and linter can be manually run using the
following command:

    make format-lint

**Formatting and linting should be at best integrated inside the IDE, for this look at
[Integrate yapf and pylint into IDE](https://github.com/geoadmin/doc-guidelines/blob/master/PYTHON.md#yapf-and-pylint-ide-integration)**

### Test your work

Testing if what you developed work is made simple. You have four targets at your disposal. **test, serve, gunicornserve, dockerrun**

    make test

This command run the integration and unit tests.

    make serve

This will serve the application through Django Server without any wsgi in front.

    make gunicornserve

This will serve the application with the Gunicorn layer in front of the application

    make dockerrun

This will serve the application with the wsgi server, inside a container. To stop serving through container press `CTRL^C`.

To stop the container run,

    make shutdown

## Deploying the project and continuous integration

When creating a PR, terraform should run a codebuild job to test and build automatically your PR as a tagged container. This container will only be pushed to dockerhub when the PR is accepted and merged.

This service is to be deployed to the Kubernetes cluster once it is merged.

### Deployment configuration

The service is configured by Environment Variable:

| Env         | Default               | Description                            |
|-------------|-----------------------|----------------------------------------|
| LOGGING_CFG | logging-cfg-local.yml | Logging configuration file             |
