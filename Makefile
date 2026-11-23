PY ?= python3
.PHONY: all test render clean info clipstat

all: test

test:
	$(PY) -m pytest -q

render:
	$(PY) -m vecpipe.cli render --config '{}' --out out.pgm

clipstat:
	$(PY) -m vecpipe.cli clipstat

info:
	$(PY) -m vecpipe.cli info

clean:
	rm -f out.pgm
	rm -rf .pytest_cache __pycache__ vecpipe/__pycache__ tests/__pycache__
