---
phase: 01-data-schema-leak-audit
reviewed: 2026-06-11T12:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - src/__init__.py
  - src/schemas/__init__.py
  - src/schemas/audit.py
  - src/schemas/entry.py
  - src/schemas/export.py
  - src/schemas/odds_trifecta.py
  - src/schemas/payoff.py
  - src/schemas/race.py
  - src/schemas/result.py
  - tests/__init__.py
  - tests/schemas/__init__.py
  - tests/schemas/conftest.py
  - tests/schemas/test_audit.py
  - tests/schemas/test_classification.py
  - tests/schemas/test_entry.py
  - tests/schemas/test_init_reexports.py
  - tests/schemas/test_odds_trifecta.py
  - tests/schemas/test_payoff.py
  - tests/schemas/test_race.py
  - tests/schemas/test_result.py
  - tests/schemas/test_schema_export.py
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-06-11
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Reviewed all 20 source and test files for the data schema and leak audit layer. The implementation is well-structured: Pydantic schemas correctly classify pre/post-race fields via `json_schema_extra`, the audit functions use exact-name matching to avoid false positives on lag features, and the `__init__.py` re-exports are complete and tested. The cross-table classification test (`test_classification.py`) with its `KAGGLE_COLUMN_MAP` provides strong machine-verifiable coverage of all 66 Kaggle columns.

Three findings identified: one warning (dead code path in a test) and two info items (unused imports in test files). No security vulnerabilities, no data leakage classification errors, and no logic bugs found in the production code.

## Warnings

### WR-01: Dead code branch in test_odds_trifecta.py

**File:** `tests/schemas/test_odds_trifecta.py:74`
**Issue:** Line 74 assigns `optional_fields` using a conditional that checks `hasattr(self, 'EXPECTED_FIELDS')`. Since `EXPECTED_FIELDS` is defined on `TestOddsTrifectaSchemaFields` (a different class), `hasattr(self, 'EXPECTED_FIELDS')` evaluates to `False` within `TestOddsTrifectaSchemaFieldTypes` -- so the first assignment produces `set()`. This is immediately overwritten on line 76 by the correct expression referencing the class attribute directly. The first assignment is dead code that obscures intent and would mask a real bug if line 76 were ever removed.
**Fix:**
```python
# In TestOddsTrifectaSchemaFieldTypes.test_all_trifecta_fields_are_optional
# Replace lines 74-76 with a single clear line:
optional_fields = TestOddsTrifectaSchemaFields.EXPECTED_FIELDS - {"race_id"}
```

## Info

### IN-01: Unused import `get_origin` in test_result.py

**File:** `tests/schemas/test_result.py:62-63`
**Issue:** `get_origin` and `get_args` are imported inside three separate test methods (`test_finish_position_is_optional_int`, `test_finish_note_is_optional_str`, `test_last_3f_is_optional_float`). While `get_args` is used, `get_origin` is imported but never referenced in the method bodies. This is not a bug but adds noise.
**Fix:** Remove `get_origin` from the inner imports, or move both imports to the module top level.

### IN-02: Unused import `get_origin` in test_race.py

**File:** `tests/schemas/test_race.py:108`
**Issue:** Inside `test_race_schema_field_types`, `get_origin(annotation)` is called on line 108 but its return value is discarded (not assigned to a variable or used in an assertion). The call serves no purpose and is likely a leftover from development.
**Fix:** Remove the unused `get_origin(annotation)` call on line 108, or assign it and use it in a type-check assertion.

---

_Reviewed: 2026-06-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
