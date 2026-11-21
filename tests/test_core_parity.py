import json

import pytest

from gateway import core_py

rust = pytest.importorskip("leash_core")
POLICY = "policies/scheduling_assistant.toml"
IDS = [f"p{i}" for i in range(12)]

# (tool, resource_types, patient_ids, recipients, ts)
POLICY_CASES = [
    ("nope", ["Patient"], [], [], 0.0),
    ("read_record", ["Bogus", "Patient"], [], [], 1.0),
    ("read_record", ["Patient", "Bogus"], ["a"], [], 2.0),
    ("send_email", [], [], ["x@evil.com"], 3.0),
    ("send_email", [], [], ["x@sub.clinic.example.org"], 4.0),
    ("send_email", [], [], ["Bob@CLINIC.example.org", "noat"], 5.0),
    ("send_email", [], [], ["Bob@CLINIC.example.org", "a@b@patients.example.org"], 6.0),
    ("read_record", ["Patient"], IDS[:10], [], 10.0),
    ("read_record", ["Patient"], ["p0"], [], 11.0),
    ("read_record", ["Patient"], ["p10"], [], 12.0),
    ("read_record", ["Patient"], ["p11"], [], 311.0),
    ("read_record", ["Patient"], ["p0"], [], 400.0),
    ("search_patients", [], [], [], 1000.0),
    ("read_record", ["Patient", "Condition", "MedicationRequest", "Encounter", "DocumentReference"], ["pt-0042"], [], 1000.0),
    ("read_record", ["Patient", "Patient"], [], [], 1001.0),
    ("read_record", [], [], [], 1002.0),
]
APPROVAL = open(POLICY).read().replace("require_approval = []", 'require_approval = ["send_email"]')

RECORDS = [
    '{"tool":"ping","n":1}',
    '{"z":"é\\n\\u0001","a":[1,{"b":null,"a":true}],"big":12345678901}',
    '{"emoji":"\\ud83d\\ude00","k":"\\"q\\""}',
    "{}",
]
BAD_RECORDS = ["[1]", '{"seq":1}', '{"prev_hash":"x"}', '{"hash":"x"}', '{"a":[{"b":1.5}]}', '{"a":1.0}', "nope"]

TEXTS = [
    "MRN-0000042 call 555-201-0042",
    "é 123-45-6789 a@b.org 1980-01-02 01/02/1980 \U0001f600 MRN-1234567",
    "x123-45-6789 123-45-67890 2080-01-01 a.b+c@d-e.co.uk 12/31/2020x",
    "",
]


def run_policy(mod, text=None):
    p = mod.Policy.from_toml_str(text) if text else mod.Policy.from_toml(POLICY)
    return [p.evaluate(*c)[:2] for c in POLICY_CASES]


def test_policy_parity():
    assert run_policy(core_py) == run_policy(rust)
    assert run_policy(core_py, APPROVAL) == run_policy(rust, APPROVAL)
    a, b = core_py.Policy.from_toml(POLICY), rust.Policy.from_toml(POLICY)
    for f in ("role", "allowed_tools", "allowed_resources", "allowed_domains"):
        assert getattr(a, f) == getattr(b, f)


def test_policy_bad_toml_parity():
    for bad in ['role = "x"', "not toml [", open(POLICY).read().replace("window_seconds = 300", 'window_seconds = "x"')]:
        for m in (core_py, rust):
            with pytest.raises(ValueError):
                m.Policy.from_toml_str(bad)


def test_prescan_parity():
    for t in TEXTS:
        assert core_py.prescan(t) == rust.prescan(t), t


def _write(mod, path, records):
    log = mod.AuditLog(str(path))
    return [log.append(r) for r in records]


def test_audit_bytes_parity(tmp_path):
    hp = _write(core_py, tmp_path / "py" / "a.jsonl", RECORDS)
    hr = _write(rust, tmp_path / "rs" / "a.jsonl", RECORDS)
    assert hp == hr
    assert (tmp_path / "py" / "a.jsonl").read_bytes() == (tmp_path / "rs" / "a.jsonl").read_bytes()
    assert (tmp_path / "py" / "a.jsonl.head").read_bytes() == (tmp_path / "rs" / "a.jsonl.head").read_bytes()
    # resume across implementations
    a, b = core_py.AuditLog(str(tmp_path / "rs" / "a.jsonl")), rust.AuditLog(str(tmp_path / "py" / "a.jsonl"))
    assert a.entries() == b.entries() == len(RECORDS)
    assert a.append('{"n":9}') == b.append('{"n":9}')
    assert (tmp_path / "py" / "a.jsonl").read_bytes() == (tmp_path / "rs" / "a.jsonl").read_bytes()


def test_audit_rejects_parity(tmp_path):
    for m in (core_py, rust):
        log = m.AuditLog(str(tmp_path / m.IMPLEMENTATION / "a.jsonl"))
        for bad in BAD_RECORDS:
            with pytest.raises(ValueError):
                log.append(bad)
        assert log.entries() == 0


def test_verify_parity_on_tampered_copies(tmp_path):
    _write(core_py, tmp_path / "a.jsonl", [json.dumps({"i": i}) for i in range(5)])
    src = tmp_path / "a.jsonl"
    lines = src.read_bytes().split(b"\n")[:-1]
    head = (tmp_path / "a.jsonl.head").read_bytes()
    variants = {
        "ok": lines,
        "edit": [lines[0], lines[1].replace(b'"i":1', b'"i":7'), *lines[2:]],
        "delete_mid": lines[:2] + lines[3:],
        "delete_first": lines[1:],
        "swap": [lines[0], lines[2], lines[1], *lines[3:]],
        "truncate": lines[:-1],
        "empty": [],
        "blank_line": [lines[0], b"", *lines[1:]],
        "garbage": [lines[0], b"{not json"],
        "not_object": [lines[0], b"[1]"],
        "bad_prev": [lines[0], lines[1].replace(lines[0][9:15], b"ffffff"), *lines[2:]],
    }
    expected = {"edit": (False, 1, "HASH_MISMATCH"), "delete_mid": (False, 2, "SEQ_MISMATCH"),
                "swap": (False, 1, "SEQ_MISMATCH"), "truncate": (False, 4, "TRUNCATED"), "ok": (True, None, "")}
    for name, ls in variants.items():
        p = tmp_path / f"v_{name}.jsonl"
        p.write_bytes(b"".join(x + b"\n" for x in ls))
        (tmp_path / f"v_{name}.jsonl.head").write_bytes(head)
        r_py, r_rs = core_py.verify_log(str(p)), rust.verify_log(str(p))
        assert r_py == r_rs, name
        if name in expected:
            assert r_py == expected[name], name
    assert core_py.verify_log(str(tmp_path / "nope.jsonl")) == rust.verify_log(str(tmp_path / "nope.jsonl")) == (True, None, "")
    (tmp_path / "nope.jsonl.head").write_bytes(head)
    assert core_py.verify_log(str(tmp_path / "nope.jsonl")) == rust.verify_log(str(tmp_path / "nope.jsonl")) == (False, 0, "TRUNCATED")


def test_worked_example_hash(tmp_path):
    for m in (core_py, rust):
        h = m.AuditLog(str(tmp_path / m.IMPLEMENTATION / "x.jsonl")).append('{"tool":"ping","n":1}')
        assert h == core_py_h0()


def core_py_h0():
    import hashlib
    return hashlib.sha256(b'{"n":1,"prev_hash":"' + b"0" * 64 + b'","seq":0,"tool":"ping"}').hexdigest()
