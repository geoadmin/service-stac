from unittest import TestCase

from stac_api.views.mixins import parse_cache_control_header


class TestViewsMixins(TestCase):

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
