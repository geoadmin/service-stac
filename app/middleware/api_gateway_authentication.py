from middleware import api_gateway

from django.conf import settings

from rest_framework.authentication import RemoteUserAuthentication


class ApiGatewayAuthentication(RemoteUserAuthentication):
    header = api_gateway.REMOTE_USER_HEADER

    def authenticate(self, request):
        if not settings.FEATURE_AUTH_ENABLE_APIGW:
            return None

        api_gateway.validate_username_header(request)
        return super().authenticate(request)

    def authenticate_header(self, request):
        # For this authentication method, users send a "Bearer" token via the
        # Authorization header. API Gateway looks up that token in Cognito and
        # sets the Geoadmin-Username and Geoadmin-Authenticated headers. In this
        # module we only care about the Geoadmin-* headers. But when
        # authentication fails with a 401 error we need to hint at the correct
        # authentication method from the point of view of the user, which is the
        # Authorization/Bearer scheme.
        return 'Bearer'
