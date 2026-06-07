# Data Quality Issues — Raw OMNY vs. Renderer Behavior

A running ledger of issues found during the renderer pilot and Allison/Engy reviews. Distinguishes:

- **Data-formatting issues** (root cause in OMNY raw data — we mitigate them downstream but the fix would ideally be upstream)
- **Renderer-side issues** (bugs or limitations in our pipeline code — not caused by OMNY)

For each issue: what it looks like, where it comes from, how we detect/handle it today, and what the long-term fix is.

---

## How to tell a data-formatting issue from a renderer issue

| Signal | Likely data issue | Likely renderer issue |
|---|---|---|
| The same pattern appears across many cases | ✓ | rarer |
| Issue is visible in raw parquet/CSV before any rendering | ✓ | no |
| The issue is specific to one prompt's truncation logic | rarer | ✓ |
| Issue is specific to one supplier (e.g., Northwell vs. Ochsner) | ✓ | rarer |
| Different cases produce different outputs from the same code path | ✓ | rarer |
| The fix lives in `_combine_date_time`, `_filter_note_rows_by_section`, etc. | mitigation, but root cause is data | ✓ |

**The simplest test**: open the raw parquet for a problematic encounter (`cache/<enc_id>_notes.parquet`). If the issue is visible there → data-formatting issue. If the data looks fine but the renderer's output is wrong → renderer issue.

---

## Part 1 — Data-formatting issues (root cause: OMNY)

### 1.1 Multi-supplier duplicate rows
**Pattern**: The same `(NOTE_ID, NOTE_TYPE, NOTE_TEXT)` row appears 3–5 times in `notes.csv`, originating from different data-supplier ingestions. Same content, different supplier_id.

**Example**: Case 1's H&P had each section ([HPI], [ASSESSMENT], etc.) duplicated 3× before our fix.

**How to identify in raw data**:
```python
notes.groupby(['NOTE_ID', 'NOTE_TYPE'])['NOTE_TEXT'].count().sort_values(ascending=False).head()
# If counts > 1, you have multi-supplier duplicates
```

**Renderer mitigation**: `df.drop_duplicates(subset=["NOTE_ID", "NOTE_TYPE", "NOTE_TEXT"])` in `_render_notes`, `render_single_note`, and `extract_section_text`.

**Long-term fix**: Upstream — OMNY should dedupe at ingestion or expose a "preferred supplier" view.

---

### 1.2 Duplicate paragraphs *within* a single `NOTE_TEXT` cell
**Pattern**: The same paragraph (sometimes identical, sometimes with placeholder names substituted) appears 3–6 times *inside* one row's NOTE_TEXT field, separated by spaces or newlines.

**Example**: Case 5 (hard/short) had identical 1,000-character paragraphs repeated 5× inside the ATTENDING COMMENTS cell — different placeholder patient names ("Sammy Correa", "Roland Nunez", "Osito Alexander") but otherwise identical text.

**How to identify in raw data**:
```python
notes['repeat_density'] = notes['NOTE_TEXT'].apply(
    lambda t: t.count(t[:100]) if isinstance(t, str) and len(t) > 100 else 1
)
notes[notes['repeat_density'] >= 3]  # Cells with repeating content
```

**Renderer mitigation**: Line-level dedupe inside each cell — added to `_render_notes` and `render_single_note`. Reduces token count ~25–30% on note prompts.

**Long-term fix**: Upstream — probably an OMNY ingestion bug. Worth raising.

---

### 1.3 Sentinel / placeholder dates (Jan 1, 2023-01-01, etc.)
**Pattern**: Discharge notes and end-of-life summaries often have NOTE_DATE = `2023-01-01 00:00` even though the encounter occurred months later. These pre-admission dates pass naive time-cutoff filters.

**Example**: Case 5 patient was admitted 2023-09-03 and died 2023-09-07, but the "DISCHARGE NOTE FOR THE EXPIRED PATIENT" had NOTE_DATE `2023-01-01`. Without filtering, that note (containing "compassionately extubated") leaked into the AE2 input.

**Allison's quote**: *"there's a lot of jan 1 dates, and these are definitely placeholder issues or dateshift/DEID issues. we'll have to work through these with omny eventually."*

**How to identify in raw data**:
```python
# Notes dated before the encounter started
notes_with_admit = notes.merge(encounters[['ENCOUNTER_ID', 'EN_START_DATE']], on='ENCOUNTER_ID')
notes_with_admit['EN_START_DATE'] = pd.to_datetime(notes_with_admit['EN_START_DATE'])
notes_with_admit['TS'] = pd.to_datetime(notes_with_admit['NOTE_DATE'])
sentinel = notes_with_admit[notes_with_admit['TS'] < notes_with_admit['EN_START_DATE']]
sentinel['NOTE_TYPE'].value_counts()  # Usually dominated by discharge note types
```

**Renderer mitigation** (two-layer):
1. Filter notes with `NOTE_DATE < EN_START_DATE` (sentinel-date guard)
2. Per Allison: exclude any `NOTE_TYPE` containing `DISCHARGE NOTE|DEATH NOTE|EXPIRED PATIENT|DECEASED` from input whenever time-truncation is active — regardless of date

**Long-term fix**: Upstream — OMNY needs to preserve real discharge timestamps. Or, build a more comprehensive sentinel-date detection (probably a list of suspicious dates: `2023-01-01`, `1900-01-01`, `1970-01-01`, etc.).

---

### 1.4 Unreliable "REASON FOR ADMISSION" field
**Pattern**: OMNY's `H&P ADULT - REASON FOR ADMISSION` section is often populated with **admission orders or process items**, not the actual chief complaint.

**Example** (Allison caught): Case 1 (CDC3E02F) had `REASON FOR ADMISSION = "serial abdominal exams"`. The actual CC was "33M presents following motorcycle crash" — buried in the HPI and confirmed by ICD code V87.7XXA (motor vehicle collision). Sonnet correctly extracted the crash; GPT matched our flawed structured-field GT and got a high score for the wrong reason.

**How to identify in raw data**: Examine `REASON FOR ADMISSION` values. Common red flags:
- "serial X" (process item)
- "observation" or "for monitoring"
- "consult" or "evaluation"
- "rule out X" (workup, not CC)

**Renderer mitigation**: S1 GT extractor now combines two sources:
1. HPI primary presenting sentence (regex matches "presents/complains/admitted/age-sex pattern")
2. The REASON FOR ADMISSION field as secondary

Both are shown to the judge.

**Long-term fix**: Don't trust any single OMNY field for the CC. Use multi-source: HPI first sentence + ICD codes (especially V/S/T trauma codes) + REASON FOR ADMISSION.

---

### 1.5 No labeled Chief Complaint section (~25% of cases)
**Pattern**: ~25% of H&P notes have **no section at all** that classifies as Chief Complaint or Reason for Admission. Cases from ASU transfers, NICU admissions, or certain templates.

**Example**: Case 1 in the original demo (encounter 2495058F) had 17 H&P sections — none of them CC.

**How to identify in raw data**: Check the H&P note's NOTE_TYPE values for any of: `CHIEF COMPLAINT`, `REASON FOR ADMISSION`. If none match, no CC section exists.

**Renderer mitigation**: HPI-first-sentence fallback (using "presents/complains/admitted/age-sex" pattern detection). Per Allison: *"HPI fallback logic checks out clinically to me."*

**Long-term fix**: Eventually have clinicians review/annotate these cases. For now, the fallback is acceptable.

---

### 1.6 Mixed types in lab/vital columns
**Pattern**: Columns like `LB_REF_HIGH` contain both numeric values and string values (e.g., `"5.4000"` as string alongside `5.4` as float). Pyarrow can't write these to parquet without coercion.

**How to identify in raw data**:
```python
labs['LB_REF_HIGH'].apply(type).value_counts()
# If you see both str and float, you have mixed types
```

**Renderer mitigation**: `build_cache.py` coerces all object-dtype columns to string before writing parquet.

**Long-term fix**: Upstream — OMNY should enforce consistent column types at ingestion.

---

### 1.7 Run-on paragraphs (no real newlines in NOTE_TEXT)
**Pattern**: Clinical narrative is stored as one long stream with double-space separators, not line-break-delimited text. Patterns anchored to `^...$` line boundaries miss most content.

**Example**: ATTENDING COMMENTS section contains "...soft nontender    Impression - left foot gas gangrene    P  admit to SICU  Continue IVAbx..." all on one line.

**How to identify in raw data**:
```python
notes['has_newlines'] = notes['NOTE_TEXT'].str.contains('\n', na=False)
notes['has_newlines'].sum() / len(notes)  # If low, content is run-on
```

**Renderer mitigation**: Our regex patterns use double-space lookarounds (`(?<=\s{2})...(?=\s{2,}|$)`) rather than line anchors.

**Long-term fix**: Upstream — OMNY could preserve original whitespace formatting.

---

### 1.8 Sections encoded in `NOTE_TYPE`, not `NOTE_TEXT`
**Pattern**: OMNY's `omny_notes_concatenated.csv` stores section labels in `NOTE_TYPE` after a `" - "` separator (e.g., `H&P ADULT - HISTORY OF PRESENT ILLNESS`), not as headers inside the text body.

This is actually a feature, not a bug — but it surprised our original design. Documented for clarity.

**Renderer mitigation**: `_classify_section()` parses the section label out of NOTE_TYPE. Word boundaries used to avoid false matches (e.g., `NSHPLAN_LIMITED_ENGLISH` ≠ "PLAN").

---

### 1.9 Narrative A&P embedded in non-A&P-labeled sections
**Pattern**: Clinicians often write the plan in narrative form inside the `ATTENDING COMMENTS` section (or even HPI) rather than the structured `ASSESSMENT` / `PLAN` sections. Section-based masking misses these.

**Example**: Case 1's H&P had `ATTENDING COMMENTS` containing "Impression - left foot gas gangrene with sepsis... admit to SICU, Continue IVAbx, Podiatry to perform amputation..." — clearly plan content, but not in a `PLAN` section.

**Renderer mitigation**: When within-note A&P masking is active (P1, P2, C2), regex redaction patterns catch narrative-form plan content (`Impression -`, `Plan:`, `Continue X`, `Hold Y`, `Admit to X`, `Disposition - X`, numbered/bulleted plan items). 5 of 6 obvious leaks caught; noun-headed actions ("Podiatry to perform amputation") survive.

**Long-term fix**: Clinicians don't follow section discipline. We accept some residual leakage; surface it during pilot review.

---

### 1.10 No primary discharge diagnosis flag
**Pattern**: Some cases have `diagnoses.csv` entries but no row with `DX_PRIMARY` in `{Y, YES, 1, TRUE}`. Our P3 GT extractor returns the first diagnosis in that case, which may not be clinically primary.

**Renderer mitigation**: Falls back to first diagnosis if no primary is flagged.

**Long-term fix**: Could use heuristics (highest specificity code, code matching admission HPI, etc.) or flag for clinician annotation.

---

### 1.11 Pediatric / NICU note kinds differ from adult
**Pattern**: Pediatric and NICU cases use different `NOTE_TYPE` prefixes:
- `H&P ADULT` → `H&P PEDIATRIC` or `H&P NICU.` (with trailing period)
- `PROGRESS NOTE ADULT` → `PROGRESS NOTE PEDS`

**Example**: Case 270C9600 was a NICU newborn (age 0, LOS 188d). Our H&P selector originally returned None.

**Renderer mitigation**: `_NOTE_KIND_FALLBACKS` chain: H&P adult → pediatric → NICU → generic H&P → admission note → ED provider note → progress note.

**Allison's direction**: *"I'm leaning towards just running the prompts on them for now, and we can always drop them or caveat them later, but it'll be good for meta to see how pediatric NICU records are different."*

---

### 1.12 ASU/transfer cases lack a fresh admission H&P
**Pattern**: Patients admitted via Ambulatory Surgery Unit or transferred from another facility don't have a new H&P. They have progress notes, transfer notes, or ED provider notes but no admission document.

**Example**: 4 of 10 medium/long pilot cases (F0DA196E, 4865A6F9, 81147F51, 270C9600).

**Renderer mitigation**: Same fallback chain extends to progress notes when no H&P type exists.

---

### 1.13 Massive lab volumes (28K+ labs)
**Pattern**: Hard/long and Meta-Hard/long cases can have 28,000+ lab results across their stay. Rendering all of them produces context that exceeds any model's window.

**Example**: One case rendered to 1.26M tokens for C8 (lab interpretation), exceeding Sonnet 4.6's 1M API cap.

**This is technically a real-data property, not a formatting bug** — but it forces renderer-side mitigation.

**Renderer mitigation today**: None — the call fails with "prompt is too long". Falls into next section.

**Long-term fix**: Per Allison's question: prompt-specific harness strategies. For C8, maybe only feed the labs and not the notes. For P10, recency truncation (last N days). See "Renderer-side issue 2.2" below.

---

### 1.14 Unicode artifacts and template field codes
**Pattern** (per SOW §5, not yet observed at scale in our pilot):
- Unicode artifacts: `→` (→) arrows, mojibake from table flattening
- Template field codes in NOTE_TYPE (e.g., `[NSPROPTRIGHTREPPHONE_GEN_A_NUR]`)

**Renderer mitigation today**: None implemented yet. Section codes are passed through as-is to the model.

**Long-term fix**: Add a normalization layer in the renderer that:
- Maps known Unicode escapes to their display form
- Unpacks template codes to legible labels (need an OMNY mapping table)

---

### 1.15 "REASON FOR ADMISSION" sometimes contains multiple unrelated entries
**Pattern**: Some cases have very short or single-word REASON FOR ADMISSION fields ("anemia", "GIB", "celluitis"). These are clinically reasonable abbreviations but the model's natural response ("symptomatic anemia with syncope and supratherapeutic INR") doesn't match well against the bare CC.

**Renderer mitigation**: Combining HPI + REASON FOR ADMISSION into a richer GT helps. Judges grade against either source.

---

### 1.16 Empty C8 ground truth (no abnormal labs flagged)
**Pattern**: ~25% of cases in our audit had no labs flagged as abnormal (`LB_ABN_RESULT` in `{H, L, HH, LL, CRITICAL, ABNORMAL, A}`). The C8 extractor returns empty.

**How to identify in raw data**:
```python
abn = labs[labs['LB_ABN_RESULT'].astype(str).str.upper().isin(['H','L','HH','LL','CRITICAL','ABNORMAL','A'])]
abn.empty  # True → no abnormal labs in source
```

**Long-term fix**: For C8, may need to:
- Use reference range computation (value outside `[ref_low, ref_high]`) instead of trusting the `LB_ABN_RESULT` flag
- Or exclude C8 from cases without flagged abnormals

---

## Part 2 — Renderer-side issues (root cause: our code)

These are issues with our pipeline that exist independent of OMNY data quality. Fixing them is on us.

### 2.1 Context overflow handling for `*_long` cells
**Issue**: Sonnet 4.6 API caps at 1M tokens. Cases with massive records (medium/long, hard/long) render past this and the API call fails.

**Current behavior**: API returns 400 "prompt is too long", task is marked errored, no partial result.

**Fix needed**: Implement per-prompt harness strategies (Allison's prompt). Options per prompt family:
- C8 (lab interp): drop notes, keep only labs + dx
- P10 (course prediction): recency truncation (last 14 days)
- P3/P4 (discharge Dx): already drops dx + only keeps H&P note (small)
- AE prompts: T-24h cutoff usually keeps these within budget

**Status**: Open. We log the failures and continue past them.

---

### 2.2 No prompt-specific harness strategies for context reduction
**Issue**: Renderer renders the same way for every prompt within a family. No automatic recency truncation or summarization for large records.

**Allison's question**: *"should we harness this somehow to reduce the record so it fits? maybe only feed the labs and not the notes for c8?"*

**Fix needed**: Per-prompt-family ablation defaults. For example:
- `C8` → auto-drop `notes`
- `P10` → auto-recency-truncate to last 14 days
- `S6–S10` → only render labs + the one source note

**Status**: Discussed but not built.

---

### 2.3 Single-threaded execution
**Issue**: `run_eval.py` makes LLM calls sequentially. Full benchmark = ~65 hours wall-clock.

**Fix needed**: Async batching across cases (Anthropic + OpenAI SDKs both support concurrent requests).

**Status**: Not built.

---

### 2.4 HPI extractor relies on `HPI:` marker
**Issue**: `_extract_hpi_cc_sentence` looks for an `HPI:` substring to find the start of HPI narrative. If the note doesn't have that marker (some pediatric templates), we fall back to whole-text scanning.

**Status**: Mitigated with fallback. Could be improved with NOTE_TYPE-based extraction since we already classify sections.

---

### 2.5 Section classifier is OMNY-specific
**Issue**: Section regex patterns (`SECTION_PATTERNS`) are hard-coded for OMNY's note conventions. If we onboard a new data partner (Segmed, GRN), the patterns won't transfer.

**Fix needed**: Per-supplier section classifier configuration, or a learned classifier.

**Status**: Acceptable for now since OMNY is our only source.

---

### 2.6 Ground-truth dedupe handles row-level + line-level, but not paraphrase-level
**Issue**: Two paragraphs with the same content but different patient placeholder names (OMNY's name injection: "Sammy Correa" → "Roland Nunez") will pass our dedupe because the strings differ.

**Status**: Open. Would need fuzzy-text dedupe (cosine similarity on embeddings, edit distance). Probably overkill for v1.

---

### 2.7 AE event detection is heuristic
**Issue**: `detect_ae_events` uses regex/CPT-code matching across three tables. Misses edge cases:
- Intubation procedures without standard CPT codes
- ICU transfers documented only in unstructured narrative
- Dialysis ordered but not administered (depends on which source you check)

**Status**: 76 of 180 Hard/Meta-Hard cases produce qualifying events. Some are likely missing detection.

---

### 2.8 No verification that the model's "1M context" actually works
**Issue**: We tried `claude-sonnet-4-6[1m]` model ID; it returned 404. Falling back to standard 200K Sonnet. Some `*_long` cases probably need a model with real 1M context.

**Status**: Open. Need to either get the 1M variant working or commit to context reduction for long cells.

---

## How issues surface in renderer outputs (diagnostic guide)

| What you see in output | Most likely root cause | Where to look |
|---|---|---|
| Ground truth is empty | Data issue 1.5 (no CC) or 1.16 (no abnormal labs) | Check raw note sections / lab abn flags |
| Same paragraph repeated 3–5× | Data issue 1.1 or 1.2 (multi-supplier dupes) | Check raw `notes.csv` row count for that NOTE_ID |
| "Discharge note" content in time-truncated input | Data issue 1.3 (sentinel date) | Check NOTE_DATE vs EN_START_DATE |
| "Plan content" in a non-Plan section | Data issue 1.9 (clinicians writing plan in ATTENDING COMMENTS) | Open the raw H&P, scan ATTENDING COMMENTS |
| Model gets discharge Dx that's "in the input" | Data issue: diagnoses table includes discharge Dx; **renderer fixed via auto-ablation for P3/P4** | Check that `_default_truncation_for("P3")` is applied |
| Render works for adult but empty for pediatric | Data issue 1.11 | Check NOTE_TYPE values for `PEDIATRIC` / `NICU` |
| API error "prompt is too long" | Renderer issue 2.1 (no context-reduction harness) | Need prompt-specific reduction strategy |
| Score is high but model response is obviously wrong | Renderer issue: GT extractor pulled the wrong field, or rubric criterion is wrong | Inspect the GT extraction code path |
| Same model produces different output for same input on rerun | Likely an LLM determinism issue, NOT renderer | Check temperature setting (should be 0.0) |

---

## Summary of what's been fixed vs what's open

### Data-quality issues mitigated in the renderer (✅)
- 1.1 Multi-supplier duplicates (row-level dedupe)
- 1.2 In-cell duplicate paragraphs (line-level dedupe)
- 1.3 Sentinel dates (filter + discharge-note exclusion)
- 1.4 Unreliable REASON FOR ADMISSION (HPI primary sentence + dual-source GT)
- 1.5 Empty CC (HPI-first-sentence fallback)
- 1.6 Mixed types (string coercion in cache)
- 1.7 Run-on paragraphs (double-space-based regex)
- 1.8 Sections in NOTE_TYPE (custom classifier)
- 1.9 Narrative A&P in non-A&P sections (regex redaction; 5/6 caught)
- 1.11 Pediatric/NICU note kinds (fallback chain)
- 1.12 ASU/transfer cases (fallback to progress notes)

### Data-quality issues open (⚠️)
- 1.10 Missing primary Dx flag (using first-row fallback, imperfect)
- 1.13 Massive lab volumes (no harness yet — see 2.1, 2.2)
- 1.14 Unicode artifacts + template codes (not implemented)
- 1.15 Sparse/single-word CC fields (mitigated by dual-source GT but bare CCs may still mismatch)
- 1.16 Empty C8 ground truth (no abnormal labs; could use computed ref-range check)

### Renderer-side issues open (⚠️)
- 2.1 Context overflow handling (logs failure, doesn't recover)
- 2.2 Per-prompt harness strategies (not built)
- 2.3 Single-threaded execution (not parallelized)
- 2.4 HPI extractor depends on `HPI:` marker (mitigated with fallback)
- 2.5 OMNY-specific section classifier (acceptable for current sources)
- 2.6 Paraphrase-level dedupe (not implemented; low priority)
- 2.7 AE event detection coverage (76/180 cases — some likely undercounted)
- 2.8 1M-context model variant unavailable on our API account

---

## Recommended priorities

For the next round of fixes, in order of impact:

1. **Build per-prompt context-reduction harness** (2.1 + 2.2) — unblocks *_long cells for C8, P10 prompts
2. **Add unicode + template code normalization** (1.14) — SOW §5 explicitly calls this out
3. **Improve AE event detection coverage** (2.7) — currently missing ~50% of potentially-eligible cases
4. **Parallelize the runner** (2.3) — needed before full 20K-case run

The data-formatting issues (Part 1) are largely handled or accepted as known limitations. The renderer-side issues (Part 2) are the active engineering work for the next sprint.
