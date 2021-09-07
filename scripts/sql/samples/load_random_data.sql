/*
this query will load random data into:
- stac_api_collection   (10 collections)
- stac_api_item         (500'000 items / collection)

you can set the number of collections and the number of items for each collection.
see inline comments

*/


begin;

TRUNCATE TABLE stac_api_collection CASCADE;

-- load random collections
WITH sample_collection AS (
select generate_series(1,10) as id,  -- second number is the number of random collections to create
	random() as integer_random, 'test'
	, md5(random()::text) as text_random
)
INSERT INTO stac_api_collection (id, name, created, updated, description, license, summaries, etag, published, summaries_eo_gsd, summaries_geoadmin_variant, summaries_geoadmin_lang, summaries_proj_epsg)
select id
, concat('collection-',id) as name
, now() + random() * interval '-365 days' as created	-- random timestamp within the last year
, now() + random() * interval '-365 days' as updated	-- random timestamp within the last year
, concat_ws(' - ', 'description ',id,text_random) as description
, 'license' as license
, '{
    "eo:gsd": [],
    "proj:epsg": [
        2056
    ],
    "geoadmin:variant": []
}'::jsonb as summaries
, text_random as etag
, TRUE as published
, '{}' as summaries_eo_gsd
, '{}' as summaries_geoadmin_variant
, '{}' as summaries_geoadmin_lang
, '{}' as summaries_proj_epsg

FROM sample_collection;


-- load random items
EXPLAIN ANALYZE VERBOSE -- comment out if you dont want explain analyze output of the insert
WITH
spatial_extent as (
	SELECT
	2400000 as xmin
	, 2800000 as xmax
	, 1000000 as ymin
	, 1350000 as ymax
	, 50000 as width
)
, collections AS (
	select
	id
	, name
	FROM stac_api_collection
), items as (
SELECT
	generate_series(1,10000) as id  -- second number is the number of random items per collections
	-- each item will get a random extent / geometry
	, st_setsrid(concat(
		'BOX(',
		spatial_extent.xmin,
		' ',
		spatial_extent.ymin,
		',',
		spatial_extent.xmin+spatial_extent.width,
		' ',
		spatial_extent.ymin+spatial_extent.width,
		')'
		)::box2d::geometry,2056) as sample_box
	from spatial_extent
)
INSERT INTO stac_api_item ( name, geometry, created, updated, etag, collection_id)
select
	concat_ws('-',collections.name,'item',items.id)  as name
	, st_transform(st_translate(sample_box
	,random()*(spatial_extent.xmax-spatial_extent.xmin-spatial_extent.width)::integer
	,random()*(spatial_extent.ymax-spatial_extent.ymin-spatial_extent.width)::integer),4326) as geometry
	, now() + random() * interval '-365 days' as created	-- random timestamp within the last year
	, now() + random() * interval '-365 days' as updated	-- random timestamp within the last year
	, md5(random()::text) as etag
	, collections.id as collection_id
from collections,items,spatial_extent order by 1 asc;

rollback;
