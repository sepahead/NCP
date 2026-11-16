"""Prototype drawing code for two new NCP 2 figures, in the visual language of
scripts/gen_diagrams.py (advisory consult, revision 5). It imports the generator from a scratch
copy and checks each figure with the generator's own validators.

Usage: new_figures.py OUT_DIR      (run from a tree that holds scripts/, contract/, spec/)
"""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import gen_diagrams as G  # noqa: E402

RULES = json.loads((G.ROOT / "spec" / "ncp2-rules.json").read_text(encoding="utf-8"))
UNRELEASED = f"NCP 2 is UNRELEASED. {G.NOT_CERTIFICATION}"
CHIP_H, CHIP_PITCH, GROUP_GAP = 46, 54, 44


def chip(c, name, x, y, w, text, color, parent):
    """One code in a rounded box."""
    c.node(name, G.Box(x, y, w, CHIP_H), parent)
    c.shape("rect", x=x, y=y, w=w, h=CHIP_H, rx=10, fill="tint", stroke=color, stroke_width=2)
    c.text(x + 16, y + 31, text, G.CELL, container=name)


def verdict_groups():
    """The three columns of the verdict map, from spec/ncp2-rules.json (members client and open)."""
    codes = RULES["codes"]

    def of(client, outcome, opening=False):
        return [e["code"] for e in codes
                if e["client"] == client and e["outcome"] == outcome and bool(e.get("open")) == opening]

    star = lambda names: [n + " *" if n in ("bad_frame", "shutdown") else n for n in names]  # noqa: E731
    return {
        "yes": [("ok", ["ok"]), ("ended", of("yes", "ended"))],
        "no": [("declined", of("no", "declined")), ("ended", star(of("no", "ended"))),
               ("rejected, in reply to open", of("no", "rejected", True))],
        "unknown": [("rejected, in reply to another request", of("unknown", "rejected")),
                    ("ended", of("unknown", "ended") + ["a code that the client does not know"]),
                    ("local events", [e["code"] for e in RULES["local_codes"]])],
    }


def chips_height(groups, per_row, wide):
    total = 0
    for _, names in groups:
        rows = sum(1 if n in wide else 0 for n in names) + -(-sum(1 for n in names if n not in wide) // per_row)
        total += 18 + rows * CHIP_PITCH - (CHIP_PITCH - CHIP_H) + GROUP_GAP
    return total - GROUP_GAP + 26


def ncp2_verdicts():
    """Every code and local event in its verdict: executed, not executed, possibly executed."""
    c = G.Canvas(
        "ncp2-verdicts", G.WIDTH, 1500,
        "What each NCP 2 answer lets the client conclude",
        "Three columns sort every outcome, code, and local event by the client's verdict: executed, "
        "not executed, or possibly executed. The codes come from spec/ncp2-rules.json. " + UNRELEASED,
    )
    y = G.header(c, "NCP 2 VERDICTS", "Every answer has one place", f"REVISION {RULES['revision']}")
    groups = verdict_groups()
    wide = {"a code that the client does not know"}
    columns = [
        dict(key="yes", name="verdict-yes", x=G.MARGIN, w=330, per_row=1, accent="turquoise",
             title="Executed", subtitle="It ran once",
             body="The owner executed the request one time."),
        dict(key="no", name="verdict-no", x=G.MARGIN + 330 + 32, w=470, per_row=1, accent="lapis",
             title="Not executed", subtitle="It never runs",
             body="The owner did not execute the request, and it never will."),
        dict(key="unknown", name="verdict-unknown", x=G.MARGIN + 330 + 32 + 470 + 32, w=632, per_row=2,
             accent="pomegranate", title="Possibly executed", subtitle="The honest unknown",
             body="The client cannot know. At most one request of a session ends here, and it is the last one."),
    ]
    top = y + 10
    for col in columns:
        col["extra"] = chips_height(groups[col["key"]], col["per_row"], wide)
    def arguments(col, **more):
        return dict(title=col["title"], body=col["body"], accent=col["accent"], subtitle=col["subtitle"],
                    extra=col["extra"], **more)
    offset = max(G.card(c, col["name"], col["x"], top, col["w"], **arguments(col, measure_only=True))[1] for col in columns)
    body_lines = max(len(G.wrap(col["body"], G.BODY, col["w"] - 52)) for col in columns)
    height = max(G.card(c, col["name"], col["x"], top, col["w"], **arguments(col, rule_offset=offset, measure_only=True))[0]
                 + (body_lines - len(G.wrap(col["body"], G.BODY, col["w"] - 52))) * G.LINE for col in columns)
    bottom = top
    for col in columns:
        layout = G.card(c, col["name"], col["x"], top, col["w"], **arguments(col, h=height, rule_offset=offset))
        yy = top + offset + 38 + body_lines * G.LINE + 8      # the same start in every column
        inner, gap = layout.body_width, 12
        each = (inner - (col["per_row"] - 1) * gap) / col["per_row"]
        for label, names in groups[col["key"]]:
            c.text(layout.body_x, yy, label, G.SMALL, container=col["name"])
            row_y, slot = yy + 18, 0
            for name in names:
                node = f"{col['name']}-{label.split(',')[0].split()[0]}-{name.replace(' *', '').replace(' ', '-')}"
                if name in wide:
                    if slot:
                        row_y, slot = row_y + CHIP_PITCH, 0
                    chip(c, node, layout.body_x, row_y, inner, name, col["accent"], col["name"])
                    row_y += CHIP_PITCH
                    continue
                chip(c, node, layout.body_x + slot * (each + gap), row_y, each, name, col["accent"], col["name"])
                slot += 1
                if slot == col["per_row"]:
                    row_y, slot = row_y + CHIP_PITCH, 0
            if slot:
                row_y += CHIP_PITCH
            yy = row_y - (CHIP_PITCH - CHIP_H) + GROUP_GAP
        bottom = max(bottom, layout.box.bottom)
    bottom = G.note(
        c, "verdict-reading", bottom + 34, "HOW TO READ IT",
        [
            "A client acts on the outcome first and on the code second. After a code that it does not "
            "know: rejected means that the frame was not admitted, declined means that the request never "
            "executes, and ended means possibly executed.",
            "* In a response that names no request, bad_frame and shutdown count as not executed only "
            "when the body binds the response to the client's chain. Otherwise the request is possibly executed.",
        ],
    ).bottom
    return G._finish(c, bottom)


def ncp2_lockstep():
    """Scenario 1 of finding D1: a delayed step, a recovery, and a copy of the first open."""
    c = G.Canvas(
        "ncp2-lockstep", G.WIDTH, 2000,
        "Lockstep recovery: a delayed step and a copy of open",
        "A step is delayed, the client recovers in a new session, and a copy of the first open arrives. "
        "With a session name as holder, the late step ran after the verdict that it did not. With an "
        "opening as holder, it is declined. " + UNRELEASED,
    )
    y = G.header(c, "NCP 2 LOCKSTEP", "A lost step gets one verdict, and it stays true", "REVISION 6")
    notes_x = 900
    notes_w = G.WIDTH - G.MARGIN - notes_x
    client_head = G.card(c, "client", G.MARGIN, y + 6, 300, "Client", subtitle="Steps the world").box
    owner_head = G.card(c, "owner", 560, y + 6, 300, "Owner", subtitle="Keeps one clock", accent="turquoise").box
    explanations = [
        ("1", "A step is on its way", "lapis", None,
         "The client sends step s for tick 42 in its first opening. No response arrives in time. "
         "The call ends: s possibly ran."),
        ("2", "Recover in a new session", "turquoise", 352,
         "The client opens a new session. The open response reports the clock and takes nothing. "
         "A take request, which acknowledges that response, makes the new opening the holder and "
         "returns the final clock: tick 41. The client concludes that s did not run, and never will."),
        ("3", "A copy of the first open", "pomegranate", None,
         "A party on the path sends the first open again, on a third connection. The owner accepts "
         "it as a third opening, with the same session name and a new nonce."),
        ("4", "The delayed step arrives", "pomegranate", None,
         "Step s reaches the first opening, whose owner still waits for its next request. What "
         "happens depends on what the holder is."),
    ]
    boxes = []
    cursor = owner_head.bottom + 30
    for number, title, accent, height, body in explanations:
        layout = G.card(c, f"step-{number}", notes_x, cursor, notes_w, title, body, number=number, accent=accent, h=height)
        boxes.append(layout.box)
        cursor = layout.box.bottom + 14
    bottom = cursor + 10
    client_line = G.lifeline(c, "client-line", client_head.cx, client_head.bottom, bottom)
    owner_line = G.lifeline(c, "owner-line", owner_head.cx, owner_head.bottom, bottom)
    # 1. The step leaves the client and waits in the network.
    middle = boxes[0].cy
    delayed = G.pill(c, "s-delayed", 470, middle - 19, "DELAYED", "pomegranate")
    c.connector("s-sent", [(client_line.right, middle), (delayed.x, middle)], "client-line", "s-delayed", "lapis")
    c.text((client_line.right + delayed.x) / 2, middle - 16, "step s, tick 42",
           G.Style("sans", 25, 600, color="ink"), anchor="middle")
    # 2. The recovery: open reports, take takes.
    middle = boxes[1].cy
    G.message(c, "open-2", client_line, owner_line, middle - 120, "open, a new session", "client-line", "owner-line", "lapis")
    G.message(c, "report-2", owner_line, client_line, middle - 40, "ok, report: tick 41, term 7", "owner-line", "client-line")
    G.message(c, "take-2", client_line, owner_line, middle + 40, "take, term 7", "client-line", "owner-line", "lapis")
    G.message(c, "taken-2", owner_line, client_line, middle + 120, "ok, final: tick 41, term 8", "owner-line", "client-line")
    # 3. The copy of the first open, and 4. the delayed step, arrive from the network.
    for name, label, box in (("copy", "COPY OF THE FIRST OPEN", boxes[2]), ("arrives", "STEP s ARRIVES", boxes[3])):
        middle = box.cy
        source = G.pill(c, f"{name}-pill", client_line.right + 26, middle - 19, label, "pomegranate")
        c.connector(name, [(source.right, middle), (owner_line.x, middle)], f"{name}-pill", "owner-line", "pomegranate")
    label_y = bottom + 70
    c.text(G.MARGIN, label_y, "WHEN THE DELAYED STEP ARRIVES", G.EYEBROW)
    results = G.card_row(
        c, label_y + 26,
        [
            dict(name="before", title="The holder is a session name", subtitle="Until revision 4",
                 accent="pomegranate",
                 body="The copy of open made the session name the holder again. Step s ran, and the "
                      "world moved to tick 42. The verdict that s did not run was false."),
            dict(name="after", title="The holder is an opening", subtitle="From revision 6",
                 accent="turquoise",
                 body="The second opening holds the ticks, and the copy of open took nothing. Step s "
                      "is declined and never runs. The verdict stays true."),
        ],
    )
    bottom = G.note(
        c, "lockstep-boundary", results[0].box.bottom + 34, "WHAT A COPY CAN STILL DO",
        "A copy of open opens a session and reads the clock. It cannot take the ticks: a take must "
        "acknowledge the open response of its own opening, which holds a fresh nonce. An exhaustive "
        "check of the Python SDK with up to two faults found no false verdict. The profile is not proved.",
    ).bottom
    return G._finish(c, bottom)


def ladder_rows():
    """The checks of rules 7.3.1 to 7.3.10. The codes of each rule come from spec/ncp2-rules.json."""
    by_rule = {}
    for entry in RULES["codes"]:
        by_rule.setdefault(entry["rule"], {}).setdefault(entry["outcome"], []).append(entry["code"])

    def codes(number):
        found = by_rule.get(f"7.3.{number}", {})
        return "; ".join(f"{outcome}: {', '.join(names)}" for outcome, names in found.items())

    return [
        (1, "Is the frame bad?", ["byte stream: ended: bad_frame; Zenoh: no answer"], "lapis"),
        (2, "Is ncp not 2?", [codes(2)], "pomegranate"),
        (3, "Does the owner hold no session?",
         ["open with seq 0: start a session (section 7.1)", "otherwise " + codes(3)], "muted"),
        (4, "Is it another session?", [codes(4)], "pomegranate"),
        (5, "Is seq equal to high?",
         ["the same request: the kept response again", "another request: " + codes(5)], "muted"),
        (6, "Is seq below high?", [codes(6)], "pomegranate"),
        (7, "Is seq above high + 1?", [codes(7)], "pomegranate"),
        (8, "Has the session ended?", [codes(8)], "pomegranate"),
        (9, "Is ack missing or wrong?", [codes(9)], "pomegranate"),
        (10, "Is it open, or does the owner stop?", [codes(10)], "muted"),
    ]


def ncp2_ladder():
    """Owner rules 7.3.1 to 7.3.13 as one path with an exit at each check."""
    c = G.Canvas(
        "ncp2-ladder", G.WIDTH, 2200,
        "The owner's checks for one frame, in order",
        "Thirteen checks in the order of section 7.3. A frame leaves at the first check that fails, with "
        "the outcome and code beside it. A frame that passes ten checks is admitted, and the owner keeps "
        "every answer from that point. " + UNRELEASED,
    )
    y = G.header(c, "NCP 2 OWNER RULES", "A frame leaves at the first check that fails", f"REVISION {RULES['revision']}")
    x = G.MARGIN
    for name, label, color in (("legend-unknown", "possibly executed", "pomegranate"),
                               ("legend-no", "not executed", "lapis"),
                               ("legend-two", "two answers", "muted")):
        x = G.legend_line(c, name, x, y + 34, label, color)
    check_x, check_w, exit_x = G.MARGIN, 620, 728
    exit_w = G.WIDTH - G.MARGIN - exit_x
    top, previous = y + 70, None
    for number, question, exits, color in ladder_rows():
        h = 62 if len(exits) == 1 else 96
        check, leave = f"check-{number}", f"exit-{number}"
        box = c.node(check, G.Box(check_x, top, check_w, h))
        c.shape("rect", x=check_x, y=top, w=check_w, h=h, rx=12, fill="card", stroke="lapis", stroke_width=3)
        G.badge(c, f"{check}-number", check_x + 40, top + h / 2, str(number), "lapis", parent=check)
        c.text(check_x + 78, top + h / 2 + 9, question, G.TITLE_NARROW, container=check)
        c.node(leave, G.Box(exit_x, top, exit_w, h))
        c.shape("rect", x=exit_x, y=top, w=exit_w, h=h, rx=12, fill="tint", stroke=color, stroke_width=3)
        for index, line in enumerate(exits):
            base = top + (40 if len(exits) == 1 else 38 + index * 34)
            c.text(exit_x + 22, base, line, G.CELL, container=leave)
        c.connector(f"leave-{number}", [(box.right, top + h / 2), (exit_x, top + h / 2)], check, leave, color)
        if previous is not None:
            c.connector(f"pass-{number}", [(previous.cx, previous.bottom), (previous.cx, top)],
                        f"check-{number - 1}", check, "turquoise")
        previous, top = box, top + h + 34
    band_h = 70
    c.node("admit", G.Box(G.MARGIN, top, G.WIDTH - 2 * G.MARGIN, band_h))
    c.shape("rect", x=G.MARGIN, y=top, w=G.WIDTH - 2 * G.MARGIN, h=band_h, rx=10, fill="note")
    c.shape("rect", x=G.MARGIN, y=top, w=10, h=band_h, rx=5, fill="saffron")
    c.text(G.MARGIN + 32, top + 44, "11   Admitted. The owner keeps every response from here on, and its answer never changes.",
           G.CELL, container="admit")
    c.connector("pass-11", [(previous.cx, previous.bottom), (previous.cx, top)], "check-10", "admit", "turquoise")
    top += band_h + 34
    answers = [("ok: the result", "turquoise"), ("declined: unknown_op, body_invalid", "lapis"),
               ("ended: result_too_large", "turquoise"), ("ended: owner_failure", "pomegranate")]
    layout = G.card(
        c, "execute", G.MARGIN, top, G.WIDTH - 2 * G.MARGIN, "Execute the request",
        "The owner calls the application at most once. close and ncp.ping need no application.",
        number="12", extra=2 * CHIP_PITCH + 70,
    )
    c.connector("pass-12", [(previous.cx, top - 34), (previous.cx, top)], "admit", "execute", "turquoise")
    each = (layout.body_width - 12) / 2
    for index, (text, color) in enumerate(answers):
        chip(c, f"answer-{index}", layout.body_x + (index % 2) * (each + 12), layout.body_y - 8 + (index // 2) * CHIP_PITCH,
             each, text, color, "execute")
    c.text(layout.body_x, layout.body_y - 8 + 2 * CHIP_PITCH + 36,
           "13   The owner keeps the response. After ended, or after close, the session is over.", G.CELL, container="execute")
    bottom = G.note(
        c, "ladder-why", layout.box.bottom + 34, "WHY THE ORDER MATTERS",
        "A copy of the last admitted request leaves at check 5 with the kept response, so it never executes "
        "twice. No check before check 11 changes any state. For the client, a rejected request other than "
        "open still means possibly executed: the owner can have lost the session and opened it again.",
    ).bottom
    return G._finish(c, bottom)


FIGURES = {"ncp2-verdicts": ncp2_verdicts, "ncp2-lockstep": ncp2_lockstep, "ncp2-ladder": ncp2_ladder}

if __name__ == "__main__":
    out = Path(sys.argv[1])
    failed = False
    for name, build in FIGURES.items():
        canvas = build()
        problems = canvas.problems() + G.contrast_problems(canvas) + G.text_rule_problems(canvas)
        for theme in G.THEMES:
            svg = canvas.render(theme)
            problems += G.accessibility_problems(f"{name}-{theme['name']}", svg)
            (out / f"{name}-{theme['name']}.svg").write_text(svg, encoding="utf-8")
        print(f"{name}: {canvas.width:.0f} x {canvas.height:.0f}; {len(canvas.texts)} texts; problems: {len(problems)}")
        for problem in problems[:12]:
            print("   ", problem)
        failed = failed or bool(problems)
    sys.exit(1 if failed else 0)
