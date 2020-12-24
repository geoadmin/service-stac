SHELL = /bin/bash

.DEFAULT_GOAL := help

SERVICE_NAME := service-stac

CURRENT_DIR := $(shell pwd)
VENV := $(CURRENT_DIR)/.venv

# Django specific
APP_SRC_DIR := app
DJANGO_MANAGER := $(CURRENT_DIR)/$(APP_SRC_DIR)/manage.py

# Test report
TEST_DIR := $(CURRENT_DIR)/$(APP_SRC_DIR)/tests

# general targets timestamps
TIMESTAMPS = .timestamps
SETTINGS_TIMESTAMP = $(TIMESTAMPS)/.settins.timestamp
DOCKER_BUILD_TIMESTAMP = $(TIMESTAMPS)/.docker-test.timestamp

# Find all python files that are not inside a hidden directory (directory starting with .)
PYTHON_FILES := $(shell find $(APP_SRC_DIR) -type f -name "*.py" -print)

# default configuration
ENV ?= dev
HTTP_PORT ?= 8000
DEBUG ?= 1
LOGGING_CFG ?= logging-cfg-local.yml
LOGGING_CFG_PATH := $(DJANGO_CONFIG_DIR)/$(LOGGING_CFG)

# Commands
PIPENV_RUN := pipenv run
PYTHON := $(PIPENV_RUN) python3
YAPF := $(PIPENV_RUN) yapf
ISORT := $(PIPENV_RUN) isort
PYLINT := $(PIPENV_RUN) pylint

# Set summon only if not already set, this allow to disable summon on environment
# that don't use it like for CodeBuild env
SUMMON ?= summon --up -p gopass -e service-stac-$(ENV)

GIT_HASH := `git rev-parse HEAD`
GIT_BRANCH := `git symbolic-ref HEAD --short 2>/dev/null`
GIT_DIRTY := `git status --porcelain`
GIT_TAG := `git describe --tags || echo "no version info"`
AUTHOR := $(USER)

# Docker variables
DOCKER_IMG_LOCAL_TAG = swisstopo/$(SERVICE_NAME):$(USER).$(GIT_TAG)
DOCKER_IMG_LOCAL_TAG_DEV = swisstopo/$(SERVICE_NAME):$(USER).$(GIT_TAG)-dev

all: help


.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo
	@echo "Possible targets:"
	@echo -e " \033[1mLOCAL DEVELOPMENT TARGETS\033[0m "
	@echo "- setup                    Create the python virtual environment and install requirements"
	@echo "- ci                       Create the python virtual environment and install requirements based on the Pipfile.lock"
	@echo -e " \033[1mFORMATING, LINTING AND TESTING TOOLS TARGETS\033[0m "
	@echo "- format                   Format the python source code"
	@echo "- lint                     Lint the python source code"
	@echo "- test                     Run the tests"
	@echo -e " \033[1mLOCAL SERVER TARGETS\033[0m "
	@echo "- serve                    Run the project using the django debug server. Port can be set by Env variable HTTP_PORT i(default: 8000)"
	@echo "- gunicornserve            Run the project using the gunicorn WSGI server. Port can be set by Env variable HTTP_PORT (default: 8000)"
	@echo -e " \033[1mDOCKER TARGETS\033[0m "
	@echo "- dockerbuild-(debug|prod) Build the project locally (with tag := $(DOCKER_IMG_LOCAL_TAG))"
	@echo "- dockerrun                Run the test container with default manage.py command 'runserver'. Note: ENV is populated from '.env.local'"
	@echo "                           Other cmds can be invoked with 'make dockerrun CMD'."
	@echo -e "                           \e[1mNote:\e[0m This will connect to your host Postgres DB. If you wanna test with a containerized DB, run 'docker-compose up'"
	@echo -e " \033[1mCLEANING TARGETS\033[0m "
	@echo "- clean                    Clean genereated files"
	@echo "- clean_venv               Clean python venv"
	@echo -e " \033[1mDJANGO TARGETS\033[0m "
	@echo -e " invoke django targets such as \033[1mserve, test, migrate, ...\033[0m  directly by calling app/manage.py COMMAND. Useful COMMANDS"
	@echo -e " > \033[1mhint:\033[0m source .venv/bin/activate to use the virualenv corresponding to this application before using app/manage.py"
	@echo "  $$ app/manage.py showmigrations (show pending and applied migrations)"
	@echo "  $$ app/manage.py makemigrations (make migrations to reflect the model state in the code in the Database)"
	@echo "  $$ app/manage.py migrate        (apply changes in the database)"
	@echo "  $$ app/manage.py shell_plus     (start an interactive python shell with all Models loaded)"


$(TIMESTAMPS):
	mkdir -p $(TIMESTAMPS)


$(SETTINGS_TIMESTAMP): $(TIMESTAMPS)
# Check if we have a default settings.py
	test -e $(APP_SRC_DIR)/config/settings.py || echo "from .settings_dev import *" > $(APP_SRC_DIR)/config/settings.py
# Check if there's a local env file
	test -e $(CURRENT_DIR)/.env.local || (cp $(CURRENT_DIR)/.env.default $(CURRENT_DIR)/.env.local && \
	echo -e "\n  \e[91ma local .env.local was created, adapt it to your needs\e[0m")
	touch $(SETTINGS_TIMESTAMP)


# Setup the development environment

.PHONY: setup
setup: $(SETTINGS_TIMESTAMP)
# Create virtual env with all packages for development
	pipenv install --dev
# Create volume directories for postgres and minio
# Note that the '/service_stac_local' part is already the bucket name
	mkdir -p .volumes/minio/service-stac-local
	mkdir -p .volumes/postgresql
	docker-compose up &


.PHONY: ci
ci: $(SETTINGS_TIMESTAMP)
# Create virtual env with all packages for development using the Pipfile.lock
	pipenv sync --dev


# call yapf to make sure your code is easier to read and respects some conventions.
.PHONY: format
format:
	$(YAPF) -p -i --style .style.yapf $(PYTHON_FILES)
	$(ISORT) $(PYTHON_FILES)


# make sure that the code conforms to the style guide
# The DJANGO_SETTINGS module must be made available to pylint
# to support e.g. string model referencec (see
# https://github.com/PyCQA/pylint-django#usage)
.PHONY: lint
lint:
	@echo "Run pylint..."
	DJANGO_SETTINGS_MODULE=config.settings $(PYLINT) $(PYTHON_FILES)


# Running tests locally
.PHONY: test
test:
	# Collect static first to avoid warning in the test
	$(PYTHON) $(DJANGO_MANAGER) collectstatic --noinput
	$(PYTHON) $(DJANGO_MANAGER) test --verbosity=2 --parallel 8 $(TEST_DIR)


###################
# Specs
.PHONY: build-specs
build-specs:
	cd spec && make build-specs


###################
# Serve targets. Using these will run the application on your local machine. You can either serve with a wsgi front (like it would be within the container), or without.

.PHONY: serve
serve:
	$(PYTHON) $(DJANGO_MANAGER) runserver $(HTTP_PORT)

.PHONY: gunicornserve
gunicornserve:
	$(PYTHON) $(APP_SRC_DIR)/wsgi.py

.PHONY: serve-spec
serve-spec:
	cd spec && make serve-spec

###################
# Docker related functions.
# Note: the timestamp magic is ommitted here on purpose, we rely on docker's
# change detection mgmt

.PHONY: dockerbuild-debug
dockerbuild-debug:
	docker build \
		--build-arg GIT_HASH="$(GIT_HASH)" \
		--build-arg GIT_BRANCH="$(GIT_BRANCH)" \
		--build-arg GIT_DIRTY="$(GIT_DIRTY)" \
		--build-arg VERSION="$(GIT_TAG)" \
		--build-arg AUTHOR="$(AUTHOR)" -t $(DOCKER_IMG_LOCAL_TAG_DEV) --target debug .

.PHONY: dockerbuild-prod
dockerbuild-prod:
	docker build \
		--build-arg GIT_HASH="$(GIT_HASH)" \
		--build-arg GIT_BRANCH="$(GIT_BRANCH)" \
		--build-arg GIT_DIRTY="$(GIT_DIRTY)" \
		--build-arg VERSION="$(GIT_TAG)" \
		--build-arg AUTHOR="$(AUTHOR)" -t $(DOCKER_IMG_LOCAL_TAG) --target production .

.PHONY: dockerrun
dockerrun: dockerbuild-debug
	@echo "starting docker debug container with populating ENV from .env.local"
	docker run -it --rm --env-file .env.local --net=host $(DOCKER_IMG_LOCAL_TAG_DEV) ./manage.py runserver


###################
# clean targets

.PHONY: clean_venv
clean_venv:
	# ignore pipenv errors by adding command prefix -
	-pipenv --rm


.PHONY: clean
clean: clean_venv
	docker-compose down
	@# clean python cache files
	find . -path ./.volumes -prune -o -name __pycache__ -type d -print0 | xargs -I {} -0 rm -rf "{}"
	rm -rf $(TIMESTAMPS)
