# Generate openapi specs for data.geo.admin.ch

## Base
The spec is based on the OGC-API-Feature spec and a number of extensions:
```
- openapi/OAFeat.yaml 		# official OGC API - Feature spec
- openapi/STAC.yaml 		# official STAC API core
- extensions/query 			# community-proposed extension for extende querying functionality
- extensions/assetquery 	# custom extension to allow querying for asset properties
```

## Build
A complete build including linting can be triggered with `make all`. This combines all for base files and applies all overwrites from `overwrites/`, creates a the output file `openapi.yaml` and applies linting to it.

## Customization
Certain parts of the spec can be overwritten by creating a new file in `overwrites/`, ending in `*.overwrite.yaml`. [`yaml-patch`](https://github.com/krishicks/yaml-patch) is used to define the overwrites. The important parts for the syntax are reproduced below (origin: README.md in https://github.com/krishicks/yaml-patch):

**NOTE: each file must end with an empty newline**

### Syntax

General syntax is the following:

```yaml
- op: <add | remove | replace | move | copy | test>
  from: <source-path> # only valid for the 'move' and 'copy' operations
  path: <target-path> # always mandatory
  value: <any-yaml-structure> # only valid for 'add', 'replace' and 'test' operations
```

#### Paths

Supported YAML path are primarily those of
[RFC 6901 JSON Pointers](https://tools.ietf.org/html/rfc6901).

A syntax extention with `=` was added to match any sub-element in a YAML
structure by key/value.

For example, the following removes all sub-nodes of the `releases` array that
have a `name` key with a value of `cassandra`:

```yaml
- op: remove
  path: /releases/name=cassandra
```

A major caveat with `=`, is that it actually performs a _recursive_ search for
matching nodes. The root node at which the recursive search is initiated, is
the node matched by the path prefix before `=`.

The second caveat is that the recursion stops at a matching node. With the
`add` operation, you could expect sub-nodes of matching nodes to also match,
but they don't.

If your document is the following and you apply the patch above, then all
sub-nodes of `/releases` that match `name=cassandra` will be removed.

```yaml
releases: # a recursive search is made, starting from this node
  - name: cassandra # does match, will be removed
  - - name: toto
    - name: cassandra # does match, will be removed!
      sub:
        - name: cassandra # not matched: the recursion stops at matching parent node
  - super:
      sub:
        name: cassandra # does match, will be removed!
```

##### Path Escaping

As in RFC 6901, escape sequences are introduced by `~`. So, `~` is escaped
`~0`, `/` is escaped `~1`. There is no escape for `=` yet.


#### Operations

Supported patch operations are those of [RFC 6902](https://tools.ietf.org/html/rfc6902).

- [`add`](https://tools.ietf.org/html/rfc6902#section-4.1)
- [`remove`](https://tools.ietf.org/html/rfc6902#section-4.2)
- [`replace`](https://tools.ietf.org/html/rfc6902#section-4.3)
- [`move`](https://tools.ietf.org/html/rfc6902#section-4.4)
- [`copy`](https://tools.ietf.org/html/rfc6902#section-4.5)
- [`test`](https://tools.ietf.org/html/rfc6902#section-4.6)

