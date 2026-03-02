---
name: medication-missed-dose
priority: high
trigger: event
event_filter:
  resource_type: MedicationAdministration
requires:
  resources: [MedicationRequest, MedicationAdministration]
  llm: true
goal: "Detect patients with dangerous medication adherence gaps"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  category: medication-safety
---

# Medication Missed Dose Detection

## Clinical Background

Medication non-adherence is a leading cause of treatment failure, particularly for ART (HIV), TB regimens, insulin, and antihypertensives. Consecutive missed doses indicate a pattern requiring intervention before clinical deterioration.

Key indicators:
- **Consecutive missed doses >= 3** for high-stakes medications (ART, TB, insulin, antihypertensive) → HIGH
- **Consecutive missed doses >= 5** for any medication → HIGH
- High-stakes medications: ART, TB drugs, insulin, antihypertensives

## Reasoning Instructions

1. Compare MedicationRequest frequency schedule against actual MedicationAdministration records
2. Calculate consecutive missed doses per patient over 4-week window
3. Identify high-stakes medications (ART, TB, insulin, antihypertensive)
4. Assess adherence trajectory (improving, stable, deteriorating)
5. Consider patterns (e.g., weekend gaps, end-of-month gaps suggesting supply issues)

## Rule-Based Fallback

When LLM is unavailable:
- `consecutive_missed >= 3 AND high_stakes_medication` → HIGH alert
- `consecutive_missed >= 5` (any medication) → HIGH alert
