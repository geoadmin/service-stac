import time

from django.core.management.base import CommandParser
from django.db.models import Q

from stac_api.models.item import Asset
from stac_api.utils import CustomBaseCommand


class Command(CustomBaseCommand):
    help = """Set asset role to 'thumbnail' for assets named 'thumbnail.png' or 'thumbnail.jpg'.
    This is a workaround as some customers are still using stac v0.9, which does not support setting
    a role on assets. Since the stac browser (>=v5.1) no longer takes assets with name 'thumbnail'
    into account but only looks at the role, the item thumbnails are no longer displayed as expected.
    See also https://swissgeoplatform.atlassian.net/browse/HDG-81
    """

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)

    def handle(self, *args, **options):
        self.print_success('running command to set asset thumbnail roles')
        start = time.monotonic()
        counter = 0

        for asset in Asset.objects.filter(Q(name='thumbnail.png') | Q(name='thumbnail.jpg')).filter(
            roles=None
        ).iterator(chunk_size=1000):
            asset.roles = ['thumbnail']
            asset.save()
            counter += 1

        self.print_success(
            f"successfully updated roles for {counter} thumbnail assets",
            extra={"duration": time.monotonic() - start}
        )
