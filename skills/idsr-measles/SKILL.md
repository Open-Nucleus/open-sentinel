---
name: idsr-measles
priority: critical
trigger: both
schedule: "0 6 * * 1"
event_filter:
  resource_type: Condition
  code_prefix: "B05"
requires:
  resources: [Condition, Immunization]
  llm: true
  adapter_features: [aggregate]
  min_data_window: 12w
goal: "Detect measles outbreaks and immunization coverage gaps"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  icd10_codes: [B05, B05.0, B05.1, B05.2, B05.3, B05.4, B05.8, B05.9]
---

# Measles Outbreak Detection (IDSR)

## Clinical Background

Measles (ICD-10: B05) is one of the most contagious viral diseases. Under IDSR, any single confirmed case warrants investigation, and clusters of ≥3 cases within 4 weeks indicate an outbreak. Immunization coverage below 95% creates outbreak susceptibility.

Key indicators:
- **Single case in zero-baseline area**: Any case where baseline is 0 → critical
- **Cluster threshold**: ≥3 cases in 4 weeks → critical
- **Doubling over baseline**: Cases > 2× baseline → high
- **Immunization gap correlation**: Low coverage + rising cases → elevated risk

## Reasoning Instructions

1. Check for any site transitioning from zero baseline to confirmed cases
2. Identify clusters (≥3 cases in 4 weeks at any site)
3. Compare against 12-week rolling baseline
4. Cross-reference with immunization coverage data
5. Note under-vaccinated populations if data available

## Rule-Based Fallback

- `count >= 1 AND baseline == 0` → CRITICAL
- `count >= 3` within 4 weeks → CRITICAL
- `count > baseline * 2` → HIGH
