-- Run only in inventory_ai_clean. One DO statement is atomic even in pgAdmin.
DO $clean$
BEGIN
    IF current_database() <> 'inventory_ai_clean' THEN
        RAISE EXCEPTION 'Refusing write: expected inventory_ai_clean';
    END IF;
    PERFORM set_config('lock_timeout', '5000', true);
    PERFORM set_config('statement_timeout', '60000', true);
    PERFORM set_config('search_path', 'pg_catalog', true);
    IF to_regclass('public.inventory_items') IS NOT NULL THEN
        IF obj_description('public.inventory_items'::regclass, 'pg_class') IS DISTINCT FROM
            'InventoryAI clean dataset v1: managed synthetic table' THEN
            RAISE EXCEPTION 'Unmanaged existing table: refusing to adopt or overwrite';
        END IF;
        -- Migration 002 and the Python verifier check the full existing contract.
        RETURN;
    END IF;
    CREATE TABLE public.inventory_items (
        item_code text NOT NULL,
        sub_code integer NOT NULL,
        activation_date date NOT NULL,
        name text NOT NULL,
        purchase_value integer NOT NULL,
        depreciation integer NOT NULL,
        current_value integer NOT NULL,
        currency text NOT NULL,
        quantity integer NOT NULL,
        inventory_number text NOT NULL,
        location text NOT NULL
    );
    COMMENT ON TABLE public.inventory_items IS 'InventoryAI clean dataset v1: managed synthetic table';
END
$clean$;
