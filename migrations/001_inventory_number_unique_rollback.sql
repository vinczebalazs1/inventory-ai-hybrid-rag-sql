-- Separate explicit approval required; removes only the index created by 001.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog;
DO $rollback$
DECLARE
    target oid := to_regclass('public.inventory_items_inventory_number_uidx');
BEGIN
    IF target IS NULL THEN
        RAISE NOTICE 'Migration index absent; no change';
        RETURN;
    END IF;
    IF obj_description(target, 'pg_class') IS DISTINCT FROM
       'InventoryAI migration 001: inventory_number business key'
       OR NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a
           ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
           WHERE i.indexrelid = target AND i.indrelid = 'public.inventory_items'::regclass
             AND i.indisunique AND i.indnkeyatts = 1 AND a.attname = 'inventory_number'
             AND i.indpred IS NULL AND i.indexprs IS NULL) THEN
        RAISE EXCEPTION 'Object ownership/definition not verified; refusing rollback';
    END IF;
    -- No CASCADE: dependencies cause a safe rollback instead of being deleted.
    DROP INDEX public.inventory_items_inventory_number_uidx;
END
$rollback$;
COMMIT;
