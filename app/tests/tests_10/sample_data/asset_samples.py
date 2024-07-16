from stac_api.utils import get_sha256_multihash

FILE_CONTENT_1 = b'Asset 1 file content'
FILE_CONTENT_2 = b'Asset 2 file content'
FILE_CONTENT_3 = b'Asset 3 file content'

# The keys here are the attribute keys of the model. They are translated to
# json keys when the api is called. (e.g. "name" will be translated to "id" when
# making an api call)
assets = {
    'asset-1': {
        'name': 'asset-1.tiff',
        'title': 'Asset 1 Title',
        'description': 'This is a full description of asset 1',
        'roles': ['data', 'visual'],
        'eo_gsd': 3.4,
        'geoadmin_lang': 'fr',
        'geoadmin_variant': 'kgrs',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=geotiff; profile=cloud-optimized",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_1),
        'file': FILE_CONTENT_1
    },
    'asset-no-checksum': {
        'name': 'asset-1.tiff',
        'title': 'Asset 1 Title',
        'description': 'This is a full description of asset 1',
        'eo_gsd': 3.4,
        'geoadmin_lang': 'fr',
        'geoadmin_variant': 'kgrs',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=geotiff; profile=cloud-optimized",
        'file': FILE_CONTENT_1
    },
    'asset-1-updated': {
        'name': 'asset-2.txt',
        'title': 'Asset 2 Title',
        'description': 'This is a full description of asset 2',
        'eo_gsd': 4,
        'geoadmin_lang': 'de',
        'geoadmin_variant': 'krel',
        'proj_epsg': 2057,
        'media_type': "text/plain"
    },
    'asset-2': {
        'name': 'asset-2.txt',
        'title': 'Asset 2 Title',
        'description': 'This is a full description of asset 2',
        'eo_gsd': 4,
        'geoadmin_lang': 'de',
        'geoadmin_variant': 'krel',
        'proj_epsg': 2057,
        'media_type': "text/plain",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_2),
        'file': FILE_CONTENT_2
    },
    'asset-3': {
        'name': 'asset-3.pdf',
        'title': 'Asset 3 Title',
        'description': 'This is a full description of asset 3',
        'eo_gsd': 5.4,
        'geoadmin_lang': 'en',
        'geoadmin_variant': 'kombs',
        'proj_epsg': 2058,
        'media_type': "application/pdf",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_3),
        'file': FILE_CONTENT_3
    },
    'asset-invalid': {
        'name': 'asset invalid name + other invalid fields',
        'title': 10,
        'description': 56,
        'eo_gsd': 'eo gsd should be a float',
        'geoadmin_lang': 12,
        'geoadmin_variant': 123,
        'proj_epsg': 'should be an int',
        'media_type': "dummy",
        'file': b'Asset 3 file content'
    },
    'asset-invalid-type': {
        'name': 'asset-invalid-type.tiff',
        'title': 'Asset invalid type Title',
        'description': 'This is a full description of asset-invalid-type',
        'eo_gsd': 3.4,
        'geoadmin_lang': 'fr',
        'geoadmin_variant': 'kgrs',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=Geotiff; profile=cloud-optimized",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_1),
        'file': FILE_CONTENT_1
    },
    'asset-missing-required': {
        'name': 'asset-missing-required',
    },
    'asset-valid-geoadmin-variant': {
        'name': 'geodadmin-variant.txt',
        'title': 'Asset Variant',
        'description': 'This asset should pass the test',
        'eo_gsd': 4,
        'geoadmin_lang': 'de',
        'geoadmin_variant': 'twenty5 characters with s',
        'proj_epsg': 2056,
        'media_type': "text/plain",
        'file': b'Asset with long geoadmin:variant'
    },
    'asset-invalid-geoadmin-variant': {
        'name': 'invalid-geodadmin-variant.txt',
        'title': 'Asset Variant Testing',
        'description': 'This asset shouldn\'t pass the test',
        'eo_gsd': 4,
        'geoadmin_lang': 'de',
        'geoadmin_variant': 'more than twenty-five characters with s',
        'proj_epsg': 2056,
        'media_type': "text/plain",
        'file': b'Asset with invalid geoadmin:variant'
    },
    'asset-no-file': {
        'name': 'asset-1.tiff',
        'title': 'Asset 1 Title',
        'description': 'This is a full description of asset 1',
        'eo_gsd': 3.4,
        'geoadmin_lang': 'fr',
        'geoadmin_variant': 'kgrs',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=geotiff; profile=cloud-optimized",
        # use a path instead of a bytes object to avoid creating a file
        'file': 'collection-1/item-1/asset-1.tiff'
    },
}

collection_assets = {
    'asset-1': {
        'name': 'asset-1.tiff',
        'title': 'Asset 1 Title',
        'description': 'This is a full description of asset 1',
        'roles': ['data', 'visual'],
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=geotiff; profile=cloud-optimized",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_1),
        'file': FILE_CONTENT_1
    },
    'asset-no-checksum': {
        'name': 'asset-1.tiff',
        'title': 'Asset 1 Title',
        'description': 'This is a full description of asset 1',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=geotiff; profile=cloud-optimized",
        'file': FILE_CONTENT_1
    },
    'asset-1-updated': {
        'name': 'asset-2.txt',
        'title': 'Asset 2 Title',
        'description': 'This is a full description of asset 2',
        'proj_epsg': 2057,
        'media_type': "text/plain"
    },
    'asset-2': {
        'name': 'asset-2.txt',
        'title': 'Asset 2 Title',
        'description': 'This is a full description of asset 2',
        'proj_epsg': 2057,
        'media_type': "text/plain",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_2),
        'file': FILE_CONTENT_2
    },
    'asset-3': {
        'name': 'asset-3.pdf',
        'title': 'Asset 3 Title',
        'description': 'This is a full description of asset 3',
        'proj_epsg': 2058,
        'media_type': "application/pdf",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_3),
        'file': FILE_CONTENT_3
    },
    'asset-invalid': {
        'name': 'asset invalid name + other invalid fields',
        'title': 10,
        'description': 56,
        'proj_epsg': 'should be an int',
        'media_type': "dummy",
        'file': b'Asset 3 file content'
    },
    'asset-invalid-type': {
        'name': 'asset-invalid-type.tiff',
        'title': 'Asset invalid type Title',
        'description': 'This is a full description of asset-invalid-type',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=Geotiff; profile=cloud-optimized",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_1),
        'file': FILE_CONTENT_1
    },
    'asset-missing-required': {
        'name': 'asset-missing-required',
    },
    'asset-no-file': {
        'name': 'asset-1.tiff',
        'title': 'Asset 1 Title',
        'description': 'This is a full description of asset 1',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=geotiff; profile=cloud-optimized",
        # use a path instead of a bytes object to avoid creating a file
        'file': 'collection-1/item-1/asset-1.tiff'
    },
}
