-- Manual approval required. Run only after the read-only audit and data review.
-- Deliberately transactional (NOT CONCURRENTLY): a failure rolls back the index.
-- Blocks writers for the short build; readers remain available. See the guide.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog;
LOCK TABLE public.inventory_items IN SHARE MODE;
DO $migration$
DECLARE
    target oid := 'public.inventory_items'::regclass;
    column_number smallint;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class t WHERE t.oid = target AND t.relkind = 'r'
                   AND NOT t.relrowsecurity AND NOT EXISTS
                   (SELECT 1 FROM pg_inherits h WHERE h.inhparent = target OR h.inhrelid = target)) THEN
        RAISE EXCEPTION 'Unsupported relation: use a plain table without inheritance or RLS';
    END IF;
    SELECT attnum INTO column_number FROM pg_attribute
    WHERE attrelid = target AND attname = 'inventory_number' AND NOT attisdropped
      AND atttypid IN ('text'::regtype, 'varchar'::regtype);
    IF column_number IS NULL THEN
        RAISE EXCEPTION 'Missing text/varchar inventory_number column';
    END IF;
    IF EXISTS (SELECT 1 FROM public.inventory_items WHERE inventory_number IS NOT NULL
               GROUP BY inventory_number HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate inventory numbers; run scripts.audit_inventory_numbers and resolve manually';
    END IF;
    IF EXISTS (SELECT 1 FROM public.inventory_items WHERE inventory_number ~ '^[[:space:]]*$') THEN
        RAISE EXCEPTION 'Blank inventory numbers require manual review';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = target
               AND i.indisunique AND i.indisvalid AND i.indisready AND i.indimmediate
               AND i.indpred IS NULL AND i.indexprs IS NULL
               AND i.indnkeyatts = 1 AND i.indkey[0] = column_number) THEN
        RAISE NOTICE 'A suitable complete unique index already exists; no change';
        RETURN;
    END IF;
    IF to_regclass('public.inventory_items_inventory_number_uidx') IS NOT NULL THEN
        RAISE EXCEPTION 'Index name occupied; inspect the existing object manually';
    END IF;
    CREATE UNIQUE INDEX inventory_items_inventory_number_uidx
        ON public.inventory_items (inventory_number);
    COMMENT ON INDEX public.inventory_items_inventory_number_uidx
        IS 'InventoryAI migration 001: inventory_number business key';
END
$migration$;
COMMIT;
