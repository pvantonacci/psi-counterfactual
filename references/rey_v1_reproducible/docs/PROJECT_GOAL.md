# Project Bayes — Project Goal

## The goal, in three layers

### 1. The immediate deliverable (v1)

**Demonstrate that a clinical AI benchmark anchored on AHRQ Patient Safety Indicators can produce defensible, model-discriminating scores.**

That means:

- Score 2 frontier models (Opus 4.7, GPT-5.5) on 5 prompts × 145 real EHR encounters with 3 independent LLM judges
- Show the scoring is reliable (inter-judge κ at moderate-to-substantial)
- Show the benchmark *discriminates* (different models get different scores; complexity stratifies; etc.)
- Show the methodology survives scrutiny (look-ahead protections, structural ground truth, transparent failure modes)

The Wednesday meeting with Meta + Jason Wei is the v1 review.

### 2. The strategic goal (v2 — paper + Meta contract)

**Establish "verifier's rule applied to medicine" as a publishable benchmark methodology.**

Jason Wei's verifier's-rule (his 2025 blog post): *"the ease of training AI to solve a task is proportional to how verifiable the task is."*

Current healthcare LLM benchmarks (HealthBench, MedHELM) violate this — their ground truth is physician opinion, and physicians disagree. Borgohain & Mariathas (2026) showed 82% of HealthBench's variance is case-level ambiguity, not annotator disagreement. Adding more annotators doesn't fix it.

Project Bayes is the proposed fix: **engineer the verifier to be structural, not opinion-based.** AHRQ PSIs are federally-defined adverse hospital events with deterministic ICD-10 code definitions and present-on-admission rules. Same chart → same label, every time. That gives us:

- **High Diff (task is hard for models)**: the chart is long, narrative, full of distractors — even frontier models struggle
- **Low Disp (the answer is unambiguous)**: AHRQ's rule book applies identically to every case

The paper deliverable says: *here's how to build a healthcare LLM benchmark that survives verifier's rule, here's our methodology, here's what we found about frontier model capability on it.*

Co-authors: Engy Ziedan (Protege), Jason Wei (Meta), Allison Fox (clinical pipeline).

### 3. The big-picture goal (why this matters)

**Solve the verification problem in healthcare LLM evaluation.**

The core problem: in medicine, **physicians often disagree with each other** about correct diagnoses, optimal treatment plans, and appropriate next steps. So when an LLM gives a clinical answer:

- If the LLM and one physician disagree, who's wrong?
- If two physicians give different "ground truths," which one is correct?
- How do we measure model improvement when the evaluation target itself is noisy?

This is the **verification problem**: clinical AI eval is unreliable as long as the ground truth is opinion-based.

Project Bayes proposes a path through it by choosing tasks where:

- The ground truth is a structural property of the chart (the patient *did* or *did not* develop a coded adverse event)
- The labeling rules are federally published and deterministic (AHRQ PSIs)
- A model that gets the right answer is *verifiably* right, regardless of which clinician you ask

If this works, it becomes the template for: discharge dx prediction (P3), mortality prediction (P4), readmission prediction (P5), adverse event identification (AE1-3). All of these have structural ground truth that doesn't depend on physician opinion.

---

## The complexity grid

The framing we used in the meeting notes:

```
                  Easy to predict        Hard to predict
                  ─────────────────────────────────────
Easy to verify   |  Boring (saturated)  |  ★ SWEET SPOT
Hard to verify   |  Wasted compute      |  Unsolved medicine
```

Project Bayes targets the **upper-right cell**: hard-to-predict but easy-to-verify cases. PSIs sit exactly there. Most existing healthcare benchmarks are in the bottom-right (hard-to-verify because ground truth is contested) or the top-left (easy-to-predict because frontier models have saturated MedQA).

---

## Three concrete success criteria

If Project Bayes succeeds, we should be able to defend these three claims:

1. **"Our benchmark discriminates between frontier models"** — different models get measurably different scores on the same cases, beyond judge noise. (v1 shows this: Opus +0.03 on C8, ~0.40 vs ~0.05 spread on other prompts.)

2. **"Our ground truth is reproducible, not opinion-based"** — two careful reviewers running our pipeline on the same chart converge on the same label. (We're testing this: Cohen's κ between judges = 0.51 at criterion level is the relevant signal.)

3. **"Our cases are hard enough to matter and easy enough to measure"** — frontier models partial-pass with measurable room for improvement. (v1 shows this: mean scores 0.17–0.45 with non-saturating, non-bottomed distributions.)

---

## What the project is NOT

Just as important — clarifying what we're not trying to do:

- **Not** a comprehensive medical knowledge test (MedQA does that, and it's saturated)
- **Not** a physician replacement evaluation (no one is testing "should we replace doctors")
- **Not** a chart-to-diagnosis end-to-end test (we're testing specific narrow capabilities)
- **Not** a regulatory submission benchmark (different stakes, different requirements)
- **Not** a clinical decision support evaluation (we're not measuring patient outcomes)

The scope is narrow: **measure frontier LLM capability on clinical reasoning tasks where the ground truth is verifiable independent of physician opinion.** That's it.

---

## One-line summary

> Project Bayes is building a healthcare LLM benchmark on real EHR data that uses AHRQ Patient Safety Indicators as a structural verifier — same chart gives the same label every time. It targets the upper-right of the difficulty-verifiability grid: tasks that are hard for current frontier models but easy to verify with deterministic rules. The v1 deliverable validates the methodology on 5 prompts × 145 cases; the v2 paper takes it to 20K cases × 31 prompts with the AHRQ adverse-event prediction prompts as the headline experiment.

---

## Stakeholders

| Role | Person | What they own |
|---|---|---|
| Principal builder | Matt Turk (Protege Data Lab) | Engineering, evaluation pipeline, analysis |
| Project lead | Engy Ziedan (Protege Data Lab) | Strategy, methodology, paper co-authorship |
| Clinical labeling | Allison Fox | PSI labeling pipeline + case selection |
| Meta sponsor / collaborator | Jason Wei + Meta team | Funding, paper co-authorship, validation of verifier's-rule framing |
| Clinical reviewers (v2) | John, Miriam | Rubric review, ground truth validation |

---

## Where this fits in the broader research landscape

Project Bayes is **methodology-first** — the contribution isn't "we found that GPT-5.5 scores 0.47 on chief complaint extraction." The contribution is:

> "Here is a reproducible methodology for building healthcare LLM benchmarks with structural ground truth, validated on a 145-case PSI cohort across 5 prompts, scaling to 20K cases for v2."

Related work to position against in the paper:
- **HealthBench (OpenAI, 2025)** — physician-rubric eval, suffers from case-level ambiguity
- **MedHELM (Stanford CRFM, 2024)** — process-task benchmark, doesn't anchor on outcomes
- **MedQA / MedMCQA** — multiple choice, saturated by GPT-5.5
- **MedAlign (Stanford, 2023)** — closer to us in using real EHR data, but uses clinician preference judgments (not structurally verifiable)

Project Bayes's position: closer to MedAlign's data philosophy (real EHR) but with structural ground truth instead of clinician opinion.
