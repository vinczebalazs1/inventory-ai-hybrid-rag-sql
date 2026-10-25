-- Constraints apply to the clean synthetic environment only; never to inventory.
-- No financial equality CHECK: accumulated depreciation is a generator convention.
DO $clean$
DECLARE
    target oid;
    rule record;
    actual text;
    expected_names text[] := ARRAY['item_code','sub_code','activation_date','name','purchase_value',
        'depreciation','current_value','currency','quantity','inventory_number','location'];
    expected_types text[] := ARRAY['text','integer','date','text','integer','integer','integer','text','integer','text','text'];
BEGIN
    IF current_database() <> 'inventory_ai_clean' THEN
        RAISE EXCEPTION 'Refusing write: expected inventory_ai_clean';
    END IF;
    PERFORM set_config('lock_timeout', '5000', true);
    PERFORM set_config('statement_timeout', '60000', true);
    PERFORM set_config('search_path', 'pg_catalog', true);
    target := to_regclass('public.inventory_items');
    IF target IS NULL OR obj_description(target, 'pg_class') IS DISTINCT FROM
        'InventoryAI clean dataset v1: managed synthetic table' THEN
        RAISE EXCEPTION 'Missing managed clean table';
    END IF;
    LOCK TABLE public.inventory_items IN ACCESS EXCLUSIVE MODE;
    IF NOT EXISTS (SELECT 1 FROM pg_class t WHERE t.oid = target AND t.relkind = 'r'
        AND NOT t.relrowsecurity AND NOT EXISTS
        (SELECT 1 FROM pg_inherits WHERE inhrelid = target OR inhparent = target))
        OR EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = target AND NOT tgisinternal)
        OR EXISTS (SELECT 1 FROM pg_rewrite WHERE ev_class = target) THEN
        RAISE EXCEPTION 'Unsupported table, trigger, rule, inheritance or RLS';
    END IF;
    IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute
            WHERE attrelid = target AND attnum > 0 AND NOT attisdropped) IS DISTINCT FROM expected_names
        OR (SELECT array_agg(format_type(atttypid, atttypmod) ORDER BY attnum) FROM pg_attribute
            WHERE attrelid = target AND attnum > 0 AND NOT attisdropped) IS DISTINCT FROM expected_types
        OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = target AND attnum > 0 AND NOT attisdropped
            AND (NOT attnotnull OR attidentity <> '' OR attgenerated <> '')) THEN
        RAISE EXCEPTION 'Existing table differs from the eleven-column clean contract';
    END IF;
    FOR rule IN SELECT * FROM (VALUES
        ('clean_inventory_format', 'inventory_number ~ ''^L-[0-9]{5,}$'''),
        ('clean_quantity_one', 'quantity = 1'),
        ('clean_name_nonblank', 'name ~ ''[^[:space:]]'''),
        ('clean_item_nonblank', 'item_code ~ ''[^[:space:]]'''),
        ('clean_location_nonblank', 'location ~ ''[^[:space:]]'''),
        ('clean_purchase_nonnegative', 'purchase_value >= 0'),
        ('clean_depreciation_nonnegative', 'depreciation >= 0'),
        ('clean_current_nonnegative', 'current_value >= 0'),
        ('clean_currency_code', 'currency ~ ''^[A-Z]{3}$''')
    ) AS rules(name, expression)
    LOOP
        SELECT pg_get_expr(conbin, conrelid) INTO actual FROM pg_constraint
            WHERE conrelid = target AND conname = rule.name AND contype = 'c' AND convalidated AND NOT connoinherit;
        IF actual IS NULL THEN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = target AND conname = rule.name) THEN
                RAISE EXCEPTION 'Unexpected existing constraint: %', rule.name;
            END IF;
            IF current_database() <> 'inventory_ai_clean' THEN
                RAISE EXCEPTION 'Refusing write: expected inventory_ai_clean';
            END IF;
            EXECUTE format('ALTER TABLE public.inventory_items ADD CONSTRAINT %I CHECK (%s)', rule.name, rule.expression);
        ELSIF regexp_replace(replace(actual, '::text', ''), '[()[:space:]]', '', 'g') <>
              regexp_replace(rule.expression, '[()[:space:]]', '', 'g') THEN
            RAISE EXCEPTION 'Constraint definition differs: %', rule.name;
        END IF;
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = target AND conname = 'clean_inventory_unique') THEN
        ALTER TABLE public.inventory_items ADD CONSTRAINT clean_inventory_unique UNIQUE (inventory_number);
    ELSIF NOT EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_index i ON i.indexrelid = c.conindid
        WHERE c.conrelid = target AND c.conname = 'clean_inventory_unique' AND c.contype = 'u'
        AND c.conkey = ARRAY[10]::smallint[] AND NOT c.condeferrable AND c.convalidated
        AND i.indisvalid AND i.indisready AND i.indimmediate) THEN
        RAISE EXCEPTION 'Inventory UNIQUE constraint has an unexpected definition';
    END IF;
END
$clean$;
