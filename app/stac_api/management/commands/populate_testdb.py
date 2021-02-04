import logging
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from stac_api.sample_data import importer
from stac_api.utils import CommandHandler

# path definition relative to the directory that contains manage.py
DATADIR = settings.BASE_DIR / 'app/stac_api/sample_data/'
logger = logging.getLogger(__name__)


class Handler(CommandHandler):

    def populate(self):
        # loop over the collection directories inside sample_data
        for collection_dir in os.scandir(DATADIR):
            if collection_dir.is_dir() and not collection_dir.name.startswith('_'):
                self.print('Import collection %s', collection_dir.name, level=1)
                importer.import_collection(collection_dir)
            else:
                self.print('Ignore file %s', collection_dir.name, level=2)
        self.print_success('Done')


class Command(BaseCommand):
    help = """Populates the local test database with sample data

    The sample data has to be located in stac_api/management/sample_data and
    structured as follows
    <collection_name>/
       |- items/
            |- <item1_name>.json
            |- <item2_name>.json
       |- collection.json
    """

    def handle(self, *args, **options):
        Handler(self, options).populate()
