.PHONY: install test lint typecheck run-api run-ui eval

install:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy src

run-api:
	uvicorn dda.api.app:app --reload

run-ui:
	streamlit run src/dda/infrastructure/ui.py

eval:
	pytest tests/eval
	python evals/run_eval.py --limit 5 --variants 1,2
