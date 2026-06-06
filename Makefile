VENV_PYTHON := /home/pvam/projects/PROTEGE\ -\ HealthBenck/PSI/bin/python
PYTHON      ?= $(shell which python 2>/dev/null | grep -q 'PSI' && echo python || echo $(VENV_PYTHON))
PSI_TYPE    ?= PSI_06_IATROGENIC_PNEUMOTHORAX

.PHONY: help pull-data identify-cases enrich-cases run-one run-all diagnostics qa notebook setup run-fresh

help:
	@echo "PSI Counterfactual Pipeline"
	@echo ""
	@echo "  ── Data refresh (requires Snowflake SSO + Anthropic API key) ──"
	@echo "  make pull-data        # 00: pull raw tables from Snowflake"
	@echo "  make identify-cases   # 01: identify PSI cases + Claude abstraction"
	@echo "  make enrich-cases     # 01b: enrich cases with LOS/complexity tiers"
	@echo "  make run-fresh        # 00 → 01 → 01b → run-all (full refresh)"
	@echo ""
	@echo "  ── Pipeline (uses cached data) ──"
	@echo "  make run-one PSI_TYPE=PSI_06_IATROGENIC_PNEUMOTHORAX"
	@echo "  make run-all          # all 16 types (~25 min)"
	@echo ""
	@echo "  ── Analysis ──"
	@echo "  make diagnostics      # donor dx analysis"
	@echo "  make qa               # QA vs spec PDF"
	@echo "  make notebook         # generate execution plan notebook"

setup:
	pip install -r requirements.txt

pull-data:
	$(PYTHON) src/00_pull_psi_tables.py

identify-cases:
	$(PYTHON) src/01_psi_pipeline.py

enrich-cases:
	$(PYTHON) src/01b_add_classification_columns.py

run-one:
	$(PYTHON) src/02_counterfactual_pipeline.py \
	  --psi-type $(PSI_TYPE) \
	  --output-root outputs

run-all:
	$(PYTHON) src/03_run_all_psi_types.py

diagnostics:
	$(PYTHON) src/04_analyze_donor_diagnostics.py

qa:
	$(PYTHON) src/05_qa_vs_spec.py

notebook:
	$(PYTHON) src/06_build_notebook.py

run-fresh: pull-data identify-cases enrich-cases run-all
