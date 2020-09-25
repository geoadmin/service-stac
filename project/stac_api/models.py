from django.contrib.gis.db import models

# pylint: disable=fixme
# TODO remove this pylint disable once this is done

# st_geometry bbox ch
BBOX_CH = 'POLYGON((2317000 913000,3057000 913000,3057000 1413000,2317000 1413000,2317000 913000))'


class Collection(models.Model):
    # TODO: is the service multilingual? title_de, title_fr, title_en, title_it, title_rm
    bgid_id = models.BigAutoField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    layer_id = models.TextField()
    geocat_uuid = models.UUIDField()
    goecat_title = models.TextField()
    geodat_description = models.TextField()
    gsd = models.TextField()
    variant = models.TextField()
    lang = models.TextField()  # TODO: what is its purpose?
    bbox = models.PolygonField(
        default=BBOX_CH, srid=2056
    )  # TODO: directly a geometry for spatial queries? 3D?
    temporal_interval = models.TimeField(
    )  # TODO: time field - how many hours are in a (leap) year? textfield?
    crs = models.URLField(default="http://www.opengis.net/def/crs/OGC/1.3/CRS84")
