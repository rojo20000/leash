import hashlib
import json

import pytest

from gateway import core_py as core

POLICY = "policies/scheduling_assistant.toml"
H0 = hashlib.sha256(
    b'{"n":1,"prev_hash":"' + b"0" * 64 + b'","seq":0,"tool":"ping"}'
).hexdigest()


def pol():
    return core.Policy.from_toml(POLICY)


def test_ping_and_impl():
    assert core.ping() == "leash_core ok" and core.IMPLEMENTATION == "python"


def test_policy_props():
    p = pol()
    assert p.role == "scheduling_assistant" and "send_email" in p.allowed_tools
    assert p.allowed_domains == ["clinic.example.org", "patients.example.org"]


def test_policy_order():
    p = pol()
    ev = lambda *a: p.evaluate(*a)[:2]
    assert ev("nope", ["Bogus"], [], ["x@evil.com"], 0.0) == ("block", "TOOL_NOT_ALLOWED")
    assert ev("read_record", ["Bogus", "Patient"], [], ["x@evil.com"], 0.0) == ("block", "RESOURCE_NOT_ALLOWED")
    assert ev("send_email", ["Patient"], [], ["a@Clinic.Example.org", "x@sub.clinic.example.org"], 0.0) == ("block", "EMAIL_DOMAIN_NOT_ALLOWED")
    assert ev("send_email", [], [], ["noat"], 0.0) == ("block", "EMAIL_DOMAIN_NOT_ALLOWED")
    assert ev("send_email", [], [], ["a@Clinic.Example.org"], 0.0) == ("allow", "OK")


def test_policy_two_addresses_in_one_recipient_blocked():  # A4
    p = pol()
    two = "attacker@outside-clinic.example, frontdesk@clinic.example.org"
    assert p.evaluate("send_email", [], [], [two], 0.0) == ("block", "EMAIL_DOMAIN_NOT_ALLOWED", "domain '' not allowed")
    assert p.evaluate("send_email", [], [], ["frontdesk@clinic.example.org\n"], 0.0)[0] == "block"
    assert p.evaluate("send_email", [], [], ["frontdesk@clinic.example.org"], 0.0)[:2] == ("allow", "OK")
    assert p.evaluate("send_email", [], [], ["x@Outside-Clinic.example"], 0.0)[2] == "domain 'outside-clinic.example' not allowed"


def test_policy_any_resource_checked():
    p = pol()
    assert p.evaluate("read_record", ["Patient", "Condition", "Bad2"], [], [], 0.0) == (
        "block", "RESOURCE_NOT_ALLOWED", "resource 'Condition' not allowed")
    assert p.evaluate("read_record", ["Patient", "Patient"], [], [], 0.0)[:2] == ("allow", "OK")
    assert p.evaluate("read_record", [], [], [], 0.0)[:2] == ("allow", "OK")


def test_policy_rate_window():
    p = pol()
    ids = [f"p{i}" for i in range(10)]
    assert p.evaluate("read_record", ["Patient"], ids, [], 0.0)[0] == "allow"
    assert p.evaluate("read_record", ["Patient"], ["p0"], [], 1.0)[0] == "allow"  # same id, still 10 distinct
    assert p.evaluate("read_record", ["Patient"], ["p10"], [], 2.0)[:2] == ("escalate", "RECORD_RATE_EXCEEDED")
    # entries at ts 0 expire when entry_ts <= ts - 300
    assert p.evaluate("read_record", ["Patient"], ["q"], [], 300.0)[0] == "allow"
    p.reset()
    assert p.evaluate("read_record", ["Patient"], ids, [], 0.0)[0] == "allow"


def test_policy_approval_and_errors():
    t = open(POLICY).read().replace("require_approval = []", 'require_approval = ["send_email"]')
    assert core.Policy.from_toml_str(t).evaluate("send_email", [], [], [], 0.0)[:2] == ("escalate", "TOOL_REQUIRES_APPROVAL")
    with pytest.raises(ValueError):
        core.Policy.from_toml_str('role = "x"')
    with pytest.raises(ValueError):
        core.Policy.from_toml_str(open(POLICY).read().replace("max_records = 10", 'max_records = "10"'))


def _log(tmp_path, n=4):
    p = str(tmp_path / "d" / "audit.jsonl")
    log = core.AuditLog(p)
    for i in range(n):
        log.append(json.dumps({"i": i, "s": "é"}))
    return p


def test_audit_worked_example(tmp_path):
    log = core.AuditLog(str(tmp_path / "x" / "audit.jsonl"))
    assert log.append('{"tool":"ping","n":1}') == H0
    line = open(log.path, "rb").read()
    assert line == ('{"hash":"%s","n":1,"prev_hash":"%s","seq":0,"tool":"ping"}\n' % (H0, "0" * 64)).encode()


def test_audit_append_rejects(tmp_path):
    log = core.AuditLog(str(tmp_path / "a.jsonl"))
    for bad in ["[1]", "3", '{"seq":1}', '{"hash":"x"}', '{"prev_hash":"x"}', '{"a":{"b":[1.5]}}', "nope"]:
        with pytest.raises(ValueError):
            log.append(bad)
    assert log.entries() == 0


def test_audit_resume_and_verify(tmp_path):
    p = _log(tmp_path)
    assert core.verify_log(p) == (True, None, "")
    log = core.AuditLog(p)
    assert log.entries() == 4
    log.append('{"i":4}')
    assert core.verify_log(p) == (True, None, "")


def test_audit_tamper_detection(tmp_path):
    p = _log(tmp_path)
    lines = open(p, "rb").read().split(b"\n")[:-1]

    def check(new, expect):
        q = str(tmp_path / "t.jsonl")
        open(q, "wb").write(b"".join(l + b"\n" for l in new))
        open(q + ".head", "wb").write(open(p + ".head", "rb").read())
        assert core.verify_log(q) == expect

    edited = lines[1].replace(b'"i":1', b'"i":9')
    check([lines[0], edited, *lines[2:]], (False, 1, "HASH_MISMATCH"))
    check([lines[0], *lines[2:]], (False, 1, "SEQ_MISMATCH"))
    check([lines[0], lines[2], lines[1], lines[3]], (False, 1, "SEQ_MISMATCH"))
    check(lines[:-1], (False, 3, "TRUNCATED"))
    check([], (False, 0, "TRUNCATED"))
    check([lines[0], b"", lines[2]], (False, 1, "BAD_JSON"))
    assert core.verify_log(str(tmp_path / "missing.jsonl")) == (True, None, "")


def test_prescan():
    assert core.prescan("MRN-0000042 call 555-201-0042") == [("MRN", 0, 11), ("PHONE", 17, 29)]
    t = "é 123-45-6789 a@b.org 1980-01-02 01/02/1980"
    kinds = [k for k, _, _ in core.prescan(t)]
    assert kinds == ["SSN", "EMAIL", "DOB", "DOB"]
    assert core.prescan(t)[0][1:] == (2, 13)
