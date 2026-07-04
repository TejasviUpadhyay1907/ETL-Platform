# Validation Engine
## Enterprise ETL & Data Quality Platform — Phase 5

**Version:** 1.0.0  
**Status:** Implemented  
**Coverage:** 89% (validation package)

---

## Table of Contents

1. Validation Architecture
2. Validation Pipeline Flow Diagram
3. Rule Engine Design
4. Quality Score Algorithm
5. Validation Lifecycle
6. Configuration Guide
7. Extension Guide (Adding New Rules)
8. Error Handling Strategy
9. API Reference
10. Validation Rule Reference

---

## 1. Validation Architecture

The Validation Engine is Stage 2 of the ETL pipeline. It receives an immutable `Dataset` object from the Ingestion Engine and returns a `ValidationResult` containing the quality analysis, row partitions, and quality score.

**Critical constraint: the Validation Engine NEVER modifies data values. It only reads and annotates.**

```
Dataset (from Ingestion Engine)
        ↓
ValidationEngine.validate()
        │
        ├── RuleRegistry.build_for_dataset()    ← YAML config → rule objects
        │       ├── SchemaValidator              (priority 10)
        │       ├── MissingValueValidator        (priority 20)
        │       ├── DuplicateValidator           (priority 25)
        │       ├── DataTypeValidator            (priority 30)
        │       ├── FormatValidator              (priority 40)
        │       ├── BusinessRuleValidator        (priority 50)
        │       ├── CategoricalValidator         (priority 45)
        │       ├── StatisticalValidator         (priority 60)
        │       └── ReferentialIntegrityValidator(priority 70)
        │
        ├── ValidationExecutor.execute()         ← runs all rules, collects violations
        │
        ├── ValidationAnnotator.annotate()       ← partitions rows into valid/rejected/warning
        │
        ├── QualityScoreCalculator.calculate()   ← computes 6-dimensional score
        │
        ├── Build ValidationReport
        │
        ├── ValidationRepository.persist()       ← writes to DB (optional)
        │
        └── ValidationResult                     ← returned to pipeline engine
```

### Design Principles

- **Strategy Pattern**: each validator is an independent, swappable strategy
- **Immutability**: `valid_df`, `rejected_df`, `warning_df` are boolean-index subsets, not copies with modified values
- **Configuration-driven**: all business rules come from YAML — zero hardcoded logic
- **Priority ordering**: schema checks run before business rules; statistical profiling runs last
- **Never raises**: `ValidationEngine.validate()` always returns a `ValidationResult`

---

## 2. Validation Pipeline Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Input: Dataset                                              │
│  ├─ metadata (filename, dataset_type, file_hash)             │
│  ├─ dataframe (raw pandas DataFrame — all strings)           │
│  └─ schema (column names, types, row count)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                     RuleRegistry
                    builds rule set
                    from YAML config
                           │
         ┌─────────────────▼──────────────────┐
         │         ValidationExecutor          │
         │  runs each rule in priority order   │
         │  ┌──────────────────────────────┐  │
         │  │ for each rule:               │  │
         │  │   violations, ms = rule.execute()│
         │  │   → list[RuleViolation]      │  │
         │  └──────────────────────────────┘  │
         └─────────────────┬──────────────────┘
                           │ all_violations
                     ValidationAnnotator
                  partitions by row_index
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          valid_df    rejected_df   warning_df
        (no ERRORs)  (≥1 ERROR)   (WARNING only)
                           │
                  QualityScoreCalculator
                    6-dimensional score
                    overall + grade
                           │
                    ValidationReport
                    violations + profiles
                    + quality_score
                           │
                  ValidationRepository
                  (DB write — optional)
                           │
                    ValidationResult
                    ← to pipeline engine
                    ← to cleaning engine
```

---

## 3. Rule Engine Design

### Strategy Pattern

Every validator inherits from `BaseValidationRule` and implements one method:

```python
class BaseValidationRule(abc.ABC):
    rule_code: str          # e.g. "SV", "MV", "BR"
    rule_category: str      # e.g. "schema", "missing", "business"
    default_severity: str   # "error" | "warning" | "info"
    priority: int           # execution order (lower = first)

    @abc.abstractmethod
    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        """Read df, return violations. NEVER modify df."""
```

### Rule Registry

The `RuleRegistry` assembles all rules for a dataset from YAML config:

```python
registry = RuleRegistry.build_for_dataset("orders")
rules = registry.get_ordered_rules()  # sorted by priority
```

### Adding a Custom Rule

```python
from app.validation.rules.base_rule import BaseValidationRule
from app.validation.models import RuleViolation

class MyCustomRule(BaseValidationRule):
    rule_code = "CUSTOM_001"
    rule_category = "custom"
    priority = 55

    def validate(self, df, dataset_type):
        violations = []
        # ... analyze df, never modify it ...
        return violations

# Register it
registry = RuleRegistry.build_for_dataset("orders")
registry.register(MyCustomRule())
```

---

## 4. Quality Score Algorithm

### Six Dimensions

| Dimension | Weight | Formula |
|---|---|---|
| **Completeness** | 30% | `(non_null_cells / total_cells) × 100` |
| **Validity** | 35% | `(valid_rows / total_rows) × 100` |
| **Consistency** | 15% | `100 - (format_violations / total_rows × 100)` |
| **Uniqueness** | 10% | `100 - (duplicate_rows / total_rows × 100)` |
| **Integrity** | 5% | `100 - (orphan_rows / total_rows × 100)` |
| **Timeliness** | 5% | `100 - (date_violations / total_rows × 100)` |

### Overall Score

```
overall = completeness × 0.30
        + validity      × 0.35
        + consistency   × 0.15
        + uniqueness    × 0.10
        + integrity     × 0.05
        + timeliness    × 0.05
```

### Letter Grades

| Score | Grade |
|---|---|
| ≥ 97 | A+ |
| ≥ 90 | A |
| ≥ 80 | B |
| ≥ 70 | C |
| ≥ 60 | D |
| < 60 | F |

---

## 5. Validation Lifecycle

### Row Fate Decision

Every row in the dataset receives one of three fates based on violations:

| Fate | Condition | DataFrame |
|---|---|---|
| **Valid** | No violations of any severity | `valid_df` |
| **Warning** | Has WARNING violations but no ERROR violations | `warning_df` |
| **Rejected** | Has at least one ERROR violation | `rejected_df` |

### Severity Levels

| Severity | Meaning | Row Fate |
|---|---|---|
| `error` | Rule failure that makes the record unsafe to load | Rejected |
| `warning` | Issue that should be investigated but record can proceed | Warning |
| `info` | Informational annotation | Valid |

### Dataset-Level Violations

Some violations apply to the entire dataset (column missing, high null rate):
- `row_index = None` → does NOT affect individual row fate
- Included in the report and affects the quality score dimensions

---

## 6. Configuration Guide

### Business Rules (config/datasets/{type}/rules.yaml)

```yaml
dataset_type: orders
rules:
  - rule_code: ORD_001
    field: order_id
    check: not_null
    severity: error
    description: "order_id must not be null"

  - rule_code: ORD_002
    field: order_total
    check: greater_than
    value: 0
    severity: error

  - rule_code: ORD_005
    field: status
    check: in_list
    values: [pending, shipped, delivered, cancelled]
    severity: error

  - rule_code: ORD_007
    field: order_total
    check: less_than
    value: 1000000
    severity: warning
```

### Supported Check Types

| Check | Required Params | Description |
|---|---|---|
| `not_null` | — | Field must not be null or empty |
| `greater_than` | `value` | Numeric field > value |
| `greater_than_or_equal` | `value` | Numeric field >= value |
| `less_than` | `value` | Numeric field < value |
| `less_than_or_equal` | `value` | Numeric field <= value |
| `between` | `min`, `max` | min <= field <= max |
| `in_list` | `values: [...]` | Field value must be in list |
| `not_in_list` | `values: [...]` | Field value must NOT be in list |
| `valid_date` | — | Value can be parsed as a date |
| `valid_email` | — | Value matches email format |
| `valid_phone` | — | Value matches phone format |
| `min_length` | `value` | String length >= value |
| `max_length` | `value` | String length <= value |
| `regex_match` | `pattern` | Value matches regex |
| `unique` | — | All values in column must be unique |

### Schema Config (config/datasets/{type}/schema.yaml)

Expected columns, required flags, and data types used by SchemaValidator and DataTypeValidator:

```yaml
dataset_type: orders
columns:
  - name: order_id
    type: string
    required: true
  - name: order_total
    type: decimal
    required: true
  - name: order_date
    type: date
    required: true
deduplication_key: [order_id]
```

---

## 7. Extension Guide

### Adding a New Validator

1. Create `app/validation/rules/my_validator.py` extending `BaseValidationRule`
2. Register it in `RuleRegistry.build_for_dataset()` for the relevant dataset types
3. Add tests in `tests/unit/test_core/test_validation_rules.py`
4. No changes to any other module required

### Adding a New Dataset Type

1. Create `config/datasets/{new_type}/schema.yaml` with column definitions
2. Create `config/datasets/{new_type}/rules.yaml` with business rules
3. Add `{new_type}` to the `DatasetType` enum in `app/utils/constants.py`
4. The validation engine automatically supports it — no code changes needed

### Adding a New Check Type

1. Add a new `elif check == "my_check":` block in `BusinessRuleValidator._apply_rule()`
2. Add a test case in `TestBusinessRuleValidator`
3. Document the new check type in this guide

---

## 8. Error Handling Strategy

| Scenario | Behaviour |
|---|---|
| Individual rule crashes | Logged as ERROR; rule returns empty violations; pipeline continues |
| Schema has no config | SchemaValidator runs with empty expected columns (no schema violations) |
| Empty DataFrame | All validators return empty violation list gracefully |
| DB persist fails | Logged as ERROR; ValidationResult is still returned to pipeline engine |
| Unknown dataset type | RuleRegistry builds with available config; missing configs are logged as warnings |

---

## 9. API Reference

### POST /api/v1/quality/run

Run validation on a previously ingested file.

**Request body:**
```json
{
  "ingestion_event_id": "a3f7b2c1-...",
  "pipeline_run_id": "b4e8c3d2-...",
  "dataset_type": "orders"
}
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "report_id": "...",
    "dataset_type": "orders",
    "quality_score": {
      "overall_score": 91.5,
      "letter_grade": "A",
      "completeness": 98.0,
      "validity": 89.5,
      "total_records": 5000,
      "valid_records": 4475,
      "invalid_records": 525
    },
    "total_violations": 312,
    "error_violations": 87,
    "passed_threshold": true
  }
}
```

### GET /api/v1/quality/report/{pipeline_run_id}

Get paginated violation list for a pipeline run.

Query parameters: `?severity=error&category=business&page=1&page_size=50`

### GET /api/v1/quality/score/{pipeline_run_id}

Get the stored quality score for a pipeline run.

### GET /api/v1/quality/summary/{pipeline_run_id}

Get a summary of the pipeline run including quality score.

---

## 10. Validation Rule Reference

### Schema Rules (SV_*)

| Code | Check | Severity |
|---|---|---|
| SV_001 | Required column missing | ERROR |
| SV_002 | Unexpected column present | WARNING |
| SV_003 | Duplicate column name | ERROR |
| SV_004 | Dataset has zero data rows | WARNING |

### Missing Value Rules (MV_*)

| Code | Check | Severity |
|---|---|---|
| MV_001 | Required field is null/empty | ERROR |
| MV_002 | Null rate exceeds threshold | WARNING |
| MV_003 | Column is completely empty | WARNING |
| MV_004 | Row is completely empty | WARNING |

### Data Type Rules (DT_*)

| Code | Check | Severity |
|---|---|---|
| DT_001 | Field value not valid for expected type | ERROR |
| DT_002 | Column has mixed types | WARNING |

### Duplicate Rules (DUP_*)

| Code | Check | Severity |
|---|---|---|
| DUP_001 | Exact duplicate row | WARNING |
| DUP_002 | Duplicate single-column key | ERROR |
| DUP_003 | Duplicate composite key | ERROR |

### Statistical Rules (STAT_*)

| Code | Check | Severity |
|---|---|---|
| STAT_001 | Column has outliers (IQR method) | WARNING |
| STAT_002 | Column has extreme skewness | WARNING |
| STAT_003 | Column has zero variance | WARNING |

### Format Rules (FMT_*)

| Code | Check | Severity |
|---|---|---|
| FMT_001 | Leading whitespace | WARNING |
| FMT_002 | Trailing whitespace | WARNING |
| FMT_003 | Invalid email format | ERROR |
| FMT_004 | Invalid phone format | WARNING |
| FMT_005 | Invalid URL format | WARNING |
| FMT_007 | Unicode control characters | WARNING |

### Referential Integrity Rules (REF_*)

| Code | Check | Severity |
|---|---|---|
| REF_001 | FK value not in reference set (orphan) | ERROR |
| REF_002 | High orphan rate (dataset-level) | ERROR/WARNING |
