---
name: vital-sign-trend
priority: high
trigger: event
event_filter:
  resource_type: Observation
requires:
  resources: [Observation]
  llm: true
goal: "Detect acute vital sign deterioration requiring immediate intervention"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  category: clinical-deterioration
  loinc_codes: [59408-5, 8867-4, 9279-1, 8310-5, 8480-6]
---

# Vital Sign Trend Analysis

## Clinical Background

Acute deterioration in vital signs is a strong predictor of adverse outcomes. Early warning scores (EWS/NEWS) use threshold-based rules to trigger clinical escalation.

Key thresholds:
- SpO2 < 92% → HIGH
- Heart rate > 120 or < 40 bpm → HIGH
- Respiratory rate > 30/min → HIGH
- Temperature > 38.5°C → MODERATE, > 40°C → HIGH
- Multiple concurrent abnormals → CRITICAL

## Reasoning Instructions

1. Evaluate all vital signs within the 24h window per patient
2. Assess trend trajectory (improving vs deteriorating)
3. Score aggregate risk from concurrent abnormals
4. Predict 6h deterioration risk based on trajectory

## Rule-Based Fallback

Apply threshold rules per vital sign. Multiple concurrent abnormals → CRITICAL.
