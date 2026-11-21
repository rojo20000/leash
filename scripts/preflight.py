"""Toolchain pre-flight for Leash. Prints PASS/FAIL per check; exits 1 on any FAIL."""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("LEASH_MODEL", "qwen3.5:9b")
HOME = Path.home()
LOCAL = Path(os.environ.get("LOCALAPPDATA", HOME))
# New installs may not be on PATH until the shell/app restarts; look in the usual places too.
EXTRA_DIRS = [
    ROOT / ".venv" / "Scripts",
    ROOT / ".venv" / "bin",
    HOME / ".cargo" / "bin",
    LOCAL / "Programs" / "Ollama",
    LOCAL / "Microsoft" / "WinGet" / "Links",
    LOCAL / "Microsoft" / "WinGet" / "Packages" / "ezwinports.make_Microsoft.Winget.Source_8wekyb3d8bbwe" / "bin",
    Path("C:/Program Files/Eclipse Adoptium"),
]
os.environ["PATH"] = os.pathsep.join([str(d) for d in EXTRA_DIRS] + [os.environ.get("PATH", "")])

failed = False


def report(ok, name, detail):
    global failed
    failed |= ok is False
    tag = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
    print(f"{tag:4}  {name:<14} {detail}")


def find_exe(cmd):
    exe = shutil.which(cmd)
    if not exe and cmd == "java":  # Temurin installs under a versioned folder
        hits = sorted(Path("C:/Program Files/Eclipse Adoptium").glob("*/bin/java.exe"))
        exe = str(hits[-1]) if hits else None
    return exe


def version(cmd, args=("--version",)):
    exe = find_exe(cmd)
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"
    out = (r.stdout + r.stderr).strip().splitlines()
    return out[0] if out else ""


def check_tool(name, cmd, args=("--version",), minimum=None, optional=False):
    v = version(cmd, args)
    if v is None:
        report(None if optional else False, name, "not found" + (" (optional)" if optional else ""))
        return
    if minimum:
        m = re.search(r"(\d+)\.(\d+)", v)
        if not m or tuple(map(int, m.groups())) < minimum:
            report(False, name, f"{v} (need {'.'.join(map(str, minimum))}+)")
            return
    report(True, name, v)


def nemotron_checks():
    """Nemotron rows: (ok True/False/None, name, detail). Never prints or returns any part of the key."""
    import tempfile

    sys.path.insert(0, str(ROOT))
    import leash.nemotron as nm

    rows = []
    from_env = bool(os.environ.get("NVIDIA_API_KEY"))
    nm.load_dotenv()
    has_key = bool(os.environ.get("NVIDIA_API_KEY"))
    if has_key:
        rows.append((True, "nvidia_key", "set (from " + ("environment)" if from_env else ".env)")))
    else:
        rows.append((False, "nvidia_key", "NVIDIA_API_KEY not set: add NVIDIA_API_KEY=... to leash/.env "
                     "(git-ignored). Live Nemotron is off; replay mode still works."))
    saved = {k: os.environ.get(k) for k in ("LEASH_NEMOTRON", "LEASH_NEMOTRON_RECORDINGS")}
    with tempfile.TemporaryDirectory() as tmp:  # preflight writes no recordings
        os.environ["LEASH_NEMOTRON"], os.environ["LEASH_NEMOTRON_RECORDINGS"] = "live", tmp
        try:
            nm._reset()
            ids = nm.list_models(refresh=True)
            if ids:
                roles = "; ".join(
                    f"{r}={i['id']}" + (f" (swap from {i['requested']})" if i["swapped"] else "")
                    for r, i in nm.config()["models"].items())
                rows.append((True, "nvidia_models", f"{len(ids)} models; {roles}"))
            else:
                rows.append((False, "nvidia_models", nm._models_error or "no models returned"))
            if has_key:
                r = nm.chat([{"role": "user", "content": "Reply with the single word ok."}], max_tokens=5)
                rows.append((True, "lightning_call", f"{r.latency_ms:.0f} ms, {r.model}") if r.ok
                            else (False, "lightning_call", r.error))
            else:
                rows.append((None, "lightning_call", "no key"))
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            nm._reset()
    return rows


def main():
    if sys.argv[1:] == ["--only", "nemotron"]:
        for row in nemotron_checks():
            report(*row)
        sys.exit(1 if failed else 0)
    py = sys.version.split()[0]
    report(sys.version_info >= (3, 12), "python", f"{py} ({sys.executable})")
    if find_exe("uv"):
        check_tool("uv", "uv")
    else:
        check_tool("pip", "pip")
    check_tool("cargo", "cargo")
    check_tool("rustc", "rustc")
    check_tool("maturin", "maturin")
    check_tool("ollama", "ollama")
    check_tool("git", "git")
    check_tool("gh", "gh")
    check_tool("make", "make")
    check_tool("java", "java", ("-version",), optional=True)

    try:
        import leash_core

        msg = leash_core.ping()
        report(msg == "leash_core ok", "leash_core", repr(msg))
    except Exception as e:  # noqa: BLE001
        report(False, "leash_core", f"{type(e).__name__}: {e}")

    try:
        import spacy

        for name in ("en_core_web_lg", "en_core_web_sm"):
            try:
                spacy.load(name)
                report(True, "spacy model", name)
                break
            except OSError:
                continue
        else:
            report(False, "spacy model", "neither en_core_web_lg nor en_core_web_sm loads")
    except Exception as e:  # noqa: BLE001
        report(False, "spacy model", f"{type(e).__name__}: {e}")

    tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "What is the weather in Chicago? Use the tool."}],
        "tools": [tool],
        "think": False,
        "stream": False,
    }
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.load(resp)
        calls = data.get("message", {}).get("tool_calls") or []
        names = [c.get("function", {}).get("name") for c in calls]
        report("get_weather" in names, "ollama tools", f"{MODEL} -> tool_calls={names}")
    except Exception as e:  # noqa: BLE001
        report(False, "ollama tools", f"{MODEL}: {type(e).__name__}: {e}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
