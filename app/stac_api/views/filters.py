from django.db.models import Q
from django.utils import timezone


def create_is_active_filter():
    """
    Create a filter to check if the item is not expired.
    """
    return Q(properties_expires__gte=timezone.now()) | Q(properties_expires=None)
