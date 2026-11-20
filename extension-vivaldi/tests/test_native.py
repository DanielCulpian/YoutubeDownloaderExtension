"""Regression tests for the native protocol, configuration, and cancellation."""
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))
import native_host
from download_worker import configurar
from system_paths import carpeta_descargas


class Fragmentado(io.BytesIO):
    """Simulate fragmented reads from a binary stream."""
    def read(self, size=-1):
        """Return a small chunk to exercise partial-read handling."""
        return super().read(min(size, 2))


def eventos(salida):
    """Collect framed events from an in-memory byte stream."""
    salida.seek(0)
    resultado = []
    while (mensaje := native_host.leer_mensaje(salida)) is not None:
        resultado.append(mensaje)
    return resultado


class NativeTests(unittest.TestCase):
    """Cover protocol framing, validation, and owned process cancellation."""
    def test_protocolo_unicode_fragmentado(self):
        """Preserve Unicode payloads across partial reads."""
        salida = io.BytesIO()
        native_host.escribir_mensaje(salida, {'titulo': 'Canción de prueba', 'valor': 25})
        self.assertEqual(native_host.leer_mensaje(Fragmentado(salida.getvalue())),
                         {'titulo': 'Canción de prueba', 'valor': 25})

    def test_protocolo_rechaza_truncado_y_excesivo(self):
        """Reject truncated, oversized, and incorrectly typed messages."""
        for datos in [b'\x01', struct.pack('<I', 10) + b'{}', struct.pack('<I', native_host.MAX_MESSAGE + 1),
                      struct.pack('<I', 2) + b'[]']:
            with self.assertRaises(ValueError):
                native_host.leer_mensaje(io.BytesIO(datos))

    def test_host_real_ping_error_y_validacion(self):
        """Exercise an actual host process without network access."""
        entrada = io.BytesIO()
        for mensaje in [{'accion': 'ping'}, {'accion': 'desconocida'},
                        {'accion': 'descargar', 'datos': {'url': 'https://example.com', 'formato': 'mp4'}}]:
            native_host.escribir_mensaje(entrada, mensaje)
        proceso = subprocess.run([sys.executable, str(BACKEND / 'native_host.py')], input=entrada.getvalue(),
                                 capture_output=True, timeout=20)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        mensajes = eventos(io.BytesIO(proceso.stdout))
        self.assertEqual([m['tipo'] for m in mensajes], ['conectado', 'error', 'error'])
        self.assertFalse(mensajes[-1]['busy'])

    def test_formatos_playlist_y_recorte(self):
        """Validate playlist output paths and clip boundary options."""
        destino = Path(__file__).resolve().parents[1] / 'downloads'
        audio = configurar('https://youtube.com/playlist?list=PL123', destino, 'mp3', playlist=True)
        self.assertFalse(audio['noplaylist'])
        self.assertEqual(Path(audio['outtmpl']).parent, destino / '%(playlist_title).120B')
        clip = configurar('https://youtu.be/test', destino, 'mp4', recortar=True, inicio='1:20', fin='100')
        self.assertEqual(clip['_intervalo'], (80, 100))
        self.assertNotIn('download_ranges', clip)
        clip['match_filter']({'duration': 120})
        with self.assertRaises(ValueError):
            clip['match_filter']({'duration': 90})
        with self.assertRaises(ValueError):
            configurar('https://youtube.com/playlist?list=PL123', destino, 'mp3', playlist=True, recortar=True)

    def test_destino_predeterminado_y_archivos_directos(self):
        """Keep individual media files directly in the Downloads directory."""
        with patch('download_worker.carpeta_descargas', return_value=Path('C:/Descargas')):
            for formato in ('mp3','mp4'):
                datos = configurar('https://youtu.be/test', formato=formato)
                self.assertEqual(Path(datos['outtmpl']).parent, Path('C:/Descargas').resolve())
        self.assertTrue(carpeta_descargas().is_absolute())

    def test_playlist_usa_nombre_de_lista_y_agrupa_ambos_formatos(self):
        """Group both output formats in a folder named after the playlist."""
        from yt_dlp import YoutubeDL
        destino = Path(__file__).resolve().parents[1] / 'downloads'
        for formato in ('mp3', 'mp4'):
            settings = configurar('https://youtube.com/playlist?list=PL123', destino, formato, playlist=True)
            with YoutubeDL(settings) as ydl:
                archivo = Path(ydl.prepare_filename({'id':'vid123','title':'Una cancion','ext':formato,
                                                    'playlist_title':'Mi playlist favorita',
                                                    'playlist_id':'PL123','playlist_index':2}))
            self.assertEqual(archivo.parent, destino / 'Mi playlist favorita')
            self.assertTrue(archivo.name.startswith('002 - '))
            self.assertEqual(archivo.suffix, '.' + formato)

    def test_subproceso_progreso_archivo_y_fin(self):
        """Forward progress and emit one terminal event per job."""
        salida = io.BytesIO()
        puente = native_host.Puente(salida)
        real_popen = subprocess.Popen
        code = "import json; print(json.dumps({'tipo':'progreso','estado':'downloading','descargado':1,'bytes':2})); print(json.dumps({'tipo':'archivo','texto':'prueba.mp4'})); print(json.dumps({'tipo':'fin','correcto':True}))"

        def iniciar(args, **kwargs):
            """Launch a controlled local worker instead of a network download."""
            return real_popen([sys.executable, '-u', '-c', code], **kwargs)

        with patch.object(native_host.subprocess, 'Popen', iniciar):
            puente.descargar({'url': 'https://youtu.be/test', 'formato': 'mp4'})
            limite = time.monotonic() + 10
            while puente.proceso is not None and time.monotonic() < limite:
                time.sleep(0.02)
        self.assertIsNone(puente.proceso)
        mensajes = eventos(salida)
        self.assertEqual([m['tipo'] for m in mensajes], ['iniciado', 'progreso', 'archivo', 'fin', 'terminado'])
        self.assertEqual(mensajes[-1]['codigo'], 0)

    def test_limpia_original_temporal_despues_del_recorte(self):
        """Remove temporary clip sources after worker completion."""
        salida = io.BytesIO()
        puente = native_host.Puente(salida)
        real_popen = subprocess.Popen
        code = ("import sys,json,pathlib; data=json.loads(sys.stdin.readline()); p=pathlib.Path(data['_temporal']); "
                "(p/'original.tmp').write_bytes(b'original'); print(json.dumps({'tipo':'mensaje','texto':str(p)}),flush=True)")
        def iniciar(args, **kwargs):
            """Launch a controlled local worker instead of a network download."""
            return real_popen([sys.executable, '-u', '-c', code], **kwargs)
        with patch.object(native_host.subprocess, 'Popen', iniciar):
            puente.descargar({'url':'https://youtu.be/test','formato':'mp4','recortar':True,'inicio':'2','fin':'62'})
            limite = time.monotonic() + 10
            while puente.proceso is not None and time.monotonic() < limite:
                time.sleep(.02)
        self.assertIsNone(puente.proceso)
        mensaje = next(e for e in eventos(salida) if e['tipo'] == 'mensaje')
        self.assertFalse(Path(mensaje['texto']).exists())

    def test_cancelar_solo_proceso_propio(self):
        """Cancel the owned worker without touching unrelated processes."""
        salida = io.BytesIO()
        puente = native_host.Puente(salida)
        proceso = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                   stdout=subprocess.PIPE, text=True)
        puente.proceso = proceso
        puente.grupo = native_host.GrupoProcesos(proceso)
        try:
            with self.assertRaises(ValueError):
                puente.descargar({'url': 'https://youtu.be/test', 'formato': 'mp4'})
            puente.detener()
            self.assertTrue(puente.cancelado)
            self.assertIsNotNone(proceso.poll())
        finally:
            if proceso.poll() is None:
                proceso.kill()
                proceso.wait()
            proceso.stdout.close()
            puente.grupo.cerrar()

    @unittest.skipUnless(os.name == 'nt', 'Agrupacion de procesos de Windows')
    def test_cancelar_tambien_detiene_proceso_hijo(self):
        """Confirm that Windows job cancellation also stops children."""
        import ctypes
        from ctypes import wintypes
        code = ("import sys, subprocess; input(); child=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)']); print(child.pid,flush=True); child.wait()")
        proceso = subprocess.Popen([sys.executable, '-u', '-c', code], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True)
        grupo = native_host.GrupoProcesos(proceso)
        handle = None
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        try:
            self.assertIsNotNone(grupo.handle, 'No se pudo agrupar el subproceso')
            proceso.stdin.write('continuar\n'); proceso.stdin.close()
            pid = int(proceso.stdout.readline())
            handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            self.assertTrue(handle)
            self.assertTrue(grupo.detener())
            proceso.wait(timeout=5)
            self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
        finally:
            grupo.cerrar()
            if proceso.poll() is None:
                proceso.kill(); proceso.wait()
            proceso.stdout.close()
            if handle:
                api.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
