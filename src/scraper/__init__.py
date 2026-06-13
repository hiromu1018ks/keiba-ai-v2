"""Scraping infrastructure package for netkeiba race data collection.

Public re-exports are added in Plan 06 (final integration) once all
submodules exist. Importing this package MUST NOT trigger any submodule
import (Codex Review HIGH #3).
"""
# Submodules: models.py, enumeration.py (Plan 02); fetcher.py (Plan 03);
# parser.py, course_codes.py, flag_crosswalk.py (Plan 04);
# normalizer.py (Plan 05); orchestrator.py (Plan 06). Re-exports wired in 06.
