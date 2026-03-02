---
name: immunisation-gap
priority: medium
trigger: schedule
schedule: "0 6 * * 1"
requires:
  resources: [Immunization, Patient]
  llm: true
goal: "Identify children with overdue immunisations per EPI schedule"
max_reflections: 2
confidence_threshold: 0.6
metadata:
  category: immunisation
---

# Immunisation Gap Detection

## Clinical Background

The WHO Expanded Programme on Immunization (EPI) defines a standard vaccination schedule for children. Missed or delayed doses increase morbidity and mortality from vaccine-preventable diseases.

Standard EPI schedule:
- BCG: birth (0d)
- OPV0: birth (0d)
- Penta1/OPV1: 6 weeks (42d)
- Penta2/OPV2: 10 weeks (70d)
- Penta3/OPV3: 14 weeks (98d)
- Measles1: 9 months (270d)
- Measles2: 15 months (450d)

Overdue by > 4 weeks → MEDIUM alert.

## Reasoning Instructions

1. For each patient with known DOB, compare expected vs received immunisations
2. Calculate delay for each missing dose
3. Generate personalised catch-up schedule
4. Note any contraindications from patient history

## Rule-Based Fallback

Compare expected schedule against completed immunisations. Overdue > 4 weeks → MEDIUM.
