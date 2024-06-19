SHELL = /bin/bash -o pipefail
.DEFAULT_GOAL := help

# List of files that should be merged.
# Note: the keys
# OVERWRITES = overwrites/*.overwrite.yaml

SPEC_HTTP_PORT ?= 8090

COMPONENTS_DIR = ./components
PARTS_COMPONENTS := $(shell find $(COMPONENTS_DIR) -type f -name "*.yaml" -print)
PARTS := openapi.yaml $(PARTS_COMPONENTS)


TRANSACTIONAL_DIR = ./transaction
PARTS_TRANSACTIONAL = $(shell find $(TRANSACTIONAL_DIR) -type f -name "*.yaml" -print)

STATIC_BASE_DIR = static/spec/v1
OPENAPI = $(STATIC_BASE_DIR)/openapi.yaml
OPENAPI_TRANSACTIONAL = $(STATIC_BASE_DIR)/openapitransactional.yaml

YQ ?= docker run --rm -v ${PWD}:/workdir 974517877189.dkr.ecr.eu-central-1.amazonaws.com/external/openapi/yq:3.3.0 yq
OPENAPI_VALIDATOR ?= docker run --volume "$(PWD)":/data 974517877189.dkr.ecr.eu-central-1.amazonaws.com/external/openapi/openapi-validator:0.54.0

all: help


.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo
	@echo "Possible targets:"
	@echo -e " \033[1mLOCAL DOCKER TARGETS\033[0m "
	@echo -e " \033[1mTREAT THE SPECS TARGETS\033[0m "
	@echo "- build-specs              Build the specs"
	@echo "- lint-specs               lint the specs"
	@echo "- serve-specs              serve the specs locally on port $(SPEC_HTTP_PORT)"


.PHONY: build-spec-openapi
build-spec-openapi: $(PARTS)
	$(YQ) merge -x $(PARTS) | \
	sed -E '/\$ref:/s/"\..*?(#.*?)"/"\1"/' > $(OPENAPI)

.PHONY: build-spec-transactional
build-spec-transactional: build-spec-openapi $(OPENAPI) $(PARTS_TRANSACTIONAL)
	$(YQ) merge -x $(OPENAPI) $(PARTS_TRANSACTIONAL) | \
	sed -E '/\$ref:/s/"\..*?(#.*?)"/"\1"/' > $(OPENAPI_TRANSACTIONAL)


.PHONY: build-specs
build-specs: build-spec-openapi build-spec-transactional


.PHONY: lint-specs
lint-specs: build-specs
	$(OPENAPI_VALIDATOR) -e $(OPENAPI)
	$(OPENAPI_VALIDATOR) -e $(OPENAPI_TRANSACTIONAL)


# Start a little server that serves api.html and openapi.yaml
# since ReDoc (the js library used in api.html) cannot load spec
# from file:/// locations, but only from http:// locations
.PHONY: serve-specs
serve-specs: $(OPENAPI_TRANSACTIONAL)
	@echo "Serving http://0.0.0.0:$(SPEC_HTTP_PORT)/api.html"
	@echo "Serving http://0.0.0.0:$(SPEC_HTTP_PORT)/apitransactional.html"
	cd $(STATIC_BASE_DIR) && python3 -m http.server $(SPEC_HTTP_PORT)

