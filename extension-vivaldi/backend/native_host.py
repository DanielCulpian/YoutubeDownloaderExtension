"""Native messaging bridge; stdout carries framed binary messages only."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import tempfile
from process_group import GrupoProcesos
from system_paths import carpeta_descargas

RAIZ = Path(__file__).resolve().parent.parent
MAX_MESSAGE = 1024 * 1024


def leer_exacto(stream, cantidad):
    """Read exactly the requested bytes and reject truncated input."""
    datos = bytearray()
    while len(datos) < cantidad:
        parte = stream.read(cantidad - len(datos))
        if not parte:
            if not datos:
                return None
            raise ValueError("Mensaje incompleto")
        datos.extend(parte)
    return bytes(datos)


def leer_mensaje(stream):
    """Decode one bounded, length-prefixed JSON native message."""
    cabecera = leer_exacto(stream, 4)
    if cabecera is None:
        return None
    longitud = struct.unpack("<I", cabecera)[0]
    if not 0 < longitud <= MAX_MESSAGE:
        raise ValueError("Longitud de mensaje no válida")
    contenido = leer_exacto(stream, longitud)
    if contenido is None:
        raise ValueError("Mensaje incompleto")
    mensaje = json.loads(contenido.decode("utf-8"))
    if not isinstance(mensaje, dict):
        raise ValueError("Se esperaba un objeto JSON")
    return mensaje


def escribir_mensaje(stream, mensaje):
    """Encode and flush one bounded native message."""
    datos = json.dumps(mensaje, ensure_ascii=False).encode("utf-8")
    if len(datos) > MAX_MESSAGE:
        raise ValueError("Respuesta demasiado grande")
    stream.write(struct.pack("<I", len(datos)) + datos)
    stream.flush()


class Puente:
    """Own the browser connection, worker process, and temporary resources."""
    def __init__(self, salida):
        """Initialize component dependencies and owned resources."""
        self.salida = salida
        self.lock = threading.Lock()
        self.proceso = None
        self.grupo = None
        self.temporal = None
        self.cancelado = False
        self.cerrado = False

    def enviar(self, mensaje):
        """Serialize output events under the bridge write lock."""
        with self.lock:
            if not self.cerrado:
                escribir_mensaje(self.salida, mensaje)

    def detener(self):
        """Terminate the owned worker and its child processes."""
        proceso = self.proceso
        grupo = self.grupo
        if proceso and proceso.poll() is None:
            self.cancelado = True
            if grupo and grupo.detener():
                pass
            elif os.name == "nt":
                resultado = subprocess.run(["taskkill", "/PID", str(proceso.pid), "/T", "/F"],
                                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if resultado.returncode and proceso.poll() is None:
                    proceso.terminate()
            elif proceso.poll() is None:
                proceso.terminate()
            try:
                proceso.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait(timeout=5)

    def descargar(self, datos):
        """Validate the request and start an isolated download worker."""
        from download_worker import configurar
        if self.proceso is not None:
            raise ValueError("Ya hay una descarga en curso. Espera o cancélala.")
        permitidos = {"url", "formato", "playlist", "recortar", "inicio", "fin", "destino"}
        solicitud = {k: v for k, v in datos.items() if k in permitidos}
        solicitud["destino"] = solicitud.get("destino") or str(carpeta_descargas())
        for campo in ("playlist", "recortar"):
            if campo in solicitud and not isinstance(solicitud[campo], bool):
                raise ValueError("Opción booleana no válida")
        configurar(**solicitud)
        temporal = tempfile.TemporaryDirectory(prefix='ytdl-clip-', ignore_cleanup_errors=True) if solicitud.get('recortar') else None
        if temporal:
            solicitud['_temporal'] = temporal.name
        try:
            proceso = subprocess.Popen(
                [sys.executable, "-u", str(RAIZ / "backend" / "download_worker.py")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError:
            if temporal:
                temporal.cleanup()
            raise
        self.proceso = proceso
        self.temporal = temporal
        self.grupo = GrupoProcesos(proceso)
        self.cancelado = False
        try:
            proceso.stdin.write(json.dumps(solicitud) + "\n")
            proceso.stdin.close()
        except OSError:
            self.detener()
            proceso.stdout.close()
            if self.grupo:
                self.grupo.cerrar()
            self.grupo = None
            self.proceso = None
            if temporal:
                temporal.cleanup()
            self.temporal = None
            raise
        self.enviar({"tipo": "iniciado", "destino": solicitud["destino"]})
        threading.Thread(target=self.seguir, args=(proceso, temporal), daemon=True).start()

    def seguir(self, proceso, temporal=None):
        """Forward worker events and release resources on completion."""
        ultimo = 0
        grupo = self.grupo
        try:
            for linea in proceso.stdout:
                try:
                    evento = json.loads(linea)
                    if not isinstance(evento, dict):
                        raise ValueError("Se esperaba un evento")
                except ValueError:
                    evento = {"tipo": "mensaje", "texto": linea.strip()[:2000]}
                ahora = time.monotonic()
                if evento.get("tipo") == "progreso" and evento.get("estado") == "downloading":
                    if ahora - ultimo < 0.3:
                        continue
                    ultimo = ahora
                self.enviar(evento)
            codigo = proceso.wait()
            cancelado = self.cancelado
            if grupo:
                grupo.cerrar()
                if self.grupo is grupo:
                    self.grupo = None
            if temporal:
                temporal.cleanup()
                if self.temporal is temporal:
                    self.temporal = None
            self.proceso = None
            self.enviar({"tipo": "terminado", "codigo": codigo, "cancelado": cancelado})
        except (BrokenPipeError, OSError):
            self.cerrado = True
        finally:
            proceso.stdout.close()
            if grupo:
                grupo.cerrar()
            if temporal:
                temporal.cleanup()

    def carpeta(self, mensaje):
        """Show the folder picker and forward its result."""
        proceso = subprocess.run([sys.executable, str(RAIZ / "backend" / "folder_picker.py")],
                                 capture_output=True, text=True, encoding="utf-8",
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.enviar({"tipo": "carpeta", "ruta": proceso.stdout.strip(), "requestId": mensaje.get("requestId")})

    def recibir(self, mensaje):
        """Dispatch an allowlisted browser command."""
        accion = mensaje.get("accion")
        if accion == "ping":
            self.enviar({"tipo": "conectado", "destino": str(carpeta_descargas()), "legacyDestination": str(RAIZ / "downloads")})
        elif accion == "descargar":
            self.descargar(mensaje.get("datos", {}))
        elif accion == "cancelar":
            self.detener()
        elif accion == "carpeta":
            threading.Thread(target=self.carpeta, args=(mensaje,), daemon=True).start()
        elif accion == "abrir":
            destino = Path(mensaje.get("destino") or carpeta_descargas()).expanduser().resolve()
            if not destino.is_dir():
                raise ValueError("La carpeta todavía no existe")
            os.startfile(str(destino))
        else:
            raise ValueError("Acción desconocida")


def main():
    """Serve native requests until the browser closes the connection."""
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    puente = Puente(sys.stdout.buffer)
    try:
        while (mensaje := leer_mensaje(sys.stdin.buffer)) is not None:
            try:
                puente.recibir(mensaje)
            except Exception as exc:
                puente.enviar({"tipo": "error", "texto": str(exc), "busy": puente.proceso is not None,
                               "requestId": mensaje.get("requestId")})
    except (BrokenPipeError, ValueError, OSError):
        pass
    finally:
        puente.cerrado = True
        puente.detener()
        if puente.grupo:
            puente.grupo.cerrar()
        if puente.temporal:
            puente.temporal.cleanup()


if __name__ == "__main__":
    main()
