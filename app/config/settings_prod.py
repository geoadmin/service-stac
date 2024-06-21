"""
Django settings for project project.
Generated by 'django-admin startproject' using Django 3.1.
For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/
For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

import os
import os.path
from pathlib import Path

import yaml

from .version import APP_VERSION  # pylint: disable=unused-import

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
os.environ['BASE_DIR'] = str(BASE_DIR)
print(f"BASE_DIR is {BASE_DIR}")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', None)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# If set to True, this will enable logger.debug prints of the output of
# EXPLAIN.. ANALYZE of certain queries and the corresponding SQL statement.
DEBUG_ENABLE_DB_EXPLAIN_ANALYZE = False

# SECURITY:
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ('HTTP_CLOUDFRONT_FORWARDED_PROTO', 'https')

# We need to have the IP of the Pod/localhost in ALLOWED_HOSTS
# as well to be able to scrape prometheus /metrics
# see kubernetes config on how `THIS_POD_IP` is obtained

ALLOWED_HOSTS = []
THIS_POD_IP = os.getenv('THIS_POD_IP')
if THIS_POD_IP:
    ALLOWED_HOSTS.append(THIS_POD_IP)
ALLOWED_HOSTS += os.getenv('ALLOWED_HOSTS', '').split(',')

# SERVICE_HOST = os.getenv('SERVICE_HOST', '127.0.0.1:8000')

# Application definition
# Apps are grouped according to
# 1. django apps
# 2. third-party apps
# 3. own apps
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'rest_framework',
    'rest_framework_gis',
    'rest_framework.authtoken',
    #  Note: If you use TokenAuthentication in production you must ensure
    #  that your API is only available over https.
    'admin_auto_filters',
    'solo.apps.SoloAppConfig',
    'storages',
    'whitenoise.runserver_nostatic',
    'django_prometheus',
    'pgtrigger',
    'config.apps.StacAdminConfig',
    'stac_api.apps.StacApiConfig',
]

# Middlewares are executed in order, once for the incoming
# request top-down, once for the outgoing response bottom up
# Note: The prometheus middlewares should always be first and
# last, put everything else in between
MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'middleware.logging.RequestResponseLoggingMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'middleware.cors.CORSHeadersMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'middleware.cache_headers.CacheHeadersMiddleware',
    'middleware.exception.ExceptionLoggingMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'config.urls'
API_BASE = 'api'
STAC_BASE = f'{API_BASE}/stac'
LOGIN_URL = "/api/stac/admin/login/"

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'app/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'middleware.settings_context_processor.inject_settings_values',
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

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'
    }, {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'
    }, {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'
    }, {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'
    }
]

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_HOST = os.environ.get('DJANGO_STATIC_HOST', '')
STATIC_URL = f'{STATIC_HOST}/api/stac/static/'
STATIC_SPEC_URL = f'{STATIC_URL}spec/'
# "manage.py collectstatic" will copy all static files to this directory, and
# whitenoise will serve the static files that are in this directory (unless DEBUG=true in which case
# it will serve the files from the same directories "manage.py collectstatic" collects data from)
STATIC_ROOT = BASE_DIR / 'var' / 'www' / 'stac_api' / 'static_files'
STATICFILES_DIRS = [BASE_DIR / "spec" / "static", BASE_DIR / "app" / "stac_api" / "templates"]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
HEALTHCHECK_ENDPOINT = os.environ.get('HEALTHCHECK_ENDPOINT', 'healthcheck')

try:
    WHITENOISE_MAX_AGE = int(os.environ.get('HTTP_STATIC_CACHE_SECONDS', '3600'))
except ValueError as error:
    raise ValueError(
        'Invalid HTTP_STATIC_CACHE_SECONDS environment value: must be an integer'
    ) from error
WHITENOISE_MIMETYPES = {
    # These sets the mime types for the api/stac/static/spec/v0.9/openapi.yaml static file
    # otherwise a default application/octet-stream is used.
    '.yaml': 'application/vnd.oai.openapi+yaml;version=3.0',
    '.yml': 'application/vnd.oai.openapi+yaml;version=3.0'
}

# Media files (i.e. uploaded content=assets in this project)
UPLOAD_FILE_CHUNK_SIZE = 1024 * 1024  # Size in Bytes
DEFAULT_FILE_STORAGE = 'stac_api.storages.S3Storage'

try:
    AWS_LEGACY = {
        "STORAGE_BUCKET_NAME": os.environ['AWS_STORAGE_BUCKET_NAME'],
        "ACCESS_KEY_ID": os.environ['AWS_ACCESS_KEY_ID'],
        "SECRET_ACCESS_KEY": os.environ['AWS_SECRET_ACCESS_KEY'],  # The AWS region of the bucket
        "S3_REGION_NAME": os.environ.get('AWS_S3_REGION_NAME', 'eu-central-1'),
        # This is the URL where to reach the S3 service and is either minio
        # on localhost or https://s3.<region>.amazonaws.com
        "S3_ENDPOINT_URL": os.environ.get('AWS_S3_ENDPOINT_URL', None),
        # The CUSTOM_DOMAIN is used to construct the correct URL when displaying
        # a link to the file in the admin UI. It must only contain the domain, but not
        # the scheme (http/https).
        "S3_CUSTOM_DOMAIN": os.environ.get('AWS_S3_CUSTOM_DOMAIN', None),
        # AWS_DEFAULT_ACL depends on bucket/user config. The user might not have
        # permissions to change ACL, then this setting must be None
        "DEFAULT_ACL": None,
        "S3_SIGNATURE_VERSION": "s3v4"
    }

    AWS_MANAGED = {
        # STORAGE_BUCKET_NAME is the only required additional var
        # The others are inferred by the ones above if they're not specified
        # So if we have two buckets on the same server with the same access key, we needn't
        # specify all the variables. But this still leaves the possibility to
        # have it in a somewhere entirely different location
        "STORAGE_BUCKET_NAME": os.environ['AWS_STORAGE_BUCKET_NAME_MANAGED'],
        "ACCESS_KEY_ID": os.environ.get('AWS_ACCESS_KEY_ID_MANAGED', AWS_LEGACY['ACCESS_KEY_ID']),
        "SECRET_ACCESS_KEY":
            os.environ.get('AWS_SECRET_ACCESS_KEY_MANAGED', AWS_LEGACY['SECRET_ACCESS_KEY']),
        "S3_REGION_NAME":
            os.environ.get('AWS_S3_REGION_NAME_MANAGED', AWS_LEGACY['S3_REGION_NAME']),
        "S3_ENDPOINT_URL": os.environ.get('AWS_S3_ENDPOINT_URL', AWS_LEGACY['S3_ENDPOINT_URL']),
        "S3_CUSTOM_DOMAIN": os.environ.get('AWS_S3_CUSTOM_DOMAIN', AWS_LEGACY['S3_CUSTOM_DOMAIN']),
        "DEFAULT_ACL": None,
        "S3_SIGNATURE_VERSION": "s3v4"
    }
except KeyError as err:
    raise KeyError(f'AWS configuration {err} missing') from err

AWS_PRESIGNED_URL_EXPIRES = int(os.environ.get('AWS_PRESIGNED_URL_EXPIRES', '3600'))

# Configure the caching
# API default cache control max-age
try:
    CACHE_MIDDLEWARE_SECONDS = int(os.environ.get('HTTP_CACHE_SECONDS', '600'))
except ValueError as error:
    raise ValueError('Invalid HTTP_CACHE_SECONDS environment value: must be an integer') from error

# Asset data default cache control max-age
try:
    STORAGE_ASSETS_CACHE_SECONDS = int(os.environ.get('HTTP_ASSETS_CACHE_SECONDS', '7200'))
except ValueError as err:
    raise ValueError('Invalid HTTP_ASSETS_CACHE_SECONDS, must be an integer') from err

# Logging
# https://docs.djangoproject.com/en/3.1/topics/logging/


# Read configuration from file
def get_logging_config():
    '''Read logging configuration
    Read and parse the yaml logging configuration file passed in the environment variable
    LOGGING_CFG and return it as dictionary
    Note: LOGGING_CFG is relative to the root of the repo
    '''
    log_config_file = os.getenv('LOGGING_CFG', 'app/config/logging-cfg-local.yml')
    if log_config_file.lower() in ['none', '0', '', 'false', 'no']:
        return {}
    log_config = {}
    with open(BASE_DIR / log_config_file, 'rt', encoding="utf-8") as fd:
        log_config = yaml.safe_load(os.path.expandvars(fd.read()))
    return log_config


LOGGING = get_logging_config()

# Testing

TEST_RUNNER = 'tests.runner.TestRunner'

# set default pagination configuration
# set authentication schemes

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'stac_api.pagination.CursorPagination',
    'PAGE_SIZE': os.environ.get('PAGE_SIZE', 100),
    'PAGE_SIZE_LIMIT': os.environ.get('PAGE_SIZE_LIMIT', 100),
    'EXCEPTION_HANDLER': 'stac_api.apps.custom_exception_handler',
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly',
    ]
}

# Exception handling

# When DEBUG is true the uncaught exceptions are handle by django a returns a detail exception
# backtrace as HTML, we can force to give a JSON message as in prod by settings this variable,
# this is usefull for unittest when we want to test exception handling. This settings can be set
# via environment variable in settings_dev.py when DEBUG=True
DEBUG_PROPAGATE_API_EXCEPTIONS = False

# Timeout in seconds for call to external services, e.g. HTTP HEAD request to
# data.geo.admin.ch/collection/item/asset to check if asset exists.
EXTERNAL_SERVICE_TIMEOUT = 3

# By default django_prometheus tracks the number of migrations
# This causes troubles in various places so we disable it
PROMETHEUS_EXPORT_MIGRATIONS = False

# STAC Browser configuration for auto generated STAC links
STAC_BROWSER_HOST = os.getenv(
    'STAC_BROWSER_HOST', None
)  # if None, the host is taken from the request url
STAC_BROWSER_BASE_PATH = os.getenv('STAC_BROWSER_BASE_PATH', 'browser/index.html')

# Regex patterns of collections that should go to the managed bucket
MANAGED_BUCKET_COLLECTION_PATTERNS = [r"^ch\.meteoschweiz\.ogd.*"]
