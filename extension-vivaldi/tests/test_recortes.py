"""FFmpeg integration tests for complete and truncated audio clips."""
import array
import gc
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import imageio_ffmpeg
from clips import recortar_local, duracion_pista, validar_pistas, RecortarPP
from yt_dlp import YoutubeDL
from yt_dlp.utils import PostProcessingError


class RecortesTests(unittest.TestCase):
    """Exercise clipping and stream verification with real FFmpeg."""
    @classmethod
    def setUpClass(cls):
        """Create a continuous audio/video fixture for the clipping suite."""
        cls.tmp = tempfile.TemporaryDirectory(prefix='ytdl-test-audio-')
        cls.raiz = Path(cls.tmp.name)
        cls.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cls.original = cls.raiz / 'original.mp4'
        subprocess.run([cls.ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=96x64:r=10:d=70',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=70',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(cls.original)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        """Delete generated media fixtures after the clipping suite."""
        # Release cyclic references held by the local-file yt-dlp test transport.
        gc.collect()
        cls.tmp.cleanup()

    def test_tramo_2_a_62_audio_completo_y_audible_al_final(self):
        """Keep a full minute of audio audible through the final quarter."""
        salida = recortar_local(self.original, self.raiz / 'tramo.mp4', 2, 62, 'mp4', self.ffmpeg)
        self.assertAlmostEqual(duracion_pista(self.ffmpeg, salida, 'a'), 60, delta=.15)
        self.assertAlmostEqual(duracion_pista(self.ffmpeg, salida, 'v'), 60, delta=.15)
        pcm = subprocess.run([self.ffmpeg, '-v', 'error', '-ss', '45', '-i', str(salida), '-t', '14',
                              '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', 'pipe:1'],
                             capture_output=True, check=True).stdout
        muestras = array.array('h', pcm)
        self.assertGreater(len(muestras), 100000)
        self.assertGreater(math.sqrt(sum(x*x for x in muestras)/len(muestras)), 100)

    def test_mp3_y_no_sobrescribe_fragmento_existente(self):
        """Create an MP3 clip without replacing an existing file."""
        destino = self.raiz / 'audio.mp3'
        destino.write_bytes(b'archivo anterior')
        salida = recortar_local(self.original, destino, 2, 5, 'mp3', self.ffmpeg)
        self.assertNotEqual(salida, destino)
        self.assertEqual(destino.read_bytes(), b'archivo anterior')
        self.assertAlmostEqual(duracion_pista(self.ffmpeg, salida, 'a'), 3, delta=.15)

    def test_detecta_pista_cortada_a_un_cuarto_y_no_publica_archivo(self):
        """Reject truncated audio instead of publishing a damaged clip."""
        dañado = self.raiz / 'audio-corto.mkv'
        subprocess.run([self.ffmpeg, '-v', 'error', '-i', str(self.original), '-f', 'lavfi', '-i',
                        'sine=duration=15', '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac',
                        str(dañado)], check=True, capture_output=True)
        with self.assertRaisesRegex(PostProcessingError, 'Audio incompleto'):
            validar_pistas(self.ffmpeg, dañado, 60, 'mp4')
        destino = self.raiz / 'no-publicado.mp4'
        with self.assertRaisesRegex(PostProcessingError, 'Audio incompleto'):
            recortar_local(dañado, destino, 2, 62, 'mp4', self.ffmpeg)
        self.assertFalse(destino.exists())
        self.assertFalse(list(self.raiz.glob('.ytdl-*')))

    def test_pipeline_real_yt_dlp_con_fuente_local(self):
        """Run the real yt-dlp postprocessing pipeline on a local fixture."""
        fuente = self.raiz / 'fuente'
        destino = self.raiz / 'salida'
        responses = []
        original_open = urllib.request.OpenerDirector.open

        def tracked_open(opener, *args, **kwargs):
            """Track local test-transport responses so Windows file handles close explicitly."""
            response = original_open(opener, *args, **kwargs)
            responses.append(response)
            return response

        try:
            with patch.object(urllib.request.OpenerDirector, 'open', tracked_open):
                with YoutubeDL({'quiet':True, 'noprogress':True, 'enable_file_urls':True, 'ffmpeg_location':self.ffmpeg,
                                'outtmpl':str(fuente/'%(id)s [2s-62s].%(ext)s')}) as ydl:
                    ydl.add_post_processor(RecortarPP(ydl, destino, (2,62), 'mp4', self.ffmpeg))
                    info = ydl.process_ie_result({'id':'local', 'title':'Local', 'url':self.original.as_uri(),
                                                 'ext':'mp4', 'duration':70, 'vcodec':'h264', 'acodec':'aac'})
        finally:
            for response in responses:
                response.close()
        archivo = Path(info['requested_downloads'][0]['filepath'])
        self.assertEqual(archivo.parent, destino)
        self.assertTrue(archivo.exists())
        validar_pistas(self.ffmpeg, archivo, 60, 'mp4')


if __name__ == '__main__':
    unittest.main()
