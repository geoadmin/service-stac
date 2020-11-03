## Specs

The API of this service is based on the [STAC API Specification](https://github.com/radiantearth/stac-api-spec) in version `0.9.0`, which itself is based on the [STAC Specification](https://github.com/radiantearth/stac-spec/tree/v0.9.0) and the [_OGC API - Features_](https://github.com/opengeospatial/ogcapi-features) specification. The default STAC spec is amended by geoadmin-specific parts that are explicitly mentioned in the spec, as well as adapted examples that resemble geoadmin-specific use cases.

The spec is OpenAPI 3.0 compliant. The files are located in `spec/` and slightly split for better understanding. Two different versions of the spec can be compiled from these source files into `spec/static/` folder: an `openapi.yaml` file that contains the 'public' part with the REST endpoint and HTTP methods (mostly GET) defined in the standard spec, and an `openapitransactional.yaml` file that is intended for internal usage and contains info about the additional `/asset` endpoint and additional writing possibilities.

The spec files can be compiled with

```bash
make build-specs
```

and previewed locally with the little html ReDoc wrappers `spec/static/api.html` and `spec/static/apitransactional.html`. The can be served locally by invoking

```bash
make serve-spec
```

which starts a simple http server that can be reached under `http://0.0.0.0:8090` (default port is `8090`, if you need another one, check the Makefile on how to do this).

The generated files along with html wrappers are also included as static targets and are available under `https://<host_env>/api/stac/v0.9/static/api.html`.
