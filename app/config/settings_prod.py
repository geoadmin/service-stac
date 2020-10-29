"""
Django settings for project project.

Generated by 'django-admin startproject' using Django 3.1.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

import os
from distutils.util import strtobool
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
print(f"BASE_DIR is {BASE_DIR}")

# Determine the application environment (dev|int|prod)
# Note: the preferred solution would be to have the default
# APP_ENV 'prod', but have it 'local' by default simplifies
# the setup
APP_ENV = os.environ.get('APP_ENV', 'local')

# If we develop locally, load ENV from file
if APP_ENV.lower() == 'local':
    print("running locally hence injecting env vars from {}".format(BASE_DIR / f'.env.{APP_ENV}'))
    # set the APP_ENV to local (in case it was set from default above)
    os.environ['APP_ENV'] = 'local'
    load_dotenv(BASE_DIR / f'.env.{APP_ENV}')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '%5+eq2851!d7qi^sze(nv2g#kt8v$7)4ck3cq*e!5c2rx%13p+'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = bool(strtobool(os.getenv('DEBUG', 'False')))

ALLOWED_HOSTS = []
if DEBUG:
    # When the debug flag is set allow local host
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
ALLOWED_HOSTS += os.getenv('ALLOWED_HOSTS', '').split(',')

# Application definition

INSTALLED_APPS = [
    'rest_framework',
    'rest_framework_gis',
    'stac_api.apps.StacApiConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.contrib.gis'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
API_BASE = 'api/stac/v0.9/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.environ.get('DB_NAME', 'service_stac'),
        'USER': os.environ.get('DB_USER', 'service_stac'),
        'PASSWORD': os.environ.get('DB_PW', 'service_stac'),
        'HOST': os.environ.get('DB_HOST', 'service_stac'),
        'PORT': os.environ.get('DB_PORT', 5432),
        'TEST': {
            'NAME': os.environ.get('DB_NAME_TEST', 'test_service_stac'),
        }
    }
}

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_HOST = os.environ.get('DJANGO_STATIC_HOST', '')
STATIC_URL = STATIC_HOST + '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'var/www/stac_api/static_files')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Logging
# https://docs.djangoproject.com/en/3.1/topics/logging/


# Read configuration from file
def get_logging_config():
    '''Read logging configuration

    Read and parse the yaml logging configuration file passed in the environment variable
    LOGGING_CFG and return it as dictionary

    Note: LOGGING_CFG is relative to the root of the repo
    '''
    log_config = {}
    with open(BASE_DIR / os.getenv('LOGGING_CFG', 'app/config/logging-cfg-local.yml'), 'rt') as fd:
        log_config = yaml.safe_load(fd.read())
    return log_config


if strtobool(os.getenv('DISABLE_LOGGING', 'False')):
    LOGGING = None
else:
    LOGGING = get_logging_config()

# Testing

TEST_RUNNER = 'tests.runner.TestRunner'
