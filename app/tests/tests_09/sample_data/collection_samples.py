providers = {
    'provider-1': {
        'name': 'provider-1',
        'roles': ['licensor', 'producer'],
        'description': 'This is a full description of the provider',
        'url': 'https://www.provider.com'
    },
    'provider-2': {
        'name': 'provider-2',
        'roles': ['licensor'],
        'description': 'This is a full description of a second provider',
        'url': 'https://www.provider.com/provider-2'
    },
    'provider-3': {
        'name': 'provider-3',
    }
}

providers_invalid = {
    'provider-invalid': {
        'name': 'provider invalid ', 'roles': ['Test'], 'url': 'This is not an url'
    },
}

links = {
    'link-1': {
        'rel': 'describedBy',
        'href': 'https://www.example.com/described-by',
        'title': 'This is an extra collection link',
        'link_type': 'description'
    }
}

multiple_links = {
    'link-1': {
        'rel': 'license',
        'href': 'https://www.example1.com/license',
        'title': 'This is an extra collection link',
        'link_type': 'description'
    },
    'link-2': {
        'rel': 'license',
        'href': 'https://www.example2.com/license',
        'title': 'This is another extra collection link',
        'link_type': 'description'
    }
}

links_invalid = {
    'link-invalid': {
        'title': 'invalid collection link relation',
        'rel': 'invalid relation',
        'href': 'not a url',
    }
}

collections = {
    'collection-1': {
        'name': 'collection-1',
        'description': 'This a collection description',
        'title': 'My collection 1',
        'license': 'proprietary',
        'providers': providers.values(),
        'links': links.values()
    },
    'collection-2': {
        'name': 'collection-2',
        'description': 'This a second open source collection description',
        'title': 'My collection 2',
        'license': 'MIT',
        'providers': [providers['provider-2']]
    },
    'collection-3': {
        'name': 'collection-3',
        'description': 'This a third open source collection description',
        'title': 'My collection 3',
        'license': 'MIT',
        'links': [links['link-1']]
    },
    'collection-4': {
        'name': 'collection-3',
        'description': 'This a fourth open source collection description',
        'title': 'My collection 4',
        'license': 'MIT'
    },
    'collection-invalid': {
        'name': 'collection invalid name',
        'description': 45,
        'title': 34,
        'license': ['proprietary'],
    },
    'collection-missing-mandatory-fields': {
        'name': 'collection-missing-mandatory-fields'
    },
    'collection-invalid-links': {
        'name': 'collection-invalid-link',
        'description': 'This is a collection with invalid user link',
        'license': 'proprietary',
        'links': [links_invalid['link-invalid']]
    },
    'collection-multiple-links': {
        'name': 'collection-multiple-link',
        'description': 'This is a collection with multiple user links',
        'license': 'proprietary',
        'links': [multiple_links['link-1'], multiple_links['link-2']]
    },
    'collection-invalid-providers': {
        'name': 'collection-invalid-provider',
        'description': 'This is a collection with invalid provider',
        'license': 'proprietary',
        'providers': providers_invalid.values()
    },
}
