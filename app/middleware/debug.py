import logging
import os
import time

logger = logging.getLogger(__name__)


def check_toolbar_env(request):
    """ callback to check whether debug toolbar should be shown or not

    for details see
    https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config  # pylint: disable=line-too-long
    """

    if os.environ.get('APP_ENV', 'prod') in ['local', 'dev']:
        return True

    return False


def request_response_logging_middleware(get_response):
    """ middleware to log all request / response pairs

    For debugging purposes it's useful to have logs of incoming
    request event and corresponding response with as much meta
    information as available.
    Note: the response payload is currently stripped to 200 chars
    """

    # One-time configuration and initialization.

    def middleware(request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        logger.info("request", extra={"request": request})
        start = time.time()

        response = get_response(request)

        logger.info(
            "request-response",
            extra={
                "request": request,
                "response": {
                    "code": response.status_code,
                    "content": str(response.content)[:200],
                    "headers": dict(response.items())
                },
                "duration": time.time() - start
            }
        )
        # Code to be executed for each request/response after
        # the view is called.

        return response

    return middleware
