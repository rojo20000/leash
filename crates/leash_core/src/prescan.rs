use regex::Regex;
use std::sync::OnceLock;

fn patterns() -> &'static Vec<(&'static str, Regex)> {
    static P: OnceLock<Vec<(&'static str, Regex)>> = OnceLock::new();
    P.get_or_init(|| {
        [
            ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
            ("MRN", r"\bMRN-\d{7}\b"),
            ("PHONE", r"\b\d{3}-\d{3}-\d{4}\b"),
            ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
            ("DOB", r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),
            ("DOB", r"\b\d{2}/\d{2}/\d{4}\b"),
        ]
        .into_iter()
        .map(|(k, r)| (k, Regex::new(r).unwrap()))
        .collect()
    })
}

/// (kind, start, end) in char offsets, sorted by (start, end, kind).
pub fn prescan(text: &str) -> Vec<(String, usize, usize)> {
    // byte offset -> char offset; identity for ASCII
    let map: Option<Vec<usize>> = if text.is_ascii() {
        None
    } else {
        let mut m = vec![0; text.len() + 1];
        for (ci, (bi, c)) in text.char_indices().enumerate() {
            for k in 0..c.len_utf8() {
                m[bi + k] = ci;
            }
        }
        m[text.len()] = text.chars().count();
        Some(m)
    };
    let conv = |b: usize| map.as_ref().map_or(b, |m| m[b]);
    let mut out: Vec<(String, usize, usize)> = patterns()
        .iter()
        .flat_map(|(k, re)| re.find_iter(text).map(move |m| (k.to_string(), m.start(), m.end())))
        .map(|(k, s, e)| (k, conv(s), conv(e)))
        .collect();
    out.sort_by(|a, b| (a.1, a.2, &a.0).cmp(&(b.1, b.2, &b.0)));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prescan_example() {
        let r = prescan("MRN-0000042 call 555-201-0042");
        assert_eq!(r, vec![("MRN".into(), 0, 11), ("PHONE".into(), 17, 29)]);
    }

    #[test]
    fn prescan_char_offsets_and_kinds() {
        let r = prescan("é 123-45-6789 a@b.org 1980-01-02 01/02/1980");
        let kinds: Vec<&str> = r.iter().map(|x| x.0.as_str()).collect();
        assert_eq!(kinds, ["SSN", "EMAIL", "DOB", "DOB"]);
        assert_eq!((r[0].1, r[0].2), (2, 13));
    }
}
