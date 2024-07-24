from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from tests.tests_10.base_test import VERSION_SHORT


def reverse_version(viewname, urlconf=None, args=None, kwargs=None, current_app=None):
    ns = VERSION_SHORT
    return reverse(ns + ':' + viewname, urlconf, args, kwargs, current_app=ns)


def calculate_extent(*args, **kwargs):
    out = StringIO()
    call_command(
        "calculate_extent",
        *args,
        stdout=out,
        stderr=StringIO(),
        **kwargs,
    )
    return out.getvalue()
