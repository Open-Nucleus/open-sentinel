"""Critical supply stockout detection skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from open_sentinel.interfaces import Skill
from open_sentinel.skills.clinical_base import (
    SUPPLY_RESPONSE_SCHEMA,
    extract_records,
    site_dedup_key,
)
from open_sentinel.types import Alert, AnalysisContext, DataRequirement, Priority, SkillTrigger


class StockoutCriticalSkill(Skill):
    def name(self) -> str:
        return "stockout-critical"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.EVENT

    def priority(self) -> Priority:
        return Priority.HIGH

    def event_filter(self) -> Optional[Dict[str, Any]]:
        return {"resource_type": "SupplyDelivery"}

    def required_data(self) -> Dict[str, DataRequirement]:
        return {
            "stock_levels": DataRequirement(
                resource_type="SupplyDelivery",
                filters={},
                time_window="12w",
                group_by=["site_id", "item_code"],
                name="stock_levels",
            ),
            "recent_consumption": DataRequirement(
                resource_type="SupplyDelivery",
                filters={},
                time_window="4w",
                group_by=["site_id", "item_code"],
                metric="sum",
                name="recent_consumption",
            ),
        }

    def response_schema(self) -> Optional[Dict[str, Any]]:
        return SUPPLY_RESPONSE_SCHEMA

    def max_reflections(self) -> int:
        return 2

    def goal(self) -> str:
        return "Detect critical supply stockouts requiring emergency response"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        stock = extract_records(ctx, "stock_levels")
        consumption = extract_records(ctx, "recent_consumption")

        lines = ["## Critical Stock Assessment\n"]
        lines.append(f"### Stock Levels ({len(stock)} records)")
        for s in stock[:30]:
            site = s.get("site_id", "unknown")
            item = s.get("item_code", "unknown")
            qty = s.get("value", s.get("quantity", 0))
            lines.append(f"- {site} / {item}: {qty} units")

        lines.append(f"\n### Recent Consumption ({len(consumption)} records)")
        for c in consumption[:30]:
            site = c.get("site_id", "unknown")
            item = c.get("item_code", "unknown")
            qty = c.get("value", c.get("quantity", 0))
            lines.append(f"- {site} / {item}: {qty} consumed")

        lines.append("\n### Analysis Required")
        lines.append("1. Identify zero-stock items by site")
        lines.append("2. Calculate days_remaining for near-stockout items")
        lines.append("3. Recommend emergency redistribution sources")
        lines.append("4. Prioritize patient-critical items (ART, TB, insulin)")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        stock = extract_records(ctx, "stock_levels")
        consumption = extract_records(ctx, "recent_consumption")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        cons_map: Dict[str, float] = {}
        for c in consumption:
            key = f"{c.get('site_id', '')}-{c.get('item_code', '')}"
            cons_map[key] = cons_map.get(key, 0) + float(c.get("value", c.get("quantity", 0)))

        for s in stock:
            site_id = s.get("site_id", "")
            item_code = s.get("item_code", "")
            current_stock = float(s.get("value", s.get("quantity", 0)))
            key = f"{site_id}-{item_code}"

            if current_stock == 0:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="supply-chain",
                    title=f"Stockout at {site_id}: {item_code} (zero stock)",
                    description=(
                        f"{item_code} at {site_id} has zero stock. "
                        f"Emergency redistribution required."
                    ),
                    site_id=site_id,
                    evidence={
                        "site_id": site_id,
                        "item_code": item_code,
                        "current_stock": 0,
                    },
                    measured_value=0.0,
                    threshold_value=0.0,
                    dedup_key=site_dedup_key(self.name(), site_id, now),
                    rule_validated=True,
                ))
                continue

            total_consumed_4w = cons_map.get(key, 0)
            avg_weekly = total_consumed_4w / 4.0 if total_consumed_4w > 0 else 0

            if avg_weekly > 0:
                days_remaining = (current_stock / avg_weekly) * 7
            else:
                continue

            if days_remaining < 7:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="high",
                    category="supply-chain",
                    title=(
                        f"Critical stockout risk at {site_id}: "
                        f"{item_code} ({int(days_remaining)}d)"
                    ),
                    description=(
                        f"{item_code} at {site_id} has approximately {int(days_remaining)} days "
                        f"of stock remaining. Emergency action required."
                    ),
                    site_id=site_id,
                    evidence={
                        "site_id": site_id,
                        "item_code": item_code,
                        "current_stock": current_stock,
                        "days_remaining": days_remaining,
                    },
                    measured_value=days_remaining,
                    threshold_value=7.0,
                    dedup_key=site_dedup_key(self.name(), site_id, now),
                    rule_validated=True,
                ))

        return alerts
