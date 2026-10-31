"""Codespaces launcher, not a GitHub Pages backend. Port stays private."""
import os
from pathlib import Path
import socket
import subprocess

root = Path(__file__).resolve().parents[1]
try:
    with socket.create_connection(('127.0.0.1', 8080), timeout=1):
        print('null worker already listening on port 8080')
except OSError:
    folder = root / 'output'
    folder.mkdir(exist_ok=True)
    command = [str(root / '.venv/bin/python'), '-B', str(root / 'web_server.py')]
    if os.environ.get('NULL_WEB_DYNAMIC') == '1':
        command.append('--private-worker')
    with (folder / 'web-launcher.log').open('ab') as log:
        subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    print('Starting null on private port 8080. Logs: output/web-launcher.log')
