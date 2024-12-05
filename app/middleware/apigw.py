from django.contrib import auth
from django.contrib.auth.middleware import PersistentRemoteUserMiddleware
from django.core.exceptions import ImproperlyConfigured


class ApiGatewayMiddleware(PersistentRemoteUserMiddleware):
    """Persist user authentication based on the API Gateway headers."""
    header = "HTTP_GEOADMIN_USERNAME"

    def get_username(self, request):
        """Extract the username from headers.

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
        """
        if request.META["HTTP_GEOADMIN_AUTHENTICATED"].lower() != "true":
            raise KeyError
        return request.META[self.header]

    # pylint: disable=no-else-return
    def process_request(self, request):
        """Copy/pasta of RemoteUserMiddleware.process_request with call to get_username.

        This is a straight copy/paste from RemoteUserMiddleware.process_request
        except for the injection of the get_username call. We hope to get rid of
        this by making upstream expose get_username so we can override it.
        The upstream change request is tracked by https://code.djangoproject.com/ticket/35971
        """
        # AuthenticationMiddleware is required so that request.user exists.
        if not hasattr(request, "user"):
            raise ImproperlyConfigured(
                "The Django remote user auth middleware requires the"
                " authentication middleware to be installed.  Edit your"
                " MIDDLEWARE setting to insert"
                " 'django.contrib.auth.middleware.AuthenticationMiddleware'"
                " before the RemoteUserMiddleware class."
            )
        try:
            username = self.get_username(request)
        except KeyError:
            # If specified header doesn't exist then remove any existing
            # authenticated remote-user, or return (leaving request.user set to
            # AnonymousUser by the AuthenticationMiddleware).
            if self.force_logout_if_no_header and request.user.is_authenticated:
                self._remove_invalid_user(request)
            return
        # If the user is already authenticated and that user is the user we are
        # getting passed in the headers, then the correct user is already
        # persisted in the session and we don't need to continue.
        if request.user.is_authenticated:
            if request.user.get_username() == self.clean_username(username, request):
                return
            else:
                # An authenticated user is associated with the request, but
                # it does not match the authorized user in the header.
                self._remove_invalid_user(request)

        # We are seeing this user for the first time in this session, attempt
        # to authenticate the user.
        user = auth.authenticate(request, remote_user=username)
        if user:
            # User is valid.  Set request.user and persist user in the session
            # by logging the user in.
            request.user = user
            auth.login(request, user)
