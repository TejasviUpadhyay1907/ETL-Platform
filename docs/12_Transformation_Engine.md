# Transformation Engine
## Enterprise ETL & Data Quality Platform — Phase 7

**Version:** 1.0.0  
**Status:** Implemented  
**Coverage:** 87.87% (transformation package)

---

## Table of Contents

1. Transformation Architecture
2. Transformer Pipeline Flow
3. Transformer Strategy Reference
4. Rule Engine & YAML Configuration
5. Expression Language Reference
6. Business Calculations Reference
7. Lineage Tracking
8. Configuration Guide
9. Extension Guide
10. API Reference

---

## 1. Transformation Architecture

The Transformation Engine is Stage 3 of the ETL pipeline. It receives a cleaned DataFrame (from the Cleaning Engine) and produces an analytics-ready DataFrame with standardised names, derived columns, enriched lookups, and ML-ready features.

**Key principle: The original cleaned_df is never modified. The engine works on a copy.**

```
cleaned_df (from Cleaning Engine)
        ↓  .copy()
TransformationEngine.transform()
        │
        ├── TransformationRegistry.build_for_dataset()
        │       Loads YAML config and constructs transformer instances in priority order
        │
        ├── TransformationExecutor.execute()
        │       Runs each transformer sequentially — output feeds next transformer
        │       ┌──────────────────────────────────────────────────┐
        │       │ Priority 10: StandardizationTransformer  (rename)│
        │       │ Priority 15: TypeCastTransformer         (types) │
        │       │ Priority 20: DateTransformer             (dates) │
        │       │ Priority 30: DerivedColumnTransformer    (expr)  │
        │       │ Priority 40: BusinessRuleTransformer     (KPIs)  │
        │       │ Priority 45: CategoricalTransformer      (maps)  │
        │       │ Priority 50: LookupTransformer            (enrich)│
        │       │ Priority 60: FeatureEngineeringTransformer (ML) │
        │       └──────────────────────────────────────────────────┘
        │
        ├── Build TransformationReport (lineage + metrics)
        │
        ├── TransformationEngine._persist() → AuditLog
        │
        └── TransformationResult
            ├── transformed_df  (analytics-ready, new DataFrame)
            └── report          (lineage, metrics, column manifest)
```

---

## 2. Transformer Pipeline Flow

Each transformer receives the working DataFrame and returns it (modified in-place or as a new copy) plus a list of `TransformationAction` objects recording what was done.

```
Input df  →  StandardizationTransformer  →  TypeCastTransformer
           (rename status→order_status)   (str→float for order_total)
                      │
                      ↓
         DateTransformer  →  DerivedColumnTransformer
        (adds order_date_year)  (adds order_age_days, is_high_value)
                      │
                      ↓
       BusinessRuleTransformer  →  CategoricalTransformer
       (adds order_value_band)    (normalises status casing)
                      │
                      ↓
       LookupTransformer  →  FeatureEngineeringTransformer
       (adds region from country)  (adds is_high_value_order)
                      │
                      ↓
              Analytics-ready DataFrame
```

---

## 3. Transformer Strategy Reference

| Transformer | Priority | Category | What It Does |
|---|---|---|---|
| `StandardizationTransformer` | 10 | standardization | Renames columns (field_mappings YAML), normalises snake_case |
| `TypeCastTransformer` | 15 | type_cast | Converts strings to float, int, datetime, bool |
| `DateTransformer` | 20 | date | Derives year/month/quarter/week/day_of_week/is_weekend/age_days per date field |
| `DerivedColumnTransformer` | 30 | derived | Evaluates expression-based derived columns from YAML |
| `BusinessRuleTransformer` | 40 | business | Dataset-specific KPI calculations (profit, margin, stock_value, full_name) |
| `CategoricalTransformer` | 45 | categorical | Alias mapping and case normalisation for categorical columns |
| `LookupTransformer` | 50 | lookup | Enriches with region (from country), currency symbol, custom lookup tables |
| `FeatureEngineeringTransformer` | 60 | feature | ML-ready features: value bands, inventory risk, payment risk, margin tier |

---

## 4. Rule Engine & YAML Configuration

All transformations are configured in `config/datasets/{type}/transformations.yaml`.

### Field Mappings (column renaming)

```yaml
field_mappings:
  status: order_status          # renames 'status' → 'order_status'
  product_id: product_id        # identity (no rename)
```

### Derived Fields (expression-based columns)

```yaml
derived_fields:
  - name: order_age_days
    expression: "days_since(order_date)"
    description: "Days since the order was placed"

  - name: is_high_value
    expression: "order_total >= 1000"
    description: "True for orders over $1000"

  - name: total_price
    expression: "multiply(quantity, unit_price)"
```

### Business Rules (additional YAML-driven calculations)

```yaml
business_rules:
  - name: discounted_total
    expression: "subtract(order_total, discount_amount)"
    description: "Net order total after discount"
```

### Category Mappings

```yaml
category_mappings:
  status:
    cancelled: canceled     # normalise British/American spelling
    on_hold: pending        # merge categories

case_normalizations:
  country: upper           # US, GB, AU
  city: title              # New York, Los Angeles
```

---

## 5. Expression Language Reference

| Expression | Syntax | Example |
|---|---|---|
| Days since date | `days_since(col)` | `days_since(order_date)` |
| Year from date | `year(col)` | `year(order_date)` |
| Month from date | `month(col)` | `month(payment_date)` |
| Quarter | `quarter(col)` | `quarter(order_date)` |
| Multiply | `multiply(a, b)` | `multiply(quantity, unit_price)` |
| Subtract | `subtract(a, b)` | `subtract(price, cost)` |
| Divide | `divide(a, b)` | `divide(revenue, units)` |
| Add | `add(a, b)` | `add(subtotal, tax_amount)` |
| Percentage | `pct(a, b)` | `pct(profit, price)` |
| Flag ≥ | `if_gte(col, value)` | `if_gte(order_total, 1000)` |
| Flag > | `if_gt(col, value)` | `if_gt(margin_pct, 50)` |
| Flag ≤ | `if_lte(col, value)` | `if_lte(quantity, reorder_point)` |
| Concat | `concat(a, 'sep', b)` | `concat(first_name, ' ', last_name)` |
| Comparison | `col >= value` | `order_total >= 500` |

---

## 6. Business Calculations Reference

### Orders Dataset

| Derived Column | Formula | Type |
|---|---|---|
| `order_value_band` | `cut(total, [0,50,200,500,1000,∞])` → micro/small/medium/large/enterprise | category |
| `avg_unit_price` | `order_total / quantity` | float |
| `is_high_value_order` | `order_total >= 500` | bool |
| `is_active_order` | `status in {pending, processing, confirmed, shipped}` | bool |
| `order_date_year/month/quarter` | Extracted from order_date | int |
| `order_date_age_days` | Days since order_date | int |

### Products Dataset

| Derived Column | Formula |
|---|---|
| `gross_profit` | `unit_price - unit_cost` |
| `margin_pct` | `(unit_price - unit_cost) / unit_price × 100` |
| `margin_tier` | low (<10%) / medium (<25%) / high (<50%) / premium (≥50%) |

### Customers Dataset

| Derived Column | Formula |
|---|---|
| `full_name` | `first_name + ' ' + last_name` |
| `customer_age` | `(today - date_of_birth) / 365.25` |
| `is_premium_customer` | `segment in {gold, platinum, vip}` |

### Inventory Dataset

| Derived Column | Formula |
|---|---|
| `stock_value` | `quantity_on_hand × unit_cost` |
| `is_low_stock` | `quantity_on_hand <= reorder_point` |
| `inventory_risk` | critical / low / normal / excess |

### Payments Dataset

| Derived Column | Formula |
|---|---|
| `days_to_payment` | `payment_date - invoice_date` |
| `payment_risk` | early / on_time / late / very_late / overdue |

---

## 7. Lineage Tracking

Every transformation is recorded as a `TransformationAction`:

```python
@dataclass
class TransformationAction:
    rule_code: str           # e.g. "FM_001", "DT_002", "BIZ_ORD_001"
    rule_category: str       # standardization | derived | business | date | ...
    column_name: str         # output column
    source_columns: list[str] # input columns used
    transformation_type: str  # rename | cast | derive | calculate | map | enrich
    description: str
    rows_affected: int
    execution_ms: float
```

The `TransformationReport.to_lineage_records()` returns the complete audit trail:

```json
[
  {"rule_code": "FM_001", "rule_category": "standardization",
   "column_name": "order_status", "source_columns": ["status"],
   "transformation_type": "rename", "rows_affected": 5000},
  {"rule_code": "DT_001", "rule_category": "date",
   "column_name": "order_date_year", "source_columns": ["order_date"],
   "transformation_type": "derive", "rows_affected": 4987},
  {"rule_code": "BIZ_ORD_001", "rule_category": "business",
   "column_name": "order_value_band", "source_columns": ["order_total"],
   "transformation_type": "calculate", "rows_affected": 5000}
]
```

---

## 8. Configuration Guide

All settings are YAML-driven. No hardcoded business logic.

| Config File | Controls |
|---|---|
| `config/datasets/{type}/transformations.yaml` | field_mappings, derived_fields, business_rules, category_mappings |
| `config/datasets/{type}/schema.yaml` | Column type declarations (drives TypeCastTransformer and DateTransformer) |

---

## 9. Extension Guide

### Adding a New Transformer

```python
from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction

class MyCustomTransformer(BaseTransformer):
    transformer_name = "MyCustomTransformer"
    transformer_category = "custom"
    priority = 55  # runs between BusinessRule (40) and Lookup (50)

    def transform(self, df, dataset_type):
        result = df.copy()
        # ... apply transformations ...
        actions = [self._action("MY_001", "new_col", ["src_col"],
                                "derive", "My custom derivation", len(result))]
        return result, actions

# Register in TransformationRegistry.build_for_dataset():
registry.register(MyCustomTransformer())
```

### Adding a New Expression

In `DerivedColumnTransformer._evaluate()`, add a new `elif` block:

```python
# my_function(col)
m = re.fullmatch(r"my_function\((\w+)\)", expr)
if m:
    col = col_lower.get(m.group(1).lower())
    if col:
        return df[col].apply(my_python_function), [col]
```

---

## 10. API Reference

### POST /api/v1/pipelines/transform

Transform a dataset by ingestion event ID.

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
    "metrics": {
      "total_rows_input": 5000,
      "total_rows_output": 5000,
      "derived_columns_created": 4,
      "business_calcs_applied": 2,
      "total_actions": 12,
      "transformers_executed": 8
    },
    "input_columns": ["order_id", "status", "order_date", ...],
    "output_columns": ["order_id", "order_status", "order_date", "order_date_year", ...],
    "added_columns": ["order_date_year", "order_value_band", "is_high_value_order", ...]
  }
}
```

### GET /api/v1/pipelines/transform/summary/{pipeline_run_id}

Returns the transformation summary from the audit log.

### GET /api/v1/pipelines/transform/metrics/{pipeline_run_id}

Returns execution metrics from the transformation audit log.

### GET /api/v1/pipelines

Lists all pipeline runs with status and quality scores.

### GET /api/v1/pipelines/{run_id}

Returns full details for a single pipeline run.
