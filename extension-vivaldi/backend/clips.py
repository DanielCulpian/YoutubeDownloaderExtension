"""Encode local clips and verify their audio and video streams."""
import os
from pathlib import Path
import re
import subprocess
import uuid

from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import PostProcessingError


def ejecutar_ffmpeg(ffmpeg, argumentos):
    """Run FFmpeg with captured output and translate failures into processing errors."""
    resultado = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-v', 'error', *argumentos],
                               capture_output=True, text=True, encoding='utf-8', errors='replace',
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if resultado.returncode:
        raise PostProcessingError('FFmpeg: ' + resultado.stderr.strip()[-2000:])
    return resultado.stdout


def duracion_pista(ffmpeg, archivo, pista):
    """Decode a selected stream and measure its actual final timestamp."""
    argumentos = ['-i', str(archivo), '-map', f'0:{pista}:0']
    argumentos += ['-progress', 'pipe:1', '-nostats', '-f', 'null', os.devnull]
    salida = ejecutar_ffmpeg(ffmpeg, argumentos)
    tiempos = re.findall(r'^out_time_us=(\d+)$', salida, re.M)
    if not tiempos:
        raise PostProcessingError(f'No se puede comprobar la pista {pista}.')
    return int(tiempos[-1]) / 1_000_000


def validar_pistas(ffmpeg, archivo, duracion, formato):
    """Reject clips with truncated audio or inconsistent stream durations."""
    tolerancia = max(0.25, min(1.0, duracion * 0.01))
    audio = duracion_pista(ffmpeg, archivo, 'a')
    if audio < duracion - tolerancia:
        raise PostProcessingError(f'Audio incompleto: {audio:.2f}s de los {duracion:.2f}s solicitados.')
    if formato == 'mp4':
        video = duracion_pista(ffmpeg, archivo, 'v')
        if video < duracion - tolerancia or abs(video - audio) > tolerancia:
            raise PostProcessingError(f'Las pistas no cubren el mismo intervalo: vídeo {video:.2f}s, audio {audio:.2f}s.')
    return audio


def recortar_local(origen, destino, inicio, fin, formato, ffmpeg):
    """Encode and verify a local clip, then publish it without overwriting files."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(f'.ytdl-{uuid.uuid4().hex}.{formato}')
    argumentos = ['-ss', str(inicio), '-i', str(origen), '-t', str(fin - inicio)]
    if formato == 'mp4':
        argumentos += ['-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'medium',
                       '-crf', '18', '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart']
    elif formato == 'mp3':
        argumentos += ['-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-q:a', '0']
    else:
        raise ValueError('Formato no válido')
    argumentos += ['-af', 'asetpts=PTS-STARTPTS', '-n', str(parcial)]
    try:
        ejecutar_ffmpeg(ffmpeg, argumentos)
        validar_pistas(ffmpeg, parcial, fin - inicio, formato)
        candidato = destino
        numero = 2
        while candidato.exists():
            candidato = destino.with_name(f'{destino.stem} ({numero}){destino.suffix}')
            numero += 1
        parcial.rename(candidato)
        return candidato
    finally:
        if parcial.exists():
            parcial.unlink()


class RecortarPP(PostProcessor):
    """Integrate verified local clipping into yt-dlp postprocessing."""
    def __init__(self, downloader, destino, intervalo, formato, ffmpeg):
        """Initialize this component and its dependencies."""
        super().__init__(downloader)
        self.destino, self.intervalo, self.formato, self.ffmpeg = Path(destino), intervalo, formato, ffmpeg

    def run(self, info):
        """Replace a downloaded source with a verified clip in the selected destination."""
        origen = Path(info['filepath'])
        destino = self.destino / (origen.stem + '.' + self.formato)
        archivo = recortar_local(origen, destino, *self.intervalo, self.formato, self.ffmpeg)
        info.update(filepath=str(archivo), ext=self.formato, __finaldir=str(self.destino))
        info['__files_to_move'] = {}
        return [str(origen)], info
