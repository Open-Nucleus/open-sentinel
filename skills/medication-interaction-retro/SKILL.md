---
name: medication-interaction-retro
priority: high
trigger: event
event_filter:
  resource_type: MedicationRequest
requires:
  resources: [MedicationRequest]
  llm: true
goal: "Detect potentially dangerous drug-drug interactions among active medications"
max_reflections: 2
confidence_threshold: 0.7
metadata:
  category: medication-safety
---

# Retrospective Medication Interaction Detection

## Clinical Background

Drug-drug interactions (DDIs) are a significant cause of adverse events, especially in polypharmacy patients common in HIV/TB co-infection, hypertension with diabetes, and elderly patients on multiple chronic medications.

Key interaction pairs:
- Rifampicin + ART (efavirenz, nevirapine) — reduces ART efficacy
- Metformin + contrast agents — lactic acidosis risk
- Warfarin + NSAIDs — bleeding risk
- ACE inhibitors + potassium-sparing diuretics — hyperkalemia

## Reasoning Instructions

1. List all active medications per patient
2. Check all pairs against known interaction databases
3. Assess severity of each interaction (contraindicated, major, moderate)
4. Consider multi-drug interaction chains (3+ drugs)
5. Note time overlap of prescriptions

## Rule-Based Fallback

Hardcoded interaction pairs checked against all active medication combinations per patient.
