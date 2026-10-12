#!/bin/zsh
# All sublime-log tests: watcher logic, the viewer's JS helpers (node), and the viewer in headless Chrome.
set -eu
cd "${0:A:h}"
python3 -m unittest test_watcher test_import -v 2>&1 | tail -5
F="$(mktemp -t sublog-fixture).json"
python3 make_fixture.py "$F" && node test_lib.js "$F"
python3 -m unittest test_viewer test_interact -v 2>&1 | tail -22
