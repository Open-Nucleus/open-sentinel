---
name: idsr-ebola
priority: critical
trigger: both
schedule: "0 6 * * 1"
event_filter:
  resource_type: Condition
  code_prefix: "A98"
requires:
  resources: [Condition]
  llm: true
  adapter_features: [aggregate]
  min_data_window: 12w
goal: "Detect Ebola virus disease and hemorrhagic fever signals"
max_reflections: 3
confidence_threshold: 0.85
metadata:
  icd10_codes: [A98.3, A98.4]
---

# Ebola Virus Disease Detection (IDSR)

## Clinical Background

Ebola virus disease (ICD-10: A98.3 — Marburg, A98.4 — Ebola) is a viral hemorrhagic fever with high case fatality. Under IDSR, EVD has **zero tolerance** — any suspected case triggers an immediate public health emergency response. The broader A98 (other viral hemorrhagic fevers) category is also monitored as a sentinel signal.

Key indicators:
- **Zero tolerance for EVD**: Any A98.3 or A98.4 case → CRITICAL
- **Hemorrhagic fever sentinel**: ≥2 broader A98 cases with no confirmed EVD → HIGH (possible undiagnosed EVD)

## Reasoning Instructions

1. Flag ANY A98.3 or A98.4 case as CRITICAL immediately
2. Monitor broader hemorrhagic fever (A98) for sentinel signals
3. Consider geographic context and contact tracing implications
4. Cross-reference with other hemorrhagic fever patterns

## Rule-Based Fallback

- Any A98.3 or A98.4 → CRITICAL (zero tolerance)
- `hemorrhagic_count >= 2 AND evd_count == 0` → HIGH (sentinel signal)
