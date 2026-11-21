import importlib, logging, os
log = logging.getLogger("leash.core")

def load_core():
    """Return the core module. LEASH_CORE=py forces gateway.core_py; LEASH_CORE=rust forces leash_core
    (ImportError propagates); unset tries leash_core then falls back to gateway.core_py on ImportError."""
    choice = os.environ.get("LEASH_CORE", "").lower()
    if choice != "py":
        try:
            mod = importlib.import_module("leash_core")
            log.info("loaded core: rust")
            return mod
        except ImportError:
            if choice == "rust":
                raise
    mod = importlib.import_module("gateway.core_py")
    log.info("loaded core: python")
    return mod
