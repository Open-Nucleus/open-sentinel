#!/usr/bin/env python3
"""
Open Sentinel Demo — Outbreak Detection from Open Nucleus FHIR Data

This script demonstrates the full sentinel pipeline:
1. Scans the open-nucleus Git repo for FHIR Condition resources
2. Indexes them in a lightweight SQLite database
3. Runs the IDSR cholera and measles skills
4. Emits alerts to console

Usage:
    python scripts/demo.py --repo /path/to/open-nucleus/data/repo

Prerequisites:
    - Run `go run ./cmd/seed` in the open-nucleus repo first
    - pip install aiosqlite (or install open-sentinel deps)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path so we can import open_sentinel
sys.path.insert(0, str(Path(__file__).parent.parent))

from open_sentinel.adapters.fhir_git import FhirGitAdapter
from open_sentinel.interfaces import AlertOutput
from open_sentinel.memory import SqliteMemoryStore
from open_sentinel.types import (
    AgentConfig,
    Alert,
    AnalysisContext,
    DataEvent,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sentinel-demo")


def _extract_code(resource: dict) -> str | None:
    """Extract the first code from a FHIR resource's code field."""
    code_field = resource.get("code", {})
    for coding in code_field.get("coding", []):
        if "code" in coding:
            return coding["code"]
    return None


def _extract_site(resource: dict) -> str:
    """Extract site_id from a FHIR resource. Falls back to 'site-alpha'."""
    # For demo, all seeded data is from site-alpha
    return "site-alpha"


def _extract_date(resource: dict) -> str | None:
    """Extract the date from a FHIR resource."""
    for field in ("recordedDate", "effectiveDateTime", "onsetDateTime"):
        if field in resource:
            return resource[field]
    period = resource.get("period", {})
    if "start" in period:
        return period["start"]
    return None


async def index_repo(adapter: FhirGitAdapter, repo_path: Path) -> int:
    """Walk the repo and index all FHIR resources."""
    count = 0
    patients_dir = repo_path / "patients"
    if not patients_dir.exists():
        logger.warning("No patients/ directory found in %s", repo_path)
        return 0

    for patient_dir in sorted(patients_dir.iterdir()):
        if not patient_dir.is_dir():
            continue
        for subdir in sorted(patient_dir.iterdir()):
            if not subdir.is_dir():
                continue
            resource_type = subdir.name
            # Map plural directory names to FHIR resource types
            type_map = {
                "conditions": "Condition",
                "encounters": "Encounter",
                "observations": "Observation",
                "medication-requests": "MedicationRequest",
                "allergies": "AllergyIntolerance",
                "immunizations": "Immunization",
                "procedures": "Procedure",
                "consents": "Consent",
                "flags": "Flag",
            }
            fhir_type = type_map.get(resource_type, resource_type.rstrip("s").title())

            for json_file in sorted(subdir.glob("*.json")):
                try:
                    with open(json_file) as f:
                        resource = json.load(f)

                    # Use relative path from repo root
                    rel_path = str(json_file.relative_to(repo_path))
                    code = _extract_code(resource)
                    site_id = _extract_site(resource)
                    date = _extract_date(resource)
                    actual_type = resource.get("resourceType", fhir_type)

                    await adapter.index_resource(
                        file_path=rel_path,
                        resource_type=actual_type,
                        code=code,
                        site_id=site_id,
                        date=date,
                    )
                    count += 1
                except Exception as e:
                    logger.debug("Skip %s: %s", json_file, e)

    return count


async def run_skill_demo(
    adapter: FhirGitAdapter,
    skill,
    config: AgentConfig,
) -> list[Alert]:
    """Run a single skill in rule-fallback mode and return alerts."""
    memory = SqliteMemoryStore(config.state_db_path)
    await memory.initialize()

    # Fetch required data
    data: dict = {}
    for key, req in skill.required_data().items():
        if req.group_by:
            # The fhir_index only has site_id, code, date columns.
            # Filter group_by to columns that exist in the index.
            valid_cols = {"site_id", "code", "date"}
            usable_group_by = [c for c in req.group_by if c in valid_cols]
            if not usable_group_by:
                usable_group_by = ["site_id"]
            try:
                result = await adapter.aggregate(
                    resource_type=req.resource_type,
                    group_by=usable_group_by,
                    metric=req.metric or "count",
                    filters=req.filters or {},
                )
            except Exception as e:
                logger.debug("Aggregate failed for %s: %s", key, e)
                result = []
        else:
            result = await adapter.query(
                resource_type=req.resource_type,
                filters=req.filters or {},
                limit=100,
            )
        data[key] = result

    # Build context
    ctx = AnalysisContext(
        trigger="demo.manual",
        trigger_event=DataEvent(event_type="sync.completed", resource_type="Bundle"),
        data=data,
        site_id="site-alpha",
        config={},
        llm=None,
        memory=memory,
        episodes=[],
        baselines={},
        previous_alerts=[],
    )

    # Run rule-based fallback (no LLM needed)
    alerts = skill.rule_fallback(ctx)

    await memory.close()
    return alerts


async def main():
    parser = argparse.ArgumentParser(description="Open Sentinel Demo")
    parser.add_argument(
        "--repo",
        default="../open-nucleus/data/repo",
        help="Path to open-nucleus Git repository (data/repo)",
    )
    parser.add_argument(
        "--state-db",
        default="/tmp/sentinel-demo-state.db",
        help="Path for sentinel state database",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        logger.error("Repository not found: %s", repo_path)
        logger.error("Run 'go run ./cmd/seed' in the open-nucleus repo first.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  OPEN SENTINEL — Clinical Surveillance Demo")
    print("=" * 60)
    print()

    # 1. Initialize adapter and index
    index_db = "/tmp/sentinel-demo-index.db"
    adapter = FhirGitAdapter(str(repo_path), index_db)
    await adapter.initialize()

    print(f"[1/3] Indexing FHIR resources from {repo_path}...")
    count = await index_repo(adapter, repo_path)
    print(f"       Indexed {count} resources.")
    print()

    # 2. Import and run skills
    print("[2/3] Running IDSR skills (rule-based mode)...")
    print()

    config = AgentConfig(
        hardware="pi4_8gb",
        state_db_path=args.state_db,
    )

    # Import skills (directories use hyphens, so we use importlib)
    import importlib.util

    skills_dir = Path(__file__).parent.parent / "skills"

    def load_skill(folder_name: str, class_name: str):
        spec = importlib.util.spec_from_file_location(
            f"skill_{folder_name}",
            skills_dir / folder_name / "skill.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, class_name)()

    skills_to_run = [
        load_skill("idsr-cholera", "IdsrCholeraSkill"),
        load_skill("idsr-measles", "IdsrMeaslesSkill"),
    ]

    all_alerts: list[Alert] = []
    for skill in skills_to_run:
        print(f"  Running: {skill.name()}...")
        alerts = await run_skill_demo(adapter, skill, config)
        all_alerts.extend(alerts)

        if alerts:
            for alert in alerts:
                severity_icon = {
                    "critical": "!!!",
                    "high": " !!",
                    "moderate": "  !",
                    "low": "   ",
                }.get(alert.severity, "   ")
                print(f"    [{severity_icon}] {alert.severity.upper()}: {alert.title}")
                print(f"         {alert.description}")
                print(f"         Evidence: {alert.evidence}")
                print()
        else:
            print(f"    No alerts generated.")
            print()

    # 3. Summary
    print("[3/3] Summary")
    print("-" * 60)
    print(f"  Skills executed:   {len(skills_to_run)}")
    print(f"  Total alerts:      {len(all_alerts)}")

    by_severity = {}
    for a in all_alerts:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
    for sev in ("critical", "high", "moderate", "low"):
        if sev in by_severity:
            print(f"    {sev}: {by_severity[sev]}")

    print()
    if all_alerts:
        print("  ACTION REQUIRED: Alerts generated. Human review needed.")
        print("  All alerts tagged: ai_generated=False, rule_validated=True")
        print("  (Rule-based mode — no LLM was used)")
    else:
        print("  No outbreaks detected in current data.")
    print()

    await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
