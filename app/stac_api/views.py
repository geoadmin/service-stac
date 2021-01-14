import json
import logging
from collections import OrderedDict
from datetime import datetime

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point
from django.contrib.gis.geos import Polygon
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from rest_framework import generics
from rest_framework import mixins
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_condition import etag

from stac_api import views_mixins
from stac_api.models import Asset
from stac_api.models import Collection
from stac_api.models import ConformancePage
from stac_api.models import Item
from stac_api.models import LandingPage
from stac_api.serializers import AssetSerializer
from stac_api.serializers import CollectionSerializer
from stac_api.serializers import ConformancePageSerializer
from stac_api.serializers import ItemSerializer
from stac_api.serializers import LandingPageSerializer
from stac_api.utils import fromisoformat
from stac_api.utils import utc_aware
from stac_api.validators import validate_geometry

logger = logging.getLogger(__name__)


def get_etag(queryset):
    if queryset.exists():
        return list(queryset.only('etag').values('etag').first().values())[0]
    return None


def get_collection_etag(request, *args, **kwargs):
    '''Get the ETag for a collection object

    The ETag is an UUID4 computed on each object changes (including relations; provider and links)
    '''
    tag = get_etag(Collection.objects.filter(name=kwargs['collection_name']))
    return tag


def get_item_etag(request, *args, **kwargs):
    '''Get the ETag for a item object

    The ETag is an UUID4 computed on each object changes (including relations; assets and links)
    '''
    tag = get_etag(
        Item.objects.filter(collection__name=kwargs['collection_name'], name=kwargs['item_name'])
    )
    return tag


def get_asset_etag(request, *args, **kwargs):
    '''Get the ETag for a asset object

    The ETag is an UUID4 computed on each object changes
    '''
    tag = get_etag(Asset.objects.filter(item__name=kwargs['item_name'], name=kwargs['asset_name']))
    return tag


def parse_datetime_query(date_time):
    '''Parse the datetime query as specified in the api-spec.md.

    Returns one of the following
        datetime, None
        datetime, '..'
        '..', datetime
        datetime, datetime
    '''
    start, sep, end = date_time.partition('/')
    try:
        if start != '..':
            start = datetime.fromisoformat(start.replace('Z', '+00:00'))
        if end and end != '..':
            end = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError as error:
        logger.error(
            'Invalid datetime query parameter "%s", must be isoformat; %s', date_time, error
        )
        raise ValidationError(
            _('Invalid datetime query parameter, must be isoformat'),
            code='datetime'
        )

    if end == '':
        end = None

    if start == '..' and (end is None or end == '..'):
        logger.error(
            'Invalid datetime query parameter "%s"; '
            'cannot start with open range when no end range is defined',
            date_time
        )
        raise ValidationError(
            _('Invalid datetime query parameter, '
              'cannot start with open range when no end range is defined'),
            code='datetime'
        )
    return start, end


def filter_by_bbox(queryset, bbox):
    '''Filter a querystring with a given bbox

    This function is a helper function, for some views, to add a bbox filter to the queryset.

    Args:
        queryset:
            A django queryset (https://docs.djangoproject.com/en/3.0/ref/models/querysets/)
        bbox:
            A string defining a spatial bbox (f.ex. 5.96, 45.82, 10.49, 47.81)

    Returns:
        The queryset with the added spatial filter

    Raises:
        ValidationError: When the bbox does not contain 4 values. Or when the polygon build
        from the bbox string is invalid.
    '''
    try:
        logger.debug('Query parameter bbox = %s', bbox)
        list_bbox_values = bbox.split(',')
        if (
            list_bbox_values[0] == list_bbox_values[2] and
            list_bbox_values[1] == list_bbox_values[3]
        ):
            bbox_geometry = Point(float(list_bbox_values[0]), float(list_bbox_values[1]))
        else:
            bbox_geometry = Polygon.from_bbox(list_bbox_values)
        validate_geometry(bbox_geometry)

    except (ValueError, ValidationError, IndexError) as error:
        logger.error(
            'Invalid bbox query parameter: '
            'Could not transform bbox "%s" to a polygon; %s'
            'f.ex. bbox=5.96, 45.82, 10.49, 47.81',
            bbox,
            error
        )
        raise ValidationError(
            _('Invalid bbox query parameter, '
              ' has to contain 4 values. f.ex. bbox=5.96,45.82,10.49,47.81'),
            code='bbox-invalid'
        )

    return queryset.filter(geometry__intersects=bbox_geometry)


def filter_by_datetime(queryset, date_time):
    '''Filter a queryset by datetime

    Args:
        queryset:
             A django queryset (https://docs.djangoproject.com/en/3.0/ref/models/querysets/)
        date_time:
            A string
    Returns:
        The queryset filtered by date_time
    '''
    start, end = parse_datetime_query(date_time)
    if end is not None:
        return _filter_by_datetime_range(queryset, start, end)
    return queryset.filter(properties_datetime=start)


def _filter_by_datetime_range(queryset, start_datetime, end_datetime):
    '''Filter a queryset by datetime range

    Helper function of filter_by_datetime

    Args:
        queryset:
            A django queryset (https://docs.djangoproject.com/en/3.0/ref/models/querysets/)
        start_datetime:
            A string with the start datetime
        end_datetime:
            A string with the end datetime
    Returns:
        The queryset filtered by datetime range
    '''
    if start_datetime == '..':
        # open start range
        return queryset.filter(
            Q(properties_datetime__lte=end_datetime) | Q(properties_end_datetime__lte=end_datetime)
        )
    if end_datetime == '..':
        # open end range
        return queryset.filter(
            Q(properties_datetime__gte=start_datetime) |
            Q(properties_end_datetime__gte=start_datetime)
        )
        # else fixed range
    return queryset.filter(
        Q(properties_datetime__range=(start_datetime, end_datetime)) | (
            Q(properties_start_datetime__gte=start_datetime) &
            Q(properties_end_datetime__lte=end_datetime)
        )
    )


class LandingPageDetail(generics.RetrieveAPIView):
    serializer_class = LandingPageSerializer
    queryset = LandingPage.objects.all()

    def get_object(self):
        return LandingPage.get_solo()


class ConformancePageDetail(generics.RetrieveAPIView):
    serializer_class = ConformancePageSerializer
    queryset = ConformancePage.objects.all()

    def get_object(self):
        return ConformancePage.get_solo()


def checker(request):
    data = {"success": True, "message": "OK"}

    return JsonResponse(data)


class CollectionList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = CollectionSerializer
    # prefetch_related is a performance optimization to reduce the number
    # of DB queries.
    # see https://docs.djangoproject.com/en/3.1/ref/models/querysets/#prefetch-related
    queryset = Collection.objects.all().prefetch_related('providers', 'links')

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'collections': serializer.data,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', request.build_absolute_uri()),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', request.build_absolute_uri(f'/{settings.API_BASE}/')),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', request.build_absolute_uri('.')),
                ])
            ]
        }

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class CollectionDetail(generics.GenericAPIView, mixins.RetrieveModelMixin, mixins.UpdateModelMixin):
    serializer_class = CollectionSerializer
    lookup_url_kwarg = "collection_name"
    queryset = Collection.objects.all()

    @etag(get_collection_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_etag)
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_collection_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def get_object(self):
        collection_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=collection_name)
        obj = get_object_or_404(queryset)
        return obj


class ItemsList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = ItemSerializer

    def get_write_request_data(self, request, *args, **kwargs):
        data = request.data.copy()
        data['collection'] = kwargs['collection_name']
        return data

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(collection__name=self.kwargs['collection_name']
                                      ).prefetch_related('assets', 'links')

        bbox = self.request.query_params.get('bbox', None)
        date_time = self.request.query_params.get('datetime', None)

        if bbox:
            queryset = filter_by_bbox(queryset, bbox)

        if date_time:
            queryset = filter_by_datetime(queryset, date_time)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': utc_aware(datetime.utcnow()),
            'features': serializer.data,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', request.build_absolute_uri()),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', request.build_absolute_uri(f'/{settings.API_BASE}/')),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', request.build_absolute_uri('.').rstrip('/')),
                ])
            ]
        }

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)


class ItemDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelMixin,
    views_mixins.UpdateModelMixin,
    views_mixins.DestroyModelMixin
):
    serializer_class = ItemSerializer
    lookup_url_kwarg = "item_name"

    def get_queryset(self):
        # filter based on the url
        queryset = Item.objects.filter(collection__name=self.kwargs['collection_name']
                                      ).prefetch_related('assets', 'links')
        return queryset

    def get_write_request_data(self, request, *args, partial=False, **kwargs):
        data = request.data.copy()
        data['collection'] = kwargs['collection_name']
        return data

    def get_object(self):
        item_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=item_name)
        obj = get_object_or_404(queryset)
        return obj

    @etag(get_item_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_item_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class SearchList(generics.GenericAPIView, mixins.ListModelMixin):
    permission_classes = [AllowAny]
    serializer_class = ItemSerializer

    def parse_request_body_for_queryset(self):
        queryset = Item.objects.all()
        data = self.request.data
        if 'ids' in data:
            queryset = self.filter_by_ids(queryset, data['ids'])
        else:
            if 'bbox' in data:
                queryset = filter_by_bbox(queryset, json.dumps(data['bbox']).strip('[]'))
            if 'date_time' in data:
                queryset = filter_by_datetime(queryset, data['date_time'])
            if 'collections' in data:
                queryset = self.filter_by_collections(queryset, data['collections'])
            if 'query' in data:
                queryset = self.filter_by_query(queryset, json.dumps(data['query']))
            if 'intersects' in data:
                queryset = self.filter_by_intersects(queryset, json.dumps(data['intersects']))

        return queryset

    def get_queryset(self):
        queryset = Item.objects.all()

        bbox = self.request.query_params.get('bbox', None)
        date_time = self.request.query_params.get('datetime', None)
        collections = self.request.query_params.get('collections', None)
        ids = self.request.query_params.get('ids', None)  # ids of items
        query = self.request.query_params.get('query', None)

        if ids:
            queryset = self.filter_by_ids(queryset, ids.split(','))
        else:  # if ids, all other restrictions are ignored
            if query:
                queryset = self.filter_by_query(queryset, query)

            if collections:
                queryset = self.filter_by_collections(queryset, collections.split(','))

            if bbox:
                queryset = filter_by_bbox(queryset, bbox)

            if date_time:
                queryset = filter_by_datetime(queryset, date_time)

        return queryset

    def filter_by_query(self, queryset, query):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements

        queriable_date_fields = ['datetime', 'created', 'updated']
        queriable_str_fields = ['title']
        int_operators = ["eq", "neq", "lt", "lte", "gt", "gte"]
        str_operators = ["startsWith", "endsWith", "contains", "in"]
        operators = int_operators + str_operators
        queriable_fields = queriable_date_fields + queriable_str_fields

        # validate json
        try:
            json_query = json.loads(query)
        except json.JSONDecodeError as error:
            message = f"The application could not decode the JSON." \
                      f"Please check the syntax ({error})." \
                      f"{query}"

            logger.error(message)
            raise ValidationError(_(message))

        for attribute in json_query:  # pylint: disable=too-many-nested-blocks
            # iterate trough the fields given in the query parameter
            if attribute in queriable_fields:
                logger.debug("attribute: %s", attribute)
                # iterate trough the operators
                for operator in json_query[attribute]:
                    if operator in operators:
                        value = json_query[attribute][operator
                                                     ]  # get the values given by the operator
                        # validate type to operation
                        if (
                            isinstance(value, str) and operator in int_operators and
                            attribute in int_operators
                        ):
                            message = f"You are not allowed to compare a string/date ({attribute})"\
                                      f" with a number operator." \
                                      f"for string use one of these {str_operators}"
                            logger.error(message)
                            raise ValidationError(_(message))
                        if (
                            isinstance(value, int) and operator in str_operators and
                            operator in str_operators
                        ):
                            message = f"You are not allowed to compare a number or a date with" \
                                      f"a string operator." \
                                      f"For numbers use one of these {int_operators}"
                            logger.error(message)
                            raise ValidationError(_(message))

                        # treate date
                        if attribute in queriable_date_fields:
                            try:
                                if isinstance(value, list):
                                    value = [fromisoformat(i) for i in value]
                                else:
                                    value = fromisoformat(value)
                            except ValueError as error:
                                message = f"Invalid dateformat: ({error})"
                                logger.error(message)
                                raise ValidationError(_(message))

                        # __eq does not exist, but = does it as well
                        if operator == 'eq':
                            query_filter = f"properties_{attribute}"
                        else:
                            query_filter = f"properties_{attribute}__{operator.lower()}"

                        queryset = queryset.filter(**{query_filter: value})

                        logger.debug("query_filter: %s", query_filter)
                        logger.debug("operator: %s", operator)
                        logger.debug("value: %s", value)
                    else:
                        message = f"Invalid operator in query argument. The operator {operator} " \
                                  f"is not supported. Use: {operators}"
                        logger.error(message)
                        raise ValidationError(_(message))
            else:
                message = f"Invalid field in query argument. The field {attribute} is not " \
                          f"a propertie. Use one of these {queriable_fields}"
                logger.error(message)
                raise ValidationError(_(message))
        return queryset

    def filter_by_intersects(self, queryset, intersects):
        try:
            logger.debug('Item query parameter intersects = %s', intersects)
            the_geom = GEOSGeometry(intersects)
        except ValueError as error:
            message = f"Invalid intersects parameter: " \
                f"Could not transform {intersects} to a geometry; {error}"
            logger.error(message)
            raise ValidationError(_(message))
        #geometry_intersects.srid = 4326  # as no other systems should be allowed
        validate_geometry(the_geom)
        queryset = queryset.filter(geometry__intersects=the_geom)
        return queryset

    def filter_by_collections(self, queryset, collections_array):
        queryset = queryset.filter(collection__name__in=collections_array)
        return queryset

    def filter_by_ids(self, queryset, ids_array):
        queryset = queryset.filter(name__in=ids_array)
        return queryset

    def list(self, request, *args, **kwargs):
        if request.method == 'POST':
            queryset = self.filter_queryset(self.parse_request_body_for_queryset())
        else:
            queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'type': 'FeatureCollection',
            'timeStamp': utc_aware(datetime.utcnow()),
            'features': serializer.data,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', request.build_absolute_uri()),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', request.build_absolute_uri(f'/{settings.API_BASE}/')),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', request.build_absolute_uri('.').rstrip('/')),
                ])
            ]
        }

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class AssetsList(generics.GenericAPIView, views_mixins.CreateModelMixin):
    serializer_class = AssetSerializer
    pagination_class = None

    def get_write_request_data(self, request, *args, **kwargs):
        data = request.data.copy()
        data['item'] = kwargs['item_name']
        return data

    def get_success_headers(self, data):  # pylint: disable=arguments-differ
        asset_link_self = self.request.build_absolute_uri() + "/" + self.request.data["id"]
        return {'Location': asset_link_self}

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            item__collection__name=self.kwargs['collection_name'],
            item__name=self.kwargs['item_name']
        )

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = {
            'assets': serializer.data,
            'links': [
                OrderedDict([
                    ('rel', 'self'),
                    ('href', request.build_absolute_uri()),
                ]),
                OrderedDict([
                    ('rel', 'root'),
                    ('href', request.build_absolute_uri(f'/{settings.API_BASE}/')),
                ]),
                OrderedDict([
                    ('rel', 'parent'),
                    ('href', request.build_absolute_uri('.').rstrip('/')),
                ]),
                OrderedDict([
                    ('rel', 'item'),
                    ('href', request.build_absolute_uri('.').rstrip('/')),
                ]),
                OrderedDict([
                    ('rel', 'collection'),
                    ('href', request.build_absolute_uri('../..').rstrip('/')),
                ])
            ]
        }

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class AssetDetail(
    generics.GenericAPIView,
    mixins.RetrieveModelMixin,
    views_mixins.UpdateModelMixin,
    views_mixins.DestroyModelMixin
):
    serializer_class = AssetSerializer
    lookup_url_kwarg = "asset_name"

    def get_write_request_data(self, request, *args, partial=False, **kwargs):
        data = request.data.copy()
        data['item'] = kwargs['item_name']
        if partial and not 'id' in data:
            # Partial update for checksum:multihash requires the asset id in order to verify the
            # file with the checksum, therefore if the id is missing in payload we take it from
            # the request path.
            data['id'] = kwargs['asset_name']
        return data

    def get_queryset(self):
        # filter based on the url
        return Asset.objects.filter(
            item__collection__name=self.kwargs['collection_name'],
            item__name=self.kwargs['item_name']
        )

    def get_object(self):
        asset_name = self.kwargs.get(self.lookup_url_kwarg)
        queryset = self.get_queryset().filter(name=asset_name)
        obj = get_object_or_404(queryset)
        return obj

    def get_serializer(self, *args, **kwargs):
        hide_fields = kwargs.pop('hide_fields', [])
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        return serializer_class(*args, hide_fields=hide_fields, **kwargs)

    @etag(get_asset_etag)
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, hide_fields=['href'], **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, hide_fields=['href'], **kwargs)

    # Here the etag is only added to support pre-conditional If-Match and If-Not-Match
    @etag(get_asset_etag)
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)


class TestHttp500(AssetDetail):

    def get(self, request, *args, **kwargs):
        logger.debug('Test request that raises an exception')

        raise AttributeError('test exception')
