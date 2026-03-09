$ErrorActionPreference = "Stop"

Write-Host "[1/3] Syntax check..."
python -m py_compile mic_chunk_client.py
python -m py_compile client_mic_chunk_ui_v1/main.py
python -m py_compile client_mic_chunk_ui_v1/flow_editor/models.py

Write-Host "[2/3] Text integrity check..."
python tools/check_text_integrity.py --strict-utf8

Write-Host "[3/3] Done."

