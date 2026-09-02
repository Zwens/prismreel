#!/usr/bin/env python3

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils.model_catalog import (
    FRONTEND_GENERATED_MODEL_CATALOG_PATH,
    GENERATED_MODEL_CATALOG_PATH,
    build_catalog_validation_report,
    load_generated_model_catalog,
    load_pricing,
)

VIDEO_GROUPS = {"t2v", "i2v", "r2v"}


def _format_surface_summary(surface_summary):
    lines = []
    for surface, groups in surface_summary.items():
        counts = ", ".join(
            f"{group}={len(model_ids)}"
            for group, model_ids in groups.items()
        )
        lines.append(f"- {surface}: {counts}")
    return lines


def check_pricing_coverage() -> list:
    """Enforce pricing for visible, active Byteplus video models (P1 scope).

    P1 owns pricing for models that declare a runtime.byteplus backend. Non-Byteplus
    models (wan, kling, vidu, etc.) are outside this phase's scope and must not fail
    the build.

    Problem: a visible, active Byteplus video model with pricing: None.
    """
    catalog = load_generated_model_catalog()
    problems = []
    covered_byteplus = 0
    total_visible = 0
    total_visible_byteplus = 0

    # Maps to check if a model uses Byteplus backend
    legacy_to_canonical = catalog.get("compat", {}).get("legacy_model_ids", {})
    modes = catalog.get("modes", {})

    for model_id, entry in catalog.get("models", {}).items():
        ui = entry.get("ui") or {}
        if entry.get("status") != "active" or not ui.get("visible_in"):
            continue
        if ui.get("selection_group") not in VIDEO_GROUPS:
            continue

        total_visible += 1

        # Check if this model uses Byteplus backend by looking up its canonical mode
        canonical_mode_id = legacy_to_canonical.get(model_id)
        has_byteplus = False
        if canonical_mode_id and canonical_mode_id in modes:
            mode = modes[canonical_mode_id]
            has_byteplus = "byteplus" in mode.get("runtime", {})

        if has_byteplus:
            total_visible_byteplus += 1
            if entry.get("pricing") is None:
                problems.append(f"{model_id}: visible Byteplus video model has no pricing entry")
            else:
                covered_byteplus += 1

    print(f"- pricing: {covered_byteplus} Byteplus video model(s) priced (P1 scope)")
    print(f"  ({total_visible} total visible video, {total_visible_byteplus} Byteplus)")
    return problems


def check_promotion_dates() -> list:
    problems = []
    for model_id, entry in load_pricing().items():
        for promo in entry.get("promotions") or []:
            ends_at = promo.get("ends_at")
            if not ends_at:
                problems.append(f"{model_id}: promotion without ends_at")
                continue
            try:
                dt.datetime.fromisoformat(ends_at)
            except ValueError:
                problems.append(f"{model_id}: unparsable ends_at {ends_at!r}")
    return problems


def main() -> int:
    report = build_catalog_validation_report()

    # Collect problems from all validators
    all_problems = list(report.errors)
    all_problems.extend(check_pricing_coverage())
    all_problems.extend(check_promotion_dates())

    status = "PASSED" if (report.ok and not all_problems) else "FAILED"
    print(f"Model catalog validation {status}")
    print(f"- backend artifact: {GENERATED_MODEL_CATALOG_PATH}")
    print(f"- frontend artifact: {FRONTEND_GENERATED_MODEL_CATALOG_PATH}")
    print(f"- families: {report.stats['families']}")
    print(f"- models: {report.stats['models']}")
    print(f"- visible models: {report.stats['visible_models']}")
    print(f"- defaults: {report.stats['defaults']}")
    print("- visible model counts by surface:")
    for line in _format_surface_summary(report.stats["surface_summary"]):
        print(f"  {line}")

    hidden_models = report.stats.get("hidden_models", [])
    planned_models = report.stats.get("planned_models", [])
    if hidden_models:
        print(f"- hidden models: {', '.join(hidden_models)}")
    if planned_models:
        print(f"- planned models: {', '.join(planned_models)}")

    # Phase 2: canonical metadata summary
    print(f"- model lines: {report.stats.get('model_lines', 0)}")
    print(f"- canonical modes: {report.stats.get('canonical_modes', 0)}")
    print(f"- legacy aliases: {report.stats.get('legacy_aliases', 0)}")
    canonical_defaults = report.stats.get("canonical_defaults", {})
    if canonical_defaults:
        print(f"- canonical defaults: {canonical_defaults}")

    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning}")

    if all_problems:
        print("Errors:")
        for error in all_problems:
            print(f"- {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
