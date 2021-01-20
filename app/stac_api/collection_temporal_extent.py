import logging

logger = logging.getLogger(__name__)


def update_temporal_extent_on_item_insert(
    collection, new_start_datetime, new_end_datetime, item_name
):
    '''This function is called from within update_temporal_extent() when a new item is inserted to
    the collection.

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
    logger.debug(
        "Inserting item %s (start_datetime: %s, end_datetime: %s) in "
        "collection %s and updating the collection's temporal extent.",
        item_name,
        new_start_datetime,
        new_end_datetime,
        collection.name,
        extra={'collection': collection.name}
    )
    if collection.extent_start_datetime is None:
        updated |= True
        # first item in collection, as extent_start_datetime is None:
        collection.extent_start_datetime = new_start_datetime
    elif collection.extent_start_datetime > new_start_datetime:
        updated |= True
        # new item starts earlier that current collection range starts
        collection.extent_start_datetime = new_start_datetime

    if collection.extent_end_datetime is None:
        updated |= True
        #first item in collection, as extent_start_datetime is None
        collection.extent_end_datetime = new_end_datetime
    elif collection.extent_end_datetime < new_end_datetime:
        updated |= True
        # new item starts after current collection's range ends
        collection.extent_end_datetime = new_end_datetime

    return updated


def update_start_temporal_extent_on_item_update(
    collection,
    old_start_datetime,
    new_start_datetime,
    old_end_datetime,
    new_end_datetime,
    item_id,
    qs_other_items=None
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
        old_end_datetime: datetime
            item's old value for properties_end_datetime
        new_end_datetime: datetime
            item's updated value for properties_end_datetime
        item_id: int
            the id of the item being treated (pk)
        qs_other_items: QuerySet | None
            queryset with all items of the collection excluding the one being updated. (optional)

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
        "Updating start of item %s in collection %s (old start: %s, new start: %s, "
        "old end: %s, new end: %s) ",
        item_id,
        collection.name,
        old_start_datetime,
        new_start_datetime,
        old_end_datetime,
        new_end_datetime,
        extra={'collection': collection.name}
    )

    if old_start_datetime == collection.extent_start_datetime:
        # item's old start_datetime was defining left bound of the temporal
        # extent interval of collection before update
        if new_start_datetime < old_start_datetime:
            updated |= True
            # item's start_datetime was shifted to the left (earlier)
            collection.extent_start_datetime = new_start_datetime
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
                'Looping over all items of collection %s,'
                'to update temporal extent, this may take a while',
                collection.name
            )
            qs_other_items_with_properties_start_datetime = qs_other_items.filter(
                properties_start_datetime__isnull=False
            )
            if qs_other_items_with_properties_start_datetime.exists():
                other_items_earliest_properties_start_datetime = (
                    qs_other_items_with_properties_start_datetime.
                    earliest('properties_start_datetime').properties_start_datetime
                )
                earliest_start_datetime = min(
                    new_start_datetime, other_items_earliest_properties_start_datetime
                )
            else:
                earliest_start_datetime = new_start_datetime
            # set earliest datetime to min(earliest_datetime of all items
            # but the one currently updated and new_start_datetime)
            logger.warning(
                'Looping over all items of collection %s,'
                'to update temporal extent, this may take a while',
                collection.name
            )
            qs_other_items_with_properties_datetime = qs_other_items.filter(
                properties_datetime__isnull=False
            )
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
            updated |= True
            collection.extent_start_datetime = min(earliest_start_datetime, earliest_datetime)
    elif new_start_datetime < collection.extent_start_datetime:
        # item's start_datetime did not define the left bound of the
        # collection's temporal extent before update, which does not
        # matter anyways, as it defines the new left bound after update
        # and collection's start_datetime can be simply adjusted
        updated |= True
        collection.extent_start_datetime = new_start_datetime

    return updated, return_qs


def update_end_temporal_extent_on_item_update(
    collection,
    old_start_datetime,
    new_start_datetime,
    old_end_datetime,
    new_end_datetime,
    item_id,
    qs_other_items=None,
    qs_other_items_with_properties_datetime=None
):
    '''This function is called from within update_temporal_extent() when an
    item in the collection is updated to check if the collection's
    end_datetime needs to be updated.

    Args:
        collection: Collection
            Collection instance on which to operate
        old_start_datetime: datetime
            item's old value for properties_start_datetime
        new_start_datetime: datetime
            item's updated value for properties_start_datetime
        old_end_datetime: datetime
            item's old value for properties_end_datetime
        new_end_datetime: datetime
            item's updated value for properties_end_datetime
        item_id: int
            the id of the item being treated (pk)
        qs_other_items: QuerySet | None
            queryset with all items of the collection excluding the one being updated. (optional)
        qs_other_items_with_properties_datetimes: QuerySet | None
            Already evaluated queryset with all items (but the one currently updated) that have
            non-null properties_datetime values (optional).

    Returns:
        bool: True if temporal extent has been updated, false otherwise
    '''
    updated = False
    logger.debug(
        "Updating end of item %s in collection %s (old start: %s, new start: %s, "
        "old end: %s, new end: %s) ",
        item_id,
        collection.name,
        old_start_datetime,
        new_start_datetime,
        old_end_datetime,
        new_end_datetime,
        extra={'collection': collection.name}
    )

    if old_end_datetime == collection.extent_end_datetime:
        # item's old end_datetime was defining the right bound of
        # the collection's temporal extent interval before update
        if new_end_datetime > old_end_datetime:
            # item's end_datetime was shifted to the right (later)
            updated |= True
            collection.extent_end_datetime = new_end_datetime
        else:
            # item's end_datetime was shifted to the left (earlier)
            # but was defining the right bound of the collection's
            # temporal extent.
            # --> hence the new end_datetime of the collection needs
            # to be determined:
            # set latest end_datetime to max(new_end_datetime and
            # end_datetime of all items but the one currently updated).
            logger.warning(
                'Looping over all items of collection %s,'
                'to update temporal extent, this may take a while',
                collection.name
            )
            qs_other_items_with_properties_end_datetime = qs_other_items.filter(
                properties_end_datetime__isnull=False
            )
            if qs_other_items_with_properties_end_datetime.exists():
                other_items_latest_end_datetime = (
                    qs_other_items_with_properties_end_datetime.latest('properties_end_datetime'
                                                                      ).properties_end_datetime
                )
                latest_end_datetime = max(new_end_datetime, other_items_latest_end_datetime)
            else:
                latest_end_datetime = new_end_datetime
            # set latest datetime to max(new_end_datetime and
            # end end_datetime of all items but the one currently updated)
            logger.warning(
                'Looping over all items of collection %s,'
                'to update temporal extent, this may take a while',
                collection.name
            )
            # get latest datetime, or none in case none exists and
            # use the already evaluated qs_other_items_with_properties_datetime, if it has
            # been passed to this function to save a DB hit.
            if qs_other_items_with_properties_datetime is None:
                qs_other_items_with_properties_datetime = qs_other_items.filter(
                    properties_datetime__isnull=False
                )
            if qs_other_items_with_properties_datetime.exists():
                other_items_latest_properties_datetime = (
                    qs_other_items_with_properties_datetime.latest('properties_datetime'
                                                                  ).properties_datetime
                )
                latest_datetime = max(new_end_datetime, other_items_latest_properties_datetime)
            else:
                latest_datetime = new_end_datetime
            updated |= True
            collection.extent_end_datetime = max(latest_end_datetime, latest_datetime)
    elif new_end_datetime > collection.extent_end_datetime:
        # item's end_datetime did not define the right bound of
        # the collection's temporal extent before update, which
        # does not matter anyways, as it defines the right bound
        # after update and collection's end_date can be simply
        # adjusted
        updated |= True
        collection.extent_end_datetime = new_end_datetime

    return updated


def update_start_temporal_extent_on_item_delete(
    collection, old_start_datetime, item_id, qs_other_items=None
):
    '''This function is called from within update_temporal_extent() when an
    item is deleted from the collection to check if the collection's
    start_datetime needs to be updated.

    Args:
        collection: Collection
            Collection instance on which to operate
        old_start_datetime: datetime
            item's old value for properties_start_datetime
        item_id: int
            the id of the item being treated (pk)
        qs_other_items: QuerySet | None
            queryset with all items of the collection excluding the one being updated. (optional)

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
        "Deleting item %s from collection %s and updating the collection's start date",
        item_id,
        collection.name,
        extra={'collection': collection.name}
    )

    if old_start_datetime == collection.extent_start_datetime:
        # item that is to be deleted defined left bound of collection's
        # temporal extent
        # first set extent_start_datetime to None, in case
        # the currently deleted item is the only item of the collection
        updated |= True
        collection.extent_start_datetime = None
        logger.warning(
            'Looping over all items of collection %s,'
            'to update temporal extent, this may take a while',
            collection.name
        )
        # get earliest start_datetime or none, in case none exists
        qs_other_items_with_properties_start_datetime = qs_other_items.filter(
            properties_start_datetime__isnull=False
        )
        if qs_other_items_with_properties_start_datetime.exists():
            earliest_start_datetime = qs_other_items_with_properties_start_datetime.earliest(
                'properties_start_datetime'
            ).properties_start_datetime
        else:
            earliest_start_datetime = None

        logger.warning(
            'Looping over all items of collection %s,'
            'to update temporal extent, this may take a while',
            collection.name
        )
        # get earliest datetime, or none in case none exists
        qs_other_items_with_properties_datetime = qs_other_items.filter(
            properties_datetime__isnull=False
        )
        if qs_other_items_with_properties_datetime.exists():
            earliest_datetime = qs_other_items_with_properties_datetime.earliest(
                'properties_datetime'
            ).properties_datetime
            return_qs = qs_other_items_with_properties_datetime
        else:
            earliest_datetime = None

        # set collection's new start_datetime to the minimum of the earliest
        # item's start_datetime or datetime
        if earliest_start_datetime is not None and earliest_datetime is not None:
            collection.extent_start_datetime = min(earliest_start_datetime, earliest_datetime)
        elif earliest_datetime is not None:
            collection.extent_start_datetime = earliest_datetime
        else:
            collection.extent_start_datetime = earliest_start_datetime

    return updated, return_qs


def update_end_temporal_extent_on_item_delete(
    collection,
    old_end_datetime,
    item_id,
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
        item_id: int
            the id of the item being treated (pk)
        qs_other_items: QuerySet | None
            queryset with all items of the collection excluding the one being updated. (optional)
        qs_other_items_with_properties_datetimes: QuerySet | None
            Already evaluated queryset with all items (but the one currently updated) that have
            non-null properties_datetime values (optional).

    Returns:
        bool: True if temporal extent has been updated, false otherwise
    '''
    updated = False
    logger.debug(
        "Deleting item %s from collection %s and updating the collection's end date",
        item_id,
        collection.name,
        extra={'collection': collection.name}
    )

    if old_end_datetime == collection.extent_end_datetime:
        # item that is to be deleted defined right bound of collection's
        # temporal extent
        # first set extent_end_datetime to None, in case
        # the currently deleted item is the only item of the collection
        updated |= True
        collection.extent_end_datetime = None

        logger.warning(
            'Looping over all items of collection %s,'
            'to update temporal extent, this may take a while',
            collection.name
        )
        # get latest end_datetime or none, in case none exists
        qs_other_items_with_properties_end_datetime = qs_other_items.filter(
            properties_end_datetime__isnull=False
        )
        if qs_other_items_with_properties_end_datetime.exists():
            latest_end_datetime = qs_other_items_with_properties_end_datetime.latest(
                'properties_end_datetime'
            ).properties_end_datetime
        else:
            latest_end_datetime = None

        # get latest datetime, or none in case none exists and
        # use the already evaluated qs_other_items_with_properties_datetime, if it has
        # been passed to this function to save a DB hit.
        logger.warning(
            'Looping over all items of collection %s,'
            'to update temporal extent, this may take a while',
            collection.name
        )
        if qs_other_items_with_properties_datetime is None:
            qs_other_items_with_properties_datetime = qs_other_items.filter(
                properties_datetime__isnull=False
            )
        if qs_other_items_with_properties_datetime.exists():
            latest_datetime = qs_other_items_with_properties_datetime.latest(
                'properties_datetime'
            ).properties_datetime
        else:
            latest_datetime = None

        # set collection's new end_datetime to the maximum of the latest
        # item's end_datetime or datetime
        if latest_end_datetime is not None and latest_datetime is not None:
            collection.extent_end_datetime = max(latest_end_datetime, latest_datetime)
        elif latest_datetime is not None:
            collection.extent_end_datetime = latest_datetime
        else:
            collection.extent_end_datetime = latest_end_datetime

    return updated


def update_temporal_extent(
    collection,
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
        updated = update_temporal_extent_on_item_insert(
            collection, new_start_datetime, new_end_datetime, item.name
        )

    # UPDATE
    elif action == "update":
        qs_other_items = None
        if old_start_datetime != new_start_datetime:
            if old_start_datetime == collection.extent_start_datetime and \
                new_start_datetime > old_start_datetime:
                # item has defined the left and bound of the
                # collection's temporal extent before the update.
                # Collection's left bound needs to be updated now:
                # get all items but the one to that is being updated:
                qs_other_items = type(item).objects.filter(collection_id=collection.pk
                                                          ).exclude(id=item.pk)
                updated_temp, qs_other_items_with_properties_datetime = (
                    update_start_temporal_extent_on_item_update(
                        collection,
                        old_start_datetime,
                        new_start_datetime,
                        old_end_datetime,
                        new_end_datetime,
                        item.pk,
                        qs_other_items
                    )
                )
                updated |= updated_temp
            else:
                # Item probably has defined the left bound before update and
                # might define the new left bound again
                updated_temp, qs_other_items_with_properties_datetime = (
                    update_start_temporal_extent_on_item_update(
                        collection,
                        old_start_datetime,
                        new_start_datetime,
                        old_end_datetime,
                        new_end_datetime,
                        item.pk,
                        qs_other_items=None
                    )
                )
                updated |= updated_temp
        if old_end_datetime != new_end_datetime:
            if old_end_datetime == collection.extent_end_datetime and \
                new_end_datetime < old_end_datetime:
                # item has defined the right bound of the
                # collection's temporal extent before the update.
                # Collection's right bound needs to be updated now:
                # get all items but the one that is being updated:
                qs_other_items = type(item).objects.filter(collection_id=collection.pk
                                                          ).exclude(id=item.pk)

                updated |= update_end_temporal_extent_on_item_update(
                    collection,
                    old_start_datetime,
                    new_start_datetime,
                    old_end_datetime,
                    new_end_datetime,
                    item.pk,
                    qs_other_items=qs_other_items,
                    qs_other_items_with_properties_datetime=qs_other_items_with_properties_datetime
                )
            else:
                # Item probably has defined the right bound before update and
                # might define the new right bound again
                updated |= update_end_temporal_extent_on_item_update(
                    collection,
                    old_start_datetime,
                    new_start_datetime,
                    old_end_datetime,
                    new_end_datetime,
                    item.pk,
                    qs_other_items=None,
                    qs_other_items_with_properties_datetime=qs_other_items_with_properties_datetime
                )

    # DELETE
    elif action == 'delete':
        if old_start_datetime == collection.extent_start_datetime or \
            old_end_datetime == collection.extent_end_datetime:
            logger.warning(
                'Looping over all items of collection %s,'
                'to update temporal extent, this may take a while',
                collection.name
            )
            # get all items but the one to be deleted:
            qs_other_items = type(item).objects.filter(collection_id=collection.pk
                                                      ).exclude(id=item.pk)
            updated_temp, qs_other_items_with_properties_datetime = (
                update_start_temporal_extent_on_item_delete(
                collection, old_start_datetime, item.pk, qs_other_items
                )
            )
            updated |= updated_temp
            updated |= update_end_temporal_extent_on_item_delete(
                collection,
                old_end_datetime,
                item.pk,
                qs_other_items=qs_other_items,
                qs_other_items_with_properties_datetime=qs_other_items_with_properties_datetime
            )
        else:
            updated_temp, qs_other_items_with_properties_datetime = (
                update_start_temporal_extent_on_item_delete(
                collection, old_start_datetime, item.pk, qs_other_items=None
                )
            )
            updated |= updated_temp
            updated |= update_end_temporal_extent_on_item_delete(
                collection,
                old_end_datetime,
                item.pk,
                qs_other_items=None,
                qs_other_items_with_properties_datetime=qs_other_items_with_properties_datetime
            )
    return updated
