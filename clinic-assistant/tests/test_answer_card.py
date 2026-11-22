"""The answer card must not claim a reviewer check that did not run.

Runs the two card functions from static/app.js under Node with a tiny stand-in for the page. Skipped when Node is
not installed (the app itself needs no Node).
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

APP_JS = Path(__file__).parent.parent / "static" / "app.js"

# What the server sends since 2.14.1: the after-model review is skipped by default (reviewer.stages = ["pre"]).
PRE_ONLY = [
    {"step": "Signed in", "status": "ok", "detail": "dr_test as clinician"},
    {"step": "Reviewer (before model)", "status": "ok", "detail": "green: no concerns (11 ms, nemotron-mini)"},
    {"step": "Local model", "status": "ok", "detail": "llama3.2:latest, 0.0s, on this machine"},
    {"step": "Reviewer (after model)", "status": "ok", "detail": "skipped (reviewer.stages)"},
    {"step": "Routed", "status": "ok", "detail": "green: no flags"},
]
BOTH = [dict(t, detail="green: no concerns (9 ms, nemotron-mini)") if t["step"] == "Reviewer (after model)" else t
        for t in PRE_ONLY]

HARNESS = r"""
const el = (tag, cls, text) => ({ text: text || "", kids: [], classes: [cls || ""],
  classList: { add(c) {} }, append(...k) { this.kids.push(...k); }, scrollIntoView() {} });
const icon = () => ({ text: "", kids: [] });
const flat = (n) => [n.text, ...(n.kids || []).map(flat)].join(" ");
%s
const out = {};
for (const [name, trace] of Object.entries(JSON.parse(process.argv.at(-1)))) {
  const log = el("div");
  addTrace(trace, log); reviewerReadout(trace, log);
  out[name] = log.kids.map(flat);
}
console.log(JSON.stringify(out));
"""


def _function(src, name):
    m = re.search(r"^function %s\(.*?^}\n" % name, src, re.S | re.M)
    assert m, name
    return m.group(0)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class AnswerCard(unittest.TestCase):
    def cards(self):
        src = APP_JS.read_text(encoding="utf-8")
        js = HARNESS % (_function(src, "addTrace") + _function(src, "reviewerReadout"))
        run = subprocess.run(["node", "-e", js, json.dumps({"pre_only": PRE_ONLY, "both": BOTH})],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_skipped_review_is_not_reported_as_no_concerns(self):
        summary, readout = (" ".join(c.split()) for c in self.cards()["pre_only"])
        self.assertIn("Reviewer (before model): no concerns", readout)
        self.assertNotIn("Reviewer (after model): no concerns", readout)
        self.assertIn("Reviewer (after model): not run", readout)
        self.assertIn("4 safety checks passed", summary)  # the skipped step is not counted as a passed check
        self.assertIn("skipped (reviewer.stages)", summary)  # and is still listed in the details

    def test_review_that_ran_still_says_no_concerns(self):
        summary, readout = (" ".join(c.split()) for c in self.cards()["both"])
        self.assertIn("Reviewer (after model): no concerns", readout)
        self.assertIn("5 safety checks passed", summary)


if __name__ == "__main__":
    unittest.main()
