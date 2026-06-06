# CLAUDE.md — PSI Counterfactual Pipeline

## Critical rules (never relax)
- Forbidden suppliers: **1990** (Advocate Aurora), **3707**, **3490** — removed at every stage
- No post-event features in the feature matrix (only data from [t0, t0+4h])
- No invented inputs; no local fallbacks for supplier filtering
- Always run scripts from the **project root**, not from inside `src/`

## Environment
```bash
source PSI/bin/activate          # activate virtualenv
# or: pip install -r requirements.txt inside PSI/ venv
```

## Entry points (in execution order)
```bash
make run-one PSI_TYPE=PSI_06_IATROGENIC_PNEUMOTHORAX   # single type
make run-all                                            # all 16 types (~40 min)
make diagnostics                                        # donor dx analysis
make qa                                                 # QA vs spec PDF
```

## Key paths
| Path | Contents |
|---|---|
| `data/raw/` | Immutable PSI input CSVs — never hand-edit |
| `data/interim/snowflake_cache/` | Snowflake parquet cache — gitignored, regenerable |
| `src/` | All pipeline scripts, prefixed by execution order |
| `outputs/PSI_XX/` | Per-type matched sets, scores, metrics |
| `results/` | Human-readable reports and tables |
| `references/` | Spec PDF and literature |

## Snowflake connection
Credentials live in `.env` (gitignored). The pipeline uses `externalbrowser` (Okta SSO).
In WSL2, Chrome at `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe` handles the flow.
After first auth, all data is cached in `data/interim/snowflake_cache/`.
