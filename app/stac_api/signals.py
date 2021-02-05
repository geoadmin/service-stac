# Un-comment with BGDIINF_SB-1625
# import logging

# from django.db.models.signals import pre_delete
# from django.dispatch import receiver

# from stac_api.models import Asset

# logger = logging.getLogger(__name__)

# @receiver(pre_delete, sender=Asset)
# def delete_s3_asset(sender, instance, **kwargs):
#     # The file is not automatically deleted by Django
#     # when the object holding its reference is deleted
#     # hence it has to be done here.
#     logger.info("The asset %s is deleted from s3", instance.file.name)
#     instance.file.delete(save=False)
