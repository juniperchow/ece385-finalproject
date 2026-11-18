#!/usr/bin/env python3
"""Run the same self-checking SV testbench with Icarus or Verilator 5+."""
import argparse
import os
import shutil
import subprocess
from pathlib import Path
from capture_vectors import generate

ROOT = Path(__file__).resolve().parents[1]


def run(argv):
    subprocess.run([str(a) for a in argv], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", choices=("auto", "iverilog", "verilator"), default="auto")
    args = parser.parse_args()
    iverilog = os.environ.get("IVERILOG", "iverilog")
    verilator = os.environ.get("VERILATOR", "verilator")
    sim = args.sim
    if sim == "auto":
        sim = "iverilog" if shutil.which(iverilog) else "verilator"
    compiler = iverilog if sim == "iverilog" else verilator
    if not shutil.which(compiler):
        parser.error(f"Missing {compiler}; install Icarus or Verilator, or set IVERILOG/VERILATOR")
    build = ROOT / "build" / "capture" / sim
    build.mkdir(parents=True, exist_ok=True)
    for divisor in (4, 8, 1000):
        exe = build / f"capture_{divisor}"
        sources = ["rtl/capture_core.sv", "tb/tb_capture_core.sv"]
        if sim == "iverilog":
            run([compiler, "-g2012", "-Wall", "-s", "tb_capture_core",
                 f"-Ptb_capture_core.SAMPLE_DIV={divisor}", "-o", exe, *sources])
        else:
            run([compiler, "--binary", "--timing", "--assert", "--language", "1800-2012",
                 "-Wall", "-Wno-DECLFILENAME", "-Wno-TIMESCALEMOD", "-Wno-UNUSEDSIGNAL",
                 "--top-module", "tb_capture_core", f"-GSAMPLE_DIV={divisor}",
                 "--Mdir", build / f"obj_{divisor}", "-o", exe, *sources])
        for seed in ((385, 2026) if divisor != 1000 else (385,)):
            vectors = build / f"vectors_{divisor}_{seed}.txt"
            generate(vectors, divisor, seed, smoke=(divisor == 1000))
            relative = vectors.relative_to(ROOT)
            command = [exe, f"+vectors={relative}"]
            if sim == "iverilog":
                command.insert(0, os.environ.get("VVP", "vvp"))
            run(command)
    print(f"PASS: all five capture regressions ({sim})", flush=True)


if __name__ == "__main__":
    main()
