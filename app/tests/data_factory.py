import logging
import re
from datetime import datetime

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.uploadedfile import SimpleUploadedFile

from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import CollectionLink
from stac_api.models import Item
from stac_api.models import ItemLink
from stac_api.models import Provider
from stac_api.utils import get_sha256_multihash
from stac_api.utils import isoformat

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

    def __init__(self, sample, required_only=False, **kwargs):
        self.sample = sample
        try:
            sample = self.samples_dict[sample]
        except KeyError as error:
            raise KeyError(f'Unknown {self.sample_name} sample: {error}')

        # Sets attributes from sample
        for key, value in sample.items():
            setattr(self, f'attr_{key}', value)
        # overwrite sample data with kwargs
        for key, value in kwargs.items():
            setattr(self, f'attr_{key}', value)

        if required_only:
            self.filter_optional(self.optional_fields)

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
                Key of the asset sample attribute to return
            default: any
                Default value to return if the key is not found

        Returns:
            Asset key value
        '''
        return getattr(self, f'attr_{key}', default)

    def set(self, key, value):
        '''Set sample key value

        Alias of sample[key] = value

        Args:
            key: string
                key to set
            value:
                value to set
        '''
        setattr(self, f'attr_{key}', value)

    def filter_optional(self, optional_attributes):
        '''Remove optional attributes'''
        for attribute in optional_attributes:
            attribute = f'attr_{attribute}'
            if hasattr(self, attribute):
                delattr(self, attribute)

    def get_attributes(self, remove_relations=True):
        '''Returns the sample data attributes as dictionary

        This can be used as arguments for the model class.

        Args:
            remove_relations: bool
                remove relational attributes (providers and links)

        Returns:
            Dictionary with the sample attributes to use to create a DB object
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
            Dictionary with the sample attributes to use to create a DB object
        '''
        return self.get_attributes()

    def key_mapped(self, key):
        '''Map an attribute key into a json key

        Some attributes in the model are different from the one for the serializer, this is the
        mapping between the two.

        Args:
            key: string
                key attribute to map into json key

        Returns:
            string, json key mapped
        '''
        return self.key_mapping.get(key, key)

    def create(self):
        '''Create the sample in DB

        Returns:
            the DB sample (model object)
        '''
        self.model_instance = self.model_class(**self.attributes)
        self.model_instance.full_clean()
        self.model_instance.save()
        return self.model_instance

    @property
    def json(self):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload or to check
        the read API payload.

        Returns
            A dictionary with the sample data
        '''
        return {
            self.key_mapped(key): value for key,
            value in self.get_attributes(remove_relations=False).items()
        }

    @property
    def model(self):
        '''Returns a django DB model object of sample data

        If the data has not yet been created in DB, then it is created.

        Returns:
            model instance
        '''
        if not self.model_instance:
            self.create()
        return self.model_instance


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

    def __init__(self, sample='collection-1', name=None, **kwargs):
        '''Create a collection sample data

        Args:
            sample: string
                Name of the sample based to use, see tests.sample_data.collection_samples
            required_only: bool
                return only attributes that are required (minimum sample data)
            name: string
                Overwrite the sample name
            **kwargs:
                any parameter will overwrite existing attributes
        '''
        super().__init__(sample=sample, name=name, **kwargs)

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
                remove relational attributes (providers and links)

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
            the DB sample (model object)
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

    @property
    def json(self):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload or to check
        the read API payload.

        Returns
            A dictionary with the sample data
        '''
        json_data = super().json
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
            list of provider model instances
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
            list of link model instances
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

    def __init__(self, sample='item-1', collection=None, name=None, **kwargs):
        '''Create a item sample data

        Args:
            sample: string
                Name of the sample based to use, see tests.sample_data.item_samples
            required_only: bool
                return only attributes that are required (minimum sample data)
            collection: Collection
                Collection DB object relations
            name: string
                Overwrite the sample name

            **kwargs:
                any parameter will overwrite existing attributes
        '''
        super().__init__(sample=sample, collection=collection, name=name, **kwargs)

        if hasattr(self, 'attr_links'):
            self.attr_links = [ItemLinkSample(**link) for link in self.attr_links]

        self.model_links_instance = []

    def get_attributes(self, remove_relations=True):
        '''Returns the sample data attributes as dictionary

        This can be used to create new DB object.

        Args:
            remove_relations: bool
                remove relational attributes (links)

        Returns:
            Dictionary with the sample attributes to use to create a DB object
        '''
        attributes = super().get_attributes(remove_relations)

        links = attributes.pop('links', None)
        if not remove_relations and links:
            attributes['links'] = [link.attributes for link in links]
        return attributes

    @property
    def json(self):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload or to check
        the read API payload.

        Returns
            A dictionary with the sample data
        '''
        json_data = {
            key: value for key, value in super().json.items() if not key.startswith('properties_')
        }
        json_data['collection'] = json_data['collection'].name
        if 'geometry' in json_data and isinstance(json_data['geometry'], GEOSGeometry):
            json_data['geometry'] = json_data['geometry'].json
        if not 'properties' in json_data:
            json_data['properties'] = self._get_properties()
        links = json_data.pop('links', [])
        if links:
            json_data['links'] = [link.json for link in self.attr_links]
        return json_data

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

    def create(self):
        '''Create the sample in DB

        Returns:
            the DB sample (model object)
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
            list of link model instances
        '''
        if not self.model_links_instance:
            attributes = self.get_attributes(remove_relations=False)
            links = attributes.pop('links', [])
            if not self.model_instance:
                self._create_model(attributes)
            self._create_model_links(links)
        return self.model_links_instance

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
        'checksum_multihash': 'checksum:multihash'
    }
    optional_fields = [
        'title', 'description', 'eo_gsd', 'geoadmin_variant', 'geoadmin_lang', 'proj_epsg', 'file'
    ]

    def __init__(self, sample='asset-1', item=None, name=None, **kwargs):
        '''Create a item sample data

        Args:
            sample: string
                Name of the sample based to use, see tests.sample_data.asset_samples
            required_only: bool
                return only attributes that are required (minimum sample data)
            item: Item
                Item DB object relations
            name: string
                Overwrite the sample name
            **kwargs:
                any parameter will overwrite existing attributes
        '''
        self.attr_name = name
        super().__init__(sample=sample, item=item, name=name, **kwargs)

        file = getattr(self, 'attr_file', None)
        if file:
            self.attr_checksum_multihash = get_sha256_multihash(file)
            self.attr_file = SimpleUploadedFile(
                f'{item.collection.name}/{item.name}/{self.attr_name}', file
            )

    @property
    def json(self):
        '''Returns a json serializable representation of the sample data

        This json payload can then be used in the write API payload or to check
        the read API payload.

        Returns
            A dictionary with the sample data
        '''
        # pylint: disable=no-member
        data = super().json
        item = data.pop('item')
        data['item'] = item.name
        file = data.pop('file', None)
        if file:
            data['href'] = \
                f'http://{settings.AWS_S3_CUSTOM_DOMAIN}/{item.collection.name}/{item.name}/{file.name}'
        return data


class FactoryBase:
    '''Factory base class
    '''
    factory_name = 'base'
    sample_class = SampleData

    def __init__(self):
        self.last = None

    @classmethod
    def get_last_name(cls, last):
        '''Return a factory name incremented by one (e.g. 'collection-1')
        '''
        if last is None:
            last = f'{cls.factory_name}-0'
        last = '{}-{}'.format(
            cls.factory_name, int(re.match(fr"{cls.factory_name}-(\d+)", last).group(1)) + 1
        )
        return last

    def create_sample(self, name=None, db_create=False, **kwargs):
        '''Create a data sample

        Args:
            name: string
                Data name, if not given it creates a '{factory_name}-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        if name:
            data_sample = self.sample_class(name=name, **kwargs)
        else:
            self.last = self.get_last_name(self.last)
            data_sample = self.sample_class(name=self.last, **kwargs)
        if db_create:
            data_sample.create()
        return data_sample

    def create_samples(self, samples, db_create=False, kwargs_list=True, **kwargs):
        '''Creates several samples

        Args:
            samples: integer | [string]
                number of DB sample to create or list of sample data name
            db_create: bool
                create the sample in the DB
            sample: string
                sample name to use for all new samples
                (NOTE: overwrite the name in samples parameter)
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

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
    # pylint: disable=arguments-differ
    factory_name = 'relation'

    def create_sample(self, rel=None, **kwargs):
        '''Create a data sample

        Args:
            rel: string
                Data rel, if not given it creates a 'rel-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        if rel:
            return self.sample_class(rel=rel, **kwargs)
        self.last = self.get_last_name(self.last)
        return self.sample_class(rel=self.last, **kwargs)


class CollectionLinkFactory(LinkFactory):
    factory_name = 'collection-link'
    sample_class = CollectionLinkSample


class CollectionFactory(FactoryBase):
    factory_name = 'collection'
    sample_class = CollectionSample

    def create_sample(self, name=None, db_create=False, **kwargs):
        '''Create a collection data sample

        Args:
            name: string
                Data name, if not given it creates a 'collection-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            db_create: bool
                create the sample in the DB
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        return super().create_sample(name=name, db_create=db_create, **kwargs)

    def create_samples(self, samples, db_create=False, kwargs_list=True, **kwargs):
        '''Creates several Collection samples

        Args:
            samples: integer | [string]
                number of DB sample to create or list of sample data name
            db_create: bool
                create the sample in the DB
            sample: string
                sample name to use for all new samples
                (NOTE: overwrite the name in samples parameter)
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

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
    # pylint: disable=arguments-differ
    factory_name = 'item'
    sample_class = ItemSample

    def create_sample(self, collection, name=None, db_create=False, **kwargs):
        '''Create an Item data sample

        Args:
            collection: Collection
                Collection model object in which to create an Item
            name: string
                Data name, if not given it creates a 'item-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            db_create: bool
                create the sample in the DB
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        return super().create_sample(name, collection=collection, db_create=db_create, **kwargs)

    def create_samples(self, samples, collection, db_create=False, **kwargs):
        '''Creates several Item samples

        Args:
            samples: integer | [string]
                number of DB sample to create or list of sample data name
            collection: Collection
                Collection model object in which to create an Item
            db_create: bool
                create the sample in the DB
            sample: string
                sample name to use for all new samples
                (NOTE: overwrite the name in samples parameter)
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            Array with the DB samples
        '''
        return super().create_samples(samples, collection=collection, db_create=db_create, **kwargs)


class AssetFactory(FactoryBase):
    # pylint: disable=arguments-differ
    factory_name = 'asset'
    sample_class = AssetSample

    def create_sample(self, item, name=None, db_create=False, **kwargs):
        '''Create an Asset data sample

        Args:
            item: Item
                Item model object in which to create an Asset
            name: string
                Data name, if not given it creates a 'asset-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        return super().create_sample(name, item=item, db_create=db_create, **kwargs)

    def create_samples(self, samples, item, db_create=False, **kwargs):
        '''Creates several Asset samples

        Args:
            samples: integer | [string]
                number of DB sample to create or list of sample data name
            db_create: bool
                create the sample in the DB
            sample: string
                sample name to use for all new samples
                (NOTE: overwrite the name in samples parameter)
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            Array with the DB samples
        '''
        return super().create_samples(samples, item=item, db_create=db_create, **kwargs)


class Factory:
    '''Factory for data samples
    '''

    def __init__(self):
        self.collections = CollectionFactory()
        self.items = ItemFactory()
        self.assets = AssetFactory()

    def create_collection_sample(self, db_create=False, required_only=False, **kwargs):
        '''Create a collection data sample

        Args:
            name: string
                Data name, if not given it creates a 'collection-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            db_create: bool
                create the sample in the DB
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        return self.collections.create_sample(
            db_create=db_create, required_only=required_only, **kwargs
        )

    def create_collection_samples(self, samples, db_create=False, **kwargs):
        '''Creates several Collection samples

        Args:
            samples: integer | [string]
                number of DB sample to create or list of sample data name
            db_create: bool
                create the sample in the DB
            sample: string
                sample name to use for all new samples
                (NOTE: overwrite the name in samples parameter)
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            Array with the DB samples
        '''
        return self.collections.create_samples(samples, db_create=db_create, **kwargs)

    def create_item_sample(self, collection, db_create=False, required_only=False, **kwargs):
        '''Create an Item data sample

        Args:
            collection: Collection
                Collection model object in which to create an Item
            name: string
                Data name, if not given it creates a 'item-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            db_create: bool
                create the sample in the DB
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        return self.items.create_sample(
            collection, db_create=db_create, required_only=required_only, **kwargs
        )

    def create_item_samples(self, samples, collection, db_create=False, **kwargs):
        '''Creates several Item samples

        Args:
            samples: integer | [string]
                number of DB sample to create or list of sample data name
            collection: Collection
                Collection model object in which to create an Item
            db_create: bool
                create the sample in the DB
            sample: string
                sample name to use for all new samples
                (NOTE: overwrite the name in samples parameter)
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            Array with the DB samples
        '''
        return self.items.create_samples(samples, collection, db_create=db_create, **kwargs)

    def create_asset_sample(self, item, db_create=False, required_only=False, **kwargs):
        '''Create an Asset data sample

        Args:
            item: Item
                Item model object in which to create an Asset
            name: string
                Data name, if not given it creates a 'asset-n' with n being incremented
                after each function call
            sample: string
                sample based on the sample named found in tests.sample_data
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            The data sample
        '''
        return self.assets.create_sample(
            item, db_create=db_create, required_only=required_only, **kwargs
        )

    def create_asset_samples(self, samples, item, db_create=False, **kwargs):
        '''Creates several Asset samples

        Args:
            samples: integer | [string]
                number of DB sample to create or list of sample data name
            db_create: bool
                create the sample in the DB
            sample: string
                sample name to use for all new samples
                (NOTE: overwrite the name in samples parameter)
            kwargs_list: bool
                If set to true, then kwargs with list values are distributed over the samples,
                otherwise the kwargs are passed as is to the sample.
            **kwargs:
                key/value pairs used to overwrite arbitrary attribute in the sample

        Returns:
            Array with the DB samples
        '''
        return self.assets.create_samples(samples, item, db_create=db_create, **kwargs)