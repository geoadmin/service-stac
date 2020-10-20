import logging
import os

from django.test.runner import DiscoverRunner


class TestRunner(DiscoverRunner):

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        if not os.getenv('TEST_ENABLE_LOGGING', None):
            logger = logging.getLogger()
            for handler in logger.handlers:
                if handler.get_name() == 'console':
                    logger.removeHandler(handler)
