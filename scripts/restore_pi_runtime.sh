#!/usr/bin/env bash
set -euo pipefail

BASE_COMMIT="f2945fad060082dae0023f4f00cade270b097c13"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RECOVERY_DIR="$REPO_DIR/recovery/pi-runtime"
DIMOS_DIR="${1:-$REPO_DIR/../DimOS}"

if [[ ! -d "$DIMOS_DIR/.git" ]]; then
  echo "DimOS checkout not found at $DIMOS_DIR" >&2
  echo "Pass its path as the first argument." >&2
  exit 2
fi

if [[ -n "$(git -C "$DIMOS_DIR" status --porcelain)" ]]; then
  echo "Refusing to overwrite a dirty DimOS checkout at $DIMOS_DIR" >&2
  exit 3
fi

actual_commit="$(git -C "$DIMOS_DIR" rev-parse HEAD)"
if [[ "$actual_commit" != "$BASE_COMMIT" ]]; then
  echo "DimOS must be checked out at $BASE_COMMIT" >&2
  echo "Current commit is $actual_commit" >&2
  exit 4
fi

(
  cd "$REPO_DIR"
  shasum -a 256 -c recovery/pi-runtime/SHA256SUMS
)

git -C "$DIMOS_DIR" apply --check "$RECOVERY_DIR/patches/pi-hardware-working-tree.patch"
git -C "$DIMOS_DIR" apply "$RECOVERY_DIR/patches/pi-hardware-working-tree.patch"
git -C "$DIMOS_DIR" apply --check "$RECOVERY_DIR/patches/pi-runtime-compat.patch"
git -C "$DIMOS_DIR" apply "$RECOVERY_DIR/patches/pi-runtime-compat.patch"

mkdir -p "$DIMOS_DIR/dimos/teleop/quest/web/static"
cp -R "$RECOVERY_DIR/staged/quest_base/." "$DIMOS_DIR/dimos/teleop/quest/"
install -m 0644 "$RECOVERY_DIR/staged/pi_support/openarm_blueprint_teleop.py" \
  "$DIMOS_DIR/dimos/robot/manipulators/openarm/blueprints/teleop.py"
install -m 0644 "$RECOVERY_DIR/staged/pi_support/all_blueprints.py" \
  "$DIMOS_DIR/dimos/robot/all_blueprints.py"
install -m 0644 "$RECOVERY_DIR/staged/pi_support/teleop_transforms.py" \
  "$DIMOS_DIR/dimos/teleop/utils/teleop_transforms.py"

install -m 0644 "$RECOVERY_DIR/staged/quest_connect_api.py" \
  "$DIMOS_DIR/scripts/quest_connect_api.py"
install -m 0644 "$RECOVERY_DIR/staged/quest_teleop_module.py" \
  "$DIMOS_DIR/dimos/teleop/quest/quest_teleop_module.py"
install -m 0644 "$RECOVERY_DIR/staged/quest_types.py" \
  "$DIMOS_DIR/dimos/teleop/quest/quest_types.py"
install -m 0644 "$RECOVERY_DIR/staged/policy_camera_bridge.py" \
  "$DIMOS_DIR/dimos/teleop/quest/policy_camera_bridge.py"
install -m 0644 "$RECOVERY_DIR/staged/policy_store.py" \
  "$DIMOS_DIR/dimos/teleop/quest/policy_store.py"
install -m 0644 "$RECOVERY_DIR/staged/openarm_quest_teleop.py" \
  "$DIMOS_DIR/dimos/robot/manipulators/openarm/quest_teleop.py"
install -m 0644 "$RECOVERY_DIR/staged/test_quest_teleop_module.py" \
  "$DIMOS_DIR/dimos/teleop/quest/test_quest_teleop_module.py"
install -m 0644 "$RECOVERY_DIR/staged/test_policy_camera_bridge.py" \
  "$DIMOS_DIR/dimos/teleop/quest/test_policy_camera_bridge.py"
install -m 0644 "$RECOVERY_DIR/staged/test_openarm_teleop.py" \
  "$DIMOS_DIR/dimos/robot/manipulators/openarm/test_openarm_teleop.py"

echo "Recovered Pi runtime source at $DIMOS_DIR"
echo "No service was installed, restarted, or sent a robot command."
echo "Run scripts/verify_pi_recovery.sh '$DIMOS_DIR' before supervised startup."
