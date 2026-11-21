#!/usr/bin/env bash
# Build dist/clinic-assistant-<version>-install.tgz from the committed git HEAD.
# data/ is left out entirely, so unpacking over an existing install never replaces the live
# clinic.db, vectors.sqlite, users.json or audit log. Uncommitted changes are not included.
#   bash scripts/make_install_tarball.sh
#   then on the Mac:  tar -xzf clinic-assistant-<version>-install.tgz -C ~/Downloads/clinic-assistant
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
ver=$(python3 -c 'import re,pathlib; print(re.search(r"\"(.+)\"", pathlib.Path("app/__init__.py").read_text()).group(1))')
mkdir -p dist
out="dist/clinic-assistant-${ver}-install.tgz"
# every tracked file except data/ and compiled caches
git ls-files -z | grep -zv -e '^data/' -e '__pycache__/' -e '\.pyc$' | tar --null -T - -czf "$out"
if tar -tzf "$out" | grep -q '^data/'; then echo "data/ slipped into the tarball; refusing" >&2; rm -f "$out"; exit 1; fi
echo "Built $out ($(tar -tzf "$out" | wc -l | tr -d ' ') files, no data/). HEAD $(git rev-parse --short HEAD)."
