# Cleaning Engine
## Enterprise ETL & Data Quality Platform — Phase 6

**Version:** 1.0.0  
**Status:** Implemented  
**Coverage:** 92.32% (cleaning package)

---

## Table of Contents

1. Cleaning Architecture
2. CleaningResult Contract (TransformationEngine compatibility)
3. Cleaning Pipeline Flow
4. Strategy Reference
5. Null Handling Strategies
6. Rule Engine & YAML Configuration
7. Lineage Tracking
8. Rollback & Preview Mode
9. Audit Model
10. Configuration Guide
11. Extension Guide
12. API Reference

---

## 1. Cleaning Architecture

The Cleaning Engine sits between the Validation Engine (Phase 5) and the already-implemented Transformation Engine (Phase 7). It receives a `ValidationResult`, repairs data quality issues, and returns a `CleaningResult` that the Transformation Engine can use **without any modification**.

```
ValidationResult (from Validation Engine)
        ↓ extract valid_df + warning_df
        ↓
CleaningEngine.clean()
        │
        ├── CleaningRegistry.build_for_dataset()
        │       Loads cleaning.yaml → constructs cleaners in priority order
        │       ┌─────────────────────────────────────────┐
        │       │ Priority 10: NullHandler                │
        │       │ Priority 20: DeduplicationHandler       │
        │       │ Priority 30: StringNormalizer           │
        │       │ Priority 35: NumericCleaner             │
        │       │ Priority 40: DateStandardizer           │
        │       │ Priority 45: CategoricalCleaner         │
        │       │ Priority 50: BusinessRuleCleaner        │
        │       └─────────────────────────────────────────┘
        │
        ├── CleaningExecutor.execute()
        │       Runs cleaners sequentially — each receives previous output
        │
        ├── CleaningActionLogger.build_metrics()
        │       Aggregates CleaningAction list into CleaningMetrics
        │
        ├── CleaningReport built with full lineage
        │
        ├── CleaningActionLogger.persist()
        │       Writes to cleaning_logs + audit_logs tables
        │
        └── CleaningResult
            ├── cleaned_df     → handed to TransformationEngine (CONTRACT)
            ├── dataset_type   → handed to TransformationEngine (CONTRACT)
            ├── pipeline_run_id → handed to TransformationEngine (CONTRACT)
            ├── cleaning_report → full audit trail
            ├── cleaning_metrics → aggregated statistics
            ├── original_df    → pre-cleaning snapshot for rollback/diff
            └── rejected_df    → rows that were dropped
```

---

## 2. CleaningResult Contract (TransformationEngine compatibility)

The TransformationEngine (Phase 7) is called exactly as follows — **this interface must never change**:

```python
transformer = TransformationEngine(session=db)
result = transformer.transform(
    cleaned_df=cleaning_result.cleaned_df,       # pandas DataFrame
    dataset_type=cleaning_result.dataset_type,   # str: "orders" | "customers" | ...
    pipeline_run_id=cleaning_result.pipeline_run_id,  # str | None
)
```

The `CleaningResult` guarantees:

| Field | Type | Required | Description |
|---|---|---|---|
| `cleaned_df` | `pd.DataFrame` | ✅ | The cleaned dataset — direct input to Transformation Engine |
| `dataset_type` | `str` | ✅ | One of: orders, customers, products, inventory, suppliers, payments |
| `pipeline_run_id` | `str \| None` | ✅ | UUID string or None |
| `cleaning_report` | `CleaningReport` | additive | Full audit trail |
| `cleaning_metrics` | `CleaningMetrics` | additive | Aggregated statistics |
| `execution_time` | `float` | additive | Seconds taken |
| `success` | `bool` | additive | Whether cleaning completed |
| `warnings` | `list[str]` | additive | Non-fatal issues |
| `errors` | `list[str]` | additive | Fatal issues |
| `original_df` | `pd.DataFrame` | additive | Pre-cleaning snapshot |
| `rejected_df` | `pd.DataFrame` | additive | Dropped rows |

---

## 3. Cleaning Pipeline Flow

```
Input DataFrame (from ValidationResult.valid_df + warning_df)
    ├── NullHandler         fills/drops/flags null values per field strategy
    ├── DeduplicationHandler removes exact and key-based duplicates
    ├── StringNormalizer    trims whitespace, normalizes case, removes control chars
    ├── NumericCleaner      strips currency, parses percentages, clips outliers
    ├── DateStandardizer    parses all date formats → ISO 8601 YYYY-MM-DD
    ├── CategoricalCleaner  maps aliases, normalizes case, handles unknowns
    └── BusinessRuleCleaner explicit value normalizations from YAML
              ↓
    cleaned_df (all values repaired, no rows with DATA changes retained from before)
    + CleaningReport (every single cell change recorded with before/after)
    + CleaningMetrics (aggregated counts for dashboard)
```

Every cleaner chains: the output of cleaner N is the input to cleaner N+1.

---

## 4. Strategy Reference

| Cleaner | Priority | Rule Codes | What It Fixes |
|---|---|---|---|
| `NullHandler` | 10 | MV_DROP, MV_FILL, MV_MEAN, MV_MED, MV_MODE, MV_ZERO, MV_FFILL, MV_BFILL, MV_INTERP, MV_FLAG | Null, NaN, empty string values |
| `DeduplicationHandler` | 20 | DUP_001 | Exact duplicate rows, key-based duplicates |
| `StringNormalizer` | 30 | STR_001, STR_002 | Whitespace, case, control characters, unicode |
| `NumericCleaner` | 35 | NUM_001–004 | Currency symbols, commas, percentages, outliers |
| `DateStandardizer` | 40 | DT_001–003 | Date format parsing → ISO 8601 |
| `CategoricalCleaner` | 45 | CAT_001–003 | Alias mapping, case normalization, unknown handling |
| `BusinessRuleCleaner` | 50 | BIZ_* | Explicit value normalization from YAML |

---

## 5. Null Handling Strategies

All strategies are configured in `config/datasets/{type}/cleaning.yaml` per field:

| Strategy | Config Value | Behaviour |
|---|---|---|
| Drop row | `null_strategy: drop_row` | Remove entire row |
| Fill default | `null_strategy: fill_default` + `default_value: X` | Replace with X |
| Fill mean | `null_strategy: fill_mean` | Replace with column mean (numeric) |
| Fill median | `null_strategy: fill_median` | Replace with column median |
| Fill mode | `null_strategy: fill_mode` | Replace with most frequent value |
| Fill zero | `null_strategy: fill_zero` | Replace with 0 |
| Forward fill | `null_strategy: forward_fill` | Propagate last valid value forward |
| Backward fill | `null_strategy: backward_fill` | Propagate next valid value backward |
| Interpolate | `null_strategy: interpolate` | Linear interpolation for ordered numeric |
| Flag | `null_strategy: flag` + `sentinel_value: MISSING` | Replace with sentinel |
| Keep | `null_strategy: keep` | Leave null as-is (explicit no-op) |

---

## 6. Rule Engine & YAML Configuration

All cleaning strategies are driven entirely by YAML. No hardcoded business logic.

### config/datasets/orders/cleaning.yaml

```yaml
dataset_type: orders
field_strategies:
  order_id:
    null_strategy: drop_row
    trim: true
    string_case: upper

  order_total:
    null_strategy: drop_row
    strip_currency: true     # remove $, £, €, commas
    rounding: 2

  order_date:
    null_strategy: drop_row
    standardize_date: true   # → ISO 8601 YYYY-MM-DD

  status:
    null_strategy: fill_default
    default_value: unknown
    string_case: lower
    trim: true
    allowed_values: [pending, processing, shipped, delivered, cancelled]
    unknown_strategy: flag

business_rules:
  status:
    - match: [ACTIVE, Active, active, A]
      replace: active
      rule_code: BIZ_STATUS_001

  payment_method:
    - match: [CC, CREDIT, credit_card]
      replace: credit_card
```

---

## 7. Lineage Tracking

Every modification produces a `CleaningAction`:

```python
@dataclass
class CleaningAction:
    rule_code: str          # e.g. "MV_FILL", "STR_001", "DUP_001"
    rule_category: str      # missing | duplicate | string | numeric | date | ...
    field_name: str | None  # column that was modified (None for row-level)
    row_index: int | None   # row position (None for dataset-level)
    original_value: Any     # value BEFORE cleaning
    cleaned_value: Any      # value AFTER cleaning
    action_type: str        # fill_null | drop_row | trim | case_normalize | ...
    reason: str             # human-readable explanation
    confidence: float       # 0.0–1.0 (1.0 = certain fix)
```

Access the full lineage:

```python
# All changes as list of dicts
lineage = result.cleaning_report.to_lineage_records()

# Before/after diff for changed cells only
diff_df = result.diff()
```

---

## 8. Rollback & Preview Mode

### Preview (dry-run)

```python
engine = CleaningEngine(session=None, dry_run=True)
preview = engine.preview(df=df, dataset_type="orders")

# preview.cleaned_df  == original df (no changes applied)
# preview.diff()      shows what WOULD change
# preview.cleaning_report.actions  lists every planned action
```

### Rollback

The original DataFrame is preserved in `CleaningResult.original_df`. To roll back:

```python
original_data = cleaning_result.original_df.copy()
```

### Diff

```python
diff = cleaning_result.diff()
# Returns DataFrame: row_index, field_name, original_value, cleaned_value, rule_code, reason
```

---

## 9. Audit Model

Every cleaning run writes to two tables:

**`audit_logs`** — one row per run:
```
event_type: STAGE_COMPLETED
stage:      cleaning
context_data: {metrics, input_columns, dropped_rows, total_actions, ...}
```

**`cleaning_logs`** — one row per modification (up to 2000):
```
pipeline_run_id, row_index, dataset_type, action_type, field_name,
original_value, cleaned_value
```

Action type values in `cleaning_logs` (DB CHECK constraint):
`duplicate_removed | null_filled | null_dropped | null_flagged | string_trimmed | case_normalized | date_standardized | numeric_cleaned | regex_applied`

---

## 10. Configuration Guide

| Config File | Controls |
|---|---|
| `config/datasets/{type}/cleaning.yaml` | All field-level cleaning strategies |
| `config/datasets/{type}/schema.yaml` | Date field detection (auto-configures DateStandardizer) |
| `config/datasets/{type}/rules.yaml` | Categorical allowed values (auto-configures CategoricalCleaner) |

### Global cleaning settings (cleaning.yaml top level)

```yaml
global_settings:
  null_threshold_pct: 50.0    # warn when column is >50% null
  dedup_keep_strategy: keep_first
  global_trim: true           # trim ALL string columns by default
  global_control_chars: true  # strip control chars from ALL string cols
```

---

## 11. Extension Guide

### Adding a New Cleaning Strategy

```python
from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction

class MyCustomCleaner(BaseCleaningRule):
    rule_name = "MyCustomCleaner"
    rule_category = "custom"
    priority = 55  # between BusinessRule (50) and any future cleaner

    def clean(self, df, dataset_type):
        result = df.copy()
        actions = []
        # ... apply cleaning, record every change as CleaningAction ...
        return result, actions

# Register in CleaningRegistry.build_for_dataset():
registry.register(MyCustomCleaner())
```

### Adding a New Null Strategy

Add a new `elif strategy == "my_strategy":` block in `NullHandler.clean()`.

### Adding a New Business Rule

No code changes needed — edit `cleaning.yaml`:

```yaml
business_rules:
  my_field:
    - match: [BAD_VALUE_1, bad_value_2]
      replace: canonical_value
      rule_code: BIZ_MY_001
      description: "Normalize bad values to canonical form"
```

---

## 12. API Reference

### POST /api/v1/cleaning/run

Run cleaning on a previously ingested file.

**Request:**
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
    "metrics": {
      "total_rows_input": 5000,
      "total_rows_output": 4975,
      "rows_dropped": 25,
      "nulls_filled": 142,
      "strings_trimmed": 89,
      "dates_standardized": 5000,
      "cleaning_pct": 68.4
    },
    "total_actions": 5231,
    "warnings": [],
    "success": true
  }
}
```

### POST /api/v1/cleaning/preview

Dry-run: compute all changes without applying them.

### POST /api/v1/cleaning/dry-run

Alias for `/preview`.

### GET /api/v1/cleaning/report/{pipeline_run_id}

Paginated cleaning action log (one row per modification).

### GET /api/v1/cleaning/summary/{pipeline_run_id}

High-level cleaning summary from audit log.

### GET /api/v1/cleaning/metrics/{pipeline_run_id}

Cleaning metrics only (counts, percentages, timing).

### GET /api/v1/cleaning/diff/{pipeline_run_id}

Before/after diff — only rows where `original_value != cleaned_value`.
