# Some simple testing tasks (sorry, UNIX only).

flake:
	flake8


test: flake
	py.test ./tests/

mypy: flake
	mypy

vtest: flake develop
	py.test ./tests/

cov cover coverage: flake
	py.test --cov aiohttp_session --cov-report html --cov-report=xml ./tests/
	@echo "open file://`pwd`/coverage/index.html"

clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -f `find . -type f -name '@*' `
	rm -f `find . -type f -name '#*#' `
	rm -f `find . -type f -name '*.orig' `
	rm -f `find . -type f -name '*.rej' `
	rm -f .coverage
	rm -rf coverage
	rm -rf build
	rm -rf cover
	# make -C docs clean
	python setup.py clean

doc:
	make -C docs html
	@echo "open file://`pwd`/docs/_build/html/index.html"

.PHONY: all build venv flake test vtest testloop cov clean doc
