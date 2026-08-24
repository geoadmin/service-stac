from unittest import TestCase

from stac_api.utils import parse_cache_control_header
from stac_api.utils import parse_sortby


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

    def test_parse_sortby_empty(self):
        result = parse_sortby(None)
        self.assertEqual(result, [])

        result = parse_sortby('')
        self.assertEqual(result, [])

        result = parse_sortby('   ')
        self.assertEqual(result, [])

    def test_parse_sortby_handles_single_field_correctly(self):
        result = parse_sortby('properties.created')
        self.assertEqual(result, [('created', True)])

        result = parse_sortby('+properties.created')
        self.assertEqual(result, [('created', True)])

        result = parse_sortby('-properties.created')
        self.assertEqual(result, [('created', False)])

    def test_parse_sortby_handles_multiple_fields_correctly(self):
        result = parse_sortby('id,-properties.updated')
        self.assertEqual(result, [('name', True), ('updated', False)])

        result = parse_sortby('-properties.created,properties.updated')
        self.assertEqual(result, [('created', False), ('updated', True)])

        result = parse_sortby('+properties.created,-collection,properties.title')
        self.assertEqual(
            result, [('created', True), ('collection__name', False), ('properties_title', True)]
        )

    def test_parse_sortby_ignores_whitespace(self):
        result = parse_sortby('properties.created , -properties.updated')
        self.assertEqual(result, [('created', True), ('updated', False)])

    def test_parse_sortby_raises_for_invalid_field(self):
        with self.assertRaises(ValueError):
            parse_sortby('invalid_field')
