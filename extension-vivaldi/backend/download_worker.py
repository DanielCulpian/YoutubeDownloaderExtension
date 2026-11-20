"""Run downloads and emit structured progress and completion events."""
import json
from pathlib import Path
import sys
import tempfile
from contextlib import ExitStack
from urllib.parse import parse_qs, urlparse

from download_options import aplicar_formato, opciones, tiempo_segundos, validar_url
from system_paths import carpeta_descargas


def configurar(url, destino=None, formato='mp4', playlist=False, recortar=False, inicio="", fin=""):
    """Validate a request and build options for a video, playlist, or local clip."""
    validar_url(url)
    query = parse_qs(urlparse(url).query)
    if playlist and not query.get("list"):
        raise ValueError("Para descargar una playlist, pega un enlace que incluya list=...")
    if not playlist and urlparse(url).path.rstrip("/") == "/playlist":
        raise ValueError("Este enlace es una playlist. Selecciona «Playlist completa».")
    if playlist and recortar:
        raise ValueError("El recorte está disponible solo para vídeos individuales.")
    destino = destino if destino and str(destino).strip() else carpeta_descargas()
    settings = aplicar_formato(opciones(Path(destino).expanduser().resolve()), formato)
    carpeta = Path(settings["outtmpl"]).parent
    if playlist:
        settings.update(noplaylist=False, ignoreerrors=True,
                        outtmpl=str(carpeta / "%(playlist_title).120B" /
                                    "%(playlist_index)03d - %(title).150B [%(id)s].%(ext)s"))
    if recortar:
        desde, hasta = tiempo_segundos(inicio), tiempo_segundos(fin)
        if hasta <= desde:
            raise ValueError("El final debe ser posterior al inicio.")

        def validar_intervalo(info, *, incomplete=False):
            """Reject live streams and clip boundaries beyond the available duration."""
            duracion = info.get("duration")
            if info.get("is_live"):
                raise ValueError("Espera a que el directo finalice para recortarlo.")
            if duracion is not None and (desde >= duracion or hasta > duracion):
                raise ValueError(f"El intervalo supera la duración ({duracion:g} segundos).")
            return None

        settings.update(match_filter=validar_intervalo, _intervalo=(desde, hasta),
                        skip_unavailable_fragments=False, postprocessors=[],
                        merge_output_format='mkv',
                        outtmpl=str(carpeta / f"%(title).150B [%(id)s] [{desde}s-{hasta}s].%(ext)s"))
        settings.pop('final_ext', None)
    return settings


def emitir(tipo, **datos):
    """Write one UTF-8-safe JSON worker event to standard output."""
    print(json.dumps(dict(tipo=tipo, **datos), ensure_ascii=True), flush=True)


class Registro:
    """Adapt yt-dlp logging to structured worker events."""
    def debug(self, mensaje):
        """Ignore verbose yt-dlp diagnostics to keep the event stream clean."""
        pass

    def warning(self, mensaje):
        """Forward a nonfatal yt-dlp warning to the interface."""
        emitir("mensaje", texto=f"Aviso: {mensaje}")

    def error(self, mensaje):
        """Forward a yt-dlp error without breaking the structured protocol."""
        emitir("mensaje", texto=f"Error: {mensaje}")


def ejecutar():
    """Download a request, process its output, and emit the final result."""
    from yt_dlp import YoutubeDL
    try:
        solicitud = json.loads(sys.stdin.readline())
        temporal_host = solicitud.pop('_temporal', None)
        settings = configurar(**solicitud)

        def progreso(data):
            """Forward download progress and playlist position to the native bridge."""
            info = data.get("info_dict", {})
            emitir("progreso", estado=data["status"], titulo=info.get("title", ""),
                   indice=info.get("playlist_index"), total=info.get("playlist_count"),
                   descargado=data.get("downloaded_bytes", 0),
                   bytes=data.get("total_bytes") or data.get("total_bytes_estimate"),
                   velocidad=data.get("speed"), eta=data.get("eta"))

        def procesando(data):
            """Report that a file is being merged, converted, or clipped."""
            emitir("procesando", titulo=data.get("info_dict", {}).get("title", ""))

        def terminado(archivo):
            """Report the final path of an individual completed media file."""
            emitir("archivo", texto=str(archivo))

        settings.update(logger=Registro(), quiet=True, noprogress=True,
                        progress_hooks=[progreso], postprocessor_hooks=[procesando],
                        post_hooks=[terminado])
        intervalo = settings.pop('_intervalo', None)
        with ExitStack() as recursos:
            if intervalo:
                from clips import RecortarPP
                import imageio_ffmpeg
                import shutil
                destino = Path(settings['outtmpl']).parent
                temporal = temporal_host or recursos.enter_context(tempfile.TemporaryDirectory(prefix='ytdl-clip-'))
                settings['outtmpl'] = str(Path(temporal) / Path(settings['outtmpl']).name)
                emitir('mensaje', texto='Recorte seguro: se descargan las pistas completas y se recortan localmente. Se comprobará la duración de audio y vídeo.')
            downloader = recursos.enter_context(YoutubeDL(settings))
            if intervalo:
                ffmpeg = shutil.which('ffmpeg') or imageio_ffmpeg.get_ffmpeg_exe()
                downloader.add_post_processor(RecortarPP(downloader, destino, intervalo, solicitud['formato'], ffmpeg))
            resultado = downloader.download([solicitud["url"]])
        emitir("fin", correcto=not resultado)
        return 1 if resultado else 0
    except Exception as exc:
        emitir("error", texto=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(ejecutar())
