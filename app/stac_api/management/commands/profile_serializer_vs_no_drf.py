import json
import logging
from timeit import timeit

from django.conf import settings
from django.core.management.base import BaseCommand

from rest_framework.test import APIRequestFactory

from stac_api.models import Item
from stac_api.utils import CommandHandler

logger = logging.getLogger(__name__)

STAC_BASE_V = settings.STAC_BASE_V


class Handler(CommandHandler):

    def profiling(self):
        # pylint: disable=import-outside-toplevel,possibly-unused-variable

        self.print('Starting profiling')
        from stac_api.serializers import ItemSerializer

        def serialize(qs):
            return {
                'features': [{
                    "id": item.name,
                    "collection": item.collection.name,
                    "geometry": str(item.geometry),
                    "created": item.created.isoformat(),
                    "updated": item.updated.isoformat(),
                    "properties": {
                        "datetime":
                            item.properties_datetime.isoformat()
                            if item.properties_datetime else '',
                        "properties_start_datetime":
                            item.properties_start_datetime.isoformat()
                            if item.properties_start_datetime else '',
                        "properties_end_datetime":
                            item.properties_end_datetime.isoformat()
                            if item.properties_end_datetime else '',
                        "properties_title": item.properties_title,
                    },
                    "type": "feature",
                    "stac_version": "0.9.0",
                    "assets": {
                        asset.name: {
                            "id": asset.name,
                            "title": asset.title,
                            "checksum_multihash": asset.checksum_multihash,
                            "description": asset.description,
                            "eo_gsd": asset.eo_gsd,
                            "geoadmin_lang": asset.geoadmin_lang,
                            "geoadmin_variant": asset.geoadmin_variant,
                            "proj_epsg": asset.proj_epsg,
                            "type": asset.media_type,
                            "created": asset.created.isoformat(),
                            "updated": asset.updated.isoformat()
                        } for asset in item.assets.all()
                    }
                } for item in qs]
            }

        collection_id = self.options["collection"]
        qs = Item.objects.filter(collection__name=collection_id
                                ).prefetch_related('assets', 'links')[:self.options['limit']]
        serialize(qs)
        context = {
            'request': APIRequestFactory().get(f'{STAC_BASE_V}/collections/{collection_id}/items')
        }
        # self.print(json.dumps(ItemSerializer(qs, context=context, many=True).data))
        serializer_time = timeit(
            stmt='ItemSerializer(qs, context=context, many=True).data',
            number=self.options['repeat'],
            globals=locals()
        )

        self.print('=' * 80)
        self.print(json.dumps(serialize(qs), indent=2))
        no_drf_time = timeit(stmt='serialize(qs)', number=self.options['repeat'], globals=locals())

        self.print_success('DRF time: %fms', serializer_time / self.options['repeat'] * 1000)
        self.print_success('NO DRF time: %fms', no_drf_time / self.options['repeat'] * 1000)


class Command(BaseCommand):
    help = """ItemSerializer vs simple serializer profiling command

    Profiling of the serialization of many items using DRF vs using a simple function.

    See https://docs.python.org/3.7/library/profile.html
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--collection',
            type=str,
            default='perftest-collection-0',
            help="Collection ID to use for the ItemSerializer profiling"
        )
        parser.add_argument('--limit', type=int, default=100, help="Limit to use for the query")
        parser.add_argument('--repeat', type=int, default=100, help="Repeat the measurement")

    def handle(self, *args, **options):
        Handler(self, options).profiling()
