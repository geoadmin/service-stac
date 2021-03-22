"""project URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include
from django.urls import path

STAC_BASE = settings.STAC_BASE


def checker(request):
    data = {"success": True, "message": "OK"}

    return JsonResponse(data)


urlpatterns = [
    path('', include('django_prometheus.urls')),
    path('checker', checker, name='checker'),
    path(f'{STAC_BASE}/', include('stac_api.urls')),
    path(f'{STAC_BASE}/admin/', admin.site.urls),
]

if settings.DEBUG:
    import debug_toolbar
    from stac_api.views_test import TestHttp500

    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
        path('tests/test_http_500', TestHttp500.as_view()),
    ] + urlpatterns
