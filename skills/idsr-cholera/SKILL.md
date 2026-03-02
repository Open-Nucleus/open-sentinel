---
name: idsr-cholera
priority: critical
trigger: both
schedule: "0 6 * * 1"
event_filter:
  resource_type: Condition
  code_prefix: "A00"
requires:
  resources: [Condition]
  llm: true
  adapter_features: [aggregate]
  min_data_window: 12w
goal: "Detect cholera outbreaks within 24 hours of first case"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  icd10_codes: [A00, A00.0, A00.1, A00.9]
---

# Cholera Outbreak Detection (IDSR)

## Clinical Background

Cholera (ICD-10: A00) is an acute diarrhoeal disease caused by Vibrio cholerae serogroups O1 and O139. Under WHO IDSR guidelines, a single confirmed case of cholera is a notifiable event requiring immediate investigation. Outbreaks can escalate within hours in settings with compromised water/sanitation.

Key surveillance indicators:
- **Zero-to-one transition**: Any case in a previously zero-baseline area is critical
- **Doubling time**: Case counts doubling over baseline within one week
- **Diarrhoeal co-occurrence**: Rising acute watery diarrhoea (A09) cases may precede confirmed cholera

## Reasoning Instructions

1. Compare current week case counts per site against the 12-week rolling baseline
2. Flag any site transitioning from 0 to ≥1 confirmed cholera case as CRITICAL
3. Flag any site with cases > 2× baseline as HIGH
4. Cross-reference with diarrhoeal disease trends (A0* codes) for early warning
5. Note geographic clustering of cases across sites
6. Consider seasonal and water/sanitation context if available

## Rule-Based Fallback

When LLM is unavailable, apply these deterministic thresholds:
- `baseline == 0 AND count >= 1` → CRITICAL alert
- `count > baseline * 2` → HIGH alert
- Otherwise → no alert
