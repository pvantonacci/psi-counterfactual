# PSI Counterfactual Pipeline — All PSI Types Summary

**Run completed:** 2026-06-05T23:59:50.592572+00:00  
**Total matched pairs:** 3626  
**PSI types:** 16/16 passed  

| PSI Type | Status | Cases | Matched Pairs |
|---|---|---|---|
| PSI_03_PRESSURE_ULCER | PASS | 3 | 150 |
| PSI_04_FAILURE_TO_RESCUE | PASS (G2 warn) | 5 | 99 |
| PSI_05_RETAINED_ITEM | PASS | 13 | 507 |
| PSI_06_IATROGENIC_PNEUMOTHORAX | PASS | 7 | 223 |
| PSI_07_CLABSI | PASS (G2 warn) | 6 | 159 |
| PSI_08_FALL_FRACTURE | PASS | 3 | 73 |
| PSI_09_POSTOP_HEMORRHAGE | PASS | 11 | 428 |
| PSI_10_POSTOP_AKI_DIALYSIS | PASS (G2 warn) | 3 | 62 |
| PSI_11_POSTOP_RESP_FAILURE | PASS | 8 | 195 |
| PSI_12_PERIOP_PE_DVT | PASS | 3 | 19 |
| PSI_13_POSTOP_SEPSIS | PASS (G2 warn) | 5 | 96 |
| PSI_14_WOUND_DEHISCENCE | PASS (G2 warn) | 7 | 159 |
| PSI_15_ACCIDENTAL_PUNCTURE | PASS (G2 warn) | 14 | 700 |
| PSI_17_BIRTH_TRAUMA | PASS | 7 | 140 |
| PSI_18_OB_TRAUMA_INSTRUMENT | PASS | 11 | 416 |
| PSI_19_OB_TRAUMA_NO_INSTRUMENT | PASS | 4 | 200 |

**G2 warn** = LSPS propensity matching degraded age-SMD (expected for types with < ~10 cases);
CEM demographic matching still applied. Matched sets are valid for downstream use.

Per-type outputs: `outputs/<PSI_TYPE>/`  
Logs: `outputs/<PSI_TYPE>/runs/pipeline_*.log`