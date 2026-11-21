#!/bin/bash
# Double-click to start Clinic Assistant. Leave this window open while you use it; close it to stop.
cd "$(dirname "$0")" || exit 1
pause() { echo; read -r -p "Press Return to close this window." _; }

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from python.org, then double-click this file again."; pause; exit 1
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

(sleep 2; open "http://127.0.0.1:8642") &
echo
echo "Opening http://127.0.0.1:8642 in your browser. Close this window to stop the app."
python3 run.py
pause
