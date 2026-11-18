#!/usr/bin/env python3
"""Generate run-length encoded cycle checks using a behavioral acquisition model.

No third-party dependencies. The oracle stores an ordinary Python list; sample
times come from elapsed clock cycles, not RTL divider/address implementation.
"""
import argparse
import random
from pathlib import Path


class Model:
    def __init__(self, divisor):
        self.divisor = divisor
        self.elapsed = 0
        self.history = [0, 0]
        self.previous = None
        self.status = "idle"
        self.frame = []
        self.mode = 0
        self.data = None

    def step(self, p):
        rst, arm, abort, din, mode, rd = (p[k] for k in
                                        ("rst", "arm", "abort", "din", "mode", "rd"))
        old_status = self.status
        pulse = valid = False
        if rst:
            self.elapsed = 0
            self.history = [0, 0]
            self.previous = None
            self.status = "idle"
            self.frame = []
            self.mode = 0
        else:
            self.elapsed += 1
            sampled = self.history.pop(0)
            self.history.append(din)
            tick = self.elapsed % self.divisor == 0
            accepting = arm and old_status in ("idle", "done")
            if old_status == "done" and rd and not abort and not accepting:
                self.data = self.frame[p["addr"]]
                valid = True
            if abort:
                self.status, self.frame, self.mode = "idle", [], 0
            elif accepting:
                self.status, self.frame, self.mode = "waiting", [], mode
            elif tick and old_status in ("waiting", "capturing"):
                edge = self.previous is not None and sampled != self.previous
                trigger = (self.mode == 0 or
                           (edge and (self.mode == 3 or sampled == (self.mode == 1))))
                if old_status == "capturing" or trigger:
                    self.frame.append(sampled)
                    self.status = "done" if len(self.frame) == 1024 else "capturing"
                    pulse = self.status == "done"
            if tick:
                self.previous = sampled
        flags = (int(self.status in ("waiting", "capturing")) |
                 (int(self.status == "waiting") << 1) |
                 (int(self.status == "done") << 2) | (int(pulse) << 3) |
                 (int(valid) << 4) | (int(self.data is not None) << 5))
        return flags, len(self.frame), self.data or 0


class Scenario:
    def __init__(self, output, divisor, seed):
        self.file = output.open("w")
        self.model = Model(divisor)
        self.div = divisor
        self.rng = random.Random(seed)
        self.p = dict(rst=0, arm=0, abort=0, din=0, mode=0, rd=0, addr=0)
        self.last = None
        self.repeat = self.cycles = self.frames = 0

    def flush(self):
        if self.last is not None:
            self.file.write(" ".join(f"{v:x}" for v in (self.repeat, *self.last)) + "\n")

    def run(self, cycles=1, **changes):
        self.p.update(changes)
        p = self.p
        ctrl = (p["rst"] | p["arm"] << 1 | p["abort"] << 2 | p["din"] << 3 |
                p["mode"] << 4 | p["rd"] << 6)
        for _ in range(cycles):
            flags, count, data = self.model.step(p)
            row = (ctrl, p["addr"], flags, count, data)
            if row != self.last:
                self.flush()
                self.last, self.repeat = row, 0
            self.repeat += 1
            self.cycles += 1
            self.frames += bool(flags & 8)

    def reset(self, din=0):
        self.run(4, rst=1, din=din, arm=0, abort=0, rd=0)
        self.run(rst=0)

    def arm(self, mode):
        self.run(arm=1, mode=mode)
        self.run(arm=0)

    def fill(self):
        # Edges fall at varied phases relative to sampling, including near clock edges.
        deadline = self.cycles + self.div * 1100
        while self.model.status != "done":
            self.run(self.rng.randint(1, 2 * self.div), din=self.rng.randrange(2),
                     rd=1, addr=self.rng.randrange(1024))
            assert self.cycles < deadline, "scenario failed to trigger/complete"
        self.run(2 * self.div, din=1, rd=0)

    def read_frame(self):
        # Consecutive reads, reverse order, randomized addresses, and idle output holding.
        for address in list(range(1024)) + list(range(1023, -1, -1)):
            self.run(rd=1, addr=address)
        for _ in range(32):
            self.run(rd=self.rng.randrange(2), addr=self.rng.randrange(1024))
        self.run(4, rd=0)

    def finish(self):
        self.flush()
        self.file.close()
        return self.cycles, self.frames


def generate(path, divisor, seed, smoke):
    s = Scenario(path, divisor, seed)
    s.reset()
    s.run(2 * divisor, rd=1)  # No stale reads before a frame exists.
    s.arm(0)
    s.fill()
    s.read_frame()
    if not smoke:
        for mode, level in ((1, 1), (2, 0), (3, 0)):
            s.reset(din=level)
            s.arm(mode)
            # Initial level is not an edge; changing mode while armed must be ignored.
            s.run(4 * divisor, mode=0, rd=1)
            assert s.model.status == "waiting"
            s.run(2 * divisor, din=1-level)
            s.run(2 * divisor, din=level)
            assert s.model.status == "capturing"
            s.run(2 * divisor, arm=1, mode=0)  # Busy arm is ignored.
            s.run(arm=0)
            s.fill()
            s.read_frame()
        # Re-arm invalidates the completed frame and suppresses a colliding read.
        s.run(arm=1, mode=0, rd=1)
        s.run(arm=0)
        s.run(4 * divisor)
        assert s.model.status == "capturing"
        s.run(abort=1, arm=1)
        assert s.model.status == "idle" and not s.model.frame
        s.run(abort=0, arm=0)
        # Abort while waiting, then reset during capture; both invalidate contents.
        s.run(2 * divisor, din=0)
        s.arm(1)
        s.run(2 * divisor)
        assert s.model.status == "waiting"
        s.run(abort=1)
        s.run(abort=0)
        s.arm(0)
        s.run(7 * divisor)
        s.reset(din=1)
        s.run(2 * divisor, rd=1)
        s.arm(0)
        # Abort exactly on the would-be final write, even with arm/read asserted.
        while len(s.model.frame) < 1023:
            s.run()
        until_final = divisor - (s.model.elapsed % divisor)
        s.run(until_final - 1)
        s.run(abort=1, arm=1, rd=1)
        assert s.model.status == "idle" and not s.model.frame
        s.run(abort=0, arm=0)
        # A fresh frame proves recovery and that no old tail survives.
        s.arm(0)
        s.fill()
        s.read_frame()
        s.run(rst=1, arm=1, abort=1, rd=1)
        s.run(rst=0, arm=0, abort=0)
    cycles, frames = s.finish()
    print(f"Generated {path}: divisor={divisor}, seed={seed}, cycles={cycles}, frames={frames}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--divisor", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=385)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.divisor < 4:
        parser.error("divisor must be at least four")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    generate(args.output, args.divisor, args.seed, args.smoke)
