# Client Mic Chunk UI v1

Minimal desktop UI for `mic_chunk_client.py`.

This project is intentionally separated from the existing CLI client and works as a thin UI wrapper:
- starts/stops the CLI process
- parses stdout logs into structured events
- shows realtime `ASR` text and `TTS` text/status

## Features (v1)

- Realtime status bar:
  - process state
  - session id
  - transport mode
  - channel mode
  - send stats (count/avg ms)
- ASR panel:
  - show committed ASR text
  - show command field when present
- TTS panel:
  - show `tts_start` text
  - show streamed `tts_segment` text (the exact text sent to TTS)
  - show `tts_interrupted` and `tts_end`
- Runtime logs panel

## Run

From `client_mic_chunk_ui_v1`:

```bash
python main.py
```

The default command points to sibling script `..\mic_chunk_client.py`.

## Notes

- This UI depends on log patterns from `mic_chunk_client.py`.
- It does not modify the original client logic.
- UI stack is `tkinter` (Python stdlib), no extra UI dependency required.
