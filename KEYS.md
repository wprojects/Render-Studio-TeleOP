# Environment keys

Copy [`.env.example`](.env.example) to `.env` in **this** repo and in the sibling **DimOS** checkout. Put real values only in local `.env` files. **Never commit `.env`.**

```bash
cp .env.example .env
# also in DimOS:
cp .env.example ../DimOS/.env
```

Quest OpenArm teleop on the LAN (HTTPS `:8443`, Peak CAN-FD, Viser) works **without** any LLM, Hugging Face, or hosted-broker keys. Leave those blank unless you want extra DimOS features.

Template of record: [`.env.example`](.env.example). Names below match that file only. Placeholders only — no real secrets.

---

## Required for this TeleOP stack

These are local network / path settings, not cloud API secrets. Update them for **your** Pi.

| Name | Where | Required? | What to set |
| --- | --- | --- | --- |
| `QUEST_HOST_IP` | `.env` | **Yes** | Raspberry Pi LAN IP. Find with `hostname -I \| awk '{print $1}'`. Also paste this IP in Render robotics configuration. |
| `DIMOS_TELEOP_HOST` | `.env` | **Yes** | Same Pi LAN IP (Quest page + Connect API). |
| `DIMOS_TELEOP_PORT` | `.env` | Yes (default is fine) | Quest HTTPS port. Default `8443`. |
| `DIMOS_CONNECT_API_HOST` | `.env` | Yes (default is fine) | Bind address for `connect_api.py`. Default `0.0.0.0`. |
| `DIMOS_CONNECT_API_PORT` | `.env` | Yes (default is fine) | Connect API HTTP port. Default `8450`. |
| `DIMOS_ROOT` | `.env` (this repo) | **Yes** for Connect API | Path to the DimOS checkout. Default `../DimOS`. |
| `LEFT_CAN_PORT` | `.env` | **Yes** for real OpenArm | Left arm bus. This stack: `can1`. |
| `RIGHT_CAN_PORT` | `.env` | **Yes** for real OpenArm | Right arm bus. This stack: `can0`. |
| `DISPLAY` | `.env` | **Yes** for Viser on the Pi | Usually `:0`. |

Then add the same LAN IP on Render (source of truth): [robotics configuration](https://render3d.app/getting-started.html#robotics-configuration).

---

## Optional — extra features only

**Not needed** for Quest + OpenArm + CAN + Render LAN linking.

| Name | Where | Required? | When to set |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | `.env` | **Optional** | DimOS LLM / agentic blueprints (natural-language control). |
| `ANTHROPIC_API_KEY` | `.env` | **Optional** | Alternate LLM provider in DimOS agents. |
| `ALIBABA_API_KEY` | `.env` | **Optional** | Qwen / Alibaba VL models in DimOS. |
| `HF_TOKEN` | `.env` | **Optional** | Hugging Face Hub gated models. |
| `HUGGINGFACE_ACCESS_TOKEN` | `.env` | **Optional** | Same role as `HF_TOKEN`; some DimOS paths read this name. |
| `HUGGINGFACE_PRV_ENDPOINT` | `.env` | **Optional** | Private Hugging Face inference endpoint. Leave blank. |
| `TRANSPORTS__BROKER__API_KEY` | `.env` | **Optional** | Hosted **dimTELE** broker ([teleop.dimensionalos.com](https://teleop.dimensionalos.com)). Not used for local Quest `:8443`. |
| `TRANSPORTS__BROKER__BROKER_URL` | `.env` | **Optional** | Broker URL. Default in the example is the public hosted broker. Only relevant if you use dimTELE. |
| `TRANSPORTS__BROKER__ROBOT_ID` | `.env` | **Optional** | Override robot id on the hosted broker. |
| `TRANSPORTS__BROKER__ROBOT_NAME` | `.env` | **Optional** | Override display name on the hosted broker. |
| `WEBRTC_SERVER_HOST` | `.env` | **Optional** | Local WebRTC bind (hosted / other robots). Default `0.0.0.0`. |
| `WEBRTC_SERVER_PORT` | `.env` | **Optional** | Local WebRTC port. Default `9991`. |
| `ROBOT_IP` | `.env` | **Optional** | IP of a **Unitree / other DimOS robot**, not this OpenArm CAN Pi. Leave blank for Quest OpenArm. |
| `CONN_TYPE` | `.env` | **Optional** | DimOS connection type for other robots. Example default `webrtc`. |
| `TEST_RTSP_URL` | `.env` | **Optional** | Test camera RTSP URL. Leave blank. |

---

## What you do **not** put in `.env`

- GitHub tokens (`ghp_`, `gho_`). Use `gh auth login`.
- TLS private keys / `*.pem` (DimOS generates teleop certs locally).
- Passwords, Peak CAN serials, or this Pi’s systemd unit paths.

---

## Quick rule

| Goal | Keys to fill |
| --- | --- |
| Quest + OpenArm + Render on the LAN | `QUEST_HOST_IP`, `DIMOS_TELEOP_HOST`, CAN ports, `DIMOS_ROOT`, `DISPLAY` |
| LLM / agents | `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` / `ALIBABA_API_KEY` |
| Gated HF models | `HF_TOKEN` or `HUGGINGFACE_ACCESS_TOKEN` |
| Hosted dimTELE (cloud broker) | `TRANSPORTS__BROKER__API_KEY` |
