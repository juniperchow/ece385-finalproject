PYTHON ?= python3
.PHONY: test test-iverilog test-verilator synth-capture
test:
	$(PYTHON) scripts/test_capture.py
test-iverilog:
	$(PYTHON) scripts/test_capture.py --sim iverilog
test-verilator:
	$(PYTHON) scripts/test_capture.py --sim verilator
synth-capture:
	vivado -mode batch -source scripts/synth_capture.tcl
