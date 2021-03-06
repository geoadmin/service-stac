import logging

from django.db.models import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from stac_api.models import Asset
from stac_api.models import AssetUpload

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=AssetUpload)
def check_on_going_upload(sender, instance, **kwargs):
    if instance.status == AssetUpload.Status.IN_PROGRESS:
        logger.error(
            "Cannot delete asset %s due to upload %s which is still in progress",
            instance.asset.name,
            instance.upload_id,
            extra={
                'upload_id': instance.upload_id,
                'asset': instance.asset.name,
                'item': instance.asset.item.name,
                'collection': instance.asset.item.collection.name
            }
        )
        raise ProtectedError(
            f"Asset {instance.asset.name} has still an upload in progress", [instance]
        )


@receiver(pre_delete, sender=Asset)
def delete_s3_asset(sender, instance, **kwargs):
    # The file is not automatically deleted by Django
    # when the object holding its reference is deleted
    # hence it has to be done here.
    logger.info("The asset %s is deleted from s3", instance.file.name)
    instance.file.delete(save=False)
