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
INSERT INTO stac_api_collection (id, name, created, updated, description, license, summaries, etag)
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
, text_random as etag FROM sample_collection;


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
	generate_series(1,500000) as id  -- second number is the number of random items per collections
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

-- test bbox on-the-fly
EXPLAIN ANALYZE 
SELECT 
"stac_api_collection"."id"
, "stac_api_collection"."name"
, "stac_api_collection"."created"
, "stac_api_collection"."updated"
, "stac_api_collection"."description"
, "stac_api_collection"."extent_start_datetime"
, "stac_api_collection"."extent_end_datetime"
, "stac_api_collection"."license"
, "stac_api_collection"."summaries"
, "stac_api_collection"."title"
, "stac_api_collection"."etag"
, st_setsrid(ST_Extent("stac_api_item"."geometry")::geometry,4326) AS "num_item" 
FROM stac_api_collection_ltclm "stac_api_collection"
LEFT OUTER JOIN "stac_api_item_ltclm" stac_api_item
ON ("stac_api_collection"."id" = "stac_api_item"."collection_id") 
GROUP BY "stac_api_collection"."id";

rollback;
