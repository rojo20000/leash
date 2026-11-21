use pyo3::prelude::*;

/// Plain-Rust core so it is unit-testable without a Python interpreter.
pub fn ping_message() -> &'static str {
    "leash_core ok"
}

/// Leash core, implemented in Rust.
#[pymodule]
mod leash_core {
    use pyo3::prelude::*;

    /// Health check: returns "leash_core ok".
    #[pyfunction]
    fn ping() -> &'static str {
        super::ping_message()
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn ping_returns_ok() {
        assert_eq!(super::ping_message(), "leash_core ok");
    }
}
