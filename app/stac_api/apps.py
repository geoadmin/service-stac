from django.apps import AppConfig

from rest_framework import pagination
from rest_framework.response import Response


class StacApiConfig(AppConfig):
    name = 'stac_api'


class CursorPagination(pagination.CursorPagination):
    ordering = 'id'

    def get_paginated_response(self, data):
        links = {}
        next_page = self.get_next_link()
        previous_page = self.get_previous_link()
        if next_page is not None:
            links.update({'rel': 'next', 'href': next_page})
        if previous_page is not None:
            links.update({'rel': 'previous', 'href': previous_page})

        if 'links' not in data and not links:
            data.update({'links': []})
        elif 'links' not in data and links:
            data.update({'links': [links]})
        elif links:
            data['links'].append(links)
        return Response(data)
