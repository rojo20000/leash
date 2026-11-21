"""N18: case file shape and the harness in off mode. No key, no network."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml" / "eval"))
GROUPS = {"benign_call", "over_broad_read", "exfiltration", "injected_doc", "clean_doc"}
KEYS = {"id", "split", "group", "call", "document_id", "document_text", "expected", "note"}


def cases():
    return [json.loads(x) for x in (ROOT / "ml" / "eval" / "nemotron_cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def test_cases_shape():
    cs = cases()
    assert 36 <= len(cs) <= 44 and len({c["id"] for c in cs}) == len(cs)
    for c in cs:
        assert KEYS <= set(c) and c["group"] in GROUPS and c["split"] in ("dev", "holdout")
        assert {"injected", "safety_flag", "decision", "recommended_action"} <= set(c["expected"])
    for s in ("dev", "holdout"):
        assert {c["group"] for c in cs if c["split"] == s} == GROUPS


def test_document_text_comes_from_corpus():
    corpus = {}
    for x in (ROOT / "data" / "corpus" / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(x)
        corpus[row["id"]] = row
    for c in cases():
        if c["document_text"]:
            cid = re.search(r"c-\d{5}", c["note"]).group()
            assert corpus[cid]["split"] == "test" and corpus[cid]["text"] == c["document_text"]
            assert corpus[cid]["label"] == c["expected"]["injected"]
        elif c["document_id"]:
            assert c["document_id"] == c["call"]["args"]["document_id"]


def test_eval_off_mode(tmp_path, monkeypatch):
    for k, v in (("LEASH_CORE", "py"), ("LEASH_NEMOTRON", "off"), ("LEASH_WARMUP", "0")):  # restored after the test
        monkeypatch.setenv(k, v)
    import nemotron_eval
    out = tmp_path / "r0.json"
    r = nemotron_eval.main(["--mode", "off", "--round", "0", "--out", str(out)])
    assert json.loads(out.read_text())["round"] == 0
    for s in ("dev", "holdout"):
        assert {"injection", "content_safety_accuracy", "reasoner_action_agreement", "reasoner_valid_json_rate"} <= set(r[s])
        assert {"tfidf", "jailbreak", "nemoguard", "combined", "combined_tfidf_jailbreak"} == set(r[s]["injection"])
    assert r["served_by"]["nemotron"] == 0
