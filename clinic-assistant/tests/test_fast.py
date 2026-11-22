"""2.14: a faster, less jumpy reviewer for CPU laptops, the poisoned record stopped red, and the install tarball."""
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

os.environ["MOCK_LLM"] = "1"
from app import llm  # noqa: E402
from app import reviewer as rmod  # noqa: E402
from app.server import App  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Fast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.app = App(data_dir=cls.tmp)
        cls.app.policy["tiers"]["green_sample_rate"] = 0

    @classmethod
    def tearDownClass(cls):
        cls.app.db.close(); cls.app.vectors.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.cfg = dict(self.app.policy["reviewer"])
        self.seen = []
        rv = self.app.reviewer
        real = rv._ask
        self.app.reviewer._ask = lambda text: self.seen.append(text) or real(text)

    def tearDown(self):
        self.app.policy["reviewer"] = self.cfg
        self.app.reviewer.__dict__.pop("_ask", None)
        os.environ.pop("REVIEWER_STAGES", None)
        self.app.reviewer.cfg["stages"] = ["pre", "post"]  # exercise both stages; shipped default is pre only

    def sess(self, user="dr_lee", role="clinician"):
        return {"user": user, "role": role, "history": []}

    def test_shipped_settings(self):
        import json, pathlib
        shipped = json.loads((pathlib.Path(__file__).parent.parent / "config" / "policy.json").read_text())
        r, fast = shipped["reviewer"], self.app.policy["demo_fast"]
        self.assertEqual((r["timeout_s"], r["stages"], r["num_predict"]), (60, ["pre"], 80))
        self.assertTrue(fast["enabled"])
        self.assertEqual(llm.chat_options(self.app.policy)["num_predict"], 200)
        self.assertEqual(llm.chat_options(self.app.policy)["num_ctx"], 2048)

    def test_reviewer_reads_short_excerpts(self):
        self.app.ask_model(self.sess("lead_ana", "clinical_lead"), "Who needs attention first?", "chat")
        pre, post = self.seen
        self.assertTrue(pre.startswith("Question: Who needs attention first?"))
        self.assertLess(len(pre), 1200 + 600 + 100)  # not the whole schedule
        self.assertLess(len(post), 700)
        ctx = self.app.today_context(self.sess("lead_ana", "clinical_lead"))
        self.assertLessEqual(ctx["count"], 12)  # demo_fast caps the general-question context

    def test_pre_only_stage(self):
        os.environ["REVIEWER_STAGES"] = "pre"
        r = self.app.ask_model(self.sess(), "Summarise", "chat", self.app.ehr.get("syn-004"))
        steps = {t["step"]: t for t in r["trace"]}
        self.assertEqual(steps["Reviewer (after model)"]["detail"], "skipped (reviewer.stages)")
        self.assertEqual(len(self.seen), 1)

    def test_placeholder_alarms_are_dropped(self):
        self.app.reviewer._ask = lambda text: '{"tier": "red", "reasons": ["Contains identifiers [P1] and [NAME]."]}'
        r = self.app.frontdesk_ask(self.sess("desk_sam", "receptionist"), "How many patients does Dr Lee have today?")
        self.assertNotEqual(r["tier"], "red", r)
        dropped = [e for e in self.app.audit.read(20) if e["event"] == "reviewer_pre"][0]["details"]
        self.assertEqual(dropped.get("dropped_placeholder_alarms"), 1)
        # unit checks of the filter
        v = {"tier": "red", "reasons": ["The text includes patient names and phone numbers."]}
        self.assertEqual(rmod.drop_placeholder_alarms(v, "Question: when is [P1] due? [PHONE]")["tier"], "green")
        self.assertEqual(rmod.drop_placeholder_alarms(v, "Call 555-123-4567 about it")["tier"], "red")  # real number
        ask = {"tier": "red", "reasons": ["Asks for phone numbers and dates of birth."]}
        self.assertEqual(rmod.drop_placeholder_alarms(ask, "list phone numbers for each patient")["tier"], "red")
        mixed = {"tier": "amber", "reasons": ["Contains names [NAME].", "Tells a patient to stop a medicine."]}
        out = rmod.drop_placeholder_alarms(mixed, "Question: [NAME] stop it?")
        self.assertEqual((out["tier"], out["reasons"]), ("amber", ["Tells a patient to stop a medicine."]))
        self.assertIn("NOT identifiers", rmod.SYSTEM)

    def test_poisoned_record_is_red_before_any_model(self):
        called = []
        real = llm.chat
        llm.chat = lambda *a, **k: called.append(1) or "x"
        try:
            r = self.app.ask_model(self.sess(), "Summarise for handover in 3 lines.", "chat", self.app.ehr.get("syn-003"))
        finally:
            llm.chat = real
        self.assertEqual(r["tier"], "red")
        self.assertTrue(any("withheld" in x for x in r["reasons"]))
        self.assertEqual((called, self.seen), ([], []))
        docs = [i for i in self.app.reviews.all() if i["kind"] == "document" and "syn-003" in i["reasons"][0]]
        self.assertEqual((len(docs), docs[0]["tier"]), (1, "red"))
        # once a lead has dealt with the document, the note stays withheld and answers are amber
        self.app.reviews.update(docs[0]["id"], lambda it: it.update(status="confirmed") and None)
        r = self.app.ask_model(self.sess(), "Summarise", "chat", self.app.ehr.get("syn-003"))
        self.assertEqual(r["tier"], "amber")
        self.assertTrue(any("withheld" in x for x in r["reasons"]))

    def test_install_tarball_has_no_data(self):
        if not (ROOT / ".git").exists() or shutil.which("git") is None:
            self.skipTest("needs a git checkout")
        out = subprocess.run(["bash", "scripts/make_install_tarball.sh"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        tgz = next((ROOT / "dist").glob("clinic-assistant-*-install.tgz"))
        with tarfile.open(tgz) as t:
            names = t.getnames()
        self.assertIn("app/server.py", names)
        self.assertFalse([n for n in names if n.startswith("data/") or n.endswith(".pyc")])


if __name__ == "__main__":
    unittest.main()
