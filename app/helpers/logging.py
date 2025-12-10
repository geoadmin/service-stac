from contextlib import contextmanager
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from logging import ERROR
from logging import INFO
from logging import getLogger
from logging.config import dictConfig
from time import time
from typing import Generator

from django.conf import settings


class TimestampedStringIO(StringIO):
    """ A StringIO-like in-memory text buffer that logs each write and stores a timestamp for when
    the content was appended.

    """

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level
        self.messages: list[tuple[float, int, str]] = []

    def write(self, s: str) -> int:
        message = s.strip()
        if message:
            self.messages.append((time(), self.level, message))
        return len(s)


@contextmanager
def redirect_std_to_logger(logger_name: str,
                           stderr_level: int = ERROR,
                           stdout_level: int = INFO) -> Generator[None, None, None]:
    """ A context manager that redirects sys.stdout and sys.stderr to the logger using the given
    levels.

    Use it like this:

        import sys
        from utils.logging import redirect_std_to_logger

        with redirect_std_to_logger('my_module'):
            sys.out('This gets logged with level INFO')
            sys.err('This gets logged with level ERROR')

    """

    stderr = TimestampedStringIO(stderr_level)
    stdout = TimestampedStringIO(stdout_level)
    exception: Exception | None = None
    with redirect_stderr(stderr), redirect_stdout(stdout):
        try:
            yield
        except Exception as e:  # pylint: disable=broad-exception-caught
            exception = e

    logger = getLogger(logger_name)
    dictConfig(settings.LOGGING)
    for _, level, message in sorted(stderr.messages + stdout.messages):
        logger.log(level, message)
    if exception:
        logger.exception(exception)
