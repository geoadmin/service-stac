from django.conf import settings
from django.contrib.auth.backends import RemoteUserBackend
from django.contrib.auth.middleware import PersistentRemoteUserMiddleware


class ApiGatewayMiddleware(PersistentRemoteUserMiddleware):
    """Persist user authentication based on the API Gateway headers."""
    header = "HTTP_GEOADMIN_USERNAME"

    def process_request(self, request):
        """Before processing the request, drop the Geoadmin-Username header if it's invalid.

        API Gateway always sends the Geoadmin-Username header regardless of
        whether it was able to authenticate the user. If it could not
        authenticate the user, the value of the header as seen on the wire is a
        single whitespace. An hexdump looks like this:

            47 65 6f 61 64 6d 69 6e 5f 75 73 65 72 6e 61 6d 65 3a 20 0d 0a
            Geoadmin-Username:...

        This doesn't seem possible to reproduce with curl. It is possible to
        reproduce with wget. It is unclear whether that technically counts as an
        empty value or a whitespace. It is also possible that AWS change their
        implementation later to send something slightly different. Regardless,
        we already have a separate signal to tell us whether that value is
        valid: Geoadmin-Authenticated. So we only consider Geoadmin-Username if
        Geoadmin-Authenticated is set to "true".

        Based on discussion in https://code.djangoproject.com/ticket/35971
        """
        if not settings.FEATURE_AUTH_ENABLE_APIGW:
            return None

        apigw_auth = request.META.get("HTTP_GEOADMIN_AUTHENTICATED", "false").lower() == "true"
        if not apigw_auth and self.header in request.META:
            del request.META[self.header]
        return super().process_request(request)


class ApiGatewayUserBackend(RemoteUserBackend):
    """ This backend is to be used in conjunction with the ``ApiGatewayMiddleware`.

    It is probably not needed to provide a custom remote user backend as our custom remote user
    middleware will never call authenticate if the feature is not enabled. But better be safe than
    sorry.
    """

    def authenticate(self, request, remote_user):
        if not settings.FEATURE_AUTH_ENABLE_APIGW:
            return None

        return super().authenticate(request, remote_user)
