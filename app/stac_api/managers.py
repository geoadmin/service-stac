import logging
from datetime import datetime

from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from rest_framework.exceptions import ValidationError

from stac_api.utils import geometry_from_bbox
from stac_api.validators import validate_geometry

logger = logging.getLogger(__name__)


class ItemQuerySet(models.QuerySet):

    def filter_by_bbox(self, bbox):
        '''Filter a querystring with a given bbox

        This function adds a bbox filter to the queryset.

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
            bbox_geometry = geometry_from_bbox(bbox)
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
            ) from None

        return self.filter(geometry__intersects=bbox_geometry)

    def filter_by_datetime(self, date_time):
        '''Filter a queryset by datetime

        Args:
            queryset:
                 A django queryset (https://docs.djangoproject.com/en/3.0/ref/models/querysets/)
            date_time:
                A string

        Returns:
            The queryset filtered by date_time
        '''
        start, end = self._parse_datetime_query(date_time)
        if end is not None:
            return self._filter_by_datetime_range(start, end)
        return self.filter(properties_datetime=start)

    def _filter_by_datetime_range(self, start_datetime, end_datetime):
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
            return self.filter(
                Q(properties_datetime__lte=end_datetime) |
                Q(properties_end_datetime__lte=end_datetime)
            )
        if end_datetime == '..':
            # open end range
            return self.filter(
                Q(properties_datetime__gte=start_datetime) |
                Q(properties_start_datetime__gte=start_datetime)
            )
            # else fixed range
        return self.filter(
            Q(properties_datetime__range=(start_datetime, end_datetime)) | (
                Q(properties_start_datetime__gte=start_datetime) &
                Q(properties_end_datetime__lte=end_datetime)
            )
        )

    def _parse_datetime_query(self, date_time):
        '''Parse the datetime query as specified in the api-spec.md.

        A helper function of filter_by_datetime

        Args:
            date_time: string
                Datetime as string (should be in isoformat)

        Returns:
            queryset filtered by datetime

        Raises:
            ValidationError: When the date_time string is not a valid isoformat
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
            ) from None

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

    def filter_by_item_name(self, item_names_array):
        '''Filter by item names parameter

        Args:
            item_names_array: list[string]
                An array of ids (string)

        Returns:
            queryset filtered by a list of ids
        '''
        return self.filter(name__in=item_names_array)

    def filter_by_collections(self, collections_array):
        '''Filter by collections parameter

        Args:
            collections_array: list[string]
                An array of collections (string)

        Returns:
            queryset filtered by a list of collections
        '''
        return self.filter(collection__name__in=collections_array)

    def filter_by_intersects(self, intersects):
        '''Filter by intersects parameter

        Args:
            intersects: string
                Is a geojson formatted string

        Returns:
            queryset filtered by intersects

        Raises:
            ValueError or GDALException: When the Geojson is not a valid geometry
        '''
        the_geom = GEOSGeometry(intersects)
        return self.filter(geometry__intersects=the_geom)

    def filter_by_query(self, query):
        '''Filter by the query parameter

        Args:
            query: dict
                {"attribute": {"operator": "value"}}
        Returns:
            queryset filtered by query
        '''
        for attribute in query:
            for operator in query[attribute]:
                value = query[attribute][operator]  # get the values given by the operator

                if attribute in ["updated", "created"]:
                    prefix = ""
                else:
                    prefix = "properties_"

                # __eq does not exist, but = does it as well
                if operator == 'eq':
                    query_filter = f"{prefix}{attribute}"
                else:
                    query_filter = f"{prefix}{attribute}__{operator.lower()}"
                return self.filter(**{query_filter: value})


class ItemManager(models.Manager):

    def get_queryset(self):
        return ItemQuerySet(self.model, using=self._db).select_related('collection')

    def filter_by_bbox(self, bbox):
        return self.get_queryset().filter_by_bbox(bbox)

    def filter_by_datetime(self, date_time):
        return self.get_queryset().filter_by_datetime(date_time)

    def filter_by_collections(self, collections_array):
        return self.get_queryset().filter_by_collections(collections_array)

    def filter_by_item_name(self, item_name_array):
        return self.get_queryset().filter_by_item_name(item_name_array)

    def filter_by_query(self, query):
        return self.get_queryset().filter_by_query(query)
