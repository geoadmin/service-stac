# List of files that should be merged. 
# Note: the keys
# OVERWRITES = overwrites/*.overwrite.yaml

PARTS = base.yml \
		components/parameters.yml \
		components/responses.yml \
		components/schemas.yml \
		paths.yml


PARTS_TRANSACTIONAL = transaction/transaction.yml

# AWS_ACCOUNT = swisstopo-3d

openapi.yaml: $(PARTS)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq yq merge -a $(PARTS) > $@

openapitransactional.yaml: openapi.yaml $(PARTS_TRANSACTIONAL)
	docker run --rm -v ${PWD}:/workdir mikefarah/yq yq merge -x openapi.yaml $(PARTS_TRANSACTIONAL) > $@
