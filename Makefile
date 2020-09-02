SHELL = /bin/bash

.DEFAULT_GOAL := help

SERVICE_NAME := service-stac

CURRENT_DIR := $(shell pwd)
VENV := $(CURRENT_DIR)/.venv
REQUIREMENTS = $(CURRENT_DIR)/requirements.txt
DEV_REQUIREMENTS = $(CURRENT_DIR)/dev_requirements.txt
TEST_REPORT_DIR := $(CURRENT_DIR)/tests/report
TEST_REPORT_FILE := nose2-junit.xml

# Django specific
DJANGO_PROJECT := project
DJANGO_PROJECT_DIR := $(CURRENT_DIR)/$(DJANGO_PROJECT)

# Python local build directory
PYTHON_LOCAL_DIR := $(CURRENT_DIR)/.local

# venv targets timestamps
VENV_TIMESTAMP = $(VENV)/.timestamp
REQUIREMENTS_TIMESTAMP = $(VENV)/.requirements.timestamp
DEV_REQUIREMENTS_TIMESTAMP = $(VENV)/.dev-requirements.timestamp

# general targets timestamps
TIMESTAMPS = .timestamps
SYSTEM_PYTHON_TIMESTAMP = $(TIMESTAMPS)/.python-system.timestamp
PYTHON_LOCAL_BUILD_TIMESTAMP = $(TIMESTAMPS)/.python-build.timestamp
DOCKER_BUILD_TIMESTAMP = $(TIMESTAMPS)/.dockerbuild.timestamp

# Find all python files that are not inside a hidden directory (directory starting with .)
PYTHON_FILES := $(shell find ${DJANGO_PROJECT_DIR}/* -type f -name "*.py" -print)

PYTHON_VERSION := 3.7.4
SYSTEM_PYTHON := $(shell ./getPythonCmd.sh ${PYTHON_VERSION} ${PYTHON_LOCAL_DIR})

# default configuration
HTTP_PORT ?= 5000

# Commands
DJANGO_MANAGER := $(DJANGO_PROJECT_DIR)/manage.py
GUNICORN := $(VENV)/bin/gunicorn
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip3
FLASK := $(VENV)/bin/flask
YAPF := $(VENV)/bin/yapf
NOSE := $(VENV)/bin/nose2
PYLINT := $(VENV)/bin/pylint


all: help


.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo
	@echo "Possible targets:"
	@echo -e " \033[1mSetup TARGETS\033[0m "
	@echo "- setup              Create the python virtual environment"
	@echo "- dev                Create the python virtual environment with developper tools"
	@echo -e " \033[1mFORMATING, LINTING AND TESTING TOOLS TARGETS\033[0m "
	@echo "- format             Format the python source code"
	@echo "- lint               Lint the python source code"
	@echo "- format-lint        Format and lint the python source code"
	@echo "- test               Run the tests"
	@echo -e " \033[1mLOCAL SERVER TARGETS\033[0m "
	@echo "- serve              Run the project using the flask debug server. Port can be set by Env variable HTTP_PORT (default: 5000)"
	@echo "- gunicornserve      Run the project using the gunicorn WSGI server. Port can be set by Env variable DEBUG_HTTP_PORT (default: 5000)"
	@echo "- dockerbuild        Build the project localy using the gunicorn WSGI server inside a container"
	@echo "- dockerrun          Run the project using the gunicorn WSGI server inside a container (exposed port: 5000)"
	@echo "- shutdown           Stop the aforementioned container"
	@echo -e " \033[1mCLEANING TARGETS\033[0m "
	@echo "- clean              Clean genereated files"
	@echo "- clean_venv         Clean python venv"


# Build targets. Calling setup is all that is needed for the local files to be installed as needed.

.PHONY: dev
dev: $(DEV_REQUIREMENTS_TIMESTAMP)


.PHONY: setup
setup: $(REQUIREMENTS_TIMESTAMP)


# linting target, calls upon yapf to make sure your code is easier to read and respects some conventions.

.PHONY: format
format: $(DEV_REQUIREMENTS_TIMESTAMP)
	$(YAPF) -p -i --style .style.yapf $(PYTHON_FILES)


.PHONY: lint
lint: $(DEV_REQUIREMENTS_TIMESTAMP)
	$(PYLINT) $(PYTHON_FILES)


.PHONY: format-lint
format-lint: format lint


# Test target

.PHONY: test
test: $(REQUIREMENTS_TIMESTAMP)
	$(PYTHON) $(DJANGO_MANAGER) test


# Serve targets. Using these will run the application on your local machine. You can either serve with a wsgi front (like it would be within the container), or without.

.PHONY: serve
serve: $(REQUIREMENTS_TIMESTAMP)
	$(PYTHON) $(DJANGO_MANAGER) runserver $(HTTP_PORT)


.PHONY: gunicornserve
gunicornserve: $(REQUIREMENTS_TIMESTAMP)
	#$(GUNICORN) --chdir $(DJANGO_PROJECT_DIR) $(DJANGO_PROJECT).wsgi
	$(PYTHON) $(DJANGO_PROJECT_DIR)/wsgi.py


# Docker related functions.

.PHONY: dockerbuild
dockerbuild: $(DOCKER_BUILD_TIMESTAMP)


.PHONY: dockerrun
dockerrun: $(DOCKER_BUILD_TIMESTAMP)
	export HTTP_PORT=$(HTTP_PORT); docker-compose up -d
	sleep 10


.PHONY: shutdown
shutdown:
	export HTTP_PORT=$(HTTP_PORT); docker-compose down


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


# Actual builds targets with dependencies

$(TIMESTAMPS):
	mkdir -p $(TIMESTAMPS)

$(VENV_TIMESTAMP): $(SYSTEM_PYTHON_TIMESTAMP)
	test -d $(VENV) || $(SYSTEM_PYTHON) -m venv $(VENV) && $(PIP) install --upgrade pip setuptools
	@touch $(VENV_TIMESTAMP)


$(REQUIREMENTS_TIMESTAMP): $(VENV_TIMESTAMP) $(REQUIREMENTS)
	$(PIP) install -U pip wheel; \
	$(PIP) install -r $(REQUIREMENTS);
	@touch $(REQUIREMENTS_TIMESTAMP)


$(DEV_REQUIREMENTS_TIMESTAMP): $(REQUIREMENTS_TIMESTAMP) $(DEV_REQUIREMENTS)
	$(PIP) install -r $(DEV_REQUIREMENTS)
	@touch $(DEV_REQUIREMENTS_TIMESTAMP)


$(DOCKER_BUILD_TIMESTAMP): $(TIMESTAMPS) $(PYTHON_FILES) $(CURRENT_DIR)/Dockerfile
	docker build -t swisstopo/$(SERVICE_NAME):local .
	touch $(DOCKER_BUILD_TIMESTAMP)


# Python local build target

ifneq ($(SYSTEM_PYTHON),)

# A system python matching version has been found use it
$(SYSTEM_PYTHON_TIMESTAMP): $(TIMESTAMPS)
	@echo "Using system" $(shell $(SYSTEM_PYTHON) --version 2>&1)
	touch $(SYSTEM_PYTHON_TIMESTAMP)


else

# No python version found, build it localy
$(SYSTEM_PYTHON_TIMESTAMP): $(TIMESTAMPS) $(PYTHON_LOCAL_BUILD_TIMESTAMP)
	@echo "Using local" $(shell $(SYSTEM_PYTHON) --version 2>&1)
	touch $(SYSTEM_PYTHON_TIMESTAMP)


$(PYTHON_LOCAL_BUILD_TIMESTAMP): $(TIMESTAMPS)
	@echo "Building a local python..."
	mkdir -p $(PYTHON_LOCAL_DIR);
	curl -z $(PYTHON_LOCAL_DIR)/Python-$(PYTHON_VERSION).tar.xz https://www.python.org/ftp/python/$(PYTHON_VERSION)/Python-$(PYTHON_VERSION).tar.xz -o $(PYTHON_LOCAL_DIR)/Python-$(PYTHON_VERSION).tar.xz;
	cd $(PYTHON_LOCAL_DIR) && tar -xf Python-$(PYTHON_VERSION).tar.xz && Python-$(PYTHON_VERSION)/configure --prefix=$(PYTHON_LOCAL_DIR)/ && make altinstall
	touch $(PYTHON_LOCAL_BUILD_TIMESTAMP)

SYSTEM_PYTHON := $(PYTHON_LOCAL_DIR)/python

endif

