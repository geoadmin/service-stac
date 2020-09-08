from django.urls import path

from . import views

urlpatterns = [
    path('api/stac/v0.9/', views.index, name='index'),
    path('checker/', views.checker, name='checker'),
]
