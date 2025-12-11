import sys
from logging import DEBUG
from logging import ERROR
from logging import FATAL
from logging import INFO
from unittest.mock import call
from unittest.mock import patch

from helpers.logging import TimestampedStringIO
from helpers.logging import redirect_std_to_logger

from django.test import TestCase


class LoggingHelperTests(TestCase):

    def test_timestamped_string_io(self):
        out = TimestampedStringIO(level=1)

        with patch('helpers.logging.time', return_value=100):
            self.assertEqual(out.write('test'), 4)
            self.assertEqual(out.messages, [(100, 1, 'test')])

    def test_redirect_std_to_logger(self):
        with patch('helpers.logging.getLogger') as logger:
            with redirect_std_to_logger('test'):
                sys.stdout.write('stdout 1')
                sys.stderr.write('stderr 1')
                sys.stderr.write('stderr 2\n')
                sys.stdout.write(' stdout 2')

        self.assertEqual(
            logger.mock_calls,
            [
                call('test'),
                call().log(INFO, 'stdout 1'),
                call().log(ERROR, 'stderr 1'),
                call().log(ERROR, 'stderr 2'),
                call().log(INFO, 'stdout 2'),
            ]
        )

    def test_redirect_std_to_logger_custom_level(self):
        with patch('helpers.logging.getLogger') as logger:
            with redirect_std_to_logger('test', stderr_level=FATAL, stdout_level=DEBUG):
                sys.stdout.write('stdout 1')
                sys.stderr.write('stderr 1')
                sys.stderr.write('stderr 2\n')
                sys.stdout.write(' stdout 2')

        self.assertEqual(
            logger.mock_calls,
            [
                call('test'),
                call().log(DEBUG, 'stdout 1'),
                call().log(FATAL, 'stderr 1'),
                call().log(FATAL, 'stderr 2'),
                call().log(DEBUG, 'stdout 2'),
            ]
        )

    def test_redirect_std_to_logger_exception(self):
        exception = RuntimeError('abort')
        with patch('helpers.logging.getLogger') as logger:
            with redirect_std_to_logger('test'):
                sys.stdout.write('stdout 1')
                sys.stderr.write(' stderr 1\n')
                raise exception

        self.assertEqual(
            logger.mock_calls,
            [
                call('test'),
                call().log(INFO, 'stdout 1'),
                call().log(ERROR, 'stderr 1'),
                call().exception(exception),
            ]
        )
