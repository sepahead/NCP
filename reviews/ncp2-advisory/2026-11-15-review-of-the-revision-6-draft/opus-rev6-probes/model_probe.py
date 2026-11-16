"""Model investigations (scratch): traces, disabled properties, extra mutants and faults."""
import dataclasses, importlib.util, sys
root = sys.argv[1]
spec = importlib.util.spec_from_file_location("lockstep_model", root + "/model/lockstep.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
LS, C = M.LS, M.C

def run(label, search):
    try:
        worlds, _ = search.run(); print(f"{label}: no violation ({worlds} worlds)")
    except M.Violation as v:
        text = str(v).split("\n")
        print(f"{label}: {text[0]}"); [print("   " + t.strip()) for t in text[1:]]

which = sys.argv[2]
if which == "trace":
    run("constant_nonce, stream", M.Search("stream", 1, "constant_nonce", False))
    run("verdict_from_open_report, stream", M.Search("stream", 1, "verdict_from_open_report", False))
if which == "noS6":
    original = M.require
    M.require = lambda cond, prop, text: original(cond or prop == "S6", prop, text)
    for shape in ("stream", "zenoh"):
        for same in (False, True):
            run(f"verdict_from_open_report without S6, {shape}, same={same}", M.Search(shape, 1, "verdict_from_open_report", same))
    for shape in ("stream", "zenoh"):
        run(f"verdict_ignores_state without S6, {shape}", M.Search(shape, 1, "verdict_ignores_state", False))
if which == "noL1":
    original = M.require
    M.require = lambda cond, prop, text: original(cond or prop == "L1", prop, text)
    for mutant in ("constant_nonce", "take_without_term", "take_keeps_term"):
        for shape in ("stream", "zenoh"):
            run(f"{mutant} without L1, {shape}", M.Search(shape, 1, mutant, False))
if which == "extra":
    class NoVerdict(M.Search):  # S4: a judge that never gives a verdict
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            def judge(known, uncertain, taken): raise M.ncp.ProtocolError("no verdict")
            self.judge = judge
    run("judge never decides (S4?)", NoVerdict("stream", 1))
    class DoubleTick(LS.Lockstep):  # S3: the tick moves by two
        def execute(self, request):
            result = super().execute(request)
            if request.op in self.ops: self.tick += 1
            return result
    class S3Search(M.Search):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self.lockstep = DoubleTick(self.app, ["step"]); self.handler = self.lockstep
    run("tick moves by two (S3?)", S3Search("stream", 1))
    class DeclineAllTakes(LS.Lockstep):  # progress
        def validate(self, request):
            if request.op == LS.TAKE: raise M.ncp.Declined("no")
            return super().validate(request)
    class ProgSearch(M.Search):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self.lockstep = DeclineAllTakes(self.app, ["step"]); self.handler = self.lockstep
    run("every take declined (progress?)", ProgSearch("stream", 0))
if which == "fresh_restart":
    class FreshRestart(M.Search):  # a restart that restores no clock (profile rule 5.7, last sentence)
        def successors(self, w):
            out = super().successors(w)
            if w.faults < self.budget and w.owners:
                s = w.stepper
                fresh = dataclasses.replace(w, owners=(), clock=(0, None, None, 0, None, 0), holder=None,
                                            stepper=dataclasses.replace(s, holds=False), rewound=True,
                                            faults=w.faults + 1)
                out.append(("the owner restarts without a saved clock", fresh))
            return out
    for shape in ("stream", "zenoh"):
        run(f"restart without a saved clock, {shape}", FreshRestart(shape, 1))
    class OlderRestart(M.Search):  # a restart to the clock before the last step (an older saved clock)
        def successors(self, w):
            out = super().successors(w)
            if w.faults < self.budget and w.owners and w.ran and w.stepper.known[0] == w.clock[0] - 1:
                s = w.stepper; k = s.known
                older = dataclasses.replace(w, owners=(), clock=(k[0], k[1], k[2], 0, None, int(k[1][1:]) if k[1] else 0),
                                            holder=None, stepper=dataclasses.replace(s, holds=False), rewound=True,
                                            faults=w.faults + 1)
                out.append(("the owner restarts to the clock saved before the last step", older))
            return out
    for shape in ("stream", "zenoh"):
        run(f"restart to the clock before the last step, {shape}", OlderRestart(shape, 1))
