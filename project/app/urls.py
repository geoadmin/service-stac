from django.urls import path

from config.settings import API_BASE_PATH
from . import views

urlpatterns = [
    path(API_BASE_PATH, views.landing_page, name='landing-page'),
    path('checker/', views.checker, name='checker'),
]
