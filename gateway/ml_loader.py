import os


def load_ml():
    """Return (module, "real"|"stub"). The stub is used only when LEASH_ML=stub; missing models raise."""
    if os.environ.get("LEASH_ML", "").lower() == "stub":
        import gateway.ml_stub as m
        return m, "stub"
    import ml.api as m
    if not m.ready():
        raise RuntimeError("ML models missing: run `make data`, or set LEASH_ML=stub for tests")
    return m, "real"
