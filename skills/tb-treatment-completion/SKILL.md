---
name: tb-treatment-completion
priority: medium
trigger: schedule
schedule: "0 6 * * 1"
requires:
  resources: [Condition, MedicationRequest, CarePlan]
  llm: true
goal: "Monitor TB treatment completion and detect treatment abandonment risk"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  category: tb
  icd10_codes: [A15, A15.0, A15.1, A15.2, A15.3]
---

# TB Treatment Completion Monitoring

## Clinical Background

Tuberculosis treatment requires 6-9 months of continuous medication. Treatment interruption leads to drug resistance, relapse, and community transmission. WHO defines treatment abandonment as >2 consecutive months without medication.

Key indicators:
- **last_dispensed > 14 days ago AND care_plan active** → HIGH (abandonment risk)
- TB medications: rifampicin, isoniazid, pyrazinamide, ethambutol

## Reasoning Instructions

1. Identify patients with active TB conditions (A15) and active care plans
2. Compare last medication dispensing date against expected schedule
3. Assess treatment phase (intensive vs continuation)
4. Score abandonment risk based on gap duration and treatment history

## Rule-Based Fallback

- `last_dispensed > 14 days ago AND care_plan.status == "active"` → HIGH alert
