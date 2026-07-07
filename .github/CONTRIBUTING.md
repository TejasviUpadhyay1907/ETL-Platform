# Contributing to ETL Platform

Thank you for your interest in contributing. This guide covers how to set up your
development environment, run tests, and submit changes.

---

## Quick Start

```bash
git clone https://github.com/TejasviUpadhyay1907/ETL-Platform.git
cd ETL-Platform
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

See [docs/FIRST_TIME_SETUP.md](../docs/FIRST_TIME_SETUP.md) for a complete walkthrough.

---

## Development Workflow

1. Fork the repo and create a branch: `git checkout -b feat/my-feature`
2. Make your changes following the conventions below
3. Run tests: `pytest tests/unit/ -q`
4. Run linting: `ruff check app/ tests/ dashboard/`
5. Push and open a Pull Request

---

## Coding Conventions

- **Python 3.12+** — type hints on all public functions
- **Black** for formatting (line length 100): `black app/ tests/ dashboard/ --line-length=100`
- **Ruff** for linting: `ruff check app/ tests/ dashboard/`
- **Mypy** for types: `mypy app/ --ignore-missing-imports`
- All DB writes wrapped in `try/except` with rollback
- No direct `print()` in app code — use `get_logger(__name__)`

---

## Extending the Platform

| Extension Point | Where to add |
|-----------------|-------------|
| New dataset type | `app/loading/load_registry.py` + `config/` |
| New validator | `app/validation/validators/` + register in `ValidationEngine` |
| New cleaning strategy | `app/cleaning/` + register in `CleaningRegistry` |
| New transformer | `app/transformation/transformers/` + register in `TransformationEngine` |
| New dashboard page | `dashboard/pages/` (numbered prefix, e.g. `11_MyPage.py`) |
| New API endpoint | `app/api/routers/` + add to `app/core/application.py` |

---

## Running Tests

```bash
# Unit tests (no DB required, fast)
pytest tests/unit/ -q

# With coverage
pytest tests/unit/ --cov=app --cov-report=term-missing

# Integration tests (requires PostgreSQL)
pytest tests/integration/ -v
```

---

## Reporting Issues

Please use GitHub Issues. Include:
- Python version (`python --version`)
- Error message and full traceback
- Steps to reproduce

---

## License

By contributing, you agree your code will be released under the [MIT License](../LICENSE).
