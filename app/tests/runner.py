import logging
import os
from distutils.util import strtobool

from django.test.runner import DiscoverRunner


class TestRunner(DiscoverRunner):

    # We run the tests with debug True
    # otherwise we run into issues with things
    # defined in settings_dev.py.
    # Other option would be a dedicated test settings
    # file, but this would require to set the ENV
    # variable DJANGO_SETTINGS_MODULE whenever running
    # tests (see https://stackoverflow.com/a/41349685/9896222)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug_mode = True

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        if not strtobool(os.getenv('TEST_ENABLE_LOGGING', 'False')):
            logger = logging.getLogger()
            for handler in logger.handlers:
                if handler.get_name() == 'console':
                    logger.removeHandler(handler)
