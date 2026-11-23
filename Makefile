PY ?= python3
.PHONY: all test render clean info bench

all: test

test:
	$(PY) -m pytest -q

bench:
	$(PY) bench/bench_flatten.py

render:
	$(PY) -m vecpipe.cli render --config '{}' --out out.pgm

info:
	$(PY) -m vecpipe.cli info

clean:
	rm -f out.pgm
	rm -rf .pytest_cache __pycache__ vecpipe/__pycache__ tests/__pycache__
