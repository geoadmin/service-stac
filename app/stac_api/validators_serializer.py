import logging

from django.utils.translation import gettext_lazy as _

from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


def validate_json_payload(serializer):
    '''
    Validate JSON payload and raise error, if extra payload or read-only fields
    in payload are found
    Args:
        serializer: serializer for which payload is checked

    Raises:
        ValidationError if extra or read-only fields in payload are found
    '''

    expected_payload = list(serializer.fields.keys())
    expected_payload_read_only = [
        field for field in serializer.fields if serializer.fields[field].read_only
    ]

    errors = {}
    for key in serializer.initial_data.keys():
        if key not in expected_payload:
            logger.error('Found unexpected payload %s', key)
            errors[key] = _("Unexpected property in payload")
        if key in expected_payload_read_only:
            logger.error('Found read-only payload %s', key)
            errors[key] = _("Found read-only property in payload")

    if errors:
        raise ValidationError(code='payload', detail=errors)


