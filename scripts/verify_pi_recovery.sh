#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIMOS_DIR="${1:-$REPO_DIR/../DimOS}"

if [[ ! -x "$DIMOS_DIR/.venv/bin/python" ]]; then
  echo "DimOS virtual environment not found at $DIMOS_DIR/.venv" >&2
  echo "Run 'uv sync' in the DimOS checkout first." >&2
  exit 2
fi

"$DIMOS_DIR/.venv/bin/python" -m compileall -q \
  "$DIMOS_DIR/dimos/teleop/quest" \
  "$DIMOS_DIR/dimos/robot/manipulators/openarm" \
  "$DIMOS_DIR/dimos/hardware/whole_body/damiao" \
  "$DIMOS_DIR/dimos/hardware/whole_body/openarm_damiao"

(
  cd "$DIMOS_DIR"
  .venv/bin/python -m pytest -q \
    dimos/teleop/quest/test_blueprints.py \
    dimos/teleop/quest/test_quest_teleop_module.py \
    dimos/teleop/quest/test_policy_camera_bridge.py \
    dimos/robot/manipulators/openarm/test_openarm_teleop.py \
    dimos/hardware/whole_body/damiao/test_adapter.py \
    dimos/hardware/whole_body/openarm_damiao/test_adapter.py
)

echo "Recovery source checks passed. No hardware command was sent."
