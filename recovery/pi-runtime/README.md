# Restore the recovered Raspberry Pi runtime

This recovery pack preserves the last Pi-side work found after the October 1 crash. It does not contain secrets, recordings, TLS private keys, or robot calibration state.

## What was recovered

The primary source is the September 27 to September 29 deployment staging directory that produced the live Pi service. Saved read-only receipts show that the Pi later ran service `1.0.8` with guarded Home, the policy runner, three policy cameras, and real OpenArm Damiao hardware.

The pack contains these layers:

1. `staged/` contains the Pi runtime modules and tests. `quest_base/` restores the Quest package that did not yet exist in the pinned upstream base. `pi_support/` restores the OpenArm Quest blueprint and registry entry.
2. `patches/pi-hardware-working-tree.patch` contains the complete five-file Pi hardware layer from Render Studio's surviving DimOS integration checkout. It includes the final Damiao MIT gripper activation change from September 29 and its tests.
3. `patches/dimos-working-tree.patch` separately preserves all 22 uncommitted files found in the older Mac DimOS checkout. The files cover Quest TeleOP, CAN setup, recording, OpenArm dataset preparation, and Viser episode review. The restore script does not mix this older worktree into the Pi runtime because it has a different base commit.
4. `patches/pi-1.0.8-gripper.patch` preserves the final incremental Pi patch for audit. Its changes are already included in `pi-hardware-working-tree.patch`.
5. `evidence/` contains saved read-only Pi responses. These responses prove the deployed capabilities and version without storing credentials.

The runnable Pi recovery is pinned to DimOS commit `f2945fad060082dae0023f4f00cade270b097c13`. Do not apply it to another commit and assume parity. The archived Mac patch records its own base, `3d65f28cc7a3dbb8a68780fedda09e7dfe2b15e6`, in `manifest.json`.

## Restore a fresh Pi

Clone both repositories as siblings:

```bash
git clone https://github.com/wprojects/Render-Studio-TeleOP.git
git clone https://github.com/dimensionalOS/dimos.git DimOS
cd DimOS
git checkout f2945fad060082dae0023f4f00cade270b097c13
cd ../Render-Studio-TeleOP
./scripts/restore_pi_runtime.sh ../DimOS
cd ../DimOS
uv sync
cd ../Render-Studio-TeleOP
./scripts/verify_pi_recovery.sh ../DimOS
```

Copy `.env.example` to `.env` and restore local values manually. Never copy a private key or old access token from an unknown disk image.

## Start safely

The restore and verification scripts never start systemd, open CAN, enable motors, Home the robot, or run a policy. After the checks pass, inspect the recovered diff:

```bash
git -C ../DimOS status --short
git -C ../DimOS diff --check
```

Install service files only after updating their user names and paths for the new Pi. The saved `openarm-pi-cameras.service` is evidence from the old machine and still contains its old `/home/steve` paths.

Keep the physical E-stop reachable. Support both arms before the first service restart. Confirm that the service reports `armed=false`, `homing=false`, and `playing=false` before any supervised motion test.

## Known recovery boundary

The crashed Pi is offline, so its final filesystem cannot be hashed directly. The source is reconstructed from the exact deployment staging files, the final gripper patch, the surviving DimOS working trees, the tests that accompanied those changes, the worklog, archived command transcripts, and saved live Pi responses. The `1.0.8` version marker, the three-camera role names, the six-button compatibility path, and the digital-trigger fallback are evidence-backed later deltas applied to the staging source. `emote_store.py` is reconstructed from its observed call contract because no standalone copy survived.

The recovered modules compile and the hardware-adapter plus camera-bridge tests pass on macOS. The complete Quest suite still needs to run on the replacement Pi because its Zenoh shared-memory fixture cannot initialize inside the macOS sandbox used for this recovery.
