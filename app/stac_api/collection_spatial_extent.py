import logging
import time

from django.contrib.gis.db.models import Extent
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon
from django.contrib.gis.geos.error import GEOSException

logger = logging.getLogger(__name__)


class CollectionSpatialExtentMixin():

    def update_bbox_extent(self, trigger, geometry, original_geometry, item):
        '''Updates the collection's spatial extent if needed when an item is updated.

        This function generates a new extent regarding all the items with the same
        collection foreign key. If there is no spatial bbox yet, the one of the geometry of the
        item is being used.

        Args:
            trigger: str
                Item trigger event, one of 'insert', 'update' or 'delete'
            geometry: GeometryField
                the geometry of the item
            original_geometry:
                the original geometry during an updated or None
            item: Item
                the item being treated

        Returns:
            bool: True if the collection temporal extent has been updated, false otherwise
        '''
        updated = False
        try:
            # insert (as item_id is None)
            if trigger == 'insert':
                # the first item of this collection
                if self.extent_geometry is None:
                    logger.info(
                        'Set collections extent_geometry with geometry %s, '
                        'triggered by the first item insertion',
                        GEOSGeometry(geometry).extent,
                        extra={
                            'collection': self.name, 'item': item.name, 'trigger': 'item-insert'
                        },
                    )
                    self.extent_geometry = Polygon.from_bbox(GEOSGeometry(geometry).extent)
                # there is already a geometry in the collection a union of the geometries
                else:
                    logger.info(
                        'Updating collections extent_geometry with geometry %s, '
                        'triggered by an item insertion',
                        GEOSGeometry(geometry).extent,
                        extra={
                            'collection': self.name, 'item': item.name, 'trigger': 'item-insert'
                        },
                    )
                    self.extent_geometry = Polygon.from_bbox(
                        GEOSGeometry(self.extent_geometry).union(GEOSGeometry(geometry)).extent
                    )
                updated |= True

            # update
            if trigger == 'update' and geometry != original_geometry:
                # is the new bbox larger than (and covering) the existing
                if Polygon.from_bbox(GEOSGeometry(geometry).extent).covers(self.extent_geometry):
                    logger.info(
                        'Updating collections extent_geometry with item geometry changed '
                        'from %s to %s, (larger and covering bbox)',
                        GEOSGeometry(original_geometry).extent,
                        GEOSGeometry(geometry).extent,
                        extra={
                            'collection': self.name, 'item': item.name, 'trigger': 'item-update'
                        },
                    )
                    self.extent_geometry = Polygon.from_bbox(GEOSGeometry(geometry).extent)
                # we need to iterate trough the items
                else:
                    logger.warning(
                        'Updating collections extent_geometry with item geometry changed '
                        'from %s to %s. We need to loop over all items of the collection, '
                        'this may take a while !',
                        GEOSGeometry(original_geometry).extent,
                        GEOSGeometry(geometry).extent,
                        extra={
                            'collection': self.name, 'item': item.name, 'trigger': 'item-update'
                        },
                    )
                    start = time.time()
                    bbox_other_items = type(item).objects.filter(collection_id=self.pk).exclude(
                        id=item.pk
                    ).only('geometry', 'collection').aggregate(Extent('geometry'))
                    geometry_updated_item = GEOSGeometry(geometry)

                    if bool(bbox_other_items['geometry__extent']):
                        geometry_other_items = GEOSGeometry(
                            Polygon.from_bbox(bbox_other_items['geometry__extent'])
                        )
                        self.extent_geometry = Polygon.from_bbox(
                            geometry_updated_item.union(geometry_other_items).extent
                        )
                    else:
                        self.extent_geometry = geometry_updated_item
                    logger.info(
                        'Collection extent_geometry updated to %s in %ss, after item update',
                        self.extent_geometry.extent,
                        time.time() - start,
                        extra={
                            'collection': self.name, 'item': item.name, 'trigger': 'item-update'
                        },
                    )
                updated |= True

            # delete, we need to iterate trough the items
            if trigger == 'delete':
                logger.warning(
                    'Updating collections extent_geometry with removal of item geometry %s. '
                    'We need to loop over all items of the collection, this may take a while !',
                    GEOSGeometry(geometry).extent,
                    extra={
                        'collection': self.name, 'item': item.name, 'trigger': 'item-delete'
                    },
                )
                start = time.time()
                bbox_other_items = type(item).objects.filter(collection_id=self.pk).exclude(
                    id=item.pk
                ).only('geometry', 'collection').aggregate(Extent('geometry'))
                if bool(bbox_other_items['geometry__extent']):
                    self.extent_geometry = GEOSGeometry(
                        Polygon.from_bbox(bbox_other_items['geometry__extent'])
                    )
                else:
                    self.extent_geometry = None
                logger.info(
                    'Collection extent_geometry updated to %s in %ss, after item deletion',
                    self.extent_geometry.extent if self.extent_geometry else None,
                    time.time() - start,
                    extra={
                        'collection': self.name, 'item': item.name, 'trigger': 'item-delete'
                    },
                )
                updated |= True
        except GEOSException as error:
            logger.error(
                'Failed to update spatial extend in collection %s with item %s, trigger=%s, '
                'current-extent=%s, new-geometry=%s, old-geometry=%s: %s',
                self.name,
                item.name,
                trigger,
                self.extent_geometry,
                GEOSGeometry(geometry).extent,
                GEOSGeometry(original_geometry).extent,
                error,
                extra={
                    'collection': self.name, 'item': item.name, 'trigger': f'item-{trigger}'
                },
            )
            raise GEOSException(
                f'Failed to update spatial extend in colletion {self.name} with item '
                f'{item.name}: {error}'
            ) from error
        return updated
