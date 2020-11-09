from datetime import timezone


def isoformat(date_time):
    '''Return a datetime object in isoformat using 'Z' as timezone instead of '+00:00'
    '''
    return date_time.isoformat().replace('+00:00', 'Z')


def utc_aware(date_time):
    '''Return a UTC date_time aware object
    '''
    return date_time.replace(tzinfo=timezone.utc)
