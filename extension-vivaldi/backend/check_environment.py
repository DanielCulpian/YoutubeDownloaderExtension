"""Validate dependencies and runtime versions before installing the host."""
import shutil
import re
import subprocess
import sys
import tkinter

import imageio_ffmpeg
import yt_dlp

if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11 or newer is required.')
runtime_valido = False
for nombre, minimo in [('node', (22, 0, 0)), ('deno', (2, 3, 0))]:
    ejecutable = shutil.which(nombre)
    if ejecutable:
        resultado = subprocess.run([ejecutable, '--version'], capture_output=True, text=True)
        version = re.search(r'(\d+)\.(\d+)\.(\d+)', resultado.stdout)
        if resultado.returncode == 0 and version and tuple(map(int, version.groups())) >= minimo:
            runtime_valido = True
if not runtime_valido:
    raise SystemExit('Install Node.js 22+ or Deno 2.3+ and open a new terminal.')
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-version'],
               check=True, capture_output=True)
print('Python, Tkinter, yt-dlp, FFmpeg, and a supported JavaScript runtime are available.')
