-- Separate administrative step. Run on postgres with autocommit enabled,
-- only after explicitly approving the inventory_ai_clean target.
-- The guarded, idempotent CLI alternative is scripts.prepare_inventory_database.
-- PostgreSQL does not allow CREATE DATABASE inside a DO/transaction block.
CREATE DATABASE inventory_ai_clean TEMPLATE template0 ENCODING 'UTF8';
