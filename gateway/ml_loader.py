import os


def load_ml():
    """Return (module, "real"|"stub")."""
    if os.environ.get("LEASH_ML", "").lower() != "stub":
        try:
            import ml.api as m
            if m.ready():
                return m, "real"
        except ImportError:
            pass
    import gateway.ml_stub as m
    return m, "stub"
