from django.http import JsonResponse


def index(request):
    data = {
        "description": "Catalog of Swiss Geodata Downloads",
        "id": "ch",
        "stac_version": "0.9.0",
        "title": "data.geo.admin.ch"
    }

    return JsonResponse(data)
