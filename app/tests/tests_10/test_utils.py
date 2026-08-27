from unittest import TestCase

from django.core.exceptions import ValidationError

from stac_api.utils import parse_cache_control_header
from stac_api.utils import parse_sortby_get
from stac_api.utils import parse_sortby_post


class TestUtils(TestCase):

    def test_parse_cache_control_header(self):
        self.assertEqual(parse_cache_control_header('max-age=360'), {'max-age': '360'})
        self.assertEqual(parse_cache_control_header('max-age=360,'), {'max-age': '360'})
        self.assertEqual(parse_cache_control_header('  max-age=360  ,   '), {'max-age': '360'})
        self.assertEqual(
            parse_cache_control_header('max-age=360, public'), {
                'max-age': '360', 'public': True
            }
        )
        self.assertEqual(
            parse_cache_control_header('  max-age   =  360  ,   test = hello'), {
                'max-age': '360', 'test': 'hello'
            }
        )
        self.assertEqual(parse_cache_control_header(''), {})
        self.assertEqual(parse_cache_control_header(','), {})
        self.assertEqual(parse_cache_control_header('   '), {})
        self.assertEqual(parse_cache_control_header('  ,   '), {})

    def test_parse_sortby_get_empty(self):
        result = parse_sortby_get(None, {})
        self.assertEqual(result, [])

        result = parse_sortby_get('', {})
        self.assertEqual(result, [])

        result = parse_sortby_get('   ', {})
        self.assertEqual(result, [])

    def test_parse_sortby_get_handles_single_field_correctly(self):
        sortable_fields = {'external': 'internal'}

        result = parse_sortby_get('external', sortable_fields)
        self.assertEqual(result, [('internal', True)])

        result = parse_sortby_get('+external', sortable_fields)
        self.assertEqual(result, [('internal', True)])

        result = parse_sortby_get('-external', sortable_fields)
        self.assertEqual(result, [('internal', False)])

    def test_parse_sortby_get_handles_multiple_fields_correctly(self):
        sortable_fields = {
            'external_1': 'internal_1',
            'external_2': 'internal_2',
            'external_3': 'internal_3',
        }

        result = parse_sortby_get('external_1,-external_2', sortable_fields)
        self.assertEqual(result, [('internal_1', True), ('internal_2', False)])

        result = parse_sortby_get('-external_1,external_2', sortable_fields)
        self.assertEqual(result, [('internal_1', False), ('internal_2', True)])

        result = parse_sortby_get('+external_1,-external_2,external_3', sortable_fields)
        self.assertEqual(
            result, [('internal_1', True), ('internal_2', False), ('internal_3', True)]
        )

    def test_parse_sortby_get_ignores_whitespace(self):
        sortable_fields = {
            'external_1': 'internal_1',
            'external_2': 'internal_2',
        }
        result = parse_sortby_get('external_1 , -external_2', sortable_fields)
        self.assertEqual(result, [('internal_1', True), ('internal_2', False)])

    def test_parse_sortby_get_raises_for_invalid_field(self):
        with self.assertRaises(ValidationError):
            parse_sortby_get('invalid_field', {'external': 'internal'})

    def test_parse_sortby_post_format_empty(self):
        result = parse_sortby_post([], {})
        self.assertEqual(result, [])

    def test_parse_sortby_post_format_handles_single_field_correctly(self):
        sortable_fields = {'external': 'internal'}

        result = parse_sortby_post([{'field': 'external', 'direction': 'asc'}], sortable_fields)
        self.assertEqual(result, [('internal', True)])

        result = parse_sortby_post([{'field': 'external', 'direction': 'desc'}], sortable_fields)
        self.assertEqual(result, [('internal', False)])

        # direction defaults to ascending when omitted
        result = parse_sortby_post([{'field': 'external'}], sortable_fields)
        self.assertEqual(result, [('internal', True)])

    def test_parse_sortby_post_format_handles_multiple_fields_correctly(self):
        sortable_fields = {
            'external_1': 'internal_1',
            'external_2': 'internal_2',
        }
        sortby_param = [{
            'field': 'external_1',
            'direction': 'asc',
        }, {
            'field': 'external_2',
            'direction': 'desc',
        }]
        result = parse_sortby_post(sortby_param, sortable_fields)
        self.assertEqual(result, [('internal_1', True), ('internal_2', False)])

        sortby_param = [{
            'field': 'external_1',
            'direction': 'desc',
        }, {
            'field': 'external_2',
            'direction': 'asc',
        }]
        result = parse_sortby_post(sortby_param, sortable_fields)
        self.assertEqual(result, [('internal_1', False), ('internal_2', True)])

    def test_parse_sortby_post_format_raises_for_invalid_field(self):
        with self.assertRaises(ValidationError):
            parse_sortby_post([{
                'field': 'invalid_field', 'direction': 'asc'
            }], {'external': 'internal'})

    def test_parse_sortby_post_format_raises_for_invalid_direction(self):
        with self.assertRaises(ValidationError):
            parse_sortby_post([{
                'field': 'external', 'direction': 'sideways'
            }], {'external': 'internal'})

    def test_parse_sortby_post_format_raises_for_missing_field(self):
        with self.assertRaises(ValidationError):
            parse_sortby_post([{'direction': 'asc'}], {'external': 'internal'})
