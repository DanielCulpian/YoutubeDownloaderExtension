"""Resolve standard system folders, including Windows redirected locations."""
import os
from pathlib import Path


def carpeta_descargas():
    """Resolve the user Downloads directory, including Windows redirection."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import uuid

        class GUID(ctypes.Structure):
            """Represent the Windows GUID ABI used by known-folder APIs."""
            _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                        ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]

        guid = GUID.from_buffer_copy(uuid.UUID('374DE290-123F-4565-9164-39C4925E467B').bytes_le)
        shell = ctypes.WinDLL('shell32')
        ole = ctypes.WinDLL('ole32')
        shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                               wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        shell.SHGetKnownFolderPath.restype = ctypes.c_long
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole.CoTaskMemFree.restype = None
        ole.CoUninitialize.argtypes = []
        ole.CoUninitialize.restype = None
        ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole.CoInitializeEx.restype = ctypes.c_long
        inicializado = ole.CoInitializeEx(None, 0)
        direccion = ctypes.c_void_p()
        try:
            if shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(direccion)) == 0:
                return Path(ctypes.wstring_at(direccion))
        finally:
            if direccion.value:
                ole.CoTaskMemFree(direccion)
            if inicializado in (0, 1):
                ole.CoUninitialize()
    return Path.home() / 'Downloads'
