SHELL = /bin/bash

.DEFAULT_GOAL := help

SERVICE_NAME := service-stac

CURRENT_DIR := $(shell pwd)
VENV := $(CURRENT_DIR)/.venv
REQUIREMENTS_DEV = $(CURRENT_DIR)/requirements_dev.txt

# Django specific
APP_SRC_DIR := app
DJANGO_MANAGER := $(CURRENT_DIR)/$(APP_SRC_DIR)/manage.py

# Test report
TEST_DIR := $(CURRENT_DIR)/tests
TEST_REPORT_DIR ?= $(TEST_DIR)/report
TEST_REPORT_FILE ?= nose2-junit.xml
TEST_REPORT_PATH := $(TEST_REPORT_DIR)/$(TEST_REPORT_FILE)

# general targets timestamps
TIMESTAMPS = .timestamps
SETUP_TIMESTAMP = $(TIMESTAMPS)/.setup.timestamp
DOCKER_BUILD_TIMESTAMP = $(TIMESTAMPS)/.docker-test.timestamp

# Docker variables
DOCKER_IMG_LOCAL_TAG = swisstopo/$(SERVICE_NAME):local
DOCKER_IMG_LOCAL_TAG_TEST = swisstopo/$(SERVICE_NAME)-test:local

# Find all python files that are not inside a hidden directory (directory starting with .)
PYTHON_FILES := $(shell find $(APP_SRC_DIR) ${TEST_DIR} -type f -name "*.py" -print)

PYTHON_VERSION := 3.7
SYSTEM_PYTHON := $(shell ./getPythonCmd.sh ${PYTHON_VERSION} ${PYTHON_LOCAL_DIR})
ifeq ($(SYSTEM_PYTHON),)
$(error "No matching python version found on system, minimum $(PYTHON_VERSION) required")
endif

# default configuration
ENV ?= dev
HTTP_PORT ?= 5000
DEBUG ?= 1
LOGGING_CFG ?= logging-cfg-local.yml
LOGGING_CFG_PATH := $(DJANGO_CONFIG_DIR)/$(LOGGING_CFG)

# Commands
# DJANGO_MANAGER := $(DJANGO_PROJECT_DIR)/manage.py
GUNICORN := $(VENV)/bin/gunicorn
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip3
FLASK := $(VENV)/bin/flask
YAPF := $(VENV)/bin/yapf
ISORT := $(VENV)/bin/isort
NOSE := $(VENV)/bin/nose2
PYLINT := $(VENV)/bin/pylint

# Set summon only if not already set, this allow to disable summon on environment
# that don't use it like for CodeBuild env
SUMMON ?= summon --up -p gopass -e service-stac-$(ENV)


all: help


.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo
	@echo "Possible targets:"
	@echo -e " \033[1mLOCAL DEVELOPMENT TARGETS\033[0m "
	@echo "- setup              Create the python virtual environment and install requirements"
	@echo -e " \033[1mFORMATING, LINTING AND TESTING TOOLS TARGETS\033[0m "
	@echo "- format             Format the python source code"
	@echo "- lint               Lint the python source code"
	@echo "- test               Run the tests"
	@echo -e " \033[1mLOCAL SERVER TARGETS\033[0m "
	@echo "- serve              Run the project using the django debug server. Port can be set by Env variable HTTP_PORT in .env.local file (default: 8000)"
	@echo "- gunicornserve      Run the project using the gunicorn WSGI server. Port can be set by Env variable DEBUG_HTTP_PORT (default: 5000)"
	@echo -e " \033[1mDOCKER TARGETS\033[0m "
	@echo "- dockerbuild-(test|prod) Build the project locally (with tag := $(DOCKER_IMG_LOCAL_TAG))"
	@echo "- dockerrun          Run the test container with default manage.py command 'runserver'. Note: ENV is populated from '.env.local'"
	@echo "                     Other cmds can be invoked with 'make dockerrun CMD'."
	@echo -e "                     \e[1mNote:\e[0m This will connect to your host Postgres DB. If you wanna test with a containerized DB, run 'docker-compose up'"
	@echo -e " \033[1mCLEANING TARGETS\033[0m "
	@echo "- clean              Clean genereated files"
	@echo "- clean_venv         Clean python venv"
	@echo -e " \033[1mDJANGO TARGETS\033[0m "
	@echo -e " invoke django targets such as \033[1mserve, test, migrate, ...\033[0m  directly by calling app/manage.py COMMAND. Useful COMMANDS"
	@echo "  $$ app/manage.py showmigrations (show pending and applied migrations)"
	@echo "  $$ app/manage.py makemigrations (make migrations to reflect the model state in the code in the Database)"
	@echo "  $$ app/manage.py migrate        (apply changes in the database)"
	@echo "  $$ app/manage.py shell_plus     (start an interactive python shell with all Models loaded)"


$(TIMESTAMPS):
	mkdir -p $(TIMESTAMPS)


# Setup the development environment
# Note: we always run then requirements_dev.txt, if there's sth to do (i.e. requirements have changed)
# 		pip will recognize
.PHONY: setup
setup: $(TIMESTAMPS)
# Test if .venv exists, if not, set it up
	test -d $(VENV) || ($(SYSTEM_PYTHON) -m venv $(VENV) && \
	$(PIP) install --upgrade pip setuptools && \
	$(PIP) install -U pip wheel);
# Install requirements, pip will track changes itself
	$(PIP) install -r $(REQUIREMENTS_DEV)
# Check if we have a default settings.py
	test -e $(APP_SRC_DIR)/config/settings.py || echo "from .settings_dev import *" > $(APP_SRC_DIR)/config/settings.py
# Check if there's a local env file
	test -e $(CURRENT_DIR)/.env.local || (cp $(CURRENT_DIR)/.env.default $(CURRENT_DIR)/.env.local && \
	echo -e "\n  \e[91ma local .env.local was created, adapt it to your needs\e[0m")
	@touch $(SETUP_TIMESTAMP)


# call yapf to make sure your code is easier to read and respects some conventions.
.PHONY: format
format: $(SETUP_TIMESTAMP)
	$(YAPF) -p -i --style .style.yapf $(PYTHON_FILES)
	$(ISORT) $(PYTHON_FILES)


# make sure that the code conforms to the style guide
.PHONY: lint
lint: $(SETUP_TIMESTAMP)
	@echo "Run pylint..."
	$(PYLINT) $(PYTHON_FILES)


# Running tests locally
.PHONY: test
test: $(SETUP_TIMESTAMP)
	mkdir -p $(TEST_REPORT_DIR)
	$(PYTHON) $(DJANGO_MANAGER) test


# Serve targets. Using these will run the application on your local machine. You can either serve with a wsgi front (like it would be within the container), or without.

.PHONY: serve
serve: $(SETUP_TIMESTAMP)
	$(PYTHON) $(DJANGO_MANAGER) runserver

.PHONY: gunicornserve
gunicornserve: $(SETUP_TIMESTAMP)
	$(PYTHON) $(APP_SRC_DIR)/wsgi.py


###################
# Docker related functions.
# Note: the timestamp magic is ommitted here on purpose, we rely on docker's
# change detection mgmt

.PHONY: dockerbuild-test
dockerbuild-test:
	docker build -t $(DOCKER_IMG_LOCAL_TAG_TEST) --target test .

.PHONY: dockerbuild-prod
dockerbuild-prod:
	docker build -t $(DOCKER_IMG_LOCAL_TAG) --target production .


###################
# Dockerrun can be invoked either with just
# "make dockerrun", which will launch the django dev server (runserver)
# or passing another manage.py command, e.g.
# "make dockerrun shell_plus"

# This is some magic to allow for the make anti-pattern "make CMD arg"
args = `arg="$(filter-out $@,$(MAKECMDGOALS))" && echo $${arg:-${1}}`
%:
	@echo "('$@' is not treated as make target, was used as arg to another target)"
    @:

.PHONY: dockerrun
dockerrun: dockerbuild-test
	@echo "starting docker test container with populating ENV from .env.local"
	docker run -it --rm --env-file .env.local --net=host $(DOCKER_IMG_LOCAL_TAG_TEST) $(call args,runserver)


###################
# clean targets

.PHONY: clean_venv
clean_venv:
	rm -rf $(VENV)


.PHONY: clean
clean: clean_venv
	@# clean python cache files
	find . -name __pycache__ -type d -print0 | xargs -I {} -0 rm -rf "{}"
	rm -rf $(PYTHON_LOCAL_DIR)
	rm -rf $(TEST_REPORT_DIR)
	rm -rf $(TIMESTAMPS)
