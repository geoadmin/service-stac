# List of files that should be merged.
# Note: the keys
# OVERWRITES = overwrites/*.overwrite.yaml

SPEC_HTTP_PORT ?= 8090

COMPONENTS_DIR = ./components
PARTS_COMPONENTS := $(shell find $(COMPONENTS_DIR) -type f -name "*.yaml" -print)
PARTS := openapi.yaml $(PARTS_COMPONENTS)


TRANSACTIONAL_DIR = ./transaction
PARTS_TRANSACTIONAL = $(shell find $(TRANSACTIONAL_DIR) -type f -name "*.yaml" -print)

STATIC_BASE_DIR = static/spec/v0.9
OPENAPI = $(STATIC_BASE_DIR)/openapi.yaml
OPENAPI_TRANSACTIONAL = $(STATIC_BASE_DIR)/openapitransactional.yaml

.PHONY: build-spec-openapi
build-spec-openapi: $(PARTS)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq:3.3.0 yq merge -x $(PARTS) | \
	sed -E '/\$ref:/s/"\..*?(#.*?)"/"\1"/' > $(OPENAPI)

.PHONY: build-spec-transactional
build-spec-transactional: build-spec-openapi $(OPENAPI) $(PARTS_TRANSACTIONAL)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq:3.3.0 yq merge -x $(OPENAPI) $(PARTS_TRANSACTIONAL) | \
	sed -E '/\$ref:/s/"\..*?(#.*?)"/"\1"/' > $(OPENAPI_TRANSACTIONAL)


.PHONY: build-specs
build-specs: build-spec-openapi build-spec-transactional


.PHONY: lint-specs
lint-specs: build-specs
	docker run --volume "$(PWD)":/data jamescooke/openapi-validator:0.54.0 -e $(OPENAPI)
	docker run --volume "$(PWD)":/data jamescooke/openapi-validator:0.54.0 -e $(OPENAPI_TRANSACTIONAL)


# Start a little server that serves api.html and openapi.yaml
# since ReDoc (the js library used in api.html) cannot load spec
# from file:/// locations, but only from http:// locations
.PHONY: serve-specs
serve-specs: $(OPENAPI_TRANSACTIONAL)
	@echo "Serving http://0.0.0.0:$(SPEC_HTTP_PORT)/api.html"
	@echo "Serving http://0.0.0.0:$(SPEC_HTTP_PORT)/apitransactional.html"
	cd $(STATIC_BASE_DIR) && python3 -m http.server $(SPEC_HTTP_PORT)

