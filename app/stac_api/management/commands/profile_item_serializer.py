import cProfile
import os
import pstats

from django.conf import settings

from rest_framework.test import APIRequestFactory

from stac_api.models.item import Item
from stac_api.utils import CommandHandler
from stac_api.utils import CustomBaseCommand

STAC_BASE_V = f'{settings.STAC_BASE}/v1'


class Handler(CommandHandler):

    def profiling(self):
        # pylint: disable=import-outside-toplevel,possibly-unused-variable
        from stac_api.serializers.item import ItemSerializer
        collection_id = self.options["collection"]
        qs = Item.objects.filter(collection__name=collection_id
                                ).prefetch_related('assets', 'links')[:self.options['limit']]
        context = {
            'request': APIRequestFactory().get(f'{STAC_BASE_V}/collections/{collection_id}/items')
        }
        cProfile.runctx(
            'ItemSerializer(qs, context=context, many=True).data',
            None,
            locals(),
            f'{settings.BASE_DIR}/{os.environ["LOGS_DIR"]}/stats-file',
            sort=self.options['sort']
        )
        stats = pstats.Stats(f'{settings.BASE_DIR}/{os.environ["LOGS_DIR"]}/stats-file')
        stats.sort_stats(self.options['sort']).print_stats()

        self.print_success('Done')


class Command(CustomBaseCommand):
    help = """ItemSerializer profiling command

    Profiling of the serialization of many items.

    See https://docs.python.org/3.7/library/profile.html
    """

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--collection',
            type=str,
            default='perftest-collection-0',
            help="Collection ID to use for the ItemSerializer profiling"
        )
        parser.add_argument('--limit', type=int, default=100, help="Limit to use for the query")
        parser.add_argument('--sort', type=str, default='tottime', help="Profiling output sorting")

    def handle(self, *args, **options):
        Handler(self, options).profiling()
