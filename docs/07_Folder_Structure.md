# Production Folder Structure
## Enterprise ETL & Data Quality Platform

**Version:** 1.0.0  

---

## Overview

The folder structure is designed around three core principles:
1. **Separation of Concerns** — each directory has one responsibility
2. **Discoverability** — a new engineer can navigate the project without guidance
3. **Scalability** — adding new dataset types, pipeline stages, or API routes requires no structural reorganization

---

## Complete Folder Structure

```
etl_platform/
│
├── app/                                # Application source code root
│   │
│   ├── api/                            # REST API layer (FastAPI routers)
│   │   ├── __init__.py
│   │   ├── dependencies.py             # Shared FastAPI dependencies (auth, db session)
│   │   ├── middleware/                 # Custom ASGI middleware
│   │   │   ├── __init__.py
│   │   │   ├── auth_middleware.py      # API key validation
│   │   │   └── rate_limit_middleware.py
│   │   ├── routers/                    # One router module per endpoint group
│   │   │   ├── __init__.py
│   │   │   ├── ingest_router.py        # /api/v1/ingest endpoints
│   │   │   ├── pipeline_router.py      # /api/v1/pipelines endpoints
│   │   │   ├── data_router.py          # /api/v1/data endpoints
│   │   │   ├── quality_router.py       # /api/v1/quality endpoints
│   │   │   ├── reports_router.py       # /api/v1/reports endpoints
│   │   │   └── health_router.py        # /api/v1/health endpoint
│   │   ├── schemas/                    # Pydantic request/response models
│   │   │   ├── __init__.py
│   │   │   ├── ingest_schemas.py
│   │   │   ├── pipeline_schemas.py
│   │   │   ├── data_schemas.py
│   │   │   ├── quality_schemas.py
│   │   │   └── report_schemas.py
│   │   └── error_handlers.py           # Global exception → HTTP response mapping
│   │
│   ├── core/                           # Core application bootstrap and config
│   │   ├── __init__.py
│   │   ├── application.py              # FastAPI app factory
│   │   ├── config.py                   # AppConfig Pydantic BaseSettings model
│   │   ├── config_loader.py            # Loads env vars + YAML, builds config
│   │   ├── config_registry.py          # Singleton config access point
│   │   └── exceptions.py              # Custom application exception hierarchy
│   │
│   ├── pipeline/                       # Pipeline engine and orchestration
│   │   ├── __init__.py
│   │   ├── engine.py                   # PipelineRunner — main orchestrator
│   │   ├── stage_executor.py           # StageExecutor — wraps each stage call
│   │   ├── context.py                  # PipelineContext — immutable run context
│   │   ├── scheduler.py               # PipelineScheduler — APScheduler integration
│   │   ├── trigger_service.py          # PipelineTriggerService — API-facing trigger
│   │   └── models.py                   # PipelineRun, StageResult domain models
│   │
│   ├── ingestion/                      # File ingestion module
│   │   ├── __init__.py
│   │   ├── file_receiver.py            # Handles upload and directory detection
│   │   ├── file_type_detector.py       # MIME type and extension validation
│   │   ├── dataset_type_resolver.py    # Maps filename patterns to DatasetType enum
│   │   ├── raw_file_store.py           # Writes raw files to versioned directory
│   │   ├── directory_watcher.py        # Polls watched directory for new files
│   │   └── models.py                   # IngestionEvent, IngestionResult models
│   │
│   ├── validation/                     # Validation engine
│   │   ├── __init__.py
│   │   ├── validator.py                # Main ValidationEngine entry point
│   │   ├── schema_validator.py         # Column presence and type validation
│   │   ├── rule_engine.py              # BusinessRuleEngine — applies rule list
│   │   ├── rule_registry.py            # Maps dataset type to rule list
│   │   ├── annotator.py                # Appends validation metadata to DataFrame
│   │   ├── quality_scorer.py           # Calculates quality score
│   │   ├── rules/                      # One rule module per rule category
│   │   │   ├── __init__.py
│   │   │   ├── base_rule.py            # Abstract BaseRule interface
│   │   │   ├── orders_rules.py         # Order-specific business rules
│   │   │   ├── customers_rules.py
│   │   │   ├── products_rules.py
│   │   │   ├── inventory_rules.py
│   │   │   ├── suppliers_rules.py
│   │   │   └── payments_rules.py
│   │   └── models.py                   # ValidationResult, ValidationReport models
│   │
│   ├── cleaning/                       # Cleaning engine
│   │   ├── __init__.py
│   │   ├── cleaner.py                  # Main CleaningEngine entry point
│   │   ├── deduplication.py            # DeduplicationHandler
│   │   ├── null_handler.py             # NullHandler with per-field strategies
│   │   ├── string_normalizer.py        # Trim, case normalization
│   │   ├── date_standardizer.py        # Date format parsing and ISO conversion
│   │   ├── numeric_cleaner.py          # Currency symbols, commas, locale handling
│   │   ├── action_logger.py            # CleaningActionLogger
│   │   └── models.py                   # CleaningResult, CleaningLog, CleaningSummary
│   │
│   ├── transformation/                 # Transformation engine
│   │   ├── __init__.py
│   │   ├── transformer_registry.py     # Maps dataset type to Transformer class
│   │   ├── base_transformer.py         # Abstract BaseTransformer interface
│   │   ├── field_mapper.py             # Column renaming and reordering
│   │   ├── derived_field_calculator.py # Computed field expressions
│   │   ├── lookup_enricher.py          # Foreign key enrichment from DB
│   │   ├── aggregation_builder.py      # Summary aggregations
│   │   ├── transformers/               # Dataset-specific transformer implementations
│   │   │   ├── __init__.py
│   │   │   ├── orders_transformer.py
│   │   │   ├── customers_transformer.py
│   │   │   ├── products_transformer.py
│   │   │   ├── inventory_transformer.py
│   │   │   ├── suppliers_transformer.py
│   │   │   └── payments_transformer.py
│   │   └── models.py                   # TransformationResult, TransformationSummary
│   │
│   ├── loading/                        # Data loader
│   │   ├── __init__.py
│   │   ├── loader.py                   # Main DataLoader entry point
│   │   ├── upsert_manager.py           # INSERT ... ON CONFLICT logic
│   │   └── models.py                   # LoadResult model
│   │
│   ├── database/                       # Database layer
│   │   ├── __init__.py
│   │   ├── engine.py                   # SQLAlchemy engine and session factory
│   │   ├── transaction.py              # TransactionManager context manager
│   │   ├── models/                     # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # Declarative base
│   │   │   ├── operational/            # Business data table models
│   │   │   │   ├── orders.py
│   │   │   │   ├── customers.py
│   │   │   │   ├── products.py
│   │   │   │   ├── inventory.py
│   │   │   │   ├── suppliers.py
│   │   │   │   └── payments.py
│   │   │   ├── pipeline/               # Pipeline metadata table models
│   │   │   │   ├── ingestion_event.py
│   │   │   │   ├── pipeline_run.py
│   │   │   │   └── stage_result.py
│   │   │   └── audit/                  # Audit and quality table models
│   │   │       ├── audit_log.py
│   │   │       ├── validation_failure.py
│   │   │       ├── cleaning_log.py
│   │   │       └── quality_score.py
│   │   └── repositories/              # Repository classes per domain
│   │       ├── __init__.py
│   │       ├── base_repository.py      # Abstract BaseRepository
│   │       ├── order_repository.py
│   │       ├── customer_repository.py
│   │       ├── product_repository.py
│   │       ├── inventory_repository.py
│   │       ├── supplier_repository.py
│   │       ├── payment_repository.py
│   │       ├── pipeline_run_repository.py
│   │       ├── ingestion_event_repository.py
│   │       ├── report_repository.py
│   │       └── audit_log_repository.py
│   │
│   ├── reporting/                      # Report generation module
│   │   ├── __init__.py
│   │   ├── orchestrator.py             # ReportOrchestrator
│   │   ├── quality_report_builder.py   # Data quality report assembly
│   │   ├── business_report_builder.py  # Business summary report assembly
│   │   ├── report_exporter.py          # CSV and Excel export
│   │   ├── report_file_store.py        # File system path management
│   │   └── models.py                   # ReportMetadata model
│   │
│   ├── dashboard/                      # Web dashboard module
│   │   ├── __init__.py
│   │   ├── router.py                   # Dashboard HTML routes
│   │   └── templates/                  # Jinja2 HTML templates
│   │       ├── base.html               # Base layout template
│   │       ├── runs_list.html          # Pipeline run history page
│   │       ├── run_detail.html         # Per-run detail page
│   │       ├── upload.html             # File upload page
│   │       ├── quality.html            # Quality metrics page
│   │       └── reports.html            # Reports list and download page
│   │
│   ├── logging/                        # Logging and audit module
│   │   ├── __init__.py
│   │   ├── logger.py                   # StructuredLogger wrapper
│   │   ├── audit_emitter.py            # AuditEventEmitter — writes to DB
│   │   └── pii_masker.py              # PIIMasker — field-level value masking
│   │
│   └── static/                         # Static web assets
│       ├── css/
│       │   └── dashboard.css
│       └── js/
│           └── dashboard.js
│
├── config/                             # All configuration files
│   ├── app.yaml                        # Application-level default configuration
│   ├── logging.yaml                    # Logging configuration
│   └── datasets/                       # Per-dataset configuration (one dir per type)
│       ├── orders/
│       │   ├── schema.yaml             # Expected columns, types, required flags
│       │   ├── rules.yaml              # Business validation rule definitions
│       │   ├── cleaning.yaml           # Per-field cleaning strategies
│       │   └── transformations.yaml    # Derived fields, mappings
│       ├── customers/
│       │   ├── schema.yaml
│       │   ├── rules.yaml
│       │   ├── cleaning.yaml
│       │   └── transformations.yaml
│       ├── products/
│       │   └── ...
│       ├── inventory/
│       │   └── ...
│       ├── suppliers/
│       │   └── ...
│       └── payments/
│           └── ...
│
├── migrations/                         # Alembic database migrations
│   ├── env.py                          # Alembic environment configuration
│   ├── script.py.mako                  # Migration script template
│   └── versions/                       # Individual migration version files
│       └── 001_initial_schema.py
│
├── data/                               # Runtime data directories (gitignored)
│   ├── raw/                            # Raw ingested files (versioned by date + run)
│   ├── reports/                        # Generated report files (by run_id)
│   └── archive/                        # Archived files (raw + reports)
│
├── logs/                               # Application log files (gitignored)
│   └── app.log
│
├── tests/                              # All test code
│   ├── __init__.py
│   ├── conftest.py                     # Shared pytest fixtures (DB, config, sample data)
│   ├── fixtures/                       # Sample test data files
│   │   ├── orders_valid.csv
│   │   ├── orders_invalid.csv
│   │   ├── customers_valid.csv
│   │   └── ... (one valid + invalid per dataset type)
│   ├── unit/                           # Unit tests (no external dependencies)
│   │   ├── test_validation/
│   │   │   ├── test_schema_validator.py
│   │   │   ├── test_rule_engine.py
│   │   │   └── test_quality_scorer.py
│   │   ├── test_cleaning/
│   │   │   ├── test_deduplication.py
│   │   │   ├── test_null_handler.py
│   │   │   ├── test_date_standardizer.py
│   │   │   └── test_numeric_cleaner.py
│   │   ├── test_transformation/
│   │   │   └── test_transformers.py
│   │   └── test_reporting/
│   │       └── test_report_builders.py
│   ├── integration/                    # Integration tests (require DB and file system)
│   │   ├── test_ingestion_pipeline.py
│   │   ├── test_full_pipeline.py       # End-to-end pipeline test per dataset
│   │   └── test_api_endpoints.py
│   └── fixtures_factory.py             # Programmatic test data generation helpers
│
├── docker/                             # Docker-related files
│   ├── Dockerfile                      # App container build file
│   ├── Dockerfile.dev                  # Development variant with hot-reload
│   └── nginx/
│       └── nginx.conf                  # Nginx reverse proxy configuration
│
├── scripts/                            # Utility and operational scripts
│   ├── seed_data.py                    # Load sample data for development
│   ├── create_api_key.py               # CLI tool to generate and register API keys
│   ├── run_migrations.py               # Wrapper for running Alembic migrations
│   └── health_check.py                 # CLI health check script
│
├── docs/                               # Project documentation
│   ├── 01_SRS.md                       # Software Requirements Specification
│   ├── 02_HLD.md                       # High-Level Design
│   ├── 03_LLD.md                       # Low-Level Design
│   ├── 04_ETL_Workflow.md              # Complete ETL workflow description
│   ├── 05_Data_Flow_Diagram.md         # Data flow narrative and diagrams
│   ├── 06_Component_Diagram.md         # Component interaction diagram
│   ├── 07_Folder_Structure.md          # This document
│   ├── 08_Development_Roadmap.md       # Development milestones
│   └── api/
│       └── openapi.yaml                # Auto-generated OpenAPI specification
│
├── .env.example                        # Example environment variable file
├── .gitignore
├── docker-compose.yml                  # Production Docker Compose definition
├── docker-compose.dev.yml              # Development Docker Compose with overrides
├── pyproject.toml                      # Python project metadata and dependencies
├── alembic.ini                         # Alembic configuration
└── README.md                           # Project overview and getting-started guide
```

---

## Directory Purpose Reference

| Directory | Purpose |
|---|---|
| `app/api/` | All HTTP layer concerns — routers, middleware, schemas, error handling |
| `app/api/routers/` | One file per logical API group; keeps routing focused and discoverable |
| `app/api/schemas/` | Pydantic models for request/response contracts; separate from ORM models |
| `app/core/` | Application bootstrap: config, app factory, exception hierarchy |
| `app/pipeline/` | Orchestration engine — the sequencer, not the business logic |
| `app/ingestion/` | File acceptance, type detection, raw file persistence |
| `app/validation/` | Schema and business rule enforcement; rules are self-contained objects |
| `app/validation/rules/` | Dataset-specific rule implementations, one module per dataset |
| `app/cleaning/` | All data normalization and repair logic |
| `app/transformation/` | Dataset-specific transformers; easily extended by adding one class |
| `app/transformation/transformers/` | Concrete transformer per dataset — isolated, testable |
| `app/loading/` | Database write logic; completely separate from business rules |
| `app/database/` | ORM models, repository classes, session management — the data access layer |
| `app/database/models/operational/` | Table definitions for business data |
| `app/database/models/pipeline/` | Table definitions for pipeline run tracking |
| `app/database/models/audit/` | Table definitions for audit and quality tracking |
| `app/database/repositories/` | One repository per domain; no raw SQL outside this directory |
| `app/reporting/` | Report building, export, and file management |
| `app/dashboard/` | HTML views and templates; no business logic |
| `app/logging/` | Shared logging infrastructure used by every other module |
| `config/` | All configuration files — never hardcode values in source code |
| `config/datasets/` | Dataset-specific schema, rules, and transformation configs |
| `migrations/` | Database migration history; every schema change is versioned here |
| `data/` | Runtime data storage; gitignored; managed by the application |
| `tests/unit/` | Fast tests with no external dependencies; run constantly during development |
| `tests/integration/` | Tests requiring database and file system; run in CI pipeline |
| `tests/fixtures/` | Static sample files for testing ingestion and pipeline stages |
| `docker/` | Container build files and reverse proxy config |
| `scripts/` | Operational utilities; not part of the application runtime |
| `docs/` | Architecture documents and API specifications |
