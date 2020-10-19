import os
import logging
import logging.config
import sys
from contextlib import contextmanager

from config.settings import get_logging_config
from nose2.main import discover

from django.test.runner import DiscoverRunner

logger = logging.getLogger(__name__)


class TestRunner(DiscoverRunner):

    err_count = 0
    _hooks = ('startTestRun', 'reportFailure', 'reportError')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_tests = None
        # Configure logging
        logging.config.dictConfig(get_logging_config())

    def hooks(self):
        return [(hook, self) for hook in self._hooks]

    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        logger.info('Running tests with nose2')
        self.extra_tests = extra_tests

        with self.test_environment():
            argv = self.make_argv(test_labels)
            print('=' * 80)
            discover(argv=argv, exit=False, extraHooks=self.hooks())

        return self.err_count

    def make_argv(self, test_labels):
        logger.debug('Make argv: test_labels=%s', test_labels)
        test_dir = os.getenv('TEST_DIR', './tests')
        argv = [
            'nose2',
            '-c',
            f'{test_dir}/unittest.cfg',
            '--start-dir',
            test_dir,
            '--junit-xml-path',
            f'{test_dir}/reports/nose2-junit.xml',
        ]

        argv.extend(['-v'] * (self.verbosity - 1))

        if self.failfast:
            argv.append('-F')

        if test_labels:
            argv.extend([t for t in test_labels if not t.startswith('-')])

        logger.debug('Call %s', argv)

        return argv

    @contextmanager
    def test_environment(self):
        self.setup_test_environment()
        old_config = self.setup_databases()
        logger.debug("Django test environment set up")
        try:
            yield
        finally:
            self.teardown_databases(old_config)
            self.teardown_test_environment()
            logger.debug("Django test environment torn down")

    # plugin hooks the runner handles
    # the hooks name are given from baseclass therefore disable pylint invalid-name
    # pylint: disable=invalid-name
    def startTestRun(self, event):
        if self.extra_tests is None:
            return
        for test in self.extra_tests:
            event.suite.addTest(test)

    def reportFailure(self, event):
        self.err_count += 1

    def reportError(self, event):
        self.reportFailure(event)
