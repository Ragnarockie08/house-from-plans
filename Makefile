BLENDER ?= /Applications/Blender.app/Contents/MacOS/Blender
HOUSE   ?= house
VARIANT ?= A
PY      := .venv/bin/python

.PHONY: setup check overlay build render check-model example need-version

setup:                      ## venv with the Python deps
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

check:                      ## plan.json vs the room table, footprint, envelope
	$(PY) tools/check_plan.py $(HOUSE) $(VARIANT)

overlay:                    ## plan.json drawn over the scan
	$(PY) tools/overlay.py $(HOUSE) $(HOUSE)/out/checks/overlay.jpg

need-version:
	@test -n "$(V)" || (echo "set V=v1 (every build gets its own out/<version>/)"; exit 1)

build: need-version         ## model only, then the model checks
	$(BLENDER) -b --factory-startup --python blender/build_model.py -- --house $(HOUSE) --version $(V) --variant $(VARIANT)
	$(PY) tools/check_model.py $(HOUSE) $(V) $(VARIANT)

render: need-version        ## model + review stills (add FAST=1 for quick previews)
	$(BLENDER) -b --factory-startup --python blender/build_model.py -- --house $(HOUSE) --version $(V) --variant $(VARIANT) --render $(if $(FAST),--fast,)
	$(PY) tools/check_model.py $(HOUSE) $(V) $(VARIANT)

example:                    ## the whole pipeline on the fictional example house
	$(MAKE) check overlay HOUSE=examples/simple-house
	$(MAKE) render HOUSE=examples/simple-house V=$(or $(V),v1) FAST=1
