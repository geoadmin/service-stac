# Generated by Django 5.0.8 on 2024-12-19 20:37

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ('stac_api', '0058_collectionlink_hreflang_itemlink_hreflang_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asset',
            name='media_type',
            field=models.CharField(
                choices=
                [(
                    'application/vnd.apache.parquet',
                    'Apache Parquet column-oriented data file format (application/vnd.apache.parquet)'
                ),
                 (
                     'application/x.ascii-grid+zip',
                     'Zipped ESRI ASCII raster format (.asc) (application/x.ascii-grid+zip)'
                 ),
                 ('application/x.ascii-xyz+zip', 'Zipped XYZ (.xyz) (application/x.ascii-xyz+zip)'),
                 ('application/x.e00+zip', 'Zipped e00 (application/x.e00+zip)'),
                 ('application/x.geotiff+zip', 'Zipped GeoTIFF (application/x.geotiff+zip)'),
                 ('image/tiff; application=geotiff', 'GeoTIFF (image/tiff; application=geotiff)'),
                 ('application/x.tiff+zip', 'Zipped TIFF (application/x.tiff+zip)'),
                 ('application/x.png+zip', 'Zipped PNG (application/x.png+zip)'),
                 ('application/x.jpeg+zip', 'Zipped JPEG (application/x.jpeg+zip)'),
                 (
                     'application/vnd.google-earth.kml+xml',
                     'KML (application/vnd.google-earth.kml+xml)'
                 ),
                 (
                     'application/vnd.google-earth.kmz',
                     'Zipped KML (application/vnd.google-earth.kmz)'
                 ), ('application/x.dxf+zip', 'Zipped DXF (application/x.dxf+zip)'),
                 ('application/gml+xml', 'GML (application/gml+xml)'),
                 ('application/x.gml+zip', 'Zipped GML (application/x.gml+zip)'),
                 ('application/vnd.las', 'LIDAR (application/vnd.las)'),
                 ('application/vnd.laszip', 'Zipped LIDAR (application/vnd.laszip)'),
                 ('application/x.vnd.las+zip', 'Zipped LAS (application/x.vnd.las+zip)'),
                 (
                     'application/vnd.laszip+copc',
                     'Cloud Optimized Point Cloud (COPC) (application/vnd.laszip+copc)'
                 ),
                 ('application/x.shapefile+zip',
                  'Zipped Shapefile (application/x.shapefile+zip)'), (
                      'application/x.filegdb+zip',
                      'Zipped File Geodatabase (application/x.filegdb+zip)'
                  ),
                 (
                     'application/x.filegdbp+zip',
                     'Zipped File Geodatabase (ArcGIS Pro) (application/x.filegdbp+zip)'
                 ),
                 (
                     'application/x.ms-access+zip',
                     'Zipped Personal Geodatabase (application/x.ms-access+zip)'
                 ), ('application/x.ms-excel+zip', 'Zipped Excel (application/x.ms-excel+zip)'),
                 ('application/x.tab+zip', 'Zipped Mapinfo-TAB (application/x.tab+zip)'),
                 (
                     'application/x.tab-raster+zip',
                     'Zipped Mapinfo-Raster-TAB (application/x.tab-raster+zip)'
                 ), ('application/x.csv+zip',
                     'Zipped CSV (application/x.csv+zip)'), ('text/csv', 'CSV (text/csv)'),
                 ('application/geopackage+sqlite3',
                  'Geopackage (application/geopackage+sqlite3)'), (
                      'application/x.geopackage+zip',
                      'Zipped Geopackage (application/x.geopackage+zip)'
                  ), ('application/geo+json', 'GeoJSON (application/geo+json)'),
                 ('application/x.geojson+zip', 'Zipped GeoJSON (application/x.geojson+zip)'),
                 (
                     'application/x.interlis; version=2.3',
                     'Interlis 2 (application/x.interlis; version=2.3)'
                 ),
                 (
                     'application/x.interlis+zip; version=2.3',
                     'Zipped XTF (2.3) (application/x.interlis+zip; version=2.3)'
                 ),
                 (
                     'application/x.interlis; version=2.4',
                     'Interlis 2 (application/x.interlis; version=2.4)'
                 ),
                 (
                     'application/x.interlis+zip; version=2.4',
                     'Zipped XTF (2.4) (application/x.interlis+zip; version=2.4)'
                 ),
                 (
                     'application/x.interlis; version=1',
                     'Interlis 1 (application/x.interlis; version=1)'
                 ),
                 (
                     'application/x.interlis+zip; version=1',
                     'Zipped ITF (application/x.interlis+zip; version=1)'
                 ),
                 (
                     'image/tiff; application=geotiff; profile=cloud-optimized',
                     'Cloud Optimized GeoTIFF (COG) (image/tiff; application=geotiff; profile=cloud-optimized)'
                 ), ('application/pdf', 'PDF (application/pdf)'),
                 ('application/x.pdf+zip', 'Zipped PDF (application/x.pdf+zip)'),
                 ('application/json', 'JSON (application/json)'),
                 ('application/x.json+zip', 'Zipped JSON (application/x.json+zip)'),
                 ('application/x-netcdf', 'NetCDF (application/x-netcdf)'),
                 ('application/x.netcdf+zip', 'Zipped NetCDF (application/x.netcdf+zip)'),
                 ('application/xml', 'XML (application/xml)'),
                 ('application/x.xml+zip', 'Zipped XML (application/x.xml+zip)'),
                 (
                     'application/vnd.mapbox-vector-tile',
                     'mbtiles (application/vnd.mapbox-vector-tile)'
                 ), ('text/plain',
                     'Text (text/plain)'), ('text/x.plain+zip', 'Zipped text (text/x.plain+zip)'),
                 ('application/x.dwg+zip', 'Zipped DWG (application/x.dwg+zip)'),
                 ('application/zip',
                  'Generic Zip File (application/zip)'), ('image/tiff', 'TIFF (image/tiff)'),
                 ('image/jpeg', 'JPEG (image/jpeg)'), ('image/png', 'PNG (image/png)'),
                 ('application/vnd.sqlite3', 'sqlite (application/vnd.sqlite3)'),
                 ('application/grib', 'GRIB/GRIB2 (application/grib)')],
                help_text=
                "This media type will be used as <em>Content-Type</em> header for the asset's object upon upload.</br></br><b>WARNING: when updating the Media Type, the asset's object Content-Type header is not automatically updated, it needs to be uploaded again.</b>",
                max_length=200
            ),
        ),
        migrations.AlterField(
            model_name='collectionasset',
            name='media_type',
            field=models.CharField(
                choices=[
                    (
                        'application/vnd.apache.parquet',
                        'Apache Parquet column-oriented data file format (application/vnd.apache.parquet)'
                    ),
                    (
                        'application/x.ascii-grid+zip',
                        'Zipped ESRI ASCII raster format (.asc) (application/x.ascii-grid+zip)'
                    ),
                    (
                        'application/x.ascii-xyz+zip',
                        'Zipped XYZ (.xyz) (application/x.ascii-xyz+zip)'
                    ), ('application/x.e00+zip', 'Zipped e00 (application/x.e00+zip)'),
                    ('application/x.geotiff+zip', 'Zipped GeoTIFF (application/x.geotiff+zip)'), (
                        'image/tiff; application=geotiff',
                        'GeoTIFF (image/tiff; application=geotiff)'
                    ), ('application/x.tiff+zip', 'Zipped TIFF (application/x.tiff+zip)'),
                    ('application/x.png+zip', 'Zipped PNG (application/x.png+zip)'),
                    ('application/x.jpeg+zip', 'Zipped JPEG (application/x.jpeg+zip)'),
                    (
                        'application/vnd.google-earth.kml+xml',
                        'KML (application/vnd.google-earth.kml+xml)'
                    ),
                    (
                        'application/vnd.google-earth.kmz',
                        'Zipped KML (application/vnd.google-earth.kmz)'
                    ), ('application/x.dxf+zip', 'Zipped DXF (application/x.dxf+zip)'),
                    ('application/gml+xml', 'GML (application/gml+xml)'),
                    ('application/x.gml+zip', 'Zipped GML (application/x.gml+zip)'),
                    ('application/vnd.las', 'LIDAR (application/vnd.las)'),
                    ('application/vnd.laszip', 'Zipped LIDAR (application/vnd.laszip)'),
                    ('application/x.vnd.las+zip', 'Zipped LAS (application/x.vnd.las+zip)'),
                    (
                        'application/vnd.laszip+copc',
                        'Cloud Optimized Point Cloud (COPC) (application/vnd.laszip+copc)'
                    ), (
                        'application/x.shapefile+zip',
                        'Zipped Shapefile (application/x.shapefile+zip)'
                    ),
                    (
                        'application/x.filegdb+zip',
                        'Zipped File Geodatabase (application/x.filegdb+zip)'
                    ),
                    (
                        'application/x.filegdbp+zip',
                        'Zipped File Geodatabase (ArcGIS Pro) (application/x.filegdbp+zip)'
                    ),
                    (
                        'application/x.ms-access+zip',
                        'Zipped Personal Geodatabase (application/x.ms-access+zip)'
                    ), ('application/x.ms-excel+zip', 'Zipped Excel (application/x.ms-excel+zip)'),
                    ('application/x.tab+zip', 'Zipped Mapinfo-TAB (application/x.tab+zip)'),
                    (
                        'application/x.tab-raster+zip',
                        'Zipped Mapinfo-Raster-TAB (application/x.tab-raster+zip)'
                    ), ('application/x.csv+zip',
                        'Zipped CSV (application/x.csv+zip)'), ('text/csv', 'CSV (text/csv)'), (
                            'application/geopackage+sqlite3',
                            'Geopackage (application/geopackage+sqlite3)'
                        ),
                    (
                        'application/x.geopackage+zip',
                        'Zipped Geopackage (application/x.geopackage+zip)'
                    ), ('application/geo+json', 'GeoJSON (application/geo+json)'),
                    ('application/x.geojson+zip', 'Zipped GeoJSON (application/x.geojson+zip)'),
                    (
                        'application/x.interlis; version=2.3',
                        'Interlis 2 (application/x.interlis; version=2.3)'
                    ),
                    (
                        'application/x.interlis+zip; version=2.3',
                        'Zipped XTF (2.3) (application/x.interlis+zip; version=2.3)'
                    ),
                    (
                        'application/x.interlis; version=2.4',
                        'Interlis 2 (application/x.interlis; version=2.4)'
                    ),
                    (
                        'application/x.interlis+zip; version=2.4',
                        'Zipped XTF (2.4) (application/x.interlis+zip; version=2.4)'
                    ),
                    (
                        'application/x.interlis; version=1',
                        'Interlis 1 (application/x.interlis; version=1)'
                    ),
                    (
                        'application/x.interlis+zip; version=1',
                        'Zipped ITF (application/x.interlis+zip; version=1)'
                    ),
                    (
                        'image/tiff; application=geotiff; profile=cloud-optimized',
                        'Cloud Optimized GeoTIFF (COG) (image/tiff; application=geotiff; profile=cloud-optimized)'
                    ), ('application/pdf', 'PDF (application/pdf)'),
                    ('application/x.pdf+zip', 'Zipped PDF (application/x.pdf+zip)'),
                    ('application/json', 'JSON (application/json)'),
                    ('application/x.json+zip', 'Zipped JSON (application/x.json+zip)'),
                    ('application/x-netcdf', 'NetCDF (application/x-netcdf)'),
                    ('application/x.netcdf+zip', 'Zipped NetCDF (application/x.netcdf+zip)'),
                    ('application/xml', 'XML (application/xml)'),
                    ('application/x.xml+zip', 'Zipped XML (application/x.xml+zip)'),
                    (
                        'application/vnd.mapbox-vector-tile',
                        'mbtiles (application/vnd.mapbox-vector-tile)'
                    ), ('text/plain', 'Text (text/plain)'),
                    ('text/x.plain+zip', 'Zipped text (text/x.plain+zip)'),
                    ('application/x.dwg+zip', 'Zipped DWG (application/x.dwg+zip)'),
                    ('application/zip',
                     'Generic Zip File (application/zip)'), ('image/tiff', 'TIFF (image/tiff)'),
                    ('image/jpeg', 'JPEG (image/jpeg)'), ('image/png', 'PNG (image/png)'),
                    ('application/vnd.sqlite3', 'sqlite (application/vnd.sqlite3)'),
                    ('application/grib', 'GRIB/GRIB2 (application/grib)')
                ],
                help_text=
                "This media type will be used as <em>Content-Type</em> header for the asset's object upon upload.</br></br><b>WARNING: when updating the Media Type, the asset's object Content-Type header is not automatically updated, it needs to be uploaded again.</b>",
                max_length=200
            ),
        ),
    ]
