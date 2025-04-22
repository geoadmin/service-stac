from unittest.mock import patch

from middleware.logging import RequestResponseLoggingMiddleware

from django.http import FileResponse
from django.http import JsonResponse
from django.test import RequestFactory
from django.test import TestCase
from django.test.utils import override_settings


class RequestResponseLoggingMiddlewareTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(LOGGING_MAX_REQUEST_PAYLOAD_SIZE=5)
    @override_settings(LOGGING_MAX_RESPONSE_PAYLOAD_SIZE=6)
    @patch('middleware.logging.time.time')
    @patch('middleware.logging.logger')
    def test_logging_middleware_logs(self, logger, time):
        request = self.factory.post(
            path='/some-url/?query=café&location=New York&path=/:foo,/:bar',
            data={'foo': 'bar'},
            content_type='application/json'
        )
        response = JsonResponse(data={'bar': 'baz'}, status=204, headers={'X-Foo': 'Bar'})

        time.side_effect = [1, 2]
        middleware = RequestResponseLoggingMiddleware(lambda r: response)
        middleware(request)

        logger.debug.assert_called_once()
        encoded = 'query=caf%C3%A9&location=New%20York&path=/:foo,/:bar'
        logger.debug.assert_called_with(
            'Request %s %s?%s',
            'POST',
            '/some-url/',
            encoded,
            extra={
                'request': request, 'request.query': encoded, 'request.payload': '{"foo'
            }
        )

        logger.info.assert_called_once()
        logger.info.assert_called_with(
            'Response %s %s %s?%s',
            204,
            'POST',
            '/some-url/',
            encoded,
            extra={
                'request': request,
                'response': {
                    'code': 204,
                    'headers': {
                        'Content-Type': 'application/json', 'X-Foo': 'Bar'
                    },
                    'duration': 1,
                    'payload': '{"bar"'
                }
            }
        )

    @patch('middleware.logging.time.time')
    @patch('middleware.logging.logger')
    def test_logging_middleware_skips_content_types(self, logger, time):
        request = self.factory.post('/some-url/', data={'foo': 'bar'})  # multipart
        response = FileResponse(content_type='application/octet-stream')

        time.side_effect = [1, 2]
        middleware = RequestResponseLoggingMiddleware(lambda r: response)
        middleware(request)

        logger.debug.assert_called_once()
        logger.debug.assert_called_with(
            'Request %s %s?%s',
            'POST',
            '/some-url/',
            '',
            extra={
                'request': request, 'request.query': ''
            }
        )

        logger.info.assert_called_once()
        logger.info.assert_called_with(
            'Response %s %s %s?%s',
            200,
            'POST',
            '/some-url/',
            '',
            extra={
                'request': request,
                'response': {
                    'code': 200,
                    'headers': {
                        'Content-Type': 'application/octet-stream',
                    },
                    'duration': 1
                }
            }
        )

    @patch('middleware.logging.logger')
    def test_logging_middleware_skips_admin_ui_request_content(self, logger):
        request = self.factory.post(
            path='/api/stac/admin/foo', data={'foo': 'bar'}, content_type='application/json'
        )
        response = JsonResponse(data={'bar': 'baz'}, status=204, headers={'X-Foo': 'Bar'})

        middleware = RequestResponseLoggingMiddleware(lambda r: response)
        middleware(request)

        logger.debug.assert_called_once()
        logger.debug.assert_called_with(
            'Request %s %s?%s',
            'POST',
            '/api/stac/admin/foo',
            '',
            extra={
                'request': request, 'request.query': ''
            }
        )
