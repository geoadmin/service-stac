# Cache Settings Update

> `Status: Accepted`

> `Date: 2025-03-04`

> `Participants: Brice Schaffner, Christoph Böcklin, Benjamin Sugden`

## Context

Cache settings have been implemented using the `update_interval` field that set at the asset upload
level and propagated up to the collection level (see [Cache Settings](2023_02_27_cache_settings.md)).
The propagation up the hierarchy was done via PG trigger and worked fine in the beginning.

But with the growing numbers of assets, items and collections, the PG trigger started to be slow
which had a significant impact on the write Endpoints.

### Proposal

To avoid performance issue due to aggregation accross all assets within a collection, we can set
the cache settings at the collection level and not at the upload level. Also in order to keep it
very simple stupid we can directly set the cache-control header value on the collection instead
of an update interval. So the collection would decide the cache settings for all of its child call.

To do so we create a new field `cache_control_header` in the collection field. To start this field
is only available on the admin interface and not on the API.

For collection aggregation endpoints, like the search endpoint or the collections list endpoint,
which can potentially contain more than one collection, we disable the cache in order to avoid any
caching issue and keep the logic simple.

## Decision

- Remove the `update_interval` field from item and collection model
- Keep the `update_interval` field in the upload and asset models
- Mark the `update_interval` field as deprecated in the models and in the openapi spec
- `update_interval` is kept as a hint but has no effect anymore
- Set the cache-control header of the search and collections list endpoints configurable via
  environment variable with a default to no cache.
- Add a new `cache_control_header` field to the collection model
- Add the new `cache_control_header` field to the admin interface
- For the GET endpoints of collection detail, items, item detail, assets, assets detail and asset
  data download, we either use the value of the related collection `cache_control_header` field or
  the default configured in the environment variable (as for before)

## Consequences

- Actually we have 3 collections that have the `update_interval` field used, so for those once this
  is deployed we need to manually set the value.

## References

- [Cache Settings](2023_02_27_cache_settings.md)
- [Jira PB-1126](https://swissgeoplatform.atlassian.net/issues/PB-1126)
