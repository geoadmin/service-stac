import logging
import time

logger = logging.getLogger(__name__)


class CollectionTemporalExtentMixin():

    def update_temporal_extent(self, item, trigger, original_item_values):
        '''Updates the collection's temporal extent if needed when items are inserted, updated or
        deleted.

        For all the given parameters this function checks, if the corresponding parameters of the
        collection need to be updated. If so, they will be updated.

        Args:
            item:
                Item thats being inserted/updated or deleted
            trigger:
                Item trigger event, one of 'insert', 'update' or 'delete'
            original_item_values: (optional)
                Dictionary with the original values of item's ['properties_datetime',
                'properties_start_datetime', 'properties_end_datetime'].

        Returns:
            bool: True if the collection summaries has been updated, false otherwise
        '''
        updated = False

        # Get the start end datetimes independently if we have a range or not, when there is no
        # range then we use the same start and end datetime
        start_datetime = item.properties_start_datetime
        end_datetime = item.properties_end_datetime
        if start_datetime is None or end_datetime is None:
            start_datetime = item.properties_datetime
            end_datetime = item.properties_datetime

        # Get the original start end datetimes independently if we have a range or not, when there
        # is no range then we use the same start and end datetime
        old_start_datetime = original_item_values.get('properties_start_datetime', None)
        old_end_datetime = original_item_values.get('properties_end_datetime', None)
        if old_start_datetime is None or old_end_datetime is None:
            old_start_datetime = original_item_values.get('properties_datetime', None)
            old_end_datetime = original_item_values.get('properties_datetime', None)

        if trigger == 'insert':
            updated |= self._update_temporal_extent(
                item, trigger, None, start_datetime, None, end_datetime
            )
        elif trigger in ['update', 'delete']:
            updated |= self._update_temporal_extent(
                item, trigger, old_start_datetime, start_datetime, old_end_datetime, end_datetime
            )
        else:
            logger.critical(
                'Failed to update collection temporal extent; invalid trigger parameter %s',
                trigger,
                extra={'collection', self.name, 'item', item.name}
            )
            raise ValueError(f'Invalid trigger parameter; {trigger}')

        return updated

    def _update_temporal_extent_on_item_insert(
        self, new_start_datetime, new_end_datetime, item_name
    ):
        '''This function is called from within update_temporal_extent() when a new item is inserted
        to the collection.

        Args:
            collection: Collection
                Collection instance on which to operate
            new_start_datetime: datetime
                item's updated value for properties_start_datetime
            new_end_datetime: datetime
                item's updated value for properties_end_datetime
            item_name: string
                the name of the item being treated

        Returns:
            bool: True if temporal extent has been updated, false otherwise
        '''
        updated = False
        if (self.extent_start_datetime is None or self.extent_start_datetime > new_start_datetime):
            logger.info(
                "Collection temporal extent start_datetime=%s updated to the "
                "item start_datetime=%s",
                self.extent_start_datetime,
                new_start_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-insert'
                }
            )
            updated |= True
            # first item in collection, as extent_start_datetime is None:
            # or
            # new item starts earlier that current collection range starts
            self.extent_start_datetime = new_start_datetime

        if self.extent_end_datetime is None or self.extent_end_datetime < new_end_datetime:
            logger.info(
                "Collection temporal extent end_datetime=%s updated to item end_datetime=%s",
                self.extent_end_datetime,
                new_end_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-insert'
                }
            )
            updated |= True
            # first item in collection, as extent_start_datetime is None
            # or
            # new item starts after current collection's range ends
            self.extent_end_datetime = new_end_datetime

        return updated

    def _update_start_temporal_extent_on_item_update(
        self, old_start_datetime, new_start_datetime, item_name, qs_other_items=None
    ):
        '''This function is called from within update_temporal_extent() when the
        start_datetime of an item in the collection is updated to check if the
        collection's start_datetime needs to be updated.

        Args:
            collection: Collection
                Collection instance on which to operate
            old_start_datetime: datetime
                item's old value for properties_start_datetime
            new_start_datetime: datetime
                item's updated value for properties_start_datetime
            item_name: str
                the name of the item being treated
            qs_other_items: QuerySet | None
                queryset with all items of the collection excluding the one being updated.
                (optional)

        Returns:
            bool: True if temporal extent has been updated, false otherwise
            return_qs: QuerySet | None
                Queryset containing all items (but the one currently updated) that have
                non-null properties_datetime values. This queryset might be used in
                update_end_temporal_extent_on_item_update() and can be passed in already
                evaluated state to save one DB hit.
        '''
        updated = False
        return_qs = None
        logger.debug(
            "Updating collection extent start datetime %s with item (old start: %s, new start: %s)",
            self.extent_start_datetime,
            old_start_datetime,
            new_start_datetime,
            extra={
                'collection': self.name, 'item': item_name, 'trigger': 'item-update'
            }
        )

        if old_start_datetime == self.extent_start_datetime:
            # item's old start_datetime was defining left bound of the temporal
            # extent interval of collection before update
            if new_start_datetime < old_start_datetime:
                logger.info(
                    "Collection temporal extent start_datetime=%s updated "
                    "to item start_datetime=%s",
                    self.extent_start_datetime,
                    new_start_datetime,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )
                updated |= True
                # item's start_datetime was shifted to the left (earlier)
                self.extent_start_datetime = new_start_datetime
            else:
                # item's start_datetime was shifted to the right (later)
                # but was defining the left bound of the temporal extent
                # of the collection before
                # --> hence the new start_datetime of the collection
                # needs to be determined:
                # set earliest start_datetime to min(earliest_start_datetime
                # of all items but the one currently updated and
                # new_start_datetime).
                logger.warning(
                    'Item was defining the start extent and its new start is more recent; '
                    'Looping over all items of the collection in order to find the new '
                    'start extent, this may take a while !',
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )
                start = time.time()
                qs_other_items_with_properties_start_datetime = qs_other_items.filter(
                    properties_start_datetime__isnull=False
                ).only('properties_start_datetime', 'collection')
                if qs_other_items_with_properties_start_datetime.exists():
                    earliest_properties_start_datetime = (
                        qs_other_items_with_properties_start_datetime.
                        earliest('properties_start_datetime').properties_start_datetime
                    )
                    earliest_start_datetime = min(
                        new_start_datetime, earliest_properties_start_datetime
                    )
                else:
                    earliest_start_datetime = new_start_datetime
                logger.info(
                    'Found the item with the earliest start_datetime properties %s in %ss',
                    earliest_start_datetime,
                    time.time() - start,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )

                start = time.time()
                # set earliest datetime to min(earliest_datetime of all items
                # but the one currently updated and new_start_datetime)
                qs_other_items_with_properties_datetime = qs_other_items.filter(
                    properties_datetime__isnull=False
                ).only('properties_datetime', 'collection')
                if qs_other_items_with_properties_datetime.exists():
                    other_items_earliest_properties_datetime = (
                        qs_other_items_with_properties_datetime.earliest('properties_datetime'
                                                                        ).properties_datetime
                    )
                    earliest_datetime = min(
                        new_start_datetime, other_items_earliest_properties_datetime
                    )
                    return_qs = qs_other_items_with_properties_datetime
                else:
                    earliest_datetime = new_start_datetime
                logger.info(
                    'Found the item with the earliest datetime properties %s in %ss',
                    earliest_datetime,
                    time.time() - start,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )

                updated |= True
                new_extent_start = min(earliest_start_datetime, earliest_datetime)
                logger.info(
                    "Collection temporal extent start_datetime updated from %s to %s",
                    self.extent_start_datetime,
                    new_extent_start,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )
                self.extent_start_datetime = new_extent_start
        elif new_start_datetime < self.extent_start_datetime:
            # item's start_datetime did not define the left bound of the
            # collection's temporal extent before update, which does not
            # matter anyways, as it defines the new left bound after update
            # and collection's start_datetime can be simply adjusted
            logger.info(
                "Collection temporal extent start_datetime=%s updated to item start_datetime=%s",
                self.extent_start_datetime,
                new_start_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                }
            )
            updated |= True
            self.extent_start_datetime = new_start_datetime

        return updated, return_qs

    def _update_end_temporal_extent_on_item_update(
        self,
        old_end_datetime,
        new_end_datetime,
        item_name,
        qs_other_items=None,
        qs_other_items_with_properties_datetime=None
    ):
        '''This function is called from within update_temporal_extent() when an
        item in the collection is updated to check if the collection's
        end_datetime needs to be updated.

        Args:
            collection: Collection
                Collection instance on which to operate
            old_end_datetime: datetime
                item's old value for properties_end_datetime
            new_end_datetime: datetime
                item's updated value for properties_end_datetime
            item_name: str
                the name of the item being treated
            qs_other_items: QuerySet | None
                queryset with all items of the collection excluding the one being updated.
                (optional)
            qs_other_items_with_properties_datetimes: QuerySet | None
                Already evaluated queryset with all items (but the one currently updated) that have
                non-null properties_datetime values (optional).

        Returns:
            bool: True if temporal extent has been updated, false otherwise
        '''
        updated = False
        logger.debug(
            "Updating collection extent_end_datetime %s with item "
            "(old end_datetime: %s, new end_datetime: %s)",
            self.extent_end_datetime,
            old_end_datetime,
            new_end_datetime,
            extra={
                'collection': self.name, 'item': item_name, 'trigger': 'item-update'
            }
        )

        if old_end_datetime == self.extent_end_datetime:
            # item's old end_datetime was defining the right bound of
            # the collection's temporal extent interval before update
            if new_end_datetime > old_end_datetime:
                logger.info(
                    "Collection temporal extent_end_datetime %s updated to item end_datetime %s",
                    self.extent_end_datetime,
                    new_end_datetime,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )
                # item's end_datetime was shifted to the right (later)
                updated |= True
                self.extent_end_datetime = new_end_datetime
            else:
                # item's end_datetime was shifted to the left (earlier)
                # but was defining the right bound of the collection's
                # temporal extent.
                # --> hence the new end_datetime of the collection needs
                # to be determined:
                # set latest end_datetime to max(new_end_datetime and
                # end_datetime of all items but the one currently updated).
                logger.warning(
                    'Item was defining the end extent and its new end is less recent; '
                    'Looping over all items of the collection in order to find the new end extent,'
                    'this may take a while !',
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )
                start = time.time()
                qs_other_items_with_properties_end_datetime = qs_other_items.filter(
                    properties_end_datetime__isnull=False
                ).only('properties_end_datetime', 'collection')
                if qs_other_items_with_properties_end_datetime.exists():
                    item_latest_end_datetime = (
                        qs_other_items_with_properties_end_datetime.
                        latest('properties_end_datetime')
                    )
                    logger.info(
                        'Found the item %s with the latest end_datetime properties %s',
                        item_latest_end_datetime,
                        item_latest_end_datetime.properties_end_datetime,
                        extra={
                            'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                        }
                    )
                    latest_end_datetime = max(
                        new_end_datetime, item_latest_end_datetime.properties_end_datetime
                    )
                else:
                    logger.info(
                        'No item with end_datetime found, use the updated item end_datetime '
                        '%s as end extent',
                        new_end_datetime,
                        extra={
                            'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                        }
                    )
                    latest_end_datetime = new_end_datetime
                logger.info(
                    'Search for the item\'s latest_end_datetime took %ss',
                    time.time() - start,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )

                start = time.time()
                # set latest datetime to max(new_end_datetime and
                # end end_datetime of all items but the one currently updated)
                # get latest datetime, or none in case none exists and
                # use the already evaluated qs_other_items_with_properties_datetime, if it has
                # been passed to this function to save a DB hit.
                if qs_other_items_with_properties_datetime is None:
                    qs_other_items_with_properties_datetime = qs_other_items.filter(
                        properties_datetime__isnull=False
                    ).only('properties_datetime', 'collection')
                if qs_other_items_with_properties_datetime.exists():
                    item_latest_properties_datetime = (
                        qs_other_items_with_properties_datetime.latest('properties_datetime')
                    )
                    logger.info(
                        'Found the item %s with the latest datetime properties %s',
                        item_latest_properties_datetime,
                        item_latest_properties_datetime.properties_datetime,
                        extra={
                            'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                        }
                    )
                    latest_datetime = max(
                        new_end_datetime, item_latest_properties_datetime.properties_datetime
                    )
                else:
                    logger.info(
                        'No item with datetime found, use the updated item end_datetime '
                        '%s as end extent',
                        new_end_datetime,
                        extra={
                            'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                        }
                    )
                    latest_datetime = new_end_datetime
                logger.info(
                    'Search for the item\'s latest_datetime took %ss',
                    time.time() - start,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )

                updated |= True
                new_extent_end_datetime = max(latest_end_datetime, latest_datetime)
                logger.info(
                    "Collection temporal extent_end_datetime %s updated to %s s",
                    self.extent_end_datetime,
                    new_extent_end_datetime,
                    extra={
                        'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                    }
                )
                self.extent_end_datetime = new_extent_end_datetime
        elif new_end_datetime > self.extent_end_datetime:
            # item's end_datetime did not define the right bound of
            # the collection's temporal extent before update, which
            # does not matter anyways, as it defines the right bound
            # after update and collection's end_date can be simply
            # adjusted
            updated |= True
            logger.info(
                "Collection temporal extent end_datetime=%s updated to item end_datetime=%s",
                self.extent_start_datetime,
                new_end_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-update'
                }
            )
            self.extent_end_datetime = new_end_datetime

        return updated

    def _update_start_temporal_extent_on_item_delete(
        self, old_start_datetime, item_name, qs_other_items=None
    ):
        '''This function is called from within update_temporal_extent() when an
        item is deleted from the collection to check if the collection's
        start_datetime needs to be updated.

        Args:
            collection: Collection
                Collection instance on which to operate
            old_start_datetime: datetime
                item's old value for properties_start_datetime
            item_name: str
                the name of the item being treated
            qs_other_items: QuerySet | None
                queryset with all items of the collection excluding the one being updated.
                (optional)

        Returns:
            bool: True if temporal extent has been updated, false otherwise
            return_qs: QuerySet | None
                Queryset containing all items (but the one currently updated) that have
                non-null properties_datetime values. This queryset might be used in
                update_end_temporal_extent_on_item_update() and can be passed in already
                evaluated state to save one DB hit.
        '''
        updated = False
        return_qs = None
        logger.debug(
            "Item deleted (start_datetime=%s) from collection, updating the "
            "collection's extent_start_datetime (current: %s) if needed",
            old_start_datetime,
            self.extent_start_datetime,
            extra={
                'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
            }
        )

        if old_start_datetime == self.extent_start_datetime:
            # item that is to be deleted defined left bound of collection's
            # temporal extent
            logger.warning(
                'Item was defining the collection\'s extent start bound. We need to loop '
                'over all items of the collection in order to update the temporal extent, '
                'this may take a while !',
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )
            start = time.time()
            # get earliest start_datetime or none, in case none exists
            qs_other_items_with_properties_start_datetime = qs_other_items.filter(
                properties_start_datetime__isnull=False
            ).only('properties_start_datetime', 'collection')
            if qs_other_items_with_properties_start_datetime.exists():
                earliest_start_datetime = qs_other_items_with_properties_start_datetime.earliest(
                    'properties_start_datetime'
                ).properties_start_datetime
            else:
                earliest_start_datetime = None
            logger.info(
                'Search for the item\'s earliest_start_datetime took %ss: found %s',
                time.time() - start,
                earliest_start_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )

            # get earliest datetime, or none in case none exists
            start = time.time()
            qs_other_items_with_properties_datetime = qs_other_items.filter(
                properties_datetime__isnull=False
            ).only('properties_datetime', 'collection')
            if qs_other_items_with_properties_datetime.exists():
                earliest_datetime = qs_other_items_with_properties_datetime.earliest(
                    'properties_datetime'
                ).properties_datetime
                return_qs = qs_other_items_with_properties_datetime
            else:
                earliest_datetime = None
            logger.info(
                'Search for the item\'s earliest_datetime took %ss: found %s',
                time.time() - start,
                earliest_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )

            # set collection's new start_datetime to the minimum of the earliest
            # item's start_datetime or datetime
            if earliest_start_datetime is not None and earliest_datetime is not None:
                new_extent_start_datetime = min(earliest_start_datetime, earliest_datetime)
            elif earliest_datetime is not None:
                new_extent_start_datetime = earliest_datetime
            elif earliest_start_datetime is not None:
                new_extent_start_datetime = earliest_start_datetime
            else:
                new_extent_start_datetime = None

            logger.info(
                'Updated collection extent_start_datetime from %s to %s',
                self.extent_start_datetime,
                new_extent_start_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )
            self.extent_start_datetime = new_extent_start_datetime
            updated |= True

        return updated, return_qs

    def _update_end_temporal_extent_on_item_delete(
        self,
        old_end_datetime,
        item_name,
        qs_other_items=None,
        qs_other_items_with_properties_datetime=None
    ):
        '''This function is called from within update_temporal_extent() when an
        item is deleted from the collection to check if the collection's
        end_datetime needs to be updated.

        Args:
            collection: Collection
                Collection instance on which to operate
            old_end_datetime: datetime
                item's old value for properties_end_datetime
            item_name: str
                the name of the item being treated
            qs_other_items: QuerySet | None
                queryset with all items of the collection excluding the one being updated.
                (optional)
            qs_other_items_with_properties_datetimes: QuerySet | None
                Already evaluated queryset with all items (but the one currently updated) that have
                non-null properties_datetime values (optional).

        Returns:
            bool: True if temporal extent has been updated, false otherwise
        '''
        updated = False
        logger.debug(
            "Item deleted (end_datetime=%s) from collection, updating the "
            "collection's extent_end_datetime (current: %s) if needed",
            old_end_datetime,
            self.extent_end_datetime,
            extra={
                'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
            }
        )

        if old_end_datetime == self.extent_end_datetime:
            # item that is to be deleted defined right bound of collection's
            # temporal extent
            logger.warning(
                'Item was defining the collection\'s extent end bound. We need to loop '
                'over all items of the collection in order to update the temporal extent, '
                'this may take a while !',
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )
            start = time.time()
            # get latest end_datetime or none, in case none exists
            qs_other_items_with_properties_end_datetime = qs_other_items.filter(
                properties_end_datetime__isnull=False
            ).only('properties_end_datetime', 'collection')
            if qs_other_items_with_properties_end_datetime.exists():
                latest_end_datetime = qs_other_items_with_properties_end_datetime.latest(
                    'properties_end_datetime'
                ).properties_end_datetime
            else:
                latest_end_datetime = None
            logger.info(
                'Search for the item\'s latest_end_datetime took %ss: found %s',
                time.time() - start,
                latest_end_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )

            # get latest datetime, or none in case none exists and
            # use the already evaluated qs_other_items_with_properties_datetime, if it has
            # been passed to this function to save a DB hit.
            start = time.time()
            if qs_other_items_with_properties_datetime is None:
                qs_other_items_with_properties_datetime = qs_other_items.filter(
                    properties_datetime__isnull=False
                ).only('properties_datetime', 'collection')
            if qs_other_items_with_properties_datetime.exists():
                latest_datetime = qs_other_items_with_properties_datetime.latest(
                    'properties_datetime'
                ).properties_datetime
            else:
                latest_datetime = None
            logger.info(
                'Search for the item\'s latest_datetime took %ss: found %s',
                time.time() - start,
                latest_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )

            # set collection's new end_datetime to the maximum of the latest
            # item's end_datetime or datetime
            if latest_end_datetime is not None and latest_datetime is not None:
                new_extent_end_datetime = max(latest_end_datetime, latest_datetime)
            elif latest_datetime is not None:
                new_extent_end_datetime = latest_datetime
            elif latest_end_datetime is not None:
                new_extent_end_datetime = latest_end_datetime
            else:
                new_extent_end_datetime = None

            logger.info(
                'Updated collection extent_end_datetime from %s to %s',
                self.extent_end_datetime,
                new_extent_end_datetime,
                extra={
                    'collection': self.name, 'item': item_name, 'trigger': 'item-delete'
                }
            )
            self.extent_end_datetime = new_extent_end_datetime
            updated |= True

        return updated

    def _update_temporal_extent(
        self,
        item,
        action,
        old_start_datetime,
        new_start_datetime,
        old_end_datetime,
        new_end_datetime
    ):
        '''Updates the collection's temporal extent when item's are updated.

        This function will only be called, if the item's properties _datetime, _start_datetime or
        _end_datetime have changed (at least one of them). If the calling item has no range defined
        (i.e. no properties.start_datetime and no properties.end_datetime, but a properties.datetime
        only), this function will be called using the item's properties.datetime both for the
        start_ and the end_datetime as well.

        Args:
            collection: Collection
                Collection instance on which to operate
            item: Item
                Item that changed
            action: str
                either up insert, update or delete
            old_start_datetime: datetime
                item's old value for properties_start_datetime or properties_datetime
            new_start_datetime: datetime
                item's updated value for properties_start_datetime or properties_datetime
            old_end_datetime: datetime
                item's old value for properties_end_datetime or properties_datetime
            new_end_datetime: datetime
                item's updated value for properties_end_datetime or properties_datetime

        Returns:
            bool: True if temporal extent has been updated, false otherwise
        '''
        updated = False
        qs_other_items_with_properties_datetime = None
        # INSERT (as item_id is None)
        if action == "insert":
            logger.debug(
                "Item Inserted (datetime: start=%s, end=%s) in collection "
                "(current extent; start=%s, end=%s); updating the collection's temporal "
                "extent if needed.",
                new_start_datetime,
                new_end_datetime,
                self.extent_start_datetime,
                self.extent_end_datetime,
                extra={
                    'collection': self.name, 'item': item.name, 'trigger': 'item-insert'
                }
            )
            updated = self._update_temporal_extent_on_item_insert(
                new_start_datetime,
                new_end_datetime,
                item.name,
            )

        # UPDATE
        elif action == "update":
            logger.debug(
                "Item updated (old datetime: start=%s, end=%s; new datetime: start=%s, end=%s) "
                "in collection (current extent; start=%s, end=%s); updating the collection's "
                "temporal extent if needed.",
                old_start_datetime,
                old_end_datetime,
                new_start_datetime,
                new_end_datetime,
                self.extent_start_datetime,
                self.extent_end_datetime,
                extra={
                    'collection': self.name, 'item': item.name, 'trigger': 'item-update'
                }
            )
            qs_other_items = None
            if old_start_datetime != new_start_datetime:
                if (
                    old_start_datetime == self.extent_start_datetime and
                    new_start_datetime > old_start_datetime
                ):
                    # item has defined the left and bound of the
                    # collection's temporal extent before the update.
                    # Collection's left bound needs to be updated now:
                    # get all items but the one to that is being updated:
                    qs_other_items = type(item).objects.filter(collection_id=self.pk
                                                              ).exclude(id=item.pk)
                    updated_temp, qs_other_items_with_properties_datetime = (
                        self._update_start_temporal_extent_on_item_update(
                            old_start_datetime,
                            new_start_datetime,
                            item.name,
                            qs_other_items
                        )
                    )
                    updated |= updated_temp
                else:
                    # Item probably has defined the left bound before update and
                    # might define the new left bound again
                    updated_temp, qs_other_items_with_properties_datetime = (
                        self._update_start_temporal_extent_on_item_update(
                            old_start_datetime,
                            new_start_datetime,
                            item.name,
                            qs_other_items=None
                        )
                    )
                    updated |= updated_temp

            if old_end_datetime != new_end_datetime:
                if (
                    old_end_datetime == self.extent_end_datetime and
                    new_end_datetime < old_end_datetime
                ):
                    # item has defined the right bound of the
                    # collection's temporal extent before the update.
                    # Collection's right bound needs to be updated now:
                    # get all items but the one that is being updated:
                    qs_other_items = type(item).objects.filter(collection_id=self.pk
                                                              ).exclude(id=item.pk)

                    updated |= self._update_end_temporal_extent_on_item_update(
                        old_end_datetime,
                        new_end_datetime,
                        item.name,
                        qs_other_items=qs_other_items,
                        qs_other_items_with_properties_datetime=
                        qs_other_items_with_properties_datetime
                    )
                else:
                    # Item probably has defined the right bound before update and
                    # might define the new right bound again
                    updated |= self._update_end_temporal_extent_on_item_update(
                        old_end_datetime,
                        new_end_datetime,
                        item.name,
                        qs_other_items=None,
                        qs_other_items_with_properties_datetime=
                        qs_other_items_with_properties_datetime
                    )

        # DELETE
        elif action == 'delete':
            logger.debug(
                "Item deleted (datetime: start=%s, end=%s) "
                "in collection (current extent; start=%s, end=%s); updating the collection's "
                "temporal extent if needed.",
                old_start_datetime,
                old_end_datetime,
                self.extent_start_datetime,
                self.extent_end_datetime,
                extra={
                    'collection': self.name, 'item': item.name, 'trigger': 'item-delete'
                }
            )
            if (
                old_start_datetime == self.extent_start_datetime or
                old_end_datetime == self.extent_end_datetime
            ):
                # get all items but the one to be deleted:
                qs_other_items = type(item).objects.filter(collection_id=self.pk
                                                          ).exclude(id=item.pk)
                updated_temp, qs_other_items_with_properties_datetime = (
                    self._update_start_temporal_extent_on_item_delete(
                        old_start_datetime,
                        item.name,
                        qs_other_items
                    )
                )
                updated |= updated_temp
                updated |= self._update_end_temporal_extent_on_item_delete(
                    old_end_datetime,
                    item.name,
                    qs_other_items=qs_other_items,
                    qs_other_items_with_properties_datetime=qs_other_items_with_properties_datetime
                )
            else:
                updated_temp, qs_other_items_with_properties_datetime = (
                    self._update_start_temporal_extent_on_item_delete(
                        old_start_datetime,
                        item.name,
                        qs_other_items=None,
                    )
                )

                updated |= updated_temp
                updated |= self._update_end_temporal_extent_on_item_delete(
                    old_end_datetime,
                    item.name,
                    qs_other_items=None,
                    qs_other_items_with_properties_datetime=qs_other_items_with_properties_datetime
                )
        return updated
