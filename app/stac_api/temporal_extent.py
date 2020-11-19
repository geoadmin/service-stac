import logging

logger = logging.getLogger(__name__)


def update_temporal_extent_on_item_insert(
    collection, new_start_datetime, new_end_datetime, item_id
):
    '''
    This function is called from within update_temporal_extent() when a new
    item is inserted to the collection.
    :param new_start_datetime: item's updated value for properties_start_datetime
    :param new_end_datetime: item's updated value for properties_end_datetime
    :param item_id: the id of the item being treated
    '''
    logger.debug(
        "Inserting item %s (start_datetime: %s, end_datetime: %s) in "
        "collection %s and updating the collection's temporal extent.",
        item_id,
        new_start_datetime,
        new_end_datetime,
        collection.collection_name,
        extra={'collection_name': collection.collection_name}
    )
    if collection.cache_start_datetime is None:
        # first item in collection, as cache_start_datetime is None:
        collection.cache_start_datetime = new_start_datetime
    elif collection.cache_start_datetime > new_start_datetime:
        # new item starts earlier that current collection range starts
        collection.cache_start_datetime = new_start_datetime

    if collection.cache_end_datetime is None:
        #first item in collection, as cache_start_datetime is None
        collection.cache_end_datetime = new_end_datetime
    elif collection.cache_end_datetime < new_end_datetime:
        # new item starts after current collection's range ends
        collection.cache_end_datetime = new_end_datetime

    collection.save()


def update_start_temporal_extent_on_item_update(
    collection,
    old_start_datetime,
    new_start_datetime,
    old_end_datetime,
    new_end_datetime,
    item_id,
    qs=None
):
    '''
    This function is called from within update_temporal_extent() when the
    start_datetime of an item in the collection is updated to check if the
    collection's start_datetime needs to be updated.
    :param old_start_datetime: item's old value for properties_start_datetime
    :param new_start_datetime: item's updated value for properties_start_datetime
    :param old_end_datetime: item's old value for properties_end_datetime
    :param new_end_datetime: item's updated value for properties_end_datetime
    :param item_id: the id of the item being treated
    :param qs: (optional) queryset with all items of the collection excluding the one
    being updated.
    '''
    logger.debug(
        "Updating start of item %s in collection %s (old start: %s, new start: %s, "
        "old end: %s, new end: %s) ",
        item_id,
        collection.collection_name,
        old_start_datetime,
        new_start_datetime,
        old_end_datetime,
        new_end_datetime,
        extra={'collection_name': collection.collection_name}
    )

    if old_start_datetime == collection.cache_start_datetime:
        # item's old start_datetime was defining left bound of the temporal
        # extent interval of collection before update
        if new_start_datetime < old_start_datetime:
            # item's start_datetime was shifted to the left (earlier)
            collection.cache_start_datetime = new_start_datetime
        else:
            # item's start_datetime was shifted to the right (later)
            # but was defining the left bound of the temporal extent
            # of the collection before
            # --> hence the new start_datetime of the collection
            # needs to be determined:
            # set earliest start_datetime to min(earliest_start_datetime
            # of all items but the one currently updated and
            # new_start_datetime).
            if bool(qs.filter(properties_start_datetime__isnull=False)):
                earliest_start_datetime = min(
                    new_start_datetime,
                    qs.filter(properties_start_datetime__isnull=False
                             ).earliest('properties_start_datetime').properties_start_datetime
                )
            else:
                earliest_start_datetime = new_start_datetime
            # set earliest datetime to min(earliest_datetime of all items
            # bute the one currently updated and new_start_datetime)
            if bool(qs.filter(properties_datetime__isnull=False)):
                earliest_datetime = min(
                    new_start_datetime,
                    qs.filter(properties_datetime__isnull=False
                             ).earliest('properties_datetime').properties_datetime
                )
            else:
                earliest_datetime = new_start_datetime
            collection.cache_start_datetime = min(earliest_start_datetime, earliest_datetime)
    elif new_start_datetime < collection.cache_start_datetime:
        # item's start_datetime did not define the left bound of the
        # collection's temporal extent before update, which does not
        # matter anyways, as it defines the new left bound after update
        # and collection's start_datetime can be simply adjusted
        collection.cache_start_datetime = new_start_datetime

    collection.save()


def update_end_temporal_extent_on_item_update(
    collection,
    old_start_datetime,
    new_start_datetime,
    old_end_datetime,
    new_end_datetime,
    item_id,
    qs=None
):
    '''
    This function is called from within update_temporal_extent() when an
    item in the collection is updated to check if the collection's
    end_datetime needs to be updated.
    :param old_start_datetime: item's old value for properties_start_datetime
    :param new_start_datetime: item's updated value for properties_start_datetime
    :param old_end_datetime: item's old value for properties_end_datetime
    :param new_end_datetime: item's updated value for properties_end_datetime
    :param item_id: the id of the item being treated
    :param qs: (optional) queryset with all items of the collection excluding the one
    being updated.
    '''
    logger.debug(
        "Updating end of item %s in collection %s (old start: %s, new start: %s, "
        "old end: %s, new end: %s) ",
        item_id,
        collection.collection_name,
        old_start_datetime,
        new_start_datetime,
        old_end_datetime,
        new_end_datetime,
        extra={'collection_name': collection.collection_name}
    )

    if old_end_datetime == collection.cache_end_datetime:
        # item's old end_datetime was defining the right bound of
        # the collection's temporal extent interval before update
        if new_end_datetime > old_end_datetime:
            # item's end_datetime was shifted to the right (later)
            collection.cache_end_datetime = new_end_datetime
        else:
            # item's end_datetime was shifted to the left (earlier)
            # but was defining the right bound of the collection's
            # temporal extent.
            # --> hence the new end_datetime of the collection needs
            # to be determined:
            # set latest end_datetime to max(new_end_datetime and
            # end_datetime of all items but the one currently updated).
            if bool(qs.filter(properties_end_datetime__isnull=False)):
                latest_end_datetime = max(
                    new_end_datetime,
                    qs.filter(properties_end_datetime__isnull=False
                             ).latest('properties_end_datetime').properties_end_datetime
                )
            else:
                latest_end_datetime = new_end_datetime
            # set latest datetime to max(new_end_datetime and
            # end end_datetime of all items but the one currently updated)
            if bool(qs.filter(properties_datetime__isnull=False)):
                latest_datetime = max(
                    new_end_datetime,
                    qs.filter(properties_datetime__isnull=False
                             ).latest('properties_datetime').properties_datetime
                )
            else:
                latest_datetime = new_end_datetime
            collection.cache_end_datetime = max(latest_end_datetime, latest_datetime)
    elif new_end_datetime > collection.cache_end_datetime:
        # item's end_datetime did not define the right bound of
        # the collection's temporal extent before update, which
        # does not matter anyways, as it defines the right bound
        # after update and collection's end_date can be simply
        # adjusted
        collection.cache_end_datetime = new_end_datetime

    collection.save()


def update_start_temporal_extent_on_item_delete(
    collection,
    old_start_datetime,
    new_start_datetime,
    old_end_datetime,
    new_end_datetime,
    item_id,
    qs=None
):
    '''
    This function is called from within update_temporal_extent() when an
    item is deleted from the collection to check if the collection's
    start_datetime needs to be updated.
    :param old_start_datetime: item's old value for properties_start_datetime
    :param new_start_datetime: item's updated value for properties_start_datetime
    :param old_end_datetime: item's old value for properties_end_datetime
    :param new_end_datetime: item's updated value for properties_end_datetime
    :param item_id: the id of the item being treated
    :param qs: (optional) queryset with all items of the collection excluding the one
    being updated.
    '''
    logger.debug(
        "Deleting item %s from collection %s and updating the collection's start date",
        item_id,
        collection.collection_name,
        extra={'collection_name': collection.collection_name}
    )

    if old_start_datetime == collection.cache_start_datetime:
        # item that is to be deleted defined left bound of collection's
        # temporal extent
        # first set cache_start_datetime to None, in case
        # the currently deleted item is the only item of the collection
        collection.cache_start_datetime = None

        logger.warning(
            'Looping (twice) over all items of collection %s,'
            'to update temporal extent, this may take a while',
            collection.collection_name
        )

        # get earliest start_datetime or none, in case none exists
        if bool(qs.filter(properties_start_datetime__isnull=False)):
            earliest_start_datetime = qs.filter(
                properties_start_datetime__isnull=False
            ).earliest('properties_start_datetime').properties_start_datetime
        else:
            earliest_start_datetime = None

        # get earliest datetime, or none in case none exists
        if bool(qs.filter(properties_datetime__isnull=False)):
            earliest_datetime = qs.filter(properties_datetime__isnull=False
                                         ).earliest('properties_datetime').properties_datetime
        else:
            earliest_datetime = None

        # set collection's new start_datetime to the minimum of the earliest
        # item's start_datetime or datetime
        if earliest_start_datetime is not None and earliest_datetime is not None:
            collection.cache_start_datetime = min(earliest_start_datetime, earliest_datetime)
        elif earliest_datetime is not None:
            collection.cache_start_datetime = earliest_datetime
        else:
            collection.cache_start_datetime = earliest_start_datetime

    collection.save()


def update_end_temporal_extent_on_item_delete(
    collection,
    old_start_datetime,
    new_start_datetime,
    old_end_datetime,
    new_end_datetime,
    item_id,
    qs=None
):
    '''
    This function is called from within update_temporal_extent() when an
    item is deleted from the collection to check if the collection's
    end_datetime needs to be updated.
    :param old_start_datetime: item's old value for properties_start_datetime
    :param new_start_datetime: item's updated value for properties_start_datetime
    :param old_end_datetime: item's old value for properties_end_datetime
    :param new_end_datetime: item's updated value for properties_end_datetime
    :param item_id: the id of the item being treated
    :param qs: (optional) queryset with all items of the collection excluding the one
    being updated.
    '''
    logger.debug(
        "Deleting item %s from collection %s and updating the collection's end date",
        item_id,
        collection.collection_name,
        extra={'collection_name': collection.collection_name}
    )

    if old_end_datetime == collection.cache_end_datetime:
        # item that is to be deleted defined right bound of collection's
        # temporal extent
        # first set cache_end_datetime to None, in case
        # the currently deleted item is the only item of the collection
        collection.cache_end_datetime = None

        logger.warning(
            'Looping (twice) over all items of collection %s,'
            'to update temporal extent, this may take a while',
            collection.collection_name
        )
        # get latest end_datetime or none, in case none exists
        if bool(qs.filter(properties_end_datetime__isnull=False)):
            latest_end_datetime = qs.filter(
                properties_end_datetime__isnull=False
            ).latest('properties_end_datetime').properties_end_datetime
        else:
            latest_end_datetime = None

        # get latest datetime, or none in case none exists
        if bool(qs.filter(properties_datetime__isnull=False)):
            latest_datetime = qs.filter(properties_datetime__isnull=False
                                       ).latest('properties_datetime').properties_datetime
        else:
            latest_datetime = None

        # set collection's new end_datetime to the maximum of the latest
        # item's end_datetime or datetime
        if latest_end_datetime is not None and latest_datetime is not None:
            collection.cache_end_datetime = max(latest_end_datetime, latest_datetime)
        elif latest_datetime is not None:
            collection.cache_end_datetime = latest_datetime
        else:
            collection.cache_end_datetime = latest_end_datetime

    collection.save()


def update_temporal_extent(
    item,
    collection,
    action,
    old_start_datetime,
    new_start_datetime,
    old_end_datetime,
    new_end_datetime,
    item_id
):
    '''
    updates the collection's temporal extent when item's are updated. This
    function will only be called, if the item's properties start_ or end_
    datetime or the properties_datetime have changed (at least one of them).
    :param action: either up (insert, update) or rm (delete)
    :param old_start_datetime: item's old value for properties_start_datetime
    :param new_start_datetime: item's updated value for properties_start_datetime
    :param old_end_datetime: item's old value for properties_end_datetime
    :param new_end_datetime: item's updated value for properties_end_datetime
    :param item_id: the id of the item being treated
    If the calling item has no range defined (i.e. no properties.start_datetime
    and no properties.end_datetime, but a properties.datetime only), this
    function will be called using the item's properties.datetime both for the
    start_ and the end_datetime as well.
    If updating the collection's temporal extent fails, an error will be raised.
    '''
    # INSERT (as item_id is None)
    if action == "insert":
        update_temporal_extent_on_item_insert(
            collection, new_start_datetime, new_end_datetime, item_id
        )

    # UPDATE
    elif action == "update":
        qs = None
        if old_start_datetime != new_start_datetime:
            if old_start_datetime == collection.cache_start_datetime and \
                new_start_datetime > old_start_datetime:
                # item has defined the left and bound of the
                # collection's temporal extent before the update.
                # Collection's left bound needs to be updated now:
                # get all items but the one to that is being updated:
                logger.warning(
                    'Looping over all items of collection %s,'
                    'to update temporal extent, this may take a while',
                    collection.collection_name
                )
                qs = item.__class__.objects.filter(collection_id=collection.pk).exclude(id=item_id)
                update_start_temporal_extent_on_item_update(
                    collection,
                    old_start_datetime,
                    new_start_datetime,
                    old_end_datetime,
                    new_end_datetime,
                    item_id,
                    qs
                )
            else:
                # Item probably has defined the left bound before update and
                # might define the new left bound again
                update_start_temporal_extent_on_item_update(
                    collection,
                    old_start_datetime,
                    new_start_datetime,
                    old_end_datetime,
                    new_end_datetime,
                    item_id
                )

        if old_end_datetime != new_end_datetime:
            if old_end_datetime == collection.cache_end_datetime and \
                new_end_datetime < old_end_datetime:
                # item has defined the right bound of the
                # collection's temporal extent before the update.
                # Collection's right bound needs to be updated now:
                # only do the query, if not already done for start_datetime above
                if qs is None:
                    # get all items but the one that is being updated:
                    logger.warning(
                        'Looping over all items of collection %s,'
                        'to update temporal extent, this may take a while',
                        collection.collection_name
                    )
                    qs = item.__class__.objects.filter(collection_id=collection.pk
                                                      ).exclude(id=item_id)

                update_end_temporal_extent_on_item_update(
                    collection,
                    old_start_datetime,
                    new_start_datetime,
                    old_end_datetime,
                    new_end_datetime,
                    item_id,
                    qs
                )
            else:
                # Item probably has defined the right bound before update and
                # might define the new right bound again
                update_end_temporal_extent_on_item_update(
                    collection,
                    old_start_datetime,
                    new_start_datetime,
                    old_end_datetime,
                    new_end_datetime,
                    item_id
                )

    # DELETE
    elif action == 'remove':
        if old_start_datetime == collection.cache_start_datetime or \
            old_end_datetime == collection.cache_end_datetime:
            logger.warning(
                'Looping over all items of collection %s,'
                'to update temporal extent, this may take a while',
                collection.collection_name
            )
            # get all items but the one to be deleted:
            qs = item.__class__.objects.filter(collection_id=collection.pk).exclude(id=item_id)
            update_start_temporal_extent_on_item_delete(
                collection,
                old_start_datetime,
                new_start_datetime,
                old_end_datetime,
                new_end_datetime,
                item_id,
                qs
            )
            update_end_temporal_extent_on_item_delete(
                collection,
                old_start_datetime,
                new_start_datetime,
                old_end_datetime,
                new_end_datetime,
                item_id,
                qs
            )
        else:
            update_start_temporal_extent_on_item_delete(
                collection,
                old_start_datetime,
                new_start_datetime,
                old_end_datetime,
                new_end_datetime,
                item_id
            )
            update_end_temporal_extent_on_item_delete(
                collection,
                old_start_datetime,
                new_start_datetime,
                old_end_datetime,
                new_end_datetime,
                item_id
            )
