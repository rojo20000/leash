use regex::Regex;
use serde::Deserialize;
use std::collections::HashSet;
use std::sync::OnceLock;

#[derive(Deserialize)]
struct Tools {
    allowed: Vec<String>,
    require_approval: Vec<String>,
}
#[derive(Deserialize)]
struct Resources {
    allowed: Vec<String>,
}
#[derive(Deserialize)]
struct Rate {
    max_records: i64,
    window_seconds: i64,
}
#[derive(Deserialize)]
struct Email {
    allowed_domains: Vec<String>,
}
#[derive(Deserialize)]
struct Raw {
    role: String,
    tools: Tools,
    resources: Resources,
    rate: Rate,
    email: Email,
}

pub struct PolicyCore {
    pub role: String,
    pub tools: Vec<String>,
    pub approval: Vec<String>,
    pub resources: Vec<String>,
    pub domains: Vec<String>,
    max: i64,
    window: i64,
    win: Vec<(f64, String)>,
}

pub type Decision = (String, String, String);

// One plain ASCII address; \A..\z so the whole recipient must match (same pattern in core_py.py).
fn addr() -> &'static Regex {
    static A: OnceLock<Regex> = OnceLock::new();
    A.get_or_init(|| Regex::new(r"\A[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\z").unwrap())
}

fn d(a: &str, b: &str, c: String) -> Decision {
    (a.to_string(), b.to_string(), c)
}

impl PolicyCore {
    pub fn from_toml_str(text: &str) -> Result<Self, String> {
        let r: Raw = toml::from_str(text).map_err(|e| format!("policy: {e}"))?;
        Ok(PolicyCore {
            role: r.role,
            tools: r.tools.allowed,
            approval: r.tools.require_approval,
            resources: r.resources.allowed,
            domains: r.email.allowed_domains.iter().map(|s| s.to_lowercase()).collect(),
            max: r.rate.max_records,
            window: r.rate.window_seconds,
            win: Vec::new(),
        })
    }

    pub fn reset(&mut self) {
        self.win.clear();
    }

    pub fn evaluate(
        &mut self,
        tool: &str,
        resource_types: &[String],
        patient_ids: &[String],
        recipients: &[String],
        ts: f64,
    ) -> Decision {
        if !self.tools.iter().any(|t| t == tool) {
            return d("block", "TOOL_NOT_ALLOWED", format!("tool {tool:?} not allowed"));
        }
        if let Some(r) = resource_types.iter().find(|r| !self.resources.contains(r)) {
            return d("block", "RESOURCE_NOT_ALLOWED", format!("resource {r:?} not allowed"));
        }
        for r in recipients {
            // no trim: Rust trim and Python str.strip disagree on some characters
            let dom = addr().captures(r).map(|c| c[1].to_ascii_lowercase()).unwrap_or_default();
            if !self.domains.iter().any(|x| *x == dom) {
                return d("block", "EMAIL_DOMAIN_NOT_ALLOWED", format!("domain {dom:?} not allowed"));
            }
        }
        let cutoff = ts - self.window as f64;
        self.win.retain(|e| e.0 > cutoff);
        self.win.extend(patient_ids.iter().map(|p| (ts, p.clone())));
        let n = self.win.iter().map(|e| e.1.as_str()).collect::<HashSet<_>>().len() as i64;
        if n > self.max {
            return d(
                "escalate",
                "RECORD_RATE_EXCEEDED",
                format!("{n} distinct records in window, max {}", self.max),
            );
        }
        if self.approval.iter().any(|t| t == tool) {
            return d("escalate", "TOOL_REQUIRES_APPROVAL", format!("tool {tool:?} requires approval"));
        }
        d("allow", "OK", String::new())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const P: &str = r#"
role = "r"
[tools]
allowed = ["read_record", "send_email"]
require_approval = ["send_email"]
[resources]
allowed = ["Patient"]
[rate]
max_records = 2
window_seconds = 300
[email]
allowed_domains = ["Clinic.example.org"]
"#;
    fn v(x: &[&str]) -> Vec<String> {
        x.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn policy_order() {
        let mut p = PolicyCore::from_toml_str(P).unwrap();
        let e = |p: &mut PolicyCore, t, r: &[&str], rc: &[&str]| p.evaluate(t, &v(r), &[], &v(rc), 0.0).1;
        assert_eq!(e(&mut p, "x", &["Bad"], &["a@evil"]), "TOOL_NOT_ALLOWED");
        assert_eq!(e(&mut p, "send_email", &["Bad", "Patient"], &["a@evil"]), "RESOURCE_NOT_ALLOWED");
        assert_eq!(e(&mut p, "send_email", &["Patient"], &["a@sub.clinic.example.org"]), "EMAIL_DOMAIN_NOT_ALLOWED");
        assert_eq!(e(&mut p, "send_email", &[], &["noat"]), "EMAIL_DOMAIN_NOT_ALLOWED");
        assert_eq!(e(&mut p, "send_email", &[], &["A@CLINIC.example.org"]), "TOOL_REQUIRES_APPROVAL");
        assert_eq!(e(&mut p, "read_record", &["Patient"], &[]), "OK");
    }

    #[test]
    fn policy_recipient_single_address() {
        // A4: same cases as RECIPIENT_CASES in tests/test_core_parity.py
        let mut p = PolicyCore::from_toml_str(&P.replace("[\"Clinic.example.org\"]", "[\"Clinic.example.org\", \"nodot\"]")).unwrap();
        let mut e = |r: &str| p.evaluate("read_record", &[], &[], &v(&["frontdesk@clinic.example.org", r]), 0.0);
        for ok in ["frontdesk@clinic.example.org", "Bob@CLINIC.EXAMPLE.ORG", "a.b+c%d_e-f@clinic.example.org"] {
            assert_eq!(e(ok).1, "OK", "{ok:?}");
        }
        for bad in [
            "attacker@outside-clinic.example, frontdesk@clinic.example.org",
            "a@b@clinic.example.org",
            "x@evil.example\u{2028}@clinic.example.org",
            " frontdesk@clinic.example.org",
            "frontdesk@clinic.example.org ",
            "frontdesk@clinic.example.org\n",
            "frontdesk@clinic.example.org\u{a0}",
            "a@b",
            "a@nodot",
            "",
            "@clinic.example.org",
            "x@\u{441}linic.example.org",
            "x@clinic.example.org\u{ff20}clinic.example.org",
            "\u{e9}@clinic.example.org",
        ] {
            let r = e(bad);
            assert_eq!((r.0.as_str(), r.1.as_str(), r.2.as_str()), ("block", "EMAIL_DOMAIN_NOT_ALLOWED", "domain \"\" not allowed"), "{bad:?}");
        }
        assert_eq!(e("x@Outside-Clinic.example").2, "domain \"outside-clinic.example\" not allowed");
    }

    #[test]
    fn policy_any_resource_checked() {
        let mut p = PolicyCore::from_toml_str(P).unwrap();
        let r = p.evaluate("read_record", &v(&["Patient", "Condition", "Bad2"]), &[], &[], 0.0);
        assert_eq!((r.1.as_str(), r.2.as_str()), ("RESOURCE_NOT_ALLOWED", "resource \"Condition\" not allowed"));
        assert_eq!(p.evaluate("read_record", &v(&["Patient", "Patient"]), &[], &[], 0.0).1, "OK");
        assert_eq!(p.evaluate("read_record", &[], &[], &[], 0.0).1, "OK");
    }

    #[test]
    fn policy_rate_window() {
        let mut p = PolicyCore::from_toml_str(P).unwrap();
        let ev = |p: &mut PolicyCore, id: &str, ts| p.evaluate("read_record", &[], &v(&[id]), &[], ts).1;
        assert_eq!(ev(&mut p, "a", 0.0), "OK");
        assert_eq!(ev(&mut p, "b", 1.0), "OK");
        assert_eq!(ev(&mut p, "a", 2.0), "OK");
        assert_eq!(ev(&mut p, "c", 3.0), "RECORD_RATE_EXCEEDED");
        assert_eq!(ev(&mut p, "d", 301.0), "RECORD_RATE_EXCEEDED"); // a@2, c@3 still in window
        assert_eq!(ev(&mut p, "e", 603.0), "OK"); // everything older expired (entry_ts <= ts - window)
    }

    #[test]
    fn policy_bad_toml() {
        assert!(PolicyCore::from_toml_str("role = 'x'").is_err());
        assert!(PolicyCore::from_toml_str(&P.replace("max_records = 2", "max_records = \"2\"")).is_err());
    }
}
