from datetime import datetime
from datetime import timezone


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
