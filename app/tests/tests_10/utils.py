from django.urls import reverse

from tests.tests_10.base_test import VERSION_SHORT


def reverse_version(viewname, urlconf=None, args=None, kwargs=None, current_app=None):
    ns = VERSION_SHORT
    return reverse(ns + ':' + viewname, urlconf, args, kwargs, current_app=ns)
