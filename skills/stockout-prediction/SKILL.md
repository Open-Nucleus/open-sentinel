---
name: stockout-prediction
priority: medium
trigger: schedule
schedule: "0 6 * * 1"
requires:
  resources: [SupplyDelivery]
  llm: true
goal: "Predict supply stockouts before they occur"
max_reflections: 2
confidence_threshold: 0.6
metadata:
  category: supply-chain
---

# Supply Stockout Prediction

## Clinical Background

Stockouts of essential medicines and supplies are a critical barrier to health service delivery in resource-limited settings. Early prediction enables redistribution and emergency procurement before patient care is impacted.

Key indicators:
- **days_remaining < 30** based on consumption rate → MEDIUM
- 12-week consumption trend analysis for seasonal patterns

## Reasoning Instructions

1. Calculate days_remaining = current_stock / avg_weekly_consumption * 7
2. Analyze 12-week consumption trends for acceleration/deceleration
3. Consider seasonal patterns and upcoming campaign needs
4. Recommend redistribution from nearby overstocked sites

## Rule-Based Fallback

- `days_remaining < 30` → MEDIUM alert with item and site details
