pub mod audit;
pub mod policy;
pub mod prescan;

use pyo3::prelude::*;

/// Plain-Rust core so it is unit-testable without a Python interpreter.
pub fn ping_message() -> &'static str {
    "leash_core ok"
}

/// Leash core, implemented in Rust.
#[pymodule]
mod leash_core {
    use crate::{audit, policy, prescan};
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    #[pymodule_export]
    const IMPLEMENTATION: &str = "rust";

    fn val<T>(r: Result<T, String>) -> PyResult<T> {
        r.map_err(PyValueError::new_err)
    }

    /// Health check: returns "leash_core ok".
    #[pyfunction]
    fn ping() -> &'static str {
        super::ping_message()
    }

    #[pyclass]
    struct Policy(policy::PolicyCore);

    #[pymethods]
    impl Policy {
        #[staticmethod]
        fn from_toml(path: &str) -> PyResult<Self> {
            let text = std::fs::read_to_string(path).map_err(|e| PyValueError::new_err(e.to_string()))?;
            Self::from_toml_str(&text)
        }
        #[staticmethod]
        fn from_toml_str(text: &str) -> PyResult<Self> {
            Ok(Policy(val(policy::PolicyCore::from_toml_str(text))?))
        }
        #[getter]
        fn role(&self) -> String {
            self.0.role.clone()
        }
        #[getter]
        fn allowed_tools(&self) -> Vec<String> {
            self.0.tools.clone()
        }
        #[getter]
        fn allowed_resources(&self) -> Vec<String> {
            self.0.resources.clone()
        }
        #[getter]
        fn allowed_domains(&self) -> Vec<String> {
            self.0.domains.clone()
        }
        fn evaluate(
            &mut self,
            tool: &str,
            resource_types: Vec<String>,
            patient_ids: Vec<String>,
            recipients: Vec<String>,
            ts: f64,
        ) -> (String, String, String) {
            self.0.evaluate(tool, &resource_types, &patient_ids, &recipients, ts)
        }
        fn reset(&mut self) {
            self.0.reset();
        }
    }

    #[pyclass]
    struct AuditLog(audit::AuditCore);

    #[pymethods]
    impl AuditLog {
        #[new]
        fn new(path: &str) -> PyResult<Self> {
            Ok(AuditLog(val(audit::AuditCore::open(path))?))
        }
        fn append(&mut self, record_json: &str) -> PyResult<String> {
            val(self.0.append(record_json))
        }
        fn entries(&self) -> usize {
            self.0.entries()
        }
        #[getter]
        fn path(&self) -> String {
            self.0.path.clone()
        }
    }

    #[pyfunction]
    fn verify_log(path: &str) -> (bool, Option<usize>, String) {
        audit::verify_log(path)
    }

    #[pyfunction(name = "prescan")]
    fn prescan_py(text: &str) -> Vec<(String, usize, usize)> {
        prescan::prescan(text)
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn ping_returns_ok() {
        assert_eq!(super::ping_message(), "leash_core ok");
    }
}
