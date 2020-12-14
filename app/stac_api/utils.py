from datetime import datetime
from datetime import timezone

from django.conf import settings

import boto3


def isoformat(date_time):
    '''Return a datetime string in isoformat using 'Z' as timezone instead of '+00:00'
    '''
    return date_time.isoformat().replace('+00:00', 'Z')


def fromisoformat(date_time):
    '''Return a datetime object from a isoformated datetime string
    '''
    return datetime.fromisoformat(date_time.replace('Z', '+00:00'))


def utc_aware(date_time):
    '''Return a UTC date_time aware object
    '''
    return date_time.replace(tzinfo=timezone.utc)


def get_link(links, rel, raise_exception=False):
    '''Get link from list based on his rel attribute

    Args:
	    links: list
			list of link object: {'href': url, 'rel': str}
        rel: string
            rel attribute to look for
        raise_exception: boolean (default=False)
            raises KeyError instead of returning None when link is not found

    Returns:
        The link object if found, else None
    '''
    for link in links:
        if link['rel'] == rel:
            return link
    if raise_exception:
        raise KeyError(f'Link with rel {rel} not found')
    return None


def get_s3_resource():
    s3 = boto3.resource('s3', endpoint_url=settings.AWS_S3_ENDPOINT_URL)
    return s3
