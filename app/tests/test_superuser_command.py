from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase


class SuperUserCommandTest(TestCase):

    @patch.dict(
        'os.environ',
        {
            'DJANGO_SUPERUSER_USERNAME': 'admin',
            'DJANGO_SUPERUSER_EMAIL': 'admin@admin.ch',
            'DJANGO_SUPERUSER_PASSWORD': 'very-secure'
        }
    )
    def test_command_creates(self):
        out = StringIO()
        call_command('manage_superuser', verbosity=2, stdout=out)
        self.assertIn('Created the superuser admin', out.getvalue())

        user = get_user_model().objects.filter(username='admin').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'admin@admin.ch')
        self.assertTrue(user.check_password('very-secure'))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    @patch.dict(
        'os.environ',
        {
            'DJANGO_SUPERUSER_USERNAME': 'admin',
            'DJANGO_SUPERUSER_EMAIL': 'admin@admin.ch',
            'DJANGO_SUPERUSER_PASSWORD': 'very-secure'
        }
    )
    def test_command_updates(self):
        user = get_user_model().objects.create(
            username='admin', email='amdin@amdin.ch', is_staff=False, is_superuser=False
        )
        user.set_password('not-secure')

        out = StringIO()
        call_command('manage_superuser', verbosity=2, stdout=out)
        self.assertIn('Updated the superuser admin', out.getvalue())

        user = get_user_model().objects.filter(username='admin').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'admin@admin.ch')
        self.assertTrue(user.check_password('very-secure'))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_fails_if_undefined(self):
        out = StringIO()
        call_command('manage_superuser', stderr=out)
        self.assertIn('Environment variables not set or empty', out.getvalue())
        self.assertEqual(get_user_model().objects.count(), 0)

    @patch.dict(
        'os.environ',
        {
            'DJANGO_SUPERUSER_USERNAME': '',
            'DJANGO_SUPERUSER_EMAIL': '',
            'DJANGO_SUPERUSER_PASSWORD': ''
        }
    )
    def test_fails_if_empty(self):
        out = StringIO()
        call_command('manage_superuser', stderr=out)
        self.assertIn('Environment variables not set or empty', out.getvalue())
        self.assertEqual(get_user_model().objects.count(), 0)
