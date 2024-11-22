from django.contrib.auth.middleware import PersistentRemoteUserMiddleware


class ApiGatewayMiddleware(PersistentRemoteUserMiddleware):
    header = "HTTP_GEOADMIN_USERNAME"
