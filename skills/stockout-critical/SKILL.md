---
name: stockout-critical
priority: high
trigger: event
event_filter:
  resource_type: SupplyDelivery
requires:
  resources: [SupplyDelivery]
  llm: true
goal: "Detect critical supply stockouts requiring emergency response"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  category: supply-chain
---

# Critical Supply Stockout Detection

## Clinical Background

A zero-stock situation or less than 7 days of supply for essential medicines represents a clinical emergency. Patients on chronic regimens (ART, TB, diabetes) face treatment interruption and potentially life-threatening consequences.

Key indicators:
- **current_stock == 0** → HIGH (active stockout)
- **days_remaining < 7** → HIGH (imminent stockout)

## Reasoning Instructions

1. Identify sites with zero stock for any essential item
2. Calculate days_remaining for items below threshold
3. Recommend emergency redistribution from nearby sites
4. Prioritize by patient impact (ART, TB medications first)

## Rule-Based Fallback

- `current_stock == 0` → HIGH alert
- `days_remaining < 7` → HIGH alert
