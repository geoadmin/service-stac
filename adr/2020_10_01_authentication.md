# Authentication

> `Status: accepted`

> `Date: 2020-10-01`

## Context
`service-stac` will be accepting machine-to-machine communication and will have an admin interface for operations/debugging. Authentication methods for this two use cases need to be defined.

## Decision
Machine-to-machine communication will be using token authentication, access to the admin interface will be granted with usernames/passwords managed in the Django admin interface. At a later stage, this might be changed to a more advanced authentication scheme.

## Consequences
Superuser and regular user permissions will be handled within the application.
