# List of files that should be merged.
# Note: the keys
# OVERWRITES = overwrites/*.overwrite.yaml

SPEC_HTTP_PORT ?= 8090

PARTS = base.yml \
		components/headers.yml \
		components/parameters.yml \
		components/responses.yml \
		components/schemas.yml \
		paths.yml


PARTS_TRANSACTIONAL = transaction/transaction.yml

STATIC_BASE_DIR = static/spec/v0.9
OPENAPI = $(STATIC_BASE_DIR)/openapi.yaml
OPENAPI_TRANSACTIONAL = $(STATIC_BASE_DIR)/openapitransactional.yaml

# AWS_ACCOUNT = swisstopo-3d

$(OPENAPI): $(PARTS)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq:3.3.0 yq merge -x $(PARTS) > $@

$(OPENAPI_TRANSACTIONAL): $(OPENAPI) $(PARTS_TRANSACTIONAL)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq:3.3.0 yq merge -x $(OPENAPI) $(PARTS_TRANSACTIONAL) > $@


.PHONY: build-specs
build-specs: $(OPENAPI_TRANSACTIONAL)


# Start a little server that serves api.html and openapi.yaml
# since ReDoc (the js library used in api.html) cannot load spec
# from file:/// locations, but only from http:// locations
.PHONY: serve-spec
serve-spec: $(OPENAPI_TRANSACTIONAL)
	@echo "Serving http://0.0.0.0:$(SPEC_HTTP_PORT)/api.html"
	@echo "Serving http://0.0.0.0:$(SPEC_HTTP_PORT)/apitransactional.html"
	cd $(STATIC_BASE_DIR) && python3 -m http.server $(SPEC_HTTP_PORT)

