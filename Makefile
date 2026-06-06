PYTHON ?= PSI/bin/python
PSI_TYPE ?= PSI_06_IATROGENIC_PNEUMOTHORAX

.PHONY: help run-one run-all diagnostics qa notebook setup

help:
	@echo "PSI Counterfactual Pipeline"
	@echo ""
	@echo "  make run-one PSI_TYPE=PSI_06_IATROGENIC_PNEUMOTHORAX"
	@echo "  make run-all"
	@echo "  make diagnostics"
	@echo "  make qa"
	@echo "  make notebook"
	@echo "  make setup"

setup:
	pip install -r requirements.txt

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
