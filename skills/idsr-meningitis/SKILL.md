---
name: idsr-meningitis
priority: critical
trigger: both
schedule: "0 6 * * 1"
event_filter:
  resource_type: Condition
  code_prefix: "A39"
requires:
  resources: [Condition]
  llm: true
  adapter_features: [aggregate]
  min_data_window: 12w
goal: "Detect meningitis outbreaks with seasonal and belt-aware thresholds"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  icd10_codes: [A39, G00, G01]
---

# Meningitis Outbreak Detection (IDSR)

## Clinical Background

Bacterial meningitis (ICD-10: A39 — meningococcal, G00 — bacterial NOS, G01 — in diseases elsewhere classified) has distinct seasonal patterns in the African meningitis belt (Dec–Jun). IDSR thresholds differ between meningitis season and off-season.

Key indicators:
- **Zero-to-one transition**: Any case in zero-baseline area → critical
- **Seasonal thresholds**: During Dec–Jun in meningitis belt, rate-based thresholds apply
- **Off-season cluster**: ≥2 cases outside meningitis season → critical
- **Doubling**: Cases > 2× baseline → high

## Reasoning Instructions

1. Determine if currently in meningitis season (Dec–Jun)
2. Apply season-appropriate thresholds
3. Compare against 12-week rolling baseline
4. Note geographic clustering
5. Consider seasonal and belt location context

## Rule-Based Fallback

- `count >= 1 AND baseline == 0` → CRITICAL
- Outside season: `count >= 2` → CRITICAL
- `count > baseline * 2` → HIGH
