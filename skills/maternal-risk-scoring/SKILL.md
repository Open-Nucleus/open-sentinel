---
name: maternal-risk-scoring
priority: high
trigger: event
event_filter:
  resource_type: Observation
requires:
  resources: [Condition, Observation, Patient]
  llm: true
goal: "Identify high-risk maternal patients requiring urgent intervention"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  category: maternal-health
  icd10_codes: [O10, O11, O13, O14, O15, O16]
---

# Maternal Risk Scoring

## Clinical Background

Maternal complications including pre-eclampsia and HELLP syndrome remain leading causes of maternal mortality. Early detection of risk factors through vital sign monitoring enables timely intervention.

Key thresholds:
- Systolic BP > 160 mmHg → HIGH
- Diastolic BP > 110 mmHg → HIGH
- Platelets < 100,000 → HIGH
- 2+ concurrent abnormals → CRITICAL (pre-eclampsia/HELLP signal)

## Reasoning Instructions

1. Analyse BP trajectories over 4 weeks per patient
2. Cross-reference lab values (platelets, liver enzymes, uric acid)
3. Consider obstetric history and gestational age
4. Multi-factor risk synthesis for pre-eclampsia/HELLP

## Rule-Based Fallback

- `systolic > 160` → HIGH
- `diastolic > 110` → HIGH
- `platelets < 100000` → HIGH
- `2+ concurrent abnormals` → CRITICAL
