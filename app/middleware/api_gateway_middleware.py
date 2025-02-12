from middleware import api_gateway

from django.conf import settings
from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth.middleware import PersistentRemoteUserMiddleware


class ApiGatewayMiddleware(PersistentRemoteUserMiddleware):
    """Persist user authentication based on the API Gateway headers."""
    header = api_gateway.REMOTE_USER_HEADER

    def process_request(self, request):
        if not settings.FEATURE_AUTH_ENABLE_APIGW:
            return None

        api_gateway.validate_username_header(request)
        return super().process_request(request)


class ApiGatewayUserBackend(RemoteUserBackend):
    """ This backend is to be used in conjunction with the ``ApiGatewayMiddleware`.

    Until proper authorization is implemented, all remote users authenticated via API Gateway
    headers are treated as superusers.

    """

    def authenticate(self, request, remote_user):
        if not settings.FEATURE_AUTH_ENABLE_APIGW:
            return None

        user = super().authenticate(request, remote_user)
        if user:
            # promote authenticated user to superuser for now until proper authorization is
            # implemented
            user.is_superuser = True
            user.save()
        return user
