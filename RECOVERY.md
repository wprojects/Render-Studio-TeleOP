# Raspberry Pi crash recovery

The last recoverable Pi runtime is stored in [`recovery/pi-runtime`](recovery/pi-runtime/README.md). It includes the September 29 OpenArm service changes and the surviving DimOS work from the prior two weeks.

Use the pinned restore script on a fresh Pi:

```bash
./scripts/restore_pi_runtime.sh ../DimOS
./scripts/verify_pi_recovery.sh ../DimOS
```

Neither script starts the robot or sends a motion command.
