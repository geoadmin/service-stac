# List of files that should be merged. 
# Note: the keys
# OVERWRITES = overwrites/*.overwrite.yaml

PARTS = base.yml \
		components/parameters.yml \
		components/responses.yml \
		components/schemas.yml \
		paths.yml


PARTS_TRANSACTIONAL = transaction/transaction.yml

OPENAPI = openapi.yaml

# AWS_ACCOUNT = swisstopo-3d

$(OPENAPI): $(PARTS)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq yq merge -a $(PARTS) > $@

openapitransactional.yaml: $(OPENAPI) $(PARTS_TRANSACTIONAL)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq yq merge -x $(OPENAPI) $(PARTS_TRANSACTIONAL) > $@

# Start a little server that serves api.html and openapi.yaml
# since ReDoc (the js library used in api.html) cannot load spec
# from file:/// locations, but only from http:// locations
.PHONY: serve-spec
serve-spec: $(OPENAPI)
	python3 -m http.server


.PHNOY: ltboc
ltboc:
	scp api.html cc-gsd:~/src/public_html/products/data.geo.admin.ch/api.html
	scp openapi.yaml cc-gsd:~/src/public_html/products/data.geo.admin.ch/openapi.yaml
	scp apitransactional.html cc-gsd:~/src/public_html/products/data.geo.admin.ch/apitransactional.html
	scp openapitransactional.yaml cc-gsd:~/src/public_html/products/data.geo.admin.ch/openapitransactional.yaml
