import logging

from django.http import JsonResponse
# from django.conf import settings

logger = logging.getLogger(__name__)


def index(request):
    data = {
        "description": "Catalog of Swiss Geodata Downloads",
        "id": "ch",
        "stac_version": "0.9.0",
        "title": "data.geo.admin.ch"
    }

    logger.debug('Landing page: %s', data)

    return JsonResponse(data)


def checker(request):
    data = {"success": True, "message": "OK"}

    return JsonResponse(data)
