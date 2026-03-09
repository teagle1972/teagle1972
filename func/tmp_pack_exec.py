import os
import stat
import zipfile
from pathlib import Path

root = Path('.')
out = Path('func_full_package_exec.zip')
exclude_files = {
    out.name,
    'func_full_package.zip',
    'func_asr_mnt_tos_alllogs_exec.zip',
    'run.log',
    'output.pcm',
    'api_test_cases.json',
    'run_api_tests.py',
    'micDemo.py',
    'ws_server.py',
    't-1.8.py',
    'tmp_pack_exec.py',
}
exclude_dirs = {
    '__pycache__',
    'audio_chunks',
    'logs',
}
keep_root_files = {
    '__init__.py',
    'main.py',
    'requirements.txt',
    'requirements.lock',
    'run.sh',
}

with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for path in sorted(root.rglob('*')):
        rel = path.as_posix()
        if rel == out.name or path.name in exclude_files:
            continue
        if any(part in exclude_dirs for part in path.parts):
            continue
        if len(path.parts) == 1 and path.is_file() and path.name not in keep_root_files:
            continue

        if path.is_dir():
            zi = zipfile.ZipInfo(rel.rstrip('/') + '/')
            zi.create_system = 3
            zi.external_attr = (stat.S_IFDIR | 0o755) << 16
            zf.writestr(zi, b'')
            continue

        data = path.read_bytes()
        zi = zipfile.ZipInfo(rel)
        zi.create_system = 3
        mode = (stat.S_IFREG | 0o755) if rel == 'run.sh' else (stat.S_IFREG | 0o644)
        zi.external_attr = mode << 16
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(zi, data)

print(out)
