# Developer Guide — ETL Platform v1.0.0

## Development Setup

```bash
git clone https://github.com/your-org/etl-platform.git
cd etl-platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # Edit with your local DB credentials
python scripts/run_migrations.py
python scripts/seed_data.py
pytest tests/unit/ -q  # Confirm 1148 tests pass
```

---

## Coding Standards

- **Python 3.12** — use `X | Y` union syntax, not `Optional[X]`
- **Line length**: 100 characters (Black enforced)
- **Type hints**: required on all public functions
- **Docstrings**: Google-style for all public classes and functions
- **Imports**: stdlib → third-party → local (Ruff/isort enforced)
- **Error handling**: raise domain exceptions from `app/core/exceptions.py`, never bare `Exception`
- **Logging**: always use `from app.logging.logger import get_logger; logger = get_logger(__name__)`

---

## Architecture Layers

```
API Layer        app/api/routers/         HTTP endpoints — no business logic
Service Layer    app/auth/*_service.py    Business logic and orchestration
Engine Layer     app/{cleaning,validation,transformation,pipeline,loading}/
Repository Layer app/database/repositories/   DB queries only
Model Layer      app/database/models/     SQLAlchemy ORM models
```

Each layer only calls downward. Routers → Services → Engines → Repositories → Models.

---

## Adding a New Dataset Type

1. **Add enum value** in `app/utils/constants.py`:
   ```python
   class DatasetType(str, Enum):
       MY_DATASET = "my_dataset"
   ```

2. **Add ORM model** in `app/database/models/operational/my_dataset.py`

3. **Add repository** in `app/database/repositories/my_dataset_repository.py`

4. **Register model** in `app/database/models/__init__.py`

5. **Add config** in `config/datasets/my_dataset.yaml`

6. **Add validation rules** in the dataset YAML config

7. **Register load strategy** in `app/loading/load_registry.py`:
   ```python
   "my_dataset": {"strategy_type": "upsert", "target_table": "my_dataset"}
   ```

8. **Add pipeline definition** in `app/pipeline/pipeline_registry.py`

9. **Create migration**: `alembic revision --autogenerate -m "add_my_dataset_table"`

10. **Add tests** in `tests/unit/test_core/`

---

## Adding a New Validation Rule

1. Create rule class in `app/validation/rules/my_rule.py`:
   ```python
   from app.validation.base_validator import BaseValidator
   
   class MyRule(BaseValidator):
       rule_code = "MY_RULE"
       
       def validate(self, df: pd.DataFrame, config: dict) -> list[Violation]:
           ...
   ```

2. Register in `app/validation/rule_registry.py`

3. Add to dataset YAML config under `validation.rules`

4. Write tests in `tests/unit/test_core/test_validation_rules.py`

---

## Adding a New Cleaning Strategy

1. Subclass `BaseCleaner` in `app/cleaning/`:
   ```python
   from app.cleaning.base_cleaner import BaseCleaner
   
   class MyStrategy(BaseCleaner):
       strategy_name = "my_strategy"
       
       def clean(self, df, config, logger):
           ...
   ```

2. Register in `app/cleaning/cleaning_registry.py`

3. Write tests in `tests/unit/test_core/test_cleaning_strategies.py`

---

## Adding a New Transformation

1. Subclass `BaseTransformer` in `app/transformation/transformers/`

2. Register in `app/transformation/transformation_registry.py`

3. Add to dataset YAML config under `transformation.transformers`

4. Write tests in `tests/unit/test_core/test_transformation_transformers.py`

---

## Running Tests

```bash
# All unit tests
pytest tests/unit/ -q

# Specific module
pytest tests/unit/test_core/test_pipeline_orchestration.py -v

# With coverage
pytest tests/unit/ --cov=app --cov-report=html

# Dashboard tests only
pytest tests/unit/test_dashboard/ -v

# Integration (requires PostgreSQL)
pytest tests/integration/ -v
```

---

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description_of_change"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# View history
alembic history
```

---

## Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files  # Run manually
```

Hooks: black, ruff, trailing-whitespace, end-of-file-fixer, check-yaml, detect-private-key

---

## Environment Variables Reference

See `.env.example` for a fully documented list. Key variables for development:

```bash
APP_ENV=development          # enables hot reload, verbose errors
DB_ECHO=True                 # logs all SQL queries
LOG_LEVEL=DEBUG              # verbose logging
LOG_JSON_FORMAT=False        # human-readable logs in development
RATE_LIMIT_ENABLED=False     # disable for local testing
PIPELINE_ENABLE_SCHEDULER=False  # avoid background scheduler in tests
```
