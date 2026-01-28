REMOTE_USER_HEADER = "HTTP_GEOADMIN_USERNAME"


def validate_username_header(request):
    """Drop the Geoadmin-Username header if it's invalid.

    This should be called before making any decision based on the value of the
    Geoadmin-Username header.

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
    # FIXME: AsgiRequest request seem to differe with header names
    # apigw_auth = request.META.get("HTTP_GEOADMIN_AUTHENTICATED", "false").lower() == "true"
    apigw_auth = request.headers.get("Geoadmin-Authenticated", "false").lower() == "true"
    if not apigw_auth and REMOTE_USER_HEADER in request.META:
        del request.META[REMOTE_USER_HEADER]
