SHELL = /bin/bash

.DEFAULT_GOAL := help

SERVICE_NAME := service-stac

CURRENT_DIR := $(shell pwd)

# Imports the environment variables
ifneq ("$(wildcard .env.local)","")
include .env.local
export
else
include .env.default
export
endif

# Django specific
APP_SRC_DIR := app
DJANGO_MANAGER := $(CURRENT_DIR)/$(APP_SRC_DIR)/manage.py
DJANGO_MANAGER_DEBUG := -m debugpy --listen localhost:5678 --wait-for-client $(CURRENT_DIR)/$(APP_SRC_DIR)/manage.py

# Test options
ifeq ($(CI),"1")
CI_TEST_OPTS := "--no-input"
else
CI_TEST_OPT :=
endif
TEST_DIR := $(CURRENT_DIR)/$(APP_SRC_DIR)/tests

# general targets timestamps
TIMESTAMPS = .timestamps
SETTINGS_TIMESTAMP = $(TIMESTAMPS)/.settins.timestamp
DOCKER_BUILD_TIMESTAMP = $(TIMESTAMPS)/.docker-test.timestamp

# Find all python files that are not inside a hidden directory (directory starting with .)
PYTHON_FILES := $(shell find $(APP_SRC_DIR) -type f -name "*.py" -print)

# default configuration
ENV ?= dev

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
# the 'local' prefix in the tag is important for lifecycle policies within
# ECR management. Those images, when pushed, are stored for a maximum of 30
# days.
DOCKER_REGISTRY = 974517877189.dkr.ecr.eu-central-1.amazonaws.com
DOCKER_IMG_LOCAL_TAG = $(DOCKER_REGISTRY)/$(SERVICE_NAME):local-$(USER).$(GIT_TAG)
DOCKER_IMG_LOCAL_TAG_DEV = $(DOCKER_REGISTRY)/$(SERVICE_NAME):local-$(USER).$(GIT_TAG)-dev

# AWS variables
AWS_DEFAULT_REGION = eu-central-1

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
	@echo "- ci-check-format          Format the python source code and check if any files has changed. This is meant to be used by the CI."
	@echo "- lint                     Lint the python source code"
	@echo "- django-checks            Run the django checks"
	@echo "- django-check-migrations  Check that no django migration file is missing"
	@echo "- test                     Run the tests"
	@echo "- test-conformance         Run stac-api-validator, needs a valid collection name, e.g. collection=ch.are.agglomerationsverkehr"
	@echo -e " \033[1mSPEC TARGETS\033[0m "
	@echo "- lint-specs               Lint the openapi specs  (openapi.yaml and openapitransactional.yaml)"
	@echo "- ci-build-check-specs     Checks that the specs have been built"
	@echo "- build-specs              Build the openapi specs (openapi.yaml and openapitransactional.yaml)"
	@echo "- serve-specs              Serve openapi specs  (openapi.yaml and openapitransactional.yaml)"
	@echo -e " \033[1mLOCAL SERVER TARGETS\033[0m "
	@echo "- serve                    Run the project using the django debug server. Port can be set by Env variable HTTP_PORT i(default: 8000)"
	@echo "- gunicornserve            Run the project using the gunicorn WSGI server. Port can be set by Env variable HTTP_PORT (default: 8000)"
	@echo -e " \033[1mDOCKER TARGETS\033[0m "
	@echo "- dockerlogin              Login to the AWS ECR registery for pulling/pushing docker images"
	@echo "- dockerbuild-(debug|prod) Build the project locally (with tag := $(DOCKER_IMG_LOCAL_TAG))"
	@echo "- dockerpush-(debug|prod)  Build and push the project localy (with tag := $(DOCKER_IMG_LOCAL_TAG))"
	@echo "- dockerrun                Run the test container with default manage.py command 'runserver'. Note: ENV is populated from '.env.local'"
	@echo "                           Other cmds can be invoked with 'make dockerrun CMD'."
	@echo -e "                           \e[1mNote:\e[0m This will connect to your host Postgres DB. If you wanna test with a containerized DB, run 'docker-compose up'"
	@echo -e " \033[1mCLEANING TARGETS\033[0m "
	@echo "- clean                    Clean genereated files"
	@echo "- clean-logs               Clean generated logs files"
	@echo "- clean-venv               Clean python venv"
	@echo "- clean-all                Clean everything (generated files and virtual environment)"
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


.PHONY: setup-logs
setup-logs:
	# create directory for unittests logs
	mkdir -m 777 -p ${LOGS_DIR}
	find ${LOGS_DIR} -type f -exec chmod 666 {} \;

# Setup the development environment

.PHONY: setup-s3-and-db
setup-s3-and-db:
	# Create volume directories for postgres and minio
	# Note that the '/service_stac_local' part is already the bucket name
	mkdir -p .volumes/minio/service-stac-local
	mkdir -p .volumes/minio/service-stac-local-managed
	mkdir -p .volumes/postgresql
	docker compose up -d

.PHONY: setup
setup: $(SETTINGS_TIMESTAMP) setup-s3-and-db setup-logs
	# Create virtual env with all packages for development
	pipenv install --dev
	pipenv shell

.PHONY: ci
ci: $(SETTINGS_TIMESTAMP) setup-s3-and-db setup-logs
	# Create virtual env with all packages for development using the Pipfile.lock
	pipenv sync --dev

# call yapf to make sure your code is easier to read and respects some conventions.
.PHONY: format
format:
	$(YAPF) -p -i --style .style.yapf $(PYTHON_FILES)
	$(ISORT) $(PYTHON_FILES)

.PHONY: ci-check-format
ci-check-format: format
	@if [[ -n `git status --porcelain --untracked-files=no` ]]; then \
	 	>&2 echo "ERROR: the following files are not formatted correctly"; \
	 	>&2 echo "'git status --porcelain' reported changes in those files after a 'make format' :"; \
		>&2 git status --porcelain --untracked-files=no; \
		exit 1; \
	fi

# make sure that the code conforms to the style guide. Note that
# - the DJANGO_SETTINGS module must be made available to pylint
#   to support e.g. string model referencec (see
#   https://github.com/PyCQA/pylint-django#usage)
# - export of migrations for prometheus stats must be disabled,
#   otherwise it's attempted to connect to the db during linting
#   (which is not available)
.PHONY: lint
lint:
	@echo "Run pylint..."
	LOGGING_CFG=0 DJANGO_SETTINGS_MODULE=config.settings $(PYLINT) $(PYTHON_FILES)

.PHONY: django-checks
django-checks:
	$(PYTHON) $(DJANGO_MANAGER) check --fail-level WARNING

.PHONY: django-check-migrations
django-check-migrations:
	@echo "Check for missing migration files"
	$(PYTHON) $(DJANGO_MANAGER) makemigrations --no-input --check

# Running tests locally
.PHONY: test
test:
	# Collect static first to avoid warning in the test
	$(PYTHON) $(DJANGO_MANAGER) collectstatic --noinput
	$(PYTHON) $(DJANGO_MANAGER) test --verbosity=2 --parallel 20 $(CI_TEST_OPT) $(TEST_DIR)

.PHONY: test-debug
test-debug:
	# Collect static first to avoid warning in the test
	$(PYTHON) $(DJANGO_MANAGER) collectstatic --noinput
	$(PYTHON) $(DJANGO_MANAGER_DEBUG) test --verbosity=2 $(CI_TEST_OPT) $(TEST_DIR)


.PHONY: test-conformance
test-conformance:
	stac-api-validator \
    --root-url http://localhost:$(HTTP_PORT)/api/stac/v1/ \
    --conformance core \
    --conformance collections \
    --collection $(collection)

###################
# Specs
.PHONY: build-specs
build-specs:
	cd spec && make build-specs


.PHONY: lint-specs
lint-specs:
	cd spec && make lint-specs


.PHONY: ci-build-check-specs
ci-build-check-specs:
	@echo "Ignore ci-build-check-specs"
	# Currently the ci-build-check-specs doesn't work because the merged output of yq
	# differ on the ci from our ubuntu development machine.
	# @if [[ -n `git status --porcelain --untracked-files=no` ]]; then \
	#  	>&2 echo "ERROR: the following files changed after building the spec"; \
	#  	>&2 echo "'git status --porcelain' reported changes in those files after a 'build-specs' :"; \
	# 	>&2 git status --porcelain --untracked-files=no; \
	# 	exit 1; \
	# fi


###################
# Serve targets. Using these will run the application on your local machine. You can either serve with a wsgi front (like it would be within the container), or without.

.PHONY: serve
serve: setup-logs
	$(PYTHON) $(DJANGO_MANAGER) runserver $(HTTP_PORT)

.PHONY: serve-debug
serve-debug: setup-logs
	$(PYTHON) $(DJANGO_MANAGER_DEBUG) runserver $(HTTP_PORT)

.PHONY: gunicornserve
gunicornserve: setup-logs
	$(PYTHON) $(APP_SRC_DIR)/wsgi.py

.PHONY: serve-specs
serve-specs:
	cd spec && make serve-specs

###################
# Docker related functions.
# Note: the timestamp magic is ommitted here on purpose, we rely on docker's
# change detection mgmt

.PHONY: dockerlogin
dockerlogin:
	aws --profile swisstopo-bgdi-builder ecr get-login-password --region $(AWS_DEFAULT_REGION) | docker login --username AWS --password-stdin $(DOCKER_REGISTRY)

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
dockerrun: dockerbuild-debug setup-logs
	@echo "starting docker debug container with populating ENV from .env.local"
	docker run \
		-it --rm \
		--env-file .env.local \
		--net=host \
		--mount type=bind,source="${PWD}/${LOGS_DIR}",target=/opt/service-stac/logs \
		$(DOCKER_IMG_LOCAL_TAG_DEV) ./wsgi.py

.PHONY: dockerrun-prod
dockerrun-prod: dockerbuild-prod setup-logs
	@echo "starting docker debug container with populating ENV from .env.local"
	docker run \
		-it --rm \
		--env-file .env.local \
		--net=host \
		--mount type=bind,source="${PWD}/${LOGS_DIR}",target=/opt/service-stac/logs \
		$(DOCKER_IMG_LOCAL_TAG) ./wsgi.py

.PHONY: dockerpush-debug
dockerpush-debug: dockerbuild-debug
	docker push $(DOCKER_IMG_LOCAL_TAG_DEV)

.PHONY: dockerpush-prod
dockerpush-prod: dockerbuild-prod
	docker push $(DOCKER_IMG_LOCAL_TAG)

###################
# clean targets

.PHONY: clean-venv
clean-venv:
	# ignore pipenv errors by adding command prefix -
	-pipenv --rm

.PHONY: clean-logs
clean-logs:
	rm -rf $(LOGS_DIR)

.PHONY: clean
clean: clean-logs
	docker compose down
	@# clean python cache files
	find . -path ./.volumes -prune -o -name __pycache__ -type d -print0 | xargs -I {} -0 rm -rf "{}"
	rm -rf $(TIMESTAMPS)

.PHONY: clean-all
clean-all: clean clean-venv
