# Importar Productos Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone script that imports products from `PRECIO_SISTEMA_NUEVO.xlsx` into the existing product tables without changing the system structure.

**Architecture:** Keep the app unchanged and add only `importar_productos_excel.py` plus focused unit tests. The script uses existing `create_app`, `db`, `Producto`, and `Categoria` models, creates missing categories, and upserts products by `codigo`. The script lives in `scripts/` and is discovered by tests via `pythonpath = . scripts` in `pytest.ini`.

**Tech Stack:** Python, Flask app context, SQLAlchemy models, openpyxl, pytest

---

## Files

- Create: `scripts/importar_productos_excel.py`
- Create: `test_importar_productos_excel.py`

## Tasks

- [ ] Write tests for header normalization, numeric parsing, and Excel-row mapping.
- [ ] Run the tests and verify they fail because the script does not exist.
- [ ] Implement the import script with `--dry-run`, `--limit`, `--file`, and `--sheet`.
- [ ] Run the focused tests and verify they pass.
- [ ] Run a dry-run against the real Excel with a small limit.

## Import Rules

- `codigo` identifies products and is required.
- Empty rows are ignored.
- Missing category becomes `Sin Categoria`.
- Missing stock uses `0` for actual stock and `5` for minimum stock.
- Missing prices use `0` except `precio_venta`, which also defaults to `0` to avoid import failure.
- Existing products are updated by `codigo`.
- New products are inserted with `activo=True`, `porcentaje_iva` from Excel or `10`.

## Self-Review Notes

- No app models, routes, templates, or migrations are changed.
- The import path is reversible by using `--dry-run` before real execution.
- The script is safe to run repeatedly because it upserts by `codigo`.
