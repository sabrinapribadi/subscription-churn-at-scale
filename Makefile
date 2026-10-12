.PHONY: install data cohorts train rank services dashboard test lint

install:
	poetry install

# Phase 0 — requires Kaggle API token and accepted competition rules
data:
	poetry run python scripts/download_data.py

cohorts:
	poetry run python scripts/build_cohorts.py

train:
	poetry run python scripts/train_model.py

rank:
	poetry run python scripts/train_ranker.py

services:
	docker compose up --build

dashboard:
	PYTHONPATH=. poetry run streamlit run src/ui/dashboard.py

lint:
	poetry run ruff check . && poetry run mypy src

test:
	poetry run pytest tests/ -v

# Real-browser tooltip check for docs/index.html (Node + Google Chrome)
hover-test:
	cd tests/browser && (test -d node_modules/puppeteer-core || npm i --no-save puppeteer-core@23) && node hover_test.js $(CURDIR)/docs/index.html /tmp | grep -E "FAIL|SUMMARY"

# Real-browser check that every interactive control changes what it should
controls-test:
	cd tests/browser && (test -d node_modules/puppeteer-core || npm i --no-save puppeteer-core@23) && node controls_test.js $(CURDIR)/docs/index.html /tmp/links.txt $(CURDIR)/data/outputs/p4_rank_calibrate.json | grep -E "FAIL|control checks"
