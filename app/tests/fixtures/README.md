# Test fixtures

This folder contains data fixture to be used in tests. See https://docs.djangoproject.com/en/5.1/topics/db/fixtures/.

## E2E tests fixture

The fixture `e2e-tests.json` is loaded by an init container in DEV and INT staging and use then needed by the E2E tests from [geoadmin/infra-e2e-tests](https://github.com/geoadmin/infra-e2e-tests)
