'''Data Factory module

The data factory can and should be used in unittests for creating sample data. A sample data can be
used either to create an object in DB and returning its corresponding django model object, and/or
for creating a JSON sample to be used in a Rest Framework serializer and/or in a HTTP request
payload.

Create samples
==============

Samples are located in the `tests.sample_data` module. The simplest way to get a sample is by using
the Factory class as follow:

    sample = Factory().create_collection_sample()

This line above creates a collection sample named `'collection-1'` using the
`sample_data.collection_samples.collections['collection-1']` as data base.

NOTE: A Factory instance keeps tracks of samples and avoids creating duplicate samples,
so you might want to keep a Factory instance in your test case to reuse it. This way if you call the
`create_collection_sample()` method again, the new sample will be named `'collection-2'` instead of
`'collection-1'`.

While creating a sample you can freely overwrite any attribute or add extra attribute by using
keywords arguments.

    sample = Factory().create_collection_sample(title='My personal title',
                                                extra_argument='This is an extra argument')

You can also define your own sample name with the `name` argument and/or choose another sample data
base with the `sample` argument.

NOTE: the sample attribute should not have any special characters and should be the same as the
Django model fields name. Each sample class as a `key_mapping` attribute that maps the sample
attribute name from model to JSON: for example the Asset `name` attribute is mapped into `id`,
the Asset `checksum_multihash` is mapped into `checksum:multihash`, etc.

You can also creates multiple samples at a time:

    samples = Factory().create_collection_samples(5)

This creates 5 collections samples: `'collection-1'`, `'collection-2'`, `'collection-3'`, ...

    samples = Factory().create_collection_samples(['collection-1',
                                                   'collection-2',
                                                   'collection-invalid'])

This creates 3 collections samples:
- 'collection-1' based on 'collection-1' sample
- 'collection-2' based on 'collection-2' sample
- 'collection-3' based on 'collection-invalid' sample

You can also overwrite sample attribute of each sample:

    samples = Factory().create_collection_samples(3, title=['Title of first collection',
                                                            'Title of second collection',
                                                            'Title of third collection'])

Using samples
=============

Each attribute of a sample can be retrieved/set using either the `get()`/`set()` method or the
dictionary way: `sample[key]`.

    print(sample.get('name')) or  print(sample['name'])

To use the sample with a Django model, uses the `sample.attributes` property or
`sample.get_attributes()` method.

    stac_api.models.Collection(**sample.attributes)

You can also use the shorthand sample.model property to get a django model instances with the
sample. The corresponding DB object is then automatically created on the first call of sample.model.

    model_instance = sample.model

To use the sample as an HTTP request payload or as serializer data, uses the sample.json property
or the `sample.get_json()` method or `sample.json` property (alias for
`sample.get_json(method='get')`).

   stac_api.serializer.ItemSerializer(data=sample.get_json(method='deserialize'))

   response = client.get(path_to_item)
   self.check_stac_item(sample.json, response.json(), 'collection-1')

'''
# pylint: disable=too-many-lines, arguments-differ
import copy
import hashlib
import logging
import re
from datetime import datetime

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.base import File
from django.core.files.uploadedfile import SimpleUploadedFile

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Provider
from stac_api.utils import get_s3_resource
from stac_api.utils import isoformat
from stac_api.validators import get_media_type

from tests.sample_data.asset_samples import assets as asset_samples
from tests.sample_data.collection_samples import collections as collection_samples
from tests.sample_data.collection_samples import links as collection_link_samples
from tests.sample_data.collection_samples import providers as provider_samples
from tests.sample_data.item_samples import items as item_samples
from tests.sample_data.item_samples import links as item_link_samples

logger = logging.getLogger(__name__)


class SampleData:
    '''Sample data base class
    '''
    model_class = models.Model
    sample_name = ''
    samples_dict = {}
    key_mapping = {}
    optional_fields = []
    read_only_fields = []

    def __init__(self, sample, required_only=False, **kwargs):
        self.sample = sample
        try:
            sample = self.samples_dict[sample]
        except KeyError as error:
            raise KeyError(f'Unknown {self.sample_name} sample: {error}') from None

        # Sets attributes from sample
        for key, value in sample.items():
            setattr(self, f'attr_{key}', value)

        if required_only:
            # remove optional fields
            self._filter_optional(self.optional_fields)

        # overwrite/add sample data with kwargs
        for key, value in kwargs.items():
            setattr(self, f'attr_{key}', value)

        self.model_instance = None

    def __call__(self, *args, **kwargs):
        '''Short hand for .json
        '''
        return self.json(*args, **kwargs)

    def __getitem__(self, key):
        if hasattr(self, f'attr_{key}'):
            return getattr(self, f'attr_{key}')
        raise KeyError(f'Sample key {key} doesn\'t exists')

    def __setitem__(self, key, value):
        setattr(self, f'attr_{key}', value)

    def get(self, key, default=None):
        '''Returns the sample key

        If the key doesn't exists then it returns the default value. In opposite to sample[key],
        this function doesn't raise KeyError if the key attribute doesn't exists.

        Args:
            key: string
                Key of the sample attribute to return.
            default: any
                Default value to return if the key is not found.

        Returns:
            Asset key value.
        '''
        return getattr(self, f'attr_{key}', default)

    def set(self, key, value):
        '''Set sample key value

        Alias of sample[key] = value

        Args:
            key: string
                Key of the sample attribute to set.
            value:
                Value to set.
        '''
        setattr(self, f'attr_{key}', value)

    def get_attributes(self, remove_relations=True):
        '''Returns the sample data attributes as dictionary

        This can be used as arguments for the model class.

        Args:
            remove_relations: bool
                Remove relational attributes (providers and links).

        Returns:
            Dictionary with the sample attributes to use to create a DB object.
        '''
        return {
            key[5:]: self.__dict__[key]
            for key in filter(lambda key: key.startswith('attr_'), self.__dict__.keys())
        }

    @property
    def attributes(self):
        '''Returns the sample data attributes as dictionary

        This can be used as arguments for the model class.

        Returns:
            Dictionary with the sample attributes to use to create a DB object.
        '''
        return self.get_attributes()

    def key_mapped(self, key):
        '''Map an attribute key into a json key

        Some attributes in the model are different from the one for the serializer, this is the
        mapping between the two.

        Args:
            key: string
                Key attribute to map into json key.

        Returns:
            string, json key mapped
        '''
        return self.key_mapping.get(key, key)

    def create(self):
        '''Create the sample in DB

        Returns:
            The DB sample (model object).
        '''
        self.model_instance = self.model_class(**self.attributes)
        self.model_instance.full_clean()
        self.model_instance.save()
        self.model_instance.refresh_from_db()
        return self.model_instance

    def copy(self):
        '''Returns a copy of the sample

        Returns:
            A copy of the sample
        '''
        return copy.copy(self)

    def get_json(self, method='get', keep_read_only=False):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload (with method='post', 'put' or
        'patch') or to check the read API payload. It can also be directly used as the serializer
        data.

        Args:
            method: string
                Method for which the JSON would be used; 'get', 'post', 'put', 'patch', 'serialize',
                'deserialize'.
            keep_read_only: bool
                keep read only fields in the json output. By default they are removed if the method
                is 'post', 'put' or 'patch'.

        Returns
            A dictionary with the sample data.
        '''
        self._check_get_json_method(method)
        return {
            self.key_mapped(key): value
            for key,
            value in self.get_attributes(remove_relations=False).items()
            if keep_read_only or self._filter_read_only_field(method, self.key_mapped(key))
        }

    @property
    def json(self):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload or to check
        the read API payload. It can also be directly used as the serializer data.

        NOTE: this output is usually for GET method.

        Returns
            A dictionary with the sample data.
        '''
        return self.get_json(method='get')

    @property
    def model(self):
        '''Returns a django DB model object of sample data

        If the data has not yet been created in DB, then it is created.

        Returns:
            Model instance.
        '''
        if not self.model_instance:
            self.create()
        return self.model_instance

    def _filter_optional(self, optional_attributes):
        '''Remove optional attributes'''
        for attribute in optional_attributes:
            attribute = f'attr_{attribute}'
            if hasattr(self, attribute):
                delattr(self, attribute)

    def _check_get_json_method(self, method):
        if method not in ['get', 'post', 'put', 'patch', 'serialize', 'deserialize']:
            raise ValueError(f'Invalid get_json() method parameter: {method}')

    def _filter_read_only_field(self, method, field):
        '''Returns True if the field needs to be added to the json output, False otherwise
        '''
        # return always read only fields for GET method
        if method in ['get', 'serialize']:
            return True
        if field in self.read_only_fields:
            # do not add read only fields to the json output for POST/PUT/PATCH/DEL and deserialize
            return False
        return True


class LinkSample(SampleData):
    '''Link Sample Data base class
    '''
    key_mapping = {'link_type': 'type'}
    optional_fields = ['title', 'link_type']

    def __init__(self, sample='link-1', rel=None, **kwargs):
        '''Create a link sample data
        '''
        super().__init__(sample=sample, rel=rel, **kwargs)


class ProviderSample(SampleData):
    '''Collection's Provider Sample Data
    '''
    model_class = Provider
    sample_name = 'provider'
    samples_dict = provider_samples
    optional_fields = ['description', 'roles', 'url']

    def __init__(self, sample='provider-1', name=None, **kwargs):
        '''Create a collection's provider sample data
        '''
        super().__init__(sample=sample, name=name, **kwargs)


class CollectionLinkSample(LinkSample):
    '''Collection's Link Sample Data
    '''
    model_class = CollectionLink
    sample_name = 'collection-link'
    samples_dict = collection_link_samples


class CollectionSample(SampleData):
    '''Collection Sample Data
    '''
    model_class = Collection
    sample_name = 'collection'
    samples_dict = collection_samples
    key_mapping = {'name': 'id'}
    optional_fields = ['title', 'providers', 'links']
    read_only_fields = [
        'crs',
        'created',
        'updated',
        'extent',
        'summaries',
        'stac_extensions',
        'stac_version',
        'itemType'
    ]

    def __init__(self, sample='collection-1', name=None, required_only=False, **kwargs):
        '''Create a collection sample data

        Args:
            sample: string
                Name of the sample based to use, see tests.sample_data.collection_samples.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            name: string
                Overwrite the sample name.
            **kwargs:
                Any parameter will overwrite existing attributes.
        '''
        super().__init__(sample, name=name, required_only=required_only, **kwargs)

        if hasattr(self, 'attr_providers'):
            self.attr_providers = [ProviderSample(**provider) for provider in self.attr_providers]

        if hasattr(self, 'attr_links'):
            self.attr_links = [CollectionLinkSample(**link) for link in self.attr_links]

        self.model_providers_instance = []
        self.model_links_instance = []

    def get_attributes(self, remove_relations=True):
        '''Returns the sample data attributes as dictionary

        This can be used as arguments for the model class.

        Args:
            remove_relations: bool
                Remove relational attributes (providers and links).

        Returns:
            Dictionary with the sample attributes to use to create a DB object
        '''
        attributes = super().get_attributes(remove_relations)
        providers = attributes.pop('providers', [])
        links = attributes.pop('links', [])
        if not remove_relations and providers:
            attributes['providers'] = [provider.attributes for provider in providers]
        if not remove_relations and links:
            attributes['links'] = [link.attributes for link in links]
        return attributes

    def create(self):
        '''Create the sample in DB

        Returns:
            the DB sample (model object).
        '''
        attributes = self.get_attributes(remove_relations=False)
        providers = attributes.pop('providers', [])
        links = attributes.pop('links', [])
        self._create_model(attributes)
        if not self.model_providers_instance:
            self._create_model_providers(providers)
        if not self.model_links_instance:
            self._create_model_links(links)
        return self.model_instance

    def get_json(self, method='get', keep_read_only=False):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload (with method='post', 'put' or
        'patch') or to check the read API payload. It can also be directly used as the serializer
        data.

        Args:
            method: string
                Method for which the JSON would be used; 'get', 'post', 'put', 'patch', 'serialize',
                'deserialize'.
            keep_read_only: bool
                keep read only fields in the json output. By default they are removed if the method
                is 'post', 'put' or 'patch'.

        Returns
            A dictionary with the sample data.
        '''
        json_data = super().get_json(method, keep_read_only)
        providers = json_data.pop('providers', [])
        links = json_data.pop('links', [])
        if providers:
            json_data['providers'] = [provider.json for provider in self.attr_providers]
        if links:
            json_data['links'] = [link.json for link in self.attr_links]
        return json_data

    @property
    def model_providers(self):
        '''Returns a django DB model object of the providers sample data

        If the data has not yet been created in DB, then it is created.

        Returns:
            List of provider model instances.
        '''
        if not self.model_providers_instance:
            attributes = self.get_attributes(remove_relations=False)
            providers = attributes.pop('providers', [])
            if not self.model_instance:
                self._create_model(attributes)
            self._create_model_providers(providers)
        return self.model_providers_instance

    @property
    def model_links(self):
        '''Returns a django DB model object of the links sample data

        If the data has not yet been created in DB, then it is created.

        Returns:
            List of link model instances.
        '''
        if not self.model_links_instance:
            attributes = self.get_attributes(remove_relations=False)
            links = attributes.pop('links', [])
            if not self.model_instance:
                self._create_model(attributes)
            self._create_model_links(links)
        return self.model_links_instance

    def _create_model(self, attributes):
        attributes.pop('providers', None)
        attributes.pop('links', None)
        self.model_instance = Collection(**attributes)
        self.model_instance.full_clean()
        self.model_instance.save()

    def _create_model_providers(self, providers):
        for provider in providers:
            provider_instance = Provider(collection=self.model_instance, **provider)
            provider_instance.full_clean()
            provider_instance.save()
            self.model_providers_instance.append(provider_instance)

    def _create_model_links(self, links):
        for link in links:
            link_instance = CollectionLink(collection=self.model_instance, **link)
            link_instance.full_clean()
            link_instance.save()
            self.model_links_instance.append(link_instance)


class ItemLinkSample(LinkSample):
    '''Item's Link Sample Data
    '''
    model_class = ItemLink
    sample_name = 'item-link'
    samples_dict = item_link_samples


class ItemSample(SampleData):
    '''Item Sample Data
    '''
    model_class = Item
    sample_name = 'item'
    samples_dict = item_samples
    key_mapping = {'name': 'id'}
    optional_fields = ['properties_title', 'links']
    read_only_fields = [
        'type',
        'bbox',
        'collection',
        'assets',
        'stac_extensions',
        'stac_version',
        'properties_created',
        'properties_updated'
    ]

    def __init__(self, collection, sample='item-1', name=None, required_only=False, **kwargs):
        '''Create a item sample data

        Args:
            collection: Collection
                Collection DB object relations.
            sample: string
                Name of the sample based to use, see tests.sample_data.item_samples.items.
            name: string
                Overwrite the sample name.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            **kwargs:
                Any parameter will overwrite existing attributes.
        '''
        super().__init__(
            sample, collection=collection, name=name, required_only=required_only, **kwargs
        )

        if hasattr(self, 'attr_links'):
            self.attr_links = [ItemLinkSample(**link) for link in self.attr_links]

        self.model_links_instance = []

    def get_attributes(self, remove_relations=True):
        '''Returns the sample data attributes as dictionary

        This can be used to create new DB object.

        Args:
            remove_relations: bool
                Remove relational attributes (links).

        Returns:
            Dictionary with the sample attributes to use to create a DB object.
        '''
        attributes = super().get_attributes(remove_relations)

        links = attributes.pop('links', None)
        if not remove_relations and links:
            attributes['links'] = [link.attributes for link in links]
        return attributes

    def get_json(self, method='get', keep_read_only=False):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload (with method='post', 'put' or
        'patch') or to check the read API payload. It can also be directly used as the serializer
        data.

        Args:
            method: string
                Method for which the JSON would be used; 'get', 'post', 'put', 'patch', 'serialize',
                'deserialize'.
            keep_read_only: bool
                keep read only fields in the json output. By default they are removed if the method
                is 'post', 'put' or 'patch'.

        Returns
            A dictionary with the sample data.
        '''
        json_data = {
            key: value
            for key,
            value in super().get_json(method, keep_read_only).items()
            if not key.startswith('properties_')
        }
        if method in ['get', 'serialize']:
            collection = self.get('collection')
            json_data['collection'] = collection.name
        if 'geometry' in json_data and isinstance(json_data['geometry'], GEOSGeometry):
            json_data['geometry'] = json_data['geometry'].json
        if not 'properties' in json_data:
            json_data['properties'] = self._get_properties()
        links = json_data.pop('links', [])
        if links:
            json_data['links'] = [link.json for link in self.attr_links]
        return json_data

    def create(self):
        '''Create the sample in DB

        Returns:
            The DB sample (model object).
        '''
        attributes = self.get_attributes(remove_relations=False)
        links = attributes.pop('links', [])
        self._create_model(attributes)
        if not self.model_links_instance and links:
            self._create_model_links(links)
        return self.model_instance

    @property
    def model_links(self):
        '''Returns a django DB model object of the links sample data

        If the data has not yet been created in DB, then it is created.

        Returns:
            List of link model instances.
        '''
        if not self.model_links_instance:
            attributes = self.get_attributes(remove_relations=False)
            links = attributes.pop('links', [])
            if not self.model_instance:
                self._create_model(attributes)
            self._create_model_links(links)
        return self.model_links_instance

    def _get_properties(self):
        properties = {}
        for attribute in self.__dict__:
            if not attribute.startswith('attr_properties_'):
                continue
            key = attribute[16:]
            value = getattr(self, attribute)
            properties[key] = value
            if key.endswith('datetime') and isinstance(value, datetime):
                properties[key] = isoformat(value)

        return properties

    def _create_model(self, attributes):
        attributes.pop('links', None)
        self.model_instance = Item(**attributes)
        self.model_instance.full_clean()
        self.model_instance.save()

    def _create_model_links(self, links):
        for link in links:
            link_instance = ItemLink(item=self.model_instance, **link)
            link_instance.full_clean()
            link_instance.save()
            self.model_links_instance.append(link_instance)


class AssetSample(SampleData):
    '''Asset Sample Data
    '''
    model_class = Asset
    sample_name = 'asset'
    samples_dict = asset_samples
    key_mapping = {
        'name': 'id',
        'eo_gsd': 'eo:gsd',
        'geoadmin_variant': 'geoadmin:variant',
        'geoadmin_lang': 'geoadmin:lang',
        'proj_epsg': 'proj:epsg',
        'media_type': 'type',
        'checksum_multihash': 'checksum:multihash',
        'file': 'href'
    }
    optional_fields = [
        'title',
        'description',
        'eo_gsd',
        'geoadmin_variant',
        'geoadmin_lang',
        'proj_epsg',
        'checksum_multihash'
    ]
    read_only_fields = ['created', 'updated', 'href', 'checksum:multihash']

    def __init__(self, item, sample='asset-1', name=None, required_only=False, **kwargs):
        '''Create a item sample data

        Args:
            item: Item
                Item DB object relations.
            sample: string
                Name of the sample based to use, see tests.sample_data.asset_samples.assets.
            name: string
                Overwrite the sample name.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            **kwargs:
                Any parameter will overwrite existing attributes.
        '''
        self.attr_name = name
        super().__init__(sample, item=item, name=name, required_only=required_only, **kwargs)

        file = getattr(self, 'attr_file', None)
        file_path = f'{item.collection.name}/{item.name}/{self.attr_name}'
        if isinstance(file, bytes):
            self.attr_file = SimpleUploadedFile(file_path, file, self.get('media_type'))

    def get_json(self, method='get', keep_read_only=False):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload (with method='post', 'put' or
        'patch') or to check the read API payload. It can also be directly used as the serializer
        data.

        Args:
            method: string
                Method for which the JSON would be used; 'get', 'post', 'put', 'patch', 'serialize',
                'deserialize'.
            keep_read_only: bool
                keep read only fields in the json output. By default they are removed if the method
                is 'post', 'put' or 'patch'

        Returns
            A dictionary with the sample data.
        '''
        data = super().get_json(method, keep_read_only)
        item = data.pop('item')
        if 'href' in data and isinstance(data['href'], File):
            data['href'] = \
                f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{item.collection.name}/{item.name}/{data["href"].name}'
        return data

    def create_asset_file(self):
        '''Create the asset File on S3 based on the binary content of attribute file

        NOTE: This method will overwrite any existing file on S3
        '''
        item = getattr(self, 'attr_item')
        file = getattr(self, 'attr_file', None)
        file_path = f'{item.collection.name}/{item.name}/{self.attr_name}'
        if file is None:
            raise ValueError('Cannot create Asset file on S3 when attribute file is None')
        self._create_file_on_s3(file_path, self.attr_file)

    def _create_file_on_s3(self, file_path, file):
        s3 = get_s3_resource()
        obj = s3.Object(settings.AWS_STORAGE_BUCKET_NAME, file_path)
        obj.upload_fileobj(
            file,
            ExtraArgs={
                'Metadata': {
                    'sha256': hashlib.sha256(file.read()).hexdigest()
                },
                "CacheControl": f"max-age={settings.STORAGE_ASSETS_CACHE_SECONDS}, public"
            }
        )


class FactoryBase:
    '''Factory base class
    '''
    factory_name = 'base'
    sample_class = SampleData

    def __init__(self):
        self.last = None

    @classmethod
    def get_last_name(cls, last, extension=''):
        '''Return a factory name incremented by one (e.g. 'collection-1')
        '''
        if last is None:
            last = f'{cls.factory_name}-0{extension}'
        last = '{}-{}{}'.format(
            cls.factory_name,
            int(re.match(fr"{cls.factory_name}-(\d+)(\.\w+)?", last).group(1)) + 1,
            extension
        )
        return last

    def create_sample(self, sample, name=None, db_create=False, **kwargs):
        '''Create a data sample

        Args:
            sample: string
                Sample based on the sample named found in tests.sample_data.
            name: string
                Data name, if not given it creates a '{factory_name}-n' with n being incremented
                after each function call.
            db_create: bool
                Create the sample in the DB.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample.
        '''
        if name:
            data_sample = self.sample_class(sample=sample, name=name, **kwargs)
        else:
            self.last = self.get_last_name(self.last)
            data_sample = self.sample_class(sample=sample, name=self.last, **kwargs)
        if db_create:
            data_sample.create()
        return data_sample

    def create_samples(self, samples, db_create=False, kwargs_list=True, **kwargs):
        '''Creates several samples

        Args:
            samples: integer | [string]
                Number of DB sample to create or list of sample data name.
            db_create: bool
                Create the sample in the DB.
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample..

        Returns:
            Array with the DB samples
        '''
        db_samples = []
        if isinstance(samples, int):
            samples = map(lambda i: None, range(samples))
        for i, sample_name in enumerate(samples):
            sample_kwargs = {
                key: value[i] if isinstance(value, list) and kwargs_list else value for key,
                value in kwargs.items()
            }
            if sample_name:
                sample_kwargs['sample'] = sample_name
            sample = self.create_sample(db_create=db_create, **sample_kwargs)
            db_samples.append(sample)
        return db_samples


class ProviderFactory(FactoryBase):
    factory_name = 'provider'
    sample_class = ProviderSample


class LinkFactory(FactoryBase):
    factory_name = 'relation'

    def create_sample(
        self, sample=None, name=None, db_create=False, rel=None, required_only=False, **kwargs
    ):
        '''Create a data sample

        Args:
            rel: string
                Data rel, if not given it creates a 'rel-n' with n being incremented
                after each function call.
            sample: string
                Sample based on the sample named found in tests.sample_data.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample.
        '''
        if rel:
            return self.sample_class(
                sample=sample,
                name=name,
                db_create=db_create,
                rel=rel,
                required_only=required_only,
                **kwargs
            )
        self.last = self.get_last_name(self.last)
        return self.sample_class(
            rel=self.last, sample=sample, required_only=required_only, **kwargs
        )


class CollectionLinkFactory(LinkFactory):
    factory_name = 'collection-link'
    sample_class = CollectionLinkSample


class CollectionFactory(FactoryBase):
    factory_name = 'collection'
    sample_class = CollectionSample

    def create_sample(
        self,
        name=None,
        sample='collection-1',
        db_create=False,
        required_only=False,
        **kwargs
    ):  # pylint: disable=arguments-renamed
        '''Create a collection data sample

        Args:
            name: string
                Data name, if not given it creates a 'collection-n' with n being incremented
                after each function call.
            sample: string
                Sample based on the sample named found in
                tests.sample_data.collection_samples.collections dictionary.
            db_create: bool
                Create the sample in the DB.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample
        '''
        return super().create_sample(
            name=name, sample=sample, db_create=db_create, required_only=required_only, **kwargs
        )

    def create_samples(self, samples, db_create=False, kwargs_list=True, **kwargs):
        '''Creates several Collection samples

        Args:
            samples: integer | [string]
                Number of DB sample to create or list of sample data name. These names should be
                in the dictionary keys of tests.sample_data.collection_samples.collections.
            db_create: bool
                Create the sample in the DB.
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            Array with the DB samples
        '''
        return super().create_samples(
            samples, db_create=db_create, kwargs_list=kwargs_list, **kwargs
        )


class ItemLinkFactory(FactoryBase):
    factory_name = 'item-link'
    sample_class = ItemLinkSample


class ItemFactory(FactoryBase):
    factory_name = 'item'
    sample_class = ItemSample

    def create_sample(
        self,
        collection,
        name=None,
        sample='item-1',
        db_create=False,
        required_only=False,
        **kwargs
    ):  # pylint: disable=arguments-renamed
        '''Create an Item data sample

        Args:
            collection: Collection
                Collection model object in which to create an Item.
            name: string
                Data name, if not given it creates a 'item-n' with n being incremented
                after each function call.
            sample: string
                Sample based on the sample named found in tests.sample_data.item_samples.items
                dictionary.
            db_create: bool
                Create the sample in the DB.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample
        '''
        sample = super().create_sample(
            sample,
            collection=collection,
            name=name,
            db_create=db_create,
            required_only=required_only,
            **kwargs
        )
        if db_create:
            collection.refresh_from_db()
        return sample

    def create_samples(self, samples, collection, db_create=False, kwargs_list=True, **kwargs):  # pylint: disable=arguments-renamed
        '''Creates several Item samples

        Args:
            samples: integer | [string]
                Number of DB sample to create or list of sample data name. These names should be
                in the dictionary keys of tests.sample_data.item_samples.items.
            collection: Collection
                Collection model object in which to create an Item.
            db_create: bool
                Create the sample in the DB.
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            Array with the DB samples
        '''
        return super().create_samples(
            samples, collection=collection, db_create=db_create, kwargs_list=kwargs_list, **kwargs
        )


class AssetFactory(FactoryBase):
    factory_name = 'asset'
    sample_class = AssetSample

    def create_sample(
        self,
        item,
        name=None,
        sample='asset-1',
        db_create=False,
        required_only=False,
        create_asset_file=False,
        **kwargs
    ):  # pylint: disable=arguments-renamed
        '''Create an Asset data sample

        Args:
            item: Item
                Item model object in which to create an Asset.
            name: string
                Data name, if not given it creates a 'asset-n' with n being incremented
                after each function call.
            sample: string
                Sample based on the sample named found in tests.sample_data.asset_samples.assets
                dictionary.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            create_asset_file: bool
                Create the asset file on S3.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample
        '''
        if name:
            data_sample = AssetSample(
                item, sample=sample, name=name, required_only=required_only, **kwargs
            )
        else:
            self.last = self.get_last_name(self.last, extension=self._get_extension(sample, kwargs))
            data_sample = AssetSample(
                item, sample=sample, name=self.last, required_only=required_only, **kwargs
            )
        if db_create:
            data_sample.create()
            item.refresh_from_db()
        if not db_create and create_asset_file:
            # when db_create is true, the asset file automatically created therefore it is not
            # necessary to explicitely create it again.
            data_sample.create_asset_file()
        return data_sample

    def create_samples(self, samples, item, db_create=False, create_asset_file=False, **kwargs):  # pylint: disable=arguments-renamed
        '''Creates several Asset samples

        Args:
            samples: integer | [string]
                Number of DB sample to create or list of sample data name. These names should be
                in the dictionary keys of tests.sample_data.asset_samples.assets.
            db_create: bool
                Create the sample in the DB.
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            create_asset_file: bool
                Create the asset file on S3.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            Array with the DB samples.
        '''
        return super().create_samples(
            samples, item=item, db_create=db_create, create_asset_file=create_asset_file, **kwargs
        )

    def _get_extension(self, sample_name, kwargs):
        media = 'text/plain'
        if 'media_type' in kwargs:
            media = kwargs['media_type']
        else:
            try:
                sample = AssetSample.samples_dict[sample_name]
            except KeyError as error:
                raise KeyError(f'Unknown {sample_name} sample: {error}') from None
            if 'media_type' in sample:
                media = sample['media_type']
        try:
            return get_media_type(media).extensions[0]
        except KeyError:
            return get_media_type('text/plain').extensions[0]


class Factory:
    '''Factory for data samples (Collection, Item and Asset)
    '''

    def __init__(self):
        self.collections = CollectionFactory()
        self.items = ItemFactory()
        self.assets = AssetFactory()

    def create_collection_sample(
        self, name=None, sample='collection-1', db_create=False, required_only=False, **kwargs
    ):
        '''Create a collection data sample

        Args:
            name: string
                Data name, if not given it creates a 'collection-n' with n being incremented
                after each function call.
            sample: string
                Sample based on the sample named found in
                tests.sample_data.collection_samples.collections dictionary.
            db_create: bool
                Create the sample in the DB.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample.
        '''
        return self.collections.create_sample(
            name=name, sample=sample, db_create=db_create, required_only=required_only, **kwargs
        )

    def create_collection_samples(self, samples, db_create=False, **kwargs):
        '''Creates several Collection samples

        Args:
            samples: integer | [string]
                Number of DB sample to create or list of sample data name. These names should be
                in the dictionary keys of tests.sample_data.collection_samples.collections.
            db_create: bool
                Create the sample in the DB.
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            Array with the DB samples.
        '''
        return self.collections.create_samples(samples, db_create=db_create, **kwargs)

    def create_item_sample(
        self,
        collection,
        name=None,
        sample='item-1',
        db_create=False,
        required_only=False,
        **kwargs
    ):
        '''Create an Item data sample

        Args:
            collection: Collection
                Collection model object in which to create an Item
            name: string
                Data name, if not given it creates a 'item-n' with n being incremented
                after each function call.
            sample: string
                Sample based on the sample named found in tests.sample_data.item_samples.items
                dictionary.
            db_create: bool
                Create the sample in the DB.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample.
        '''
        return self.items.create_sample(
            collection,
            name=name,
            sample=sample,
            db_create=db_create,
            required_only=required_only,
            **kwargs
        )

    def create_item_samples(self, samples, collection, db_create=False, **kwargs):
        '''Creates several Item samples

        Args:
            samples: integer | [string]
                Number of DB sample to create or list of sample data name. These names should be
                in the dictionary keys of tests.sample_data.item_samples.items.
            collection: Collection
                Collection model object in which to create an Item.
            db_create: bool
                Create the sample in the DB.
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            Array with the DB samples.
        '''
        return self.items.create_samples(samples, collection, db_create=db_create, **kwargs)

    def create_asset_sample(
        self,
        item,
        name=None,
        sample='asset-1',
        db_create=False,
        required_only=False,
        create_asset_file=False,
        **kwargs
    ):
        '''Create an Asset data sample

        Args:
            item: Item
                Item model object in which to create an Asset.
            name: string
                Data name, if not given it creates a 'asset-n' with n being incremented
                after each function call.
            sample: string
                Sample based on the sample named found in tests.sample_data.asset_samples.assets
                dictionary.
            required_only: bool
                Return only attributes that are required (minimum sample data).
            create_asset_file: bool
                Create the asset file on S3.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            The data sample.
        '''
        return self.assets.create_sample(
            item,
            name=name,
            sample=sample,
            db_create=db_create,
            required_only=required_only,
            create_asset_file=create_asset_file,
            **kwargs
        )

    def create_asset_samples(
        self, samples, item, db_create=False, create_asset_file=False, **kwargs
    ):
        '''Creates several Asset samples

        Args:
            samples: integer | [string]
                Number of DB sample to create or list of sample data name. These names should be
                in the dictionary keys of tests.sample_data.asset_samples.assets.
            db_create: bool
                Create the sample in the DB.
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            create_asset_file: bool
                Create the asset file on S3.
            **kwargs:
                Key/value pairs used to overwrite arbitrary attribute in the sample.

        Returns:
            Array with the DB samples-.
        '''
        return self.assets.create_samples(
            samples, item, db_create=db_create, create_asset_file=create_asset_file, **kwargs
        )
