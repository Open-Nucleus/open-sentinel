"""Supply stockout prediction skill."""

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


class StockoutPredictionSkill(Skill):
    def name(self) -> str:
        return "stockout-prediction"

    def trigger(self) -> SkillTrigger:
        return SkillTrigger.SCHEDULE

    def schedule(self) -> Optional[str]:
        return "0 6 * * 1"

    def priority(self) -> Priority:
        return Priority.MEDIUM

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
        return "Predict supply stockouts before they occur"

    def build_prompt(self, ctx: AnalysisContext) -> str:
        stock = extract_records(ctx, "stock_levels")
        consumption = extract_records(ctx, "recent_consumption")

        lines = ["## Supply Stock Data\n"]
        lines.append(f"### Current Stock Levels ({len(stock)} records, 12-week window)")
        for s in stock[:30]:
            site = s.get("site_id", "unknown")
            item = s.get("item_code", "unknown")
            qty = s.get("value", s.get("quantity", 0))
            lines.append(f"- {site} / {item}: {qty} units")

        lines.append(f"\n### Recent Consumption ({len(consumption)} records, 4-week window)")
        for c in consumption[:30]:
            site = c.get("site_id", "unknown")
            item = c.get("item_code", "unknown")
            qty = c.get("value", c.get("quantity", 0))
            lines.append(f"- {site} / {item}: {qty} consumed")

        lines.append("\n### Analysis Required")
        lines.append("1. Calculate days_remaining per site/item")
        lines.append("2. Analyze 12-week consumption trends")
        lines.append("3. Identify items at risk of stockout within 30 days")
        lines.append("4. Recommend redistribution from overstocked sites")

        return "\n".join(lines)

    def rule_fallback(self, ctx: AnalysisContext) -> List[Alert]:
        stock = extract_records(ctx, "stock_levels")
        consumption = extract_records(ctx, "recent_consumption")
        now = datetime.now(timezone.utc)
        alerts: List[Alert] = []

        # Build consumption map: (site_id, item_code) -> total consumed in 4w
        cons_map: Dict[str, float] = {}
        for c in consumption:
            key = f"{c.get('site_id', '')}-{c.get('item_code', '')}"
            cons_map[key] = cons_map.get(key, 0) + float(c.get("value", c.get("quantity", 0)))

        for s in stock:
            site_id = s.get("site_id", "")
            item_code = s.get("item_code", "")
            current_stock = float(s.get("value", s.get("quantity", 0)))
            key = f"{site_id}-{item_code}"

            total_consumed_4w = cons_map.get(key, 0)
            avg_weekly = total_consumed_4w / 4.0 if total_consumed_4w > 0 else 0

            if avg_weekly > 0:
                days_remaining = (current_stock / avg_weekly) * 7
            else:
                days_remaining = 999

            if days_remaining < 30:
                alerts.append(Alert(
                    skill_name=self.name(),
                    severity="moderate",
                    category="supply-chain",
                    title=(
                        f"Stockout risk at {site_id}: "
                        f"{item_code} ({int(days_remaining)}d remaining)"
                    ),
                    description=(
                        f"{item_code} at {site_id} has approximately {int(days_remaining)} days "
                        f"of stock remaining at current consumption rate. "
                        f"Current stock: {current_stock}, weekly consumption: {avg_weekly:.1f}."
                    ),
                    site_id=site_id,
                    evidence={
                        "site_id": site_id,
                        "item_code": item_code,
                        "current_stock": current_stock,
                        "days_remaining": days_remaining,
                        "avg_weekly_consumption": avg_weekly,
                    },
                    measured_value=days_remaining,
                    threshold_value=30.0,
                    dedup_key=site_dedup_key(self.name(), site_id, now),
                    rule_validated=True,
                ))

        return alerts
