BEGIN;

DROP TABLE IF EXISTS commercial_price_facts CASCADE;
DROP TABLE IF EXISTS commercial_price_source_rows CASCADE;
DROP TABLE IF EXISTS commercial_price_source_units CASCADE;
DROP TABLE IF EXISTS commercial_price_documents CASCADE;

DROP TABLE IF EXISTS knowledge_workbench_fact_registry_applications CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_fact_registry_application_queue CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_registry_update_applications CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_registry_snapshots CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_fact_triples CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_fact_relations CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_fact_mentions CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_canonical_facts CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_fact_registries CASCADE;

DROP TABLE IF EXISTS knowledge_base CASCADE;
DROP TABLE IF EXISTS knowledge_documents CASCADE;

COMMIT;
