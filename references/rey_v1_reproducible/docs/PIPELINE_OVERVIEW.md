# Project Bayes — Pipeline Overview

We're building the end-to-end pipeline that takes real patient records and produces a graded report card on how well an AI model handles clinical reasoning tasks. There are four major components.

---

## 1. Case Selection

We selected **360 real inpatient encounters** from three health systems:

- Northwell
- Ochsner
- St. Luke's

Cases are organized into a **4 × 3 evaluation grid**:

**4 complexity tiers:**
- easy
- medium
- hard
- meta hard

**3 length-of-stay buckets:**
- short (3–4 days)
- medium (4–6 days)
- long (7+ days)

This creates:
- **12 cells total**
- **30 cases per cell**

The goal is to test whether models behave differently across distinct clinical scenarios. A routine 4-day admission is fundamentally different from a prolonged ICU stay.

---

## 2. The Renderer

The raw OMNY data lives in structured tables:

- notes
- labs
- vitals
- medications
- procedures
- etc.

We do not feed those raw tables directly to the model.

Instead, we built a renderer that converts the structured data into clinician-readable text:

- notes are reconstructed by section
- labs become normalized tables with reference ranges and abnormal flags
- medications become timestamped bullet lists

The renderer also handles **answer hiding** for prediction tasks. There are two mechanisms:

### Within-note truncation
Used when the answer appears in the same note:
- remove sections like Assessment & Plan

### Time-based truncation
Used when the answer occurs later in the hospitalization:
- apply a strict timestamp cutoff across all data sources

This prevents information leakage into prediction prompts.

---

## 3. Prompts and Rubrics

The benchmark contains four prompt families.

### Structure
Extraction tasks:
- chief complaint
- lab values
- medications
- diagnoses

### Content
Reasoning tasks:
- summarize
- compare
- interpret
- differential diagnosis

### Prediction
The model predicts future information after part of the chart is hidden:
- discharge diagnosis
- imaging findings
- clinical course

### Adverse Event
Predict near-term deterioration:
- ICU transfer
- intubation
- dialysis initiation
- etc.

Each prompt has a detailed rubric:
- checklist-style evaluation
- binary criteria
- positive and negative point values

This allows structured grading of model outputs.

---

## 4. LLM Judges

After the model generates a response, two independent LLM judges evaluate it:

- **Claude Sonnet 4.6**
- **GPT-5.4**

Each judge grades every rubric criterion independently.

Using two judges gives us:
- inter-rater reliability measurement
- disagreement detection
- human-review escalation for ambiguous cases

Scores are aggregated into:
- per-case scores
- normalized 0–1 metrics
- disagreement statistics

---

## Bonus: Universal Criteria

In addition to prompt-specific rubrics, every response is graded on **five cross-cutting criteria**:

- hallucination
- unsafe recommendations
- task adherence
- terminology precision
- acknowledgment of uncertainty

This creates a benchmark-wide safety and reliability signal.

---

## Output Artifacts

Each (case, prompt) pair produces one row in a results table containing:

- patient ID
- complexity tier
- LOS bucket
- prompt type
- model response
- ground truth
- judge scores
- judge disagreement
- inference cost

We also produce a **criterion-level table**:
- one row per rubric criterion
- full score traceability
