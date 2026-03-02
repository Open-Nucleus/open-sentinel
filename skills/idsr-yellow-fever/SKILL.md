---
name: idsr-yellow-fever
priority: critical
trigger: both
schedule: "0 6 * * 1"
event_filter:
  resource_type: Condition
  code_prefix: "A95"
requires:
  resources: [Condition]
  llm: true
  adapter_features: [aggregate]
  min_data_window: 12w
goal: "Detect any suspected yellow fever case for immediate investigation"
max_reflections: 2
confidence_threshold: 0.8
metadata:
  icd10_codes: [A95, A95.0, A95.1, A95.9]
---

# Yellow Fever Detection (IDSR)

## Clinical Background

Yellow fever (ICD-10: A95) is a mosquito-borne viral hemorrhagic fever. Under IDSR guidelines, yellow fever has **zero tolerance** — any single suspected case requires immediate notification and investigation. A95.0 is sylvatic (jungle), A95.1 is urban, A95.9 is unspecified.

Key indicators:
- **Zero tolerance**: Any suspected case → CRITICAL alert
- **No baseline needed**: Even one case in any context is notifiable

## Reasoning Instructions

1. Flag ANY suspected yellow fever case as CRITICAL immediately
2. Note geographic location for vector control response
3. Check for clustering across sites
4. Consider vaccination status if available

## Rule-Based Fallback

- `count >= 1` → CRITICAL (zero tolerance for any suspected case)
