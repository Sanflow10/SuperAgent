.PHONY: install test lint typecheck audit dry-run run

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements-dev.txt

test:
	. .venv/bin/activate && pytest -q

lint:
	. .venv/bin/activate && ruff check .

typecheck:
	. .venv/bin/activate && mypy agents core tools main.py

audit:
	./audit.sh

dry-run:
	. .venv/bin/activate && python main.py --dry-run "descreva seu objetivo"

run:
	. .venv/bin/activate && python main.py "$(GOAL)"
