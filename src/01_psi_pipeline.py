"""
01_psi_pipeline.py
==================
Runs the PSI adverse-event detection pipeline locally.

Stages A+B run as SQL against Snowflake (same as the Snowpark notebook).
Stage C calls the Anthropic API (Claude) instead of Snowflake Cortex.

Run from project root:
    source PSI/bin/activate
    python src/01_psi_pipeline.py

Requires:
    pip install snowflake-connector-python anthropic pandas python-dotenv
    SF_USER and ANTHROPIC_API_KEY in .env (or exported in the shell)
"""

import json
import os
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
import pandas as pd
import snowflake.connector

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Snowflake connection
# ---------------------------------------------------------------------------

SNOWFLAKE_CONFIG = {
    "account":       os.environ.get("SF_ACCOUNT",   "APHHHWO-PROTEGE_PARTNER"),
    "user":          os.environ["SF_USER"],
    "authenticator": "externalbrowser",
    "role":          os.environ.get("SF_ROLE",      "READ_ONLY"),
    "warehouse":     os.environ.get("SF_WAREHOUSE", "READ_ONLY_2XL_WH"),
}

# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------

CONFIG = {
    "NOTES": "OMNY_PROTEGE.PUBLIC.OMNY_NOTES_CONCATENATED",
    "DIAG":  "OMNY_PROTEGE.PUBLIC.OMNY_DIAGNOSES_ENCOUNTERS",
    "PROC":  "OMNY_PROTEGE.PUBLIC.OMNY_PROCEDURES",
    "ENC":   "OMNY_REPL_ID.CUSTOM.ENCOUNTERS",

    "CSV_PATH": "data/raw/psi_inpatient_cases.csv",

    "CLAUDE_MODEL":    "claude-sonnet-4-6",
    "MAX_NOTE_CHARS":  12000,

    # Balanced case-control mode: 5 positives + 5 negatives per implemented PSI.
    # Positives  = Claude says YES + hospital-acquired + no exclusion + HIGH confidence.
    # Negatives  = same ICD match, Claude says NO + HIGH confidence.
    "BALANCED_MODE":   True,
    "CASES_PER_LABEL": 5,        # target per label per measure
    "IMPLEMENTED_ONLY": True,    # only run the 16 Part-1 PSIs

    # Default per-measure candidate cap. Override per measure in PER_MEASURE_LIMITS.
    "PER_MEASURE_LIMIT":  200,
    "CANDIDATE_LIMIT":    None,
    "OVERSAMPLE_FACTOR":  5,

    # Per-measure overrides — measures that already hit 5 positives stay at 50.
    "PER_MEASURE_LIMITS": {
        "PSI_06_IATROGENIC_PNEUMOTHORAX":    50,
        "PSI_15_ACCIDENTAL_PUNCTURE":        50,
        "PSI_18_OB_TRAUMA_INSTRUMENT":       50,
        "PSI_19_OB_TRAUMA_NO_INSTRUMENT":    50,
    },

    "REQUIRE_NOTE_REGEX": True,
    "MAX_WORKERS":        8,
}

# ---------------------------------------------------------------------------
# PSI definitions — copied verbatim from the Snowpark notebook
# ---------------------------------------------------------------------------

_JSON_SCHEMA = (
    '{\n'
    '  "psi_event_present": "YES|NO|UNCERTAIN",\n'
    '  "hospital_acquired_not_poa": "YES|NO|UNCERTAIN",\n'
    '  "is_exclusion": "YES|NO",\n'
    '  "exclusion_reason": "short phrase or empty",\n'
    '  "evidence_span": "<=200 char non-verbatim paraphrase of the sentence(s) that show it",\n'
    '  "confidence": "HIGH|MEDIUM|LOW",\n'
    '  "rationale": "10-30 words, non-verbatim"\n'
    '}'
)

_PROMPT_HEADER = (
    'You are a patient-safety chart abstractor reviewing one clinical note.\n'
    'Return ONLY valid JSON. No markdown, no commentary, no extra keys.\n\n'
    'General rules:\n'
    '- "psi_event_present" = YES only if the note documents that THIS specific '
    'complication actually occurred for this patient (not merely listed as a risk, '
    'a counseling topic, a family history, a rule-out that was negative, or boilerplate).\n'
    '- "hospital_acquired_not_poa" = YES only if the note indicates the event '
    'developed DURING this hospitalization/encounter, i.e. it was NOT present on '
    'admission and was NOT the reason the patient came in. If the complaint is '
    'described as the presenting/admitting problem, answer NO. If timing is unclear, '
    'answer UNCERTAIN.\n'
    '- "is_exclusion" = YES if any listed exclusion below is documented.\n'
    '- Never quote more than a short paraphrase in evidence_span.\n\n'
)


def _build_prompt(event_label, event_definition, exclusion_lines):
    excl = ''.join('  - ' + e + '\n' for e in exclusion_lines)
    return (
        _PROMPT_HEADER
        + 'Target complication: ' + event_label + '\n'
        + 'Definition of a positive event:\n  ' + event_definition + '\n\n'
        + 'Documented exclusions (if present, set is_exclusion=YES):\n' + excl + '\n'
        + 'Output JSON schema:\n' + _JSON_SCHEMA + '\n\n'
        + 'Note:\n<note>\n{NOTE_TEXT}\n</note>\n'
    )


PSI_DEFINITIONS = {

    "PSI_03_PRESSURE_ULCER": {
        "title": "Pressure Ulcer (Stage 3/4 or unstageable)",
        "cohort_gate": "Inpatient (ENCOUNTER_TYPE='HOSPITAL ENCOUNTER'), age>=18, LOS>=3 days",
        "icd10_regex": r"^L89\.",
        "cohort_note_regex": r"(?i)(pressure (ulcer|injury|sore)|decubitus|bed ?sore|stage (3|4|III|IV)|unstageable)",
        "classifier_prompt": _build_prompt(
            "Stage 3, stage 4, or unstageable pressure ulcer",
            "A stage 3/4 or unstageable pressure ulcer (or deep tissue injury that "
            "progressed) that developed during this admission.",
            [
                "ulcer or deep tissue injury was present on admission at the same anatomic site",
                "principal reason for admission was the pressure ulcer itself",
                "severe burns or exfoliative skin disorder present",
                "length of stay < 3 days",
                "obstetric or newborn encounter",
            ],
        ),
    },

    "PSI_04_FAILURE_TO_RESCUE": {
        "title": "Death among surgical inpatients with a serious treatable complication",
        "cohort_gate": "Surgical inpatient, age 18-89, who developed shock/arrest, sepsis, pneumonia, GI bleed, or DVT/PE",
        "icd10_regex": r"^(R57|I46|A40|A41|R65\.2|J1[2-8]|J69|K25|K26|K27|K28|K92\.[012]|I26|I82\.4|I82\.6|I82\.7)",
        "cohort_note_regex": r"(?i)(\bexpired\b|deceased|\bdeath\b|cardiac arrest|septic|pneumonia|GI bleed|hemorrhage|pulmonary embol|deep vein|\bDVT\b|\bPE\b)",
        "classifier_prompt": _build_prompt(
            "In-hospital death following a serious treatable complication",
            "Patient died during this admission AND had developed one of: shock/cardiac "
            "arrest, sepsis, pneumonia, GI hemorrhage/acute ulcer, or DVT/PE during the stay.",
            [
                "transferred to another acute care facility (not an in-hospital death)",
                "admitted from a hospice facility",
                "the complication was clearly present on admission",
            ],
        ),
    },

    "PSI_05_RETAINED_ITEM": {
        "title": "Retained surgical item / unretrieved device fragment",
        "cohort_gate": "Surgical/medical inpatient age>=18 or obstetric any age",
        "icd10_regex": r"^T81\.5",
        "cohort_note_regex": r"(?i)(retained (foreign|surgical|sponge|instrument|item)|unretrieved|device fragment|object left)",
        "classifier_prompt": _build_prompt(
            "Retained surgical item or unretrieved device fragment",
            "A foreign body / surgical item / device fragment unintentionally left in the "
            "patient after a procedure on this stay.",
            [
                "the retained item was present on admission (from a prior facility/procedure)",
                "newborn encounter",
            ],
        ),
    },

    "PSI_06_IATROGENIC_PNEUMOTHORAX": {
        "title": "Iatrogenic pneumothorax",
        "cohort_gate": "Surgical/medical inpatient, age>=18",
        "icd10_regex": r"^J95\.81",
        "cohort_note_regex": r"(?i)(pneumothorax|collapsed lung|iatrogenic)",
        "classifier_prompt": _build_prompt(
            "Iatrogenic pneumothorax",
            "A pneumothorax caused by a procedure/intervention (e.g. line placement, "
            "biopsy, thoracentesis) during this stay.",
            [
                "non-traumatic pneumothorax present on admission",
                "chest trauma, rib fractures, or traumatic pneumothorax",
                "expected after thoracic/pleural/lung surgery or biopsy or trans-pleural cardiac procedure",
                "pleural effusion as the driver",
                "obstetric encounter",
            ],
        ),
    },

    "PSI_07_CLABSI": {
        "title": "Central venous catheter-related bloodstream infection",
        "cohort_gate": "Surgical/medical inpatient age>=18 or obstetric any age, LOS>=2 days",
        "icd10_regex": r"^T80\.21",
        "cohort_note_regex": r"(?i)(central (line|venous|catheter)|CLABSI|CVC|PICC|bloodstream infection|line infection|bacteremia)",
        "classifier_prompt": _build_prompt(
            "Central line-associated bloodstream infection (CLABSI)",
            "A bloodstream infection attributed to a central venous catheter that "
            "developed during this stay.",
            [
                "the CLABSI was present on admission",
                "active cancer diagnosis",
                "immunocompromised state",
                "length of stay < 2 days",
            ],
        ),
    },

    "PSI_08_FALL_FRACTURE": {
        "title": "In-hospital fall-associated fracture (hip vs other)",
        "cohort_gate": "Surgical/medical inpatient, age>=18",
        "icd10_regex": r"^(S72|S32\.[0-8]|S22|S12|S02|S42|S52|S62|S82|S92)",
        "cohort_note_regex": r"(?i)(fell|fall|found on (the )?floor|fracture|broke|broken (hip|bone|wrist|arm|leg))",
        "classifier_prompt": _build_prompt(
            "In-hospital fall-associated fracture",
            "A fracture sustained from a fall that occurred DURING this hospitalization. "
            "Note whether it is a hip fracture or other fracture.",
            [
                "fracture was present on admission / was the reason for admission",
                "joint prosthesis-associated (periprosthetic) fracture",
                "obstetric encounter",
            ],
        ),
    },

    "PSI_09_POSTOP_HEMORRHAGE": {
        "title": "Postoperative hemorrhage or hematoma (with treatment procedure)",
        "cohort_gate": "Surgical inpatient age>=18 with an OR procedure",
        "icd10_regex": r"^(K91\.84|I97\.41|I97\.42|N99\.6|J95\.83|G97\.3|H59\.3|M96\.83|E36\.0)",
        "cohort_note_regex": r"(?i)(post[- ]?op(erative)? (bleed|hemorrhage|hematoma)|return to (the )?OR|reoperat|evacuat(e|ion) of hematoma|control of (bleeding|hemorrhage))",
        "classifier_prompt": _build_prompt(
            "Postoperative hemorrhage or hematoma requiring treatment",
            "Bleeding or hematoma after a surgery on this stay that REQUIRED a treatment "
            "procedure (return to OR, evacuation, control of hemorrhage).",
            [
                "hemorrhage/hematoma present on admission or principal diagnosis",
                "the only/first OR procedure WAS the treatment of the hemorrhage",
                "coagulation disorder, or medication-related coagulopathy present on admission",
                "thrombolytics given before/on the day of the treatment procedure",
                "obstetric encounter",
            ],
        ),
    },

    "PSI_10_POSTOP_AKI_DIALYSIS": {
        "title": "Postoperative acute kidney injury requiring dialysis",
        "cohort_gate": "ELECTIVE surgical inpatient age>=18 with an OR procedure",
        "icd10_regex": r"^N17\.",
        "cohort_note_regex": r"(?i)(acute (kidney|renal) (injury|failure)|\bAKI\b|\bARF\b|dialysis|\bCRRT\b|hemodialysis|renal replacement)",
        "classifier_prompt": _build_prompt(
            "Postoperative acute kidney injury requiring new dialysis",
            "Acute kidney failure that developed after an elective surgery on this stay AND "
            "required initiation of dialysis.",
            [
                "acute kidney failure present on admission",
                "dialysis or dialysis-access procedure before/on the day of the first OR procedure (chronic dialysis)",
                "CKD stage 5 or end-stage renal disease",
                "cardiac arrest, severe dysrhythmia, or shock",
                "principal diagnosis of urinary tract obstruction",
                "nephrectomy of a solitary kidney",
                "non-elective admission or obstetric encounter",
            ],
        ),
    },

    "PSI_11_POSTOP_RESP_FAILURE": {
        "title": "Postoperative respiratory failure",
        "cohort_gate": "ELECTIVE surgical inpatient age>=18",
        "icd10_regex": r"^(J95\.82|J96\.0|J96\.2)",
        "cohort_note_regex": r"(?i)(respiratory failure|reintubat|prolonged (mechanical )?ventilation|failed extubation|unplanned intubation|vent(ilator)? dependen)",
        "classifier_prompt": _build_prompt(
            "Postoperative respiratory failure",
            "Acute respiratory failure, prolonged mechanical ventilation, or reintubation "
            "after an elective surgery on this stay.",
            [
                "acute respiratory failure present on admission",
                "tracheostomy present on admission, or tracheostomy was the only/first OR procedure",
                "end-stage heart failure (principal or POA)",
                "malignant hyperthermia; neuromuscular or degenerative neuro disorder POA",
                "airway/laryngeal/pharyngeal/facial surgery, esophageal surgery, lung cancer procedure, or lung/heart transplant",
                "admission for treatment of a respiratory disease",
                "non-elective admission or obstetric encounter",
            ],
        ),
    },

    "PSI_12_PERIOP_PE_DVT": {
        "title": "Perioperative pulmonary embolism or proximal DVT",
        "cohort_gate": "Surgical inpatient age>=18 with an OR procedure",
        "icd10_regex": r"^(I26|I82\.4|I82\.6|I82\.7)",
        "cohort_note_regex": r"(?i)(pulmonary embol|PE\b|deep vein thromb|DVT|proximal (femoral|popliteal|iliac) (thrombus|clot))",
        "classifier_prompt": _build_prompt(
            "Perioperative PE or proximal DVT",
            "A pulmonary embolism or a PROXIMAL deep vein thrombosis that developed after a "
            "surgery on this stay.",
            [
                "PE or proximal DVT present on admission or principal diagnosis",
                "DVT is distal/calf-vein only (not proximal)",
                "heparin-induced thrombocytopenia",
                "vena cava interruption or thrombectomy before/same day as first OR procedure, or only OR procedure",
                "extracorporeal membrane oxygenation (ECMO)",
                "acute brain or spinal injury present on admission",
                "obstetric encounter",
            ],
        ),
    },

    "PSI_13_POSTOP_SEPSIS": {
        "title": "Postoperative sepsis",
        "cohort_gate": "ELECTIVE surgical inpatient age>=18",
        "icd10_regex": r"^(A40|A41|R65\.2|T81\.44)",
        "cohort_note_regex": r"(?i)(sepsis|septic shock|septicemia|bacteremia|SIRS|severe sepsis)",
        "classifier_prompt": _build_prompt(
            "Postoperative sepsis",
            "Sepsis that developed after an elective surgery on this stay.",
            [
                "sepsis present on admission or principal diagnosis",
                "any infection present on admission (principal, or secondary POA)",
                "first OR procedure on/after the 10th day of admission",
                "non-elective admission or obstetric encounter",
            ],
        ),
    },

    "PSI_14_WOUND_DEHISCENCE": {
        "title": "Postoperative abdominal wound dehiscence (with reclosure)",
        "cohort_gate": "Abdominopelvic surgery inpatient age>=18, LOS>=2 days",
        "icd10_regex": r"^T81\.3",
        "cohort_note_regex": r"(?i)(wound dehiscence|dehisced|wound disruption|fascial (dehiscence|disruption)|evisceration|reclosure|burst abdomen)",
        "classifier_prompt": _build_prompt(
            "Postoperative wound dehiscence with abdominal-wall reclosure",
            "Disruption of an internal/abdominal surgical wound after abdominopelvic surgery "
            "on this stay that required an abdominal-wall reclosure procedure.",
            [
                "wound disruption present on admission or principal diagnosis",
                "reclosure occurred on/before the date of the index abdominopelvic surgery",
                "length of stay < 2 days",
                "obstetric encounter",
            ],
        ),
    },

    "PSI_15_ACCIDENTAL_PUNCTURE": {
        "title": "Abdominopelvic accidental puncture or laceration",
        "cohort_gate": "Inpatient age>=18 with an abdominopelvic procedure + related follow-up procedure 1-30 days later",
        "icd10_regex": r"^(K91\.71|K91\.72|J95\.71|J95\.72|G97\.4|G97\.5|N99\.71|N99\.72|N99\.73|E36\.1|I97\.5|D78\.1|D78\.2)",
        "cohort_note_regex": r"(?i)(accidental (puncture|laceration)|inadvertent|incidental (enterotomy|cystotomy|durotomy)|serosal tear|injury to (the )?(spleen|bowel|bladder|ureter|vessel|diaphragm))",
        "classifier_prompt": _build_prompt(
            "Accidental puncture or laceration during an abdominopelvic procedure",
            "An accidental/inadvertent puncture or laceration of an organ or structure that "
            "occurred during an abdominopelvic procedure on this stay (often followed by a "
            "repair procedure).",
            [
                "the puncture/laceration was present on admission or principal diagnosis",
                "the injury was intentional/planned as part of the procedure",
                "obstetric encounter",
            ],
        ),
    },

    "PSI_17_BIRTH_TRAUMA": {
        "title": "Birth trauma - injury to neonate",
        "cohort_gate": "Newborn",
        "icd10_regex": r"^P1[0-5]",
        "cohort_note_regex": r"(?i)(birth (injury|trauma)|brachial plexus|\bErb('?s)?\b|clavic(le|ular) fracture|cephalohematoma|subgaleal|skull fracture|facial nerve (palsy|injury))",
        "classifier_prompt": _build_prompt(
            "Birth trauma injury to the neonate",
            "A birth-related injury to the newborn (e.g. brachial plexus injury, fracture, "
            "significant scalp/skull injury) documented for this delivery.",
            [
                "preterm infant with birth weight < 2000 g",
                "osteogenesis imperfecta",
                "injury is a minor/expected finding only (e.g. trivial caput) - judge severity",
            ],
        ),
    },

    "PSI_18_OB_TRAUMA_INSTRUMENT": {
        "title": "Obstetric trauma - vaginal delivery with instrument",
        "cohort_gate": "Instrument-assisted vaginal delivery",
        "icd10_regex": r"^O70\.[23]",
        "cohort_note_regex": r"(?i)(third|fourth|3rd|4th)[- ]?degree (perineal )?(laceration|tear)|(forceps|vacuum|instrument)[- ]?assisted",
        "classifier_prompt": _build_prompt(
            "Third or fourth degree obstetric laceration (instrument-assisted delivery)",
            "A 3rd or 4th degree perineal laceration sustained during an instrument-assisted "
            "(forceps/vacuum) vaginal delivery on this stay.",
            [
                "delivery was not vaginal (e.g. cesarean)",
                "laceration is 1st or 2nd degree only",
            ],
        ),
    },

    "PSI_19_OB_TRAUMA_NO_INSTRUMENT": {
        "title": "Obstetric trauma - vaginal delivery without instrument",
        "cohort_gate": "Spontaneous (non-instrument) vaginal delivery",
        "icd10_regex": r"^O70\.[23]",
        "cohort_note_regex": r"(?i)(third|fourth|3rd|4th)[- ]?degree (perineal )?(laceration|tear)",
        "classifier_prompt": _build_prompt(
            "Third or fourth degree obstetric laceration (spontaneous vaginal delivery)",
            "A 3rd or 4th degree perineal laceration during a spontaneous (non-instrument) "
            "vaginal delivery on this stay.",
            [
                "instrument-assisted delivery (belongs to PSI 18)",
                "delivery was not vaginal",
                "laceration is 1st or 2nd degree only",
            ],
        ),
    },
}

PROPOSED_2A_DEFINITIONS = {

    "PROP_ASPIRATION_PNEUMONIA": {
        "title": "Aspiration pneumonia (perioperative)",
        "cohort_gate": "Elective surgical inpatient; exclude seizure/trauma/overdose/poisoning; exclude OB",
        "icd10_regex": r"^J69\.",
        "cohort_note_regex": r"(?i)(aspirat(ion|ed)|aspiration pneumon|inhal(ation|ed) of (food|vomit|gastric))",
        "classifier_prompt": _build_prompt(
            "Perioperative aspiration pneumonia",
            "Aspiration pneumonia that developed perioperatively during this stay (e.g. "
            "intraoperatively or in recovery), not present on admission.",
            [
                "aspiration pneumonia present on admission",
                "principal diagnosis of seizure, trauma, drug overdose, or poisoning",
                "aspiration occurred late in an ICU course (less attributable) - note timing",
                "obstetric encounter",
            ],
        ),
    },

    "PROP_CABG_AFTER_PTCA": {
        "title": "CABG following PCI/PTCA in same stay",
        "cohort_gate": "Discharge with a PCI/PTCA procedure; CABG same day or next day",
        "icd10_regex": r"^(I21|I97\.7|I97\.89|T81\.71|T82\.8)",
        "cohort_note_regex": r"(?i)(emergen(t|cy) (CABG|bypass)|failed (PCI|angioplasty|stent)|coronary (perforation|dissection)|rescue bypass|crash(ed)? (on table|to (the )?OR))",
        "classifier_prompt": _build_prompt(
            "CABG following a failed/complicated PCI in the same stay",
            "A coronary artery bypass graft performed because a percutaneous coronary "
            "intervention (PCI/PTCA) on this stay failed or caused a complication.",
            [
                "the CABG was a planned/staged procedure, not a rescue",
                "CABG and PCI are unrelated encounters",
            ],
        ),
    },

    "PROP_INTRAOP_NERVE_INJURY": {
        "title": "Intraoperative nerve compression injury",
        "cohort_gate": "Surgical inpatient; exclude trauma, peripheral nerve disorders, dorsopathies",
        "icd10_regex": r"^(G56|G57|S14\.3|S44|S54|S64|S74|S84|G58\.9)",
        "cohort_note_regex": r"(?i)(nerve (injury|palsy|compression)|ulnar (neuropathy|palsy)|brachial plexus|positioning injury|peroneal (palsy|nerve)|foot drop)",
        "classifier_prompt": _build_prompt(
            "Intraoperative peripheral nerve compression/positioning injury",
            "A peripheral nerve injury (e.g. ulnar, brachial plexus, peroneal) attributed to "
            "patient positioning/handling during a procedure on this stay.",
            [
                "nerve injury/disorder present on admission",
                "principal diagnosis of trauma",
                "pre-existing peripheral neuropathy or dorsopathy explains it",
            ],
        ),
    },

    "PROP_MALIGNANT_HYPERTHERMIA": {
        "title": "Malignant hyperthermia",
        "cohort_gate": "Surgical inpatient (anesthesia); exclude OB",
        "icd10_regex": r"^T88\.3",
        "cohort_note_regex": r"(?i)(malignant hyperthermia|dantrolene|MH (crisis|episode|reaction)|hyperthermi.* anesthesi)",
        "classifier_prompt": _build_prompt(
            "Malignant hyperthermia reaction to anesthesia",
            "A malignant hyperthermia event triggered by anesthesia during a procedure on "
            "this stay (often treated with dantrolene).",
            [
                "documented only as a family/personal history risk, no actual event",
                "obstetric encounter",
            ],
        ),
    },

    "PROP_POSTOP_AMI": {
        "title": "Postoperative acute myocardial infarction",
        "cohort_gate": "Elective NON-cardiac surgical inpatient; exclude cardiac surgery, OB",
        "icd10_regex": r"^I21\.",
        "cohort_note_regex": r"(?i)(myocardial infarction|\bNSTEMI\b|\bSTEMI\b|troponin (rise|positive|elevat)|post[- ]?op(erative)? (\bMI\b|infarct)|\bacute MI\b)",
        "classifier_prompt": _build_prompt(
            "Postoperative acute myocardial infarction",
            "An acute MI that developed after an elective non-cardiac surgery on this stay.",
            [
                "AMI present on admission or principal diagnosis",
                "patient underwent cardiac surgery (excluded population)",
                "non-elective admission or obstetric encounter",
            ],
        ),
    },

    "PROP_POSTOP_IATRO_CARDIAC": {
        "title": "Postoperative iatrogenic cardiac complication",
        "cohort_gate": "Surgical inpatient; exclude OB",
        "icd10_regex": r"^(I97\.7|I97\.71|I97\.710|I97\.711|I97\.790|I97\.791|I97\.89)",
        "cohort_note_regex": r"(?i)(iatrogenic|intraoperative|post[- ]?procedur(e|al)) (cardiac|heart|cardiogenic)|procedure[- ]?(induced|related) (cardiac|arrhythmia)",
        "classifier_prompt": _build_prompt(
            "Postoperative iatrogenic cardiac complication",
            "A cardiac complication (e.g. intra/post-procedural cardiac arrest, dysfunction) "
            "caused by a procedure during this stay.",
            [
                "the cardiac condition was present on admission",
                "obstetric encounter",
            ],
        ),
    },

    "PROP_POSTOP_IATRO_NEURO": {
        "title": "Postoperative iatrogenic nervous-system complication",
        "cohort_gate": "Surgical inpatient; exclude OB",
        "icd10_regex": r"^(G97\.3|G97\.4|G97\.5|G97\.81|G97\.82)",
        "cohort_note_regex": r"(?i)(iatrogenic|intraoperative|post[- ]?procedur(e|al)) (nerv|neuro|CNS|cerebral|spinal)|procedure[- ]?(induced|related) (stroke|neuro)",
        "classifier_prompt": _build_prompt(
            "Postoperative iatrogenic nervous-system complication",
            "A nervous-system complication (e.g. intra/post-procedural CNS injury, hemorrhage, "
            "or infarction) caused by a procedure during this stay.",
            [
                "the neurological condition was present on admission",
                "obstetric encounter",
            ],
        ),
    },

    "PROP_REOPEN_SURGICAL_SITE": {
        "title": "Unplanned reopening of surgical site",
        "cohort_gate": "Surgical inpatient; reopening >=1 day after index procedure",
        "icd10_regex": r"^(T81\.3|T81\.4|T81\.89|T81\.9)",
        "cohort_note_regex": r"(?i)(return(ed)? to (the )?OR|reexplorat|re[- ]?operat|reopen(ing|ed)? of (the )?(wound|surgical site)|take[- ]?back|washout)",
        "classifier_prompt": _build_prompt(
            "Unplanned reopening of a surgical site",
            "An unplanned return to the operating room / reopening of a surgical site at least "
            "one day after the index procedure on this stay, due to a complication.",
            [
                "the reopening was a planned/staged procedure",
                "reopening for failed hardware removal or other non-complication reason",
                "patient is immunocompromised and reopening is for an expected wound issue",
            ],
        ),
    },

    "PROP_SUTURE_OF_LACERATION": {
        "title": "Suture of an accidental laceration during a procedure",
        "cohort_gate": "Surgical inpatient; exclude foreign body, trauma, OB",
        "icd10_regex": r"^(K91\.71|K91\.72|N99\.71|N99\.72|J95\.71|J95\.72|H59\.3)",
        "cohort_note_regex": r"(?i)(accidental laceration|inadvertent (injury|laceration)|repair of (iatrogenic|accidental)|serosal tear repaired|incidental (enterotomy|cystotomy))",
        "classifier_prompt": _build_prompt(
            "Repair (suture) of an accidental intra-procedure laceration",
            "An accidental laceration that occurred during a procedure on this stay and was "
            "repaired/sutured (same day or later).",
            [
                "laceration present on admission (trauma)",
                "any foreign-body diagnosis present",
                "the laceration was trivial / expected for the procedure - judge significance",
                "obstetric encounter",
            ],
        ),
    },

    "PROP_OB_WOUND_CESAREAN": {
        "title": "Obstetric wound complication - cesarean",
        "cohort_gate": "Cesarean delivery",
        "icd10_regex": r"^O90\.0",
        "cohort_note_regex": r"(?i)(c[- ]?section|cesarean).{0,40}(wound|incision).{0,20}(disrupt|dehisce|infect|breakdown)|disruption of cesarean (wound|incision)",
        "classifier_prompt": _build_prompt(
            "Cesarean wound complication (disruption/dehiscence)",
            "A disruption, dehiscence, or significant complication of the cesarean delivery "
            "wound on this stay.",
            [
                "wound complication present on admission",
                "delivery was not a cesarean",
            ],
        ),
    },

    "PROP_OB_WOUND_VAGINAL": {
        "title": "Obstetric wound complication - vaginal (perineal)",
        "cohort_gate": "Vaginal delivery",
        "icd10_regex": r"^(O90\.1|O71\.7)",
        "cohort_note_regex": r"(?i)(perineal (wound|laceration).{0,20}(disrupt|dehisce|breakdown)|vulval? hematoma|perineal hematoma|episiotomy (dehiscence|breakdown))",
        "classifier_prompt": _build_prompt(
            "Perineal/vaginal delivery wound complication",
            "A perineal wound disruption or vulvar/perineal hematoma after a vaginal delivery "
            "on this stay.",
            [
                "complication present on admission",
                "delivery was a cesarean (belongs to the cesarean measure)",
            ],
        ),
    },

    "PROP_OTHER_OB_COMPLICATIONS": {
        "title": "Other obstetric complications",
        "cohort_gate": "All deliveries",
        "icd10_regex": r"^O7[0-5]",
        "cohort_note_regex": r"(?i)(obstetric (complication|injury)|postpartum (complication|hemorrhage)|retained placenta|uterine inversion)",
        "classifier_prompt": _build_prompt(
            "Other significant obstetric complication",
            "A significant obstetric complication during delivery on this stay (heterogeneous: "
            "e.g. severe postpartum hemorrhage, retained placenta, uterine inversion).",
            [
                "complication present on admission",
                "complication is minor/expected - judge significance",
            ],
        ),
    },

    "PROP_POSTPARTUM_UTI": {
        "title": "Post-partum urinary tract infection",
        "cohort_gate": "All deliveries",
        "icd10_regex": r"^O86\.2",
        "cohort_note_regex": r"(?i)(post[- ]?partum|puerperal).{0,30}(UTI|urinary (tract )?infection|cystitis|pyelonephritis)",
        "classifier_prompt": _build_prompt(
            "Post-partum urinary tract infection",
            "A urinary tract infection that developed post-partum during this delivery stay.",
            [
                "UTI / infection present on admission",
                "infection of the amniotic cavity (different entity)",
            ],
        ),
    },
}

PROPOSED_2B_DEFINITIONS = {

    "REJ_POSTOP_PNEUMONIA": {
        "title": "Postoperative pneumonia",
        "cohort_gate": "Surgical inpatient; exclude respiratory MDC, immunocompromised, cancer, OB",
        "icd10_regex": r"^(J1[3-8]|J15|J16|J18)",
        "cohort_note_regex": r"(?i)(pneumonia|HAP|hospital[- ]acquired pneumonia|VAP|ventilator[- ]associated|new (infiltrate|consolidation))",
        "classifier_prompt": _build_prompt(
            "Postoperative (hospital-acquired) pneumonia",
            "Bacterial/hospital-acquired pneumonia that developed after a surgery on this stay.",
            [
                "pneumonia present on admission",
                "admission primarily for a respiratory condition",
                "active cancer or immunocompromised state",
                "obstetric encounter",
            ],
        ),
    },

    "REJ_DOSAGE_COMPLICATION": {
        "title": "Medication dosage complication / misadventure",
        "cohort_gate": "All inpatients",
        "icd10_regex": r"^(T36|T37|T38|T39|T4[0-9]|T50|Y63)",
        "cohort_note_regex": r"(?i)(wrong (dose|dosage|medication|drug)|overdose (given|administered)|medication error|dosing error|adverse drug (event|reaction)|ADE\b|under[- ]?dose|omitted (dose|medication))",
        "classifier_prompt": _build_prompt(
            "Medication dosage complication / administration error",
            "A complication from a medication dosing/administration error during this stay "
            "(wrong dose, wrong dilution, omitted necessary drug, radiation overdose, etc.).",
            [
                "the adverse drug effect was present on admission (home-med related)",
                "documented only as a counseling topic or general risk, no actual event",
            ],
        ),
    },

    "REJ_IATROGENIC_HYPOTENSION": {
        "title": "Iatrogenic / postprocedural hypotension",
        "cohort_gate": "All inpatients",
        "icd10_regex": r"^(I95\.2|I95\.81|I95\.89)",
        "cohort_note_regex": r"(?i)(iatrogenic hypotension|post[- ]?procedur(e|al) hypotension|drug[- ]?induced hypotension|hypotension (after|following) (procedure|anesthesia))",
        "classifier_prompt": _build_prompt(
            "Iatrogenic / procedure-related hypotension",
            "Clinically significant hypotension caused by a drug or procedure during this stay.",
            [
                "hypotension present on admission",
                "hypotension from the patient's underlying disease (e.g. sepsis, bleeding) rather than iatrogenic",
            ],
        ),
    },

    "REJ_CDIFF": {
        "title": "Intestinal infection due to C. difficile",
        "cohort_gate": "All inpatients; exclude trauma, OB",
        "icd10_regex": r"^A04\.7",
        "cohort_note_regex": r"(?i)(c\.?\s?diff|clostridi(um|oides) difficile|pseudomembranous colitis|CDI\b|positive (C\.?\s?diff|toxin))",
        "classifier_prompt": _build_prompt(
            "Hospital-onset Clostridioides difficile infection",
            "A C. difficile intestinal infection that developed during this stay "
            "(hospital-onset), typically after antibiotics.",
            [
                "C. difficile infection present on admission",
                "principal diagnosis of trauma",
                "obstetric encounter",
            ],
        ),
    },

    "REJ_POSTOP_IATRO_DIGESTIVE": {
        "title": "Postoperative iatrogenic digestive complication",
        "cohort_gate": "Surgical inpatient",
        "icd10_regex": r"^K91\.",
        "cohort_note_regex": r"(?i)(post[- ]?op(erative)?|iatrogenic|post[- ]?procedur(e|al)) (ileus|GI|digestive|intestinal|anastomotic)|anastomotic (leak|failure)",
        "classifier_prompt": _build_prompt(
            "Postoperative iatrogenic digestive-system complication",
            "A digestive-system complication (e.g. postoperative ileus, anastomotic leak) "
            "caused by a procedure during this stay.",
            ["the digestive condition was present on admission"],
        ),
    },

    "REJ_POSTOP_IATRO_RESPIRATORY": {
        "title": "Postoperative iatrogenic respiratory complication",
        "cohort_gate": "Surgical inpatient",
        "icd10_regex": r"^J95\.",
        "cohort_note_regex": r"(?i)(post[- ]?op(erative)?|iatrogenic|post[- ]?procedur(e|al)) (respiratory|pulmonary|atelectas)|procedure[- ]?related (respiratory|pulmonary)",
        "classifier_prompt": _build_prompt(
            "Postoperative iatrogenic respiratory-system complication",
            "A respiratory-system complication caused by a procedure during this stay "
            "(excluding the more specific PSI 06/11 events).",
            ["the respiratory condition was present on admission"],
        ),
    },

    "REJ_POSTOP_IATRO_URINARY": {
        "title": "Postoperative iatrogenic urinary complication",
        "cohort_gate": "Surgical inpatient",
        "icd10_regex": r"^N99\.",
        "cohort_note_regex": r"(?i)(post[- ]?op(erative)?|iatrogenic|post[- ]?procedur(e|al)) (urinary|bladder|ureter|renal)|procedure[- ]?related (urinary|bladder)",
        "classifier_prompt": _build_prompt(
            "Postoperative iatrogenic urinary-system complication",
            "A urinary-system complication caused by a procedure during this stay.",
            ["the urinary condition was present on admission"],
        ),
    },

    "REJ_POSTOP_IATRO_VASCULAR": {
        "title": "Postoperative iatrogenic peripheral vascular complication",
        "cohort_gate": "Surgical inpatient",
        "icd10_regex": r"^I97\.",
        "cohort_note_regex": r"(?i)(post[- ]?op(erative)?|iatrogenic|post[- ]?procedur(e|al)) (vascular|arterial|venous)|procedure[- ]?related (vascular|arterial)",
        "classifier_prompt": _build_prompt(
            "Postoperative iatrogenic peripheral vascular complication",
            "A peripheral vascular complication caused by a procedure during this stay.",
            ["the vascular condition was present on admission"],
        ),
    },

    "REJ_OB_THROMBOSIS_EMBOLISM": {
        "title": "Obstetric thrombosis or embolism",
        "cohort_gate": "All deliveries",
        "icd10_regex": r"^(O22\.[23]|O87\.[019]|O88)",
        "cohort_note_regex": r"(?i)(post[- ]?partum|puerperal|obstetric).{0,30}(thromb|embol|DVT|PE)|amniotic fluid embol",
        "classifier_prompt": _build_prompt(
            "Obstetric (postpartum) thrombosis or embolism",
            "A venous thrombosis or embolism arising in the obstetric/postpartum period on "
            "this delivery stay.",
            ["thrombosis/embolism present on admission"],
        ),
    },

    "REJ_PUERPERAL_INFECTION": {
        "title": "Major puerperal infection",
        "cohort_gate": "All deliveries; exclude amniotic-cavity infection POA",
        "icd10_regex": r"^O85",
        "cohort_note_regex": r"(?i)(puerperal (sepsis|infection|fever)|endometritis|post[- ]?partum (sepsis|infection))",
        "classifier_prompt": _build_prompt(
            "Major puerperal infection",
            "A major puerperal infection (e.g. puerperal sepsis, endometritis) that developed "
            "during this delivery stay.",
            [
                "infection present on admission",
                "antepartum infection of the amniotic cavity",
            ],
        ),
    },
}

ALL_DEFINITIONS = {}
ALL_DEFINITIONS.update({k: dict(v, part="1_implemented")   for k, v in PSI_DEFINITIONS.items()})
ALL_DEFINITIONS.update({k: dict(v, part="2A_experimental") for k, v in PROPOSED_2A_DEFINITIONS.items()})
ALL_DEFINITIONS.update({k: dict(v, part="2B_rejected")     for k, v in PROPOSED_2B_DEFINITIONS.items()})


def _active_definitions() -> dict:
    """Returns the subset of ALL_DEFINITIONS to run, based on CONFIG."""
    if CONFIG.get("IMPLEMENTED_ONLY"):
        return {k: v for k, v in ALL_DEFINITIONS.items() if v["part"] == "1_implemented"}
    return ALL_DEFINITIONS

# ---------------------------------------------------------------------------
# SQL helpers — unchanged from the notebook (produce valid Snowflake SQL)
# ---------------------------------------------------------------------------

def _sql_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def _regex_predicate(column: str, pattern: str) -> str:
    case_insensitive = False
    if pattern.startswith("(?i)"):
        case_insensitive = True
        pattern = pattern[4:]
    flags = ("i" if case_insensitive else "c") + "s"
    esc = _sql_escape(pattern)
    return f"REGEXP_INSTR({column}, '{esc}', 1, 1, 0, '{flags}') > 0"


def build_candidates_sql() -> str:
    """Stages A+B: ICD-10 regex + note-text regex, with per-measure and overall caps."""
    per       = CONFIG.get("PER_MEASURE_LIMIT")
    overall   = CONFIG.get("CANDIDATE_LIMIT")
    oversample = CONFIG.get("OVERSAMPLE_FACTOR", 5)

    active     = _active_definitions()
    overrides  = CONFIG.get("PER_MEASURE_LIMITS", {})

    def _per_measure_limit(code):
        return overrides.get(code, per)

    dx_blocks = []
    for code, d in active.items():
        dx_blocks.append(f"""
    SELECT
        d.ENCOUNTER_ID,
        '{code}'                          AS PSI_CODE,
        '{_sql_escape(d["title"])}'       AS PSI_TITLE,
        '{d["part"]}'                     AS PART,
        ANY_VALUE(d.AGE)                  AS AGE,
        ANY_VALUE(d.SEX)                  AS SEX,
        ANY_VALUE(d.ENCOUNTER_TYPE)       AS ENCOUNTER_TYPE,
        LISTAGG(DISTINCT d.DIAGNOSIS_CODE, ', ')
            WITHIN GROUP (ORDER BY d.DIAGNOSIS_CODE) AS MATCHED_DX_CODES
    FROM {CONFIG["DIAG"]} d
    JOIN {CONFIG["ENC"]} e ON e.ENCOUNTER_ID = d.ENCOUNTER_ID
    WHERE {_regex_predicate("d.DIAGNOSIS_CODE", d["icd10_regex"])}
      AND (
          d.ENCOUNTER_TYPE = 'HOSPITAL ENCOUNTER'
          OR e.EN_SETTING = 'INPATIENT'
          OR e.EN_TYPE ILIKE '%INPATIENT%'
          OR e.EN_SETTING_DET = 'INPATIENT'
      )
    GROUP BY d.ENCOUNTER_ID""")

    flagged_dx = "    UNION ALL".join(dx_blocks)

    # Build per-measure oversample cap as a CASE expression.
    oversample_cases = "\n".join(
        f"        WHEN '{code}' THEN {int(_per_measure_limit(code)) * int(oversample)}"
        for code in active
    )
    default_oversample = int(per or 0) * int(oversample)

    dx_sampled = f"""SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY PSI_CODE ORDER BY RANDOM()) AS _dxrn
    FROM (
{flagged_dx}
    )
)
WHERE _dxrn <= CASE PSI_CODE
{oversample_cases}
        ELSE {default_oversample}
    END"""

    note_when = []
    for code, d in active.items():
        note_rgx = d.get("cohort_note_regex")
        if CONFIG["REQUIRE_NOTE_REGEX"] and note_rgx:
            pred = _regex_predicate("n.NOTE_TEXT", note_rgx)
            note_when.append(f"        WHEN s.PSI_CODE = '{code}' THEN {pred}")
        else:
            note_when.append(f"        WHEN s.PSI_CODE = '{code}' THEN TRUE")
    note_case = "\n".join(note_when)

    joined = f"""SELECT
    n.ENCOUNTER_ID,
    s.PSI_CODE, s.PSI_TITLE, s.PART,
    n.NOTE_ID, n.NOTE_DATE, n.NOTE_TYPE, n.NOTE_TEXT,
    s.MATCHED_DX_CODES, s.AGE, s.SEX, s.ENCOUNTER_TYPE
FROM (
{dx_sampled}
) s
JOIN {CONFIG["NOTES"]} n
  ON UPPER(n.ENCOUNTER_ID) = UPPER(s.ENCOUNTER_ID)
WHERE CASE
{note_case}
        ELSE TRUE END
QUALIFY ROW_NUMBER() OVER
    (PARTITION BY s.PSI_CODE, n.ENCOUNTER_ID ORDER BY n.NOTE_DATE DESC) = 1"""

    final_cases = "\n".join(
        f"        WHEN '{code}' THEN {int(_per_measure_limit(code))}"
        for code in active
    )
    default_final = int(per or 0)

    final = f"""SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY PSI_CODE ORDER BY RANDOM()) AS _rn
    FROM (
{joined}
    )
)
WHERE _rn <= CASE PSI_CODE
{final_cases}
        ELSE {default_final}
    END"""
    if overall:
        final += f"\nQUALIFY ROW_NUMBER() OVER (ORDER BY _rn, RANDOM()) <= {int(overall)}"
    return final


# ---------------------------------------------------------------------------
# Stage C — Anthropic chart review
# ---------------------------------------------------------------------------

def _classify_row(client: anthropic.Anthropic, row: dict) -> dict:
    """Call Claude to review one candidate note. Returns the row enriched with classifier fields."""
    psi_code = row["PSI_CODE"]
    note_text = (row["NOTE_TEXT"] or "")[:CONFIG["MAX_NOTE_CHARS"]]
    prompt = ALL_DEFINITIONS[psi_code]["classifier_prompt"].replace("{NOTE_TEXT}", note_text)

    for attempt in range(4):
        try:
            msg = client.messages.create(
                model=CONFIG["CLAUDE_MODEL"],
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            # Strip markdown fences if the model wraps output in ```json ... ```
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw.strip())
            return {**row, **{k.upper(): str(v) for k, v in parsed.items()}, "RAW_JSON": raw}
        except anthropic.RateLimitError:
            wait = 20 * (attempt + 1)
            print(f"  Rate limit hit — waiting {wait}s ...", flush=True)
            time.sleep(wait)
        except (json.JSONDecodeError, Exception) as e:
            if attempt == 3:
                print(f"  Classification failed for {psi_code}/{row.get('NOTE_ID')}: {e}")
                return {**row, "PSI_EVENT_PRESENT": "ERROR", "RAW_JSON": str(e)}
            time.sleep(2 * (attempt + 1))

    return {**row, "PSI_EVENT_PRESENT": "ERROR", "RAW_JSON": "max retries exceeded"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def connect() -> snowflake.connector.SnowflakeConnection:
    for _wb in [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ]:
        if os.path.exists(_wb):
            webbrowser.register("wsl-windows-browser", None,
                                webbrowser.BackgroundBrowser(_wb), preferred=True)
            break
    print("Opening browser for SSO authentication ...")
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    print("Connected.\n")
    return conn


def main() -> pd.DataFrame:
    out_path = Path(CONFIG["CSV_PATH"])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    balanced   = CONFIG.get("BALANCED_MODE", False)
    n_per_label = CONFIG.get("CASES_PER_LABEL", 5)
    active_keys = set(_active_definitions().keys())

    print(f">> Model: {CONFIG['CLAUDE_MODEL']}  |  "
          f"measures={len(active_keys)}  |  "
          f"PER_MEASURE_LIMIT={CONFIG.get('PER_MEASURE_LIMIT')}  |  "
          f"mode={'balanced ±' + str(n_per_label) if balanced else 'flag-only'}")

    # ── Stage A+B: pull candidates from Snowflake ──────────────────────────
    conn = connect()
    try:
        print(">> Stage A+B: ICD-10 regex + note-text filter against Snowflake ...")
        sql = build_candidates_sql()
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
        print("   Snowflake connection closed.")

    candidates = pd.DataFrame(rows, columns=cols)
    print(f"   → {len(candidates):,} candidates across {candidates['PSI_CODE'].nunique()} measures")

    if candidates.empty:
        print("   No candidates found — check table names and regex patterns.")
        candidates.to_csv(out_path, index=False)
        return candidates

    # ── Stage C: Anthropic chart review ────────────────────────────────────
    print(f">> Stage C: Anthropic chart review "
          f"({CONFIG['MAX_WORKERS']} workers, {len(candidates):,} notes) ...")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    candidate_dicts = candidates.to_dict(orient="records")

    results = []
    with ThreadPoolExecutor(max_workers=CONFIG["MAX_WORKERS"]) as pool:
        futures = {pool.submit(_classify_row, client, row): i
                   for i, row in enumerate(candidate_dicts)}
        done = 0
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            if done % 50 == 0:
                print(f"   ... {done}/{len(candidates)} classified", flush=True)

    df = pd.DataFrame(results)

    # Drop internal sampling columns
    for col in ("_RN", "_DXRN"):
        if col in df.columns:
            df = df.drop(columns=[col])

    # ── Balanced selection ──────────────────────────────────────────────────
    if balanced:
        high = df["CONFIDENCE"] == "HIGH"

        pos_mask = (
            high
            & (df["PSI_EVENT_PRESENT"] == "YES")
            & (df["HOSPITAL_ACQUIRED_NOT_POA"].isin(["YES", "UNCERTAIN"]))
            & (df["IS_EXCLUSION"] == "NO")
        )
        neg_mask = (
            high
            & (df["PSI_EVENT_PRESENT"] == "NO")
        )

        pieces = []
        print("\n>> Balanced selection (target: "
              f"{n_per_label} positive + {n_per_label} negative per measure):")
        for code in sorted(active_keys):
            pos = df[pos_mask & (df["PSI_CODE"] == code)].head(n_per_label).copy()
            neg = df[neg_mask & (df["PSI_CODE"] == code)].head(n_per_label).copy()
            pos["LABEL"] = "positive"
            neg["LABEL"] = "negative"
            pieces.extend([pos, neg])
            print(f"   {code}: {len(pos)} positive, {len(neg)} negative")

        output = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()

    # ── Flag-only mode (original behaviour) ────────────────────────────────
    else:
        mask = (
            (df["PSI_EVENT_PRESENT"] == "YES")
            & (df["HOSPITAL_ACQUIRED_NOT_POA"].isin(["YES", "UNCERTAIN"]))
            & (df["IS_EXCLUSION"] == "NO")
            & (df["CONFIDENCE"] == "HIGH")
        )
        output = df[mask].copy()
        output["LABEL"] = "positive"
        print(f"\n>> Confirmed PSI flags: {len(output)} (HIGH confidence only)")

    # Save full classification results
    all_path = out_path.parent / (out_path.stem.replace("balanced_cases", "all_classified") + ".csv")
    df.to_csv(all_path, index=False)
    print(f">> Full classifications written: {all_path}  ({len(df)} rows)")

    print(f"\n>> Total rows: {len(output)}")
    output.to_csv(out_path, index=False)
    print(f">> Balanced output written: {out_path}")
    return output


if __name__ == "__main__":
    main()
