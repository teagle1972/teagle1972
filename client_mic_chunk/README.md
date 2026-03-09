# Mic Chunk Client

Standalone client for realtime voice dialog with the `func` service.

Supported transports:
- `WebSocket` (default): dual-channel realtime
  - control: `GET /ws/realtime/control`
  - media: `GET /ws/realtime/media`
  - legacy single-channel still supported via `--ws-single-channel` + `--ws-path /ws/realtime/audio`
- `HTTP` (legacy): `POST /api/v3/audio/chunks` for per-chunk upload mode.

It opens microphone PCM, sends fixed-size chunks continuously, and can play/save streamed TTS audio.

## 1) Install

```bash
cd client_mic_chunk
pip install -r requirements.txt
```

## 2) Run

```bash
python mic_chunk_client.py \
  --base-url http://127.0.0.1:8080 \
  --chunk-ms 100 \
  --transport ws \
  --playback
```

## 3) Common options

- `--transport ws|http`: ws for full-duplex realtime, http for legacy chunk mode
- `--ws-split-channels`: use dual websocket channels (default)
- `--ws-control-path /ws/realtime/control`: control websocket path
- `--ws-media-path /ws/realtime/media`: media websocket path
- `--ws-single-channel`: fallback to old single websocket mode
- `--ws-path /ws/realtime/audio`: single-channel websocket path (only with `--ws-single-channel`)
- `--session-id my_session_001`: fixed session id
- `--sample-rate 16000`: mic capture sample rate
- `--chunk-ms 100`: slice duration per request
- `--response-mode stream_audio|json`: http mode response mode
- `--playback`: play returned PCM stream (default on)
- `--no-playback`: disable local speaker playback
- `--output-device-index N`: choose speaker device index
- `--list-output-devices`: print all speaker devices and exit
- `--playback-sample-rate 24000`: output sample rate
- `--save-dir ./tts_pcm`: save returned audio chunks as `.pcm`
- `--max-chunks 10`: stop automatically

## 4) Notes

- For full-duplex realtime, use `--transport ws`.
- HTTP mode remains available for compatibility/testing.
- If your environment cannot install `PyAudio`, use `--response-mode json` first to verify upload/ASR flow.
- Frequency/size aligned with `test/t-1.8.py` -> `test/micDemo.py`:
  - `SEGMENT_DURATION_MS=100`
  - `DEFAULT_SAMPLE_RATE=16000`, 16bit, mono
  - one packet = `16000 * 0.1 * 2 * 1 = 3200` bytes
  - packet frequency = `10` packets/second

## 5) Developer Baseline

- Repository defaults are now standardized via:
  - `.editorconfig` (UTF-8, LF, whitespace rules)
  - `.gitattributes` (text normalization)
- Text integrity guard:
  - `python tools/check_text_integrity.py --strict-utf8`
- One-shot local check (PowerShell):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\dev_check.ps1`
