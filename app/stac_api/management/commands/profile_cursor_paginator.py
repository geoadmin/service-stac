import cProfile
import logging
import pstats

from django.conf import settings
from django.core.management.base import BaseCommand

from rest_framework.pagination import CursorPagination
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from stac_api.models import Item
from stac_api.utils import CommandHandler

logger = logging.getLogger(__name__)

API_BASE = settings.API_BASE


class Handler(CommandHandler):

    def profiling(self):
        # pylint: disable=import-outside-toplevel,possibly-unused-variable
        collection_id = self.options["collection"]
        qs = Item.objects.filter(collection__name=collection_id).prefetch_related('assets', 'links')
        request = Request(
            APIRequestFactory().
            get(f'{API_BASE}/collections/{collection_id}/items?limit={self.options["limit"]}')
        )
        paginator = CursorPagination()

        cProfile.runctx(
            'paginator.paginate_queryset(qs, request)',
            None,
            locals(),
            f'{settings.BASE_DIR}/logs/stats-file',
            sort=self.options['sort']
        )
        stats = pstats.Stats(f'{settings.BASE_DIR}/logs/stats-file')
        stats.sort_stats(self.options['sort']).print_stats()

        self.print_success('Done')


class Command(BaseCommand):
    help = """Paginator paginate_queryset() profiling command

    Profiling of the method paginator.paginate_queryset(qs, request)

    See https://docs.python.org/3.7/library/profile.html
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--collection',
            type=str,
            default='perftest-collection-0',
            help="Collection ID to use for the queryset profiling"
        )
        parser.add_argument('--limit', type=int, default=100, help="Limit to use for the queryset")
        parser.add_argument('--sort', type=str, default='tottime', help="Profiling output sorting")
        parser.add_argument(
            '--lines', type=str, default=50, help="Profiling output numbers of line to show"
        )

    def handle(self, *args, **options):
        Handler(self, options).profiling()
