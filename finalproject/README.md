# Capture subsystem

Single-channel 100 kS/s acquisition with configurable sampled-edge triggering and
1024 x 16-bit frozen-frame BRAM. This is the first subsystem; FFT and HDMI are not
connected yet. The existing starter project is preserved.

## Run

From `finalproject/`, on Linux with Python 3 and Icarus Verilog or Verilator 5+:

```export PATH=$PATH:./tools/Xilinx/Vivado/2022.2/bin/
make test                 # Prefer Icarus if installed; otherwise Verilator
make test-iverilog
make test-verilator
make synth-capture        # Teammate's Vivado machine; no GUI or HDMI IP required
```

`python3 /path/to/finalproject/scripts/test_capture.py` also works from any directory.
Tool overrides: `IVERILOG`, `VVP`, `VERILATOR`, and Make's `PYTHON`. Generated
vectors, executables, and reports stay under ignored `build/capture/`.

## Interface contract

| Item | Contract |
|---|---|
| Module | `rtl/capture_core.sv`, SystemVerilog 1800-2012 |
| `clk`, `rst` | 100 MHz system clock; active-high **synchronous** reset, at least one rising edge. Board reset release must be synchronized upstream. |
| `SAMPLE_DIV` | Integer clocks/sample, default 1000; supported >=4. Sampling rate is `clk_hz / SAMPLE_DIV`. No generated sampling clock. |
| `probe_async` | One digital input through two `ASYNC_REG` flops. Acquisition observes the value presented two system edges earlier; analog metastability is not modeled in simulation. |
| `arm` | One-cycle system-domain strobe accepted only when `busy=0`; immediately invalidates an old frame and latches mode. Busy arm requests are ignored, not queued. |
| `trigger_mode[1:0]` | 0 immediate, 1 rising, 2 falling, 3 either edge. Latched on accepted arm. Edges are between consecutive 100 kS/s samples, including the last idle sample. |
| `abort_capture` | Synchronous level; priority over arm, trigger, final write, and read. Returns to idle and invalidates the frame. Divider/input history continue. |
| `armed`, `busy` | Armed means waiting for trigger. Busy covers waiting and collecting. |
| `done`, `done_pulse` | `done` remains high while a complete frame is owned by readers. `done_pulse` is one cycle on the final write. Cleared by reset/abort/re-arm. |
| `sample_count[10:0]` | Number of stored samples, 0 through 1024; zeroed by reset/abort/accepted arm. |
| Frame format | 1024 chronological 16-bit unsigned words, each exactly 0 or 1. Triggering sample is word 0. No pre-trigger data. FFT stage must explicitly convert to its Q-format. |
| `rd_en`, `rd_addr[9:0]` | Synchronous BRAM request, accepted only when `done` is already high and no reset/abort/re-arm occurs. One request per clock supported. |
| `rd_valid`, `rd_data[15:0]` | Request/address present before edge N produces registered data and valid immediately after edge N (one synchronous read stage). Data holds without an accepted read and is unspecified before the first accepted read. Only use data when valid. |
| Clock ownership | All control, status, and BRAM reads use `clk`. No ports may connect directly to the future 74.25 MHz pixel domain. |
| Memory and DSP | Reset never clears RAM. Block-RAM attribute plus synchronous read/write template; no DSP resources needed here. |
| Constraints | `constraints/capture_ooc.xdc`: 10 ns core clock and false path only to synchronizer stage one. Physical input pin mapping belongs to future board integration. |

Sampling phase is free-running from reset; the first sampling edge is the
`SAMPLE_DIV`th clock after reset is released. Arming on a sample edge does not
capture on that same edge. Immediate mode starts on the next sample edge. Edge
mode requires a valid previous sample, preventing reset startup from creating a
false edge. An input pulse entirely between sampling instants can be missed.
The frame covers 10.24 ms of sampling slots (10.23 ms between first and last samples).

Read ownership is deliberately serialized: acquisition freezes after one frame.
Complete processing/reading before re-arming. The later pixel-domain integration
must add a frame-ownership handshake with stable data and acknowledgment, or a
proper dual-clock buffer; synchronizing individual multi-bit data wires is not sufficient.

## Verification and synthesis boundary

`scripts/capture_vectors.py` generates deterministic, run-length encoded vectors
from a Python model with a list-backed frame and elapsed-time sampling schedule.
`tb/tb_capture_core.sv` checks status/count/data on every simulated cycle and
exits nonzero on mismatch. No hand-maintained hex tables are needed. This block
has no ROM LUTs, so no RTL `$readmemh` paths are needed yet.

Five regressions cover divisors 4 and 8 with two seeds each, plus one full
1024-sample capture at the production divisor 1000. Coverage includes all trigger
modes, startup-high/low suppression of false triggers, latched mode, ignored busy
arm, read rejection before completion, every address forward/backward, random read
gaps, frozen-frame retention, re-arm/read collision, reset during capture,
abort while waiting/collecting/on the final sample, and recovery to a new frame.

Validated locally on 2026-11-18 with Verilator 5.38: all five regressions passed,
1,221,372 cycles checked and 21 completed frames. Separate RTL-only `-Wall` lint
passed without warning suppression. The Icarus runner is provided but has not
been executed in this environment. Vivado is unavailable locally.

Portable simulation checks digital behavior, not physical metastability, placement,
BRAM inference, or timing closure. The Vivado out-of-context script checks that
BRAM is inferred and produces utilization, timing, and CDC reports. It does not
produce a board bitstream or claim full-chip I/O timing closure. The original
`finalproject.xpr` still has its pre-existing top-name mismatch and missing HDMI
IP; this subsystem's batch flow does not depend on that project.
