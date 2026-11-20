"""Build validated download and output-format settings."""
from pathlib import Path
import shutil
from urllib.parse import urlparse


def validar_url(value: str) -> str:
    """Validate and normalize a supported YouTube URL."""
    value = value.strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (
        host in {"youtu.be", "youtube.com"} or host.endswith(".youtube.com")
    ):
        raise ValueError("Introduce un enlace válido de YouTube (https://...).")
    return value


def opciones(destino: Path) -> dict:
    """Build default yt-dlp options and locate FFmpeg and a JavaScript runtime."""
    import imageio_ffmpeg

    runtimes = {name: {} for name in ("deno", "node") if shutil.which(name)}
    if not runtimes:
        raise RuntimeError(
            "No se encuentra Node.js ni Deno. Instala uno y vuelve a abrir la consola."
        )
    return {
        "format": "bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
        "final_ext": "mp4",
        "ffmpeg_location": shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe(),
        "js_runtimes": runtimes,
        "outtmpl": str(destino / "%(title).180B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "continuedl": True,
        "overwrites": False,
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": False,
        "socket_timeout": 30,
    }


def tiempo_segundos(value: str) -> int:
    """Parse an integer timestamp in seconds, MM:SS, or HH:MM:SS format."""
    partes = value.strip().split(":")
    if not 1 <= len(partes) <= 3 or any(not p.isascii() or not p.isdigit() for p in partes):
        raise ValueError("Usa HH:MM:SS, MM:SS o segundos enteros (por ejemplo, 1:30 o 90).")
    numeros = list(map(int, partes))
    if len(numeros) > 1 and numeros[-1] >= 60 or len(numeros) == 3 and numeros[-2] >= 60:
        raise ValueError("Los campos de segundos y minutos de HH:MM:SS deben ser menores de 60.")
    total = 0
    for numero in numeros:
        total = total * 60 + numero
    return total


def aplicar_formato(base, formato):
    """Select MP4 video processing or highest-quality MP3 audio extraction."""
    if formato not in {"mp4", "mp3"}:
        raise ValueError("El formato debe ser mp4 o mp3.")
    settings = dict(base)
    plantilla = Path(base["outtmpl"])
    settings["outtmpl"] = str(plantilla)
    settings["final_ext"] = formato
    if formato == "mp3":
        settings.pop("merge_output_format", None)
        settings["format"] = "bestaudio/best"
        settings["postprocessors"] = [{
            "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0",
        }]
    return settings
