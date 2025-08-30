.PHONY: clean
clean: clean-python clean-tests clean-system

.PHONY: clean-python
clean-python:
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '*.pyd' -exec rm -f {} +
	@find . -name '__pycache__' -exec rm -fr {} +
	@uv cache clean

.PHONY: clean-tests
clean-tests:
	@rm -rf .mypy_cache/ .pytest_cache/ .ruff_cache/ htmlcov/ .coverage

.PHONY: clean-system
clean-system:
	@find . -name '*~' -exec rm -f {} +
	@find . -name '.DS_Store' -exec rm -f {} +

.PHONY: update-requirements
update-requirements:
	uv pip compile --universal \
		requirements/requirements.in \
		--output-file requirements/requirements.txt
	uv pip compile --universal \
		requirements/requirements-dev.in \
		--output-file requirements/requirements-dev.txt

.PHONY: sync-requirements
sync-requirements:
	uv pip sync \
		requirements/requirements.txt \
		requirements/requirements-dev.txt

.PHONY: setup-environment
setup-environment:
	uv python pin 3.12.7
	uv venv
	. .venv/bin/activate
	make sync-requirements

.PHONY: check
check:
	@echo "Checking lint & format"
	coverage run -m pytest -v --black --ruff --mypy --isort ./src/
