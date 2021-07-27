# Application Architecture

> `Status: accepted`

> `Date: 2020-08-13`

## Context
`service-stac` is a new service with use cases that are different to the ones in all existing services, specially the fully CRUD (create, read, update, delete) REST interface. Therefore, the choice of the application structure cannot simply be borrowed from an existing service. The use cases for this service will involve heavy read/write access to data via JSON REST API interface of a substantial amount of assets and metadata objects (tens to hundreds of Millions). Additionally, data must be editable manually, at least in a start/migration phase.

## Decision
The following decisions are taken regarding the application architecture
- Programming Language **Python**: Python is used in most of the backend services and is the programming language that's best known within devs, so no reason to change here.
- Application Framework **Django**: Django is used as application framework. Django is very mature and has a wide user community. It comes with excellent documentation and a powerfull ORM. Futhermore, there are well-supported and maintained extensions, e.g. for designing REST API's that can considerably reduce the amount of boilerplate code needed for serializing, authentication, ....
- Asset Storage **S3**: Since this service runs on AWS assets will be stored in S3 object store.
- Metadata Storage **PostGIS**: Since Metadata can contain arbitrary geoJSON-supported geometries, Postgres along with the PostGIS extension is used as storage for metadata.

The application architecture does initially only involve syncronous operations. Async tasks will be reconsider once certain write operations don't meet performance requirements anymore.

## Consequences
Developers not familiar with Django will have to walk through the [Django tutorial](https://docs.djangoproject.com/en/dev/intro/) before they get started with development.
