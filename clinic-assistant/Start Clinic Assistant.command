#!/bin/bash
# Double-click to start Clinic Assistant. Leave this window open while you use it; close it to stop.
cd "$(dirname "$0")" || exit 1
pause() { echo; read -r -p "Press Return to close this window." _; }

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from python.org, then double-click this file again."; pause; exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
  echo "This needs Python 3.8 or newer. Install a newer Python from python.org."; pause; exit 1
fi

# Stop an older Clinic Assistant that is still using the same address (common after updating).
for pid in $(lsof -ti tcp:8642 -sTCP:LISTEN 2>/dev/null); do
  if ps -o command= -p "$pid" | grep -q "python"; then
    echo "Stopping the older Clinic Assistant that was still running..."
    kill "$pid"; sleep 1
  fi
done

python3 setup_demo.py || { pause; exit 1; }

if curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama is running. Answers come from your local model (slow on an Intel Mac: up to a minute or two)."
else
  echo "Ollama is not running, so the app starts with a stand-in model that returns placeholder answers."
  echo "To use the real model: open the Ollama app, then close this window and double-click this file again."
  export MOCK_LLM=1
fi

if lsof -ti tcp:8642 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Something else is using port 8642. Close it, then double-click this file again."; pause; exit 1
fi

# Open the browser only once the app is really answering (up to 30 seconds).
( for _ in $(seq 1 60); do
    if curl -s --max-time 1 http://127.0.0.1:8642/api/version >/dev/null 2>&1; then open "http://127.0.0.1:8642"; exit 0; fi
    sleep 0.5
  done; echo "The app didn't start. Scroll up for the error." ) &
echo
echo "Demo PIN for showing patient details and saving changes: 1234"
echo "Opening http://127.0.0.1:8642 in your browser when it's ready. Close this window to stop the app."
python3 run.py
pause
