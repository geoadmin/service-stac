from django.http import JsonResponse, HttpResponse
from django.conf import settings


def index(request):
    data = {
        "description": "Catalog of Swiss Geodata Downloads",
        "id": "ch",
        "stac_version": "0.9.0",
        "title": "data.geo.admin.ch"
    }

    return JsonResponse(data)

#http://localhost:5000/hello/world get setting from dev.env
def hello_world(request):
    return HttpResponse("HELLO_WORLD = %s" % settings.HELLO_WORLD)
