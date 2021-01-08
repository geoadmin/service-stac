from stac_api.utils import get_sha256_multihash

FILE_CONTENT_1 = b'Asset 1 file content'
FILE_CONTENT_2 = b'Asset 2 file content'
FILE_CONTENT_3 = b'Asset 3 file content'

assets = {
    'asset-1': {
        'name': 'asset-1',
        'title': 'Asset 1 Title',
        'description': 'This is a full description of asset 1',
        'eo_gsd': 3.4,
        'geoadmin_lang': 'fr',
        'geoadmin_variant': 'kgrs',
        'proj_epsg': 2056,
        'media_type': "image/tiff; application=geotiff; profile=cloud-optimized",
        'checksum_multihash': get_sha256_multihash(FILE_CONTENT_1),
        'file': FILE_CONTENT_1
    },
    'asset-1-updated': {
        'name': 'asset-2',
        'title': 'Asset 2 Title',
        'description': 'This is a full description of asset 2',
        'eo_gsd': 4,
        'geoadmin_lang': 'de',
        'geoadmin_variant': 'krel',
        'proj_epsg': 2057,
        'media_type': "text/plain"
    },
    'asset-2': {
        'name': 'asset-2',
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
        'name': 'asset-3',
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
    'asset-missing-required': {
        'name': 'asset-missing-required',
    }
}
