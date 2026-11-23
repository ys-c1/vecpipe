PY ?= python3
.PHONY: all test render clean info bench

all: test

test:
	$(PY) -m pytest -q

render:
	$(PY) -m vecpipe.cli render --config '{}' --out out.pgm

info:
	$(PY) -m vecpipe.cli info

bench:
	$(PY) -I bench/bench_atlas.py

clean:
	rm -f out.pgm
	rm -rf .pytest_cache __pycache__ vecpipe/__pycache__ tests/__pycache__
