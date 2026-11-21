use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Write;

pub const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";

fn canon(v: &Value) -> String {
    serde_json::to_string(v).unwrap()
}

fn sha(v: &Value) -> String {
    hex::encode(Sha256::digest(canon(v).as_bytes()))
}

fn has_float(v: &Value) -> bool {
    match v {
        Value::Number(n) => n.is_f64(),
        Value::Array(a) => a.iter().any(has_float),
        Value::Object(o) => o.values().any(has_float),
        _ => false,
    }
}

fn read_lines(path: &str) -> Result<Vec<String>, String> {
    let data = String::from_utf8_lossy(&fs::read(path).map_err(|e| e.to_string())?).into_owned();
    if data.is_empty() {
        return Ok(vec![]);
    }
    let mut lines: Vec<String> = data.split('\n').map(String::from).collect();
    if lines.last().is_some_and(|l| l.is_empty()) {
        lines.pop();
    }
    Ok(lines)
}

pub struct AuditCore {
    pub path: String,
    n: usize,
    next: u64,
    prev: String,
}

impl AuditCore {
    pub fn open(path: &str) -> Result<Self, String> {
        let p = std::path::Path::new(path);
        if let Some(d) = p.parent() {
            fs::create_dir_all(d).map_err(|e| e.to_string())?;
        }
        if !p.exists() {
            fs::File::create(p).map_err(|e| e.to_string())?;
        }
        let lines = read_lines(path)?;
        let (mut next, mut prev) = (0, GENESIS.to_string());
        if let Some(l) = lines.last() {
            let v: Value = serde_json::from_str(l).map_err(|e| e.to_string())?;
            next = v["seq"].as_u64().ok_or("last line has no seq")? + 1;
            prev = v["hash"].as_str().ok_or("last line has no hash")?.to_string();
        }
        Ok(AuditCore { path: path.to_string(), n: lines.len(), next, prev })
    }

    pub fn entries(&self) -> usize {
        self.n
    }

    pub fn append(&mut self, record_json: &str) -> Result<String, String> {
        let v: Value = serde_json::from_str(record_json).map_err(|e| format!("record is not valid JSON: {e}"))?;
        let Value::Object(mut rec) = v else {
            return Err("record must be a JSON object".into());
        };
        if ["seq", "prev_hash", "hash"].iter().any(|k| rec.contains_key(*k)) {
            return Err("record must not contain seq, prev_hash or hash".into());
        }
        if rec.values().any(has_float) {
            return Err("record must not contain floats".into());
        }
        rec.insert("seq".into(), Value::from(self.next));
        rec.insert("prev_hash".into(), Value::from(self.prev.clone()));
        let h = sha(&Value::Object(rec.clone()));
        rec.insert("hash".into(), Value::from(h.clone()));
        let mut line = canon(&Value::Object(rec));
        line.push('\n');
        let mut f = fs::OpenOptions::new().append(true).create(true).open(&self.path).map_err(|e| e.to_string())?;
        f.write_all(line.as_bytes()).map_err(|e| e.to_string())?;
        fs::write(format!("{}.head", self.path), format!("{} {}\n", self.next, h)).map_err(|e| e.to_string())?;
        self.next += 1;
        self.n += 1;
        self.prev = h.clone();
        Ok(h)
    }
}

type Verdict = (bool, Option<usize>, String);

fn bad(i: usize, why: &str) -> Verdict {
    (false, Some(i), why.to_string())
}

pub fn verify_log(path: &str) -> Verdict {
    let head = fs::read(format!("{path}.head")).ok().map(|b| String::from_utf8_lossy(&b).trim().to_string());
    if !std::path::Path::new(path).exists() {
        return if head.is_none() { (true, None, String::new()) } else { bad(0, "TRUNCATED") };
    }
    let Ok(lines) = read_lines(path) else { return bad(0, "BAD_JSON") };
    let mut prev = GENESIS.to_string();
    let mut last = String::new();
    for (i, line) in lines.iter().enumerate() {
        let Ok(Value::Object(mut rec)) = serde_json::from_str::<Value>(line) else {
            return bad(i, "BAD_JSON");
        };
        if rec.get("seq").and_then(Value::as_u64) != Some(i as u64) {
            return bad(i, "SEQ_MISMATCH");
        }
        if rec.get("prev_hash").and_then(Value::as_str) != Some(prev.as_str()) {
            return bad(i, "PREV_HASH_MISMATCH");
        }
        let stored = rec.remove("hash");
        let rec: Map<String, Value> = rec;
        let want = sha(&Value::Object(rec));
        match stored.as_ref().and_then(Value::as_str) {
            Some(s) if s == want => {
                prev = want;
                last = format!("{i} {prev}");
            }
            _ => return bad(i, "HASH_MISMATCH"),
        }
    }
    if head.is_some_and(|h| h != last) {
        return bad(lines.len(), "TRUNCATED");
    }
    (true, None, String::new())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> String {
        let d = std::env::temp_dir().join(format!("leash_core_{}_{}", name, std::process::id()));
        let _ = fs::remove_dir_all(&d);
        d.join("sub").join("audit.jsonl").to_string_lossy().into_owned()
    }

    fn make(name: &str) -> (String, Vec<String>) {
        let p = tmp(name);
        let mut a = AuditCore::open(&p).unwrap();
        for i in 0..4 {
            a.append(&format!(r#"{{"i":{i},"s":"é"}}"#)).unwrap();
        }
        let lines = fs::read_to_string(&p).unwrap().lines().map(String::from).collect();
        (p, lines)
    }

    fn write<S: AsRef<str>>(p: &str, lines: &[S]) -> Verdict {
        let q = format!("{p}.t");
        fs::write(&q, lines.iter().map(|l| format!("{}\n", l.as_ref())).collect::<String>()).unwrap();
        fs::copy(format!("{p}.head"), format!("{q}.head")).unwrap();
        verify_log(&q)
    }

    #[test]
    fn audit_worked_example() {
        let p = tmp("ex");
        let mut a = AuditCore::open(&p).unwrap();
        let h = a.append(r#"{"tool":"ping","n":1}"#).unwrap();
        let want = hex::encode(Sha256::digest(
            format!(r#"{{"n":1,"prev_hash":"{GENESIS}","seq":0,"tool":"ping"}}"#).as_bytes(),
        ));
        assert_eq!(h, want);
        assert_eq!(
            fs::read_to_string(&p).unwrap(),
            format!("{{\"hash\":\"{h}\",\"n\":1,\"prev_hash\":\"{GENESIS}\",\"seq\":0,\"tool\":\"ping\"}}\n")
        );
    }

    #[test]
    fn audit_append_rejects() {
        let mut a = AuditCore::open(&tmp("rej")).unwrap();
        for b in ["[1]", "3", r#"{"seq":1}"#, r#"{"hash":"x"}"#, r#"{"a":{"b":[1.5]}}"#, "nope"] {
            assert!(a.append(b).is_err(), "{b}");
        }
        assert_eq!(a.entries(), 0);
    }

    #[test]
    fn audit_resume_and_verify() {
        let (p, _) = make("res");
        assert_eq!(verify_log(&p), (true, None, String::new()));
        let mut a = AuditCore::open(&p).unwrap();
        assert_eq!(a.entries(), 4);
        a.append(r#"{"i":4}"#).unwrap();
        assert_eq!(verify_log(&p), (true, None, String::new()));
    }

    #[test]
    fn audit_edit_delete_reorder_truncate_detected() {
        let (p, l) = make("tamper");
        let edited = l[1].replace(r#""i":1"#, r#""i":9"#);
        let r = |s: &str, k: usize| (false, Some(k), s.to_string());
        assert_eq!(write(&p, &[&l[0], &edited, &l[2], &l[3]]), r("HASH_MISMATCH", 1));
        assert_eq!(write(&p, &[&l[0], &l[2], &l[3]]), r("SEQ_MISMATCH", 1));
        assert_eq!(write(&p, &[&l[0], &l[2], &l[1], &l[3]]), r("SEQ_MISMATCH", 1));
        assert_eq!(write(&p, &[&l[0], &l[1], &l[2]]), r("TRUNCATED", 3));
        assert_eq!(write(&p, &Vec::<String>::new()), r("TRUNCATED", 0));
        assert_eq!(write(&p, &[&l[0], &String::new(), &l[2]]), r("BAD_JSON", 1));
        assert_eq!(verify_log("no/such/file.jsonl"), (true, None, String::new()));
    }
}
