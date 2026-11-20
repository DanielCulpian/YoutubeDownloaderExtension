"""Cancel the downloader and FFmpeg as one owned Windows process tree."""
import os


class GrupoProcesos:
    """Group the downloader and FFmpeg under one Windows job."""
    def __init__(self, proceso):
        """Initialize component dependencies and owned resources."""
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes

        class Limites(ctypes.Structure):
            """Represent the native Windows basic job limits."""
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]

        class Contadores(ctypes.Structure):
            """Represent native Windows job I/O counters."""
            _fields_ = [(nombre, ctypes.c_uint64) for nombre in
                        ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                         'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class Extendidos(ctypes.Structure):
            """Represent the native Windows extended job limits."""
            _fields_ = [('BasicLimitInformation', Limites), ('IoInfo', Contadores),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.TerminateJobObject.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        handle = self.api.CreateJobObjectW(None, None)
        if not handle:
            return
        info = Extendidos()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (self.api.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info))
                and self.api.AssignProcessToJobObject(handle, wintypes.HANDLE(int(proceso._handle)))):
            self.handle = handle
        else:
            self.api.CloseHandle(handle)

    def detener(self):
        """Terminate the owned worker and its child processes."""
        return bool(self.handle and self.api.TerminateJobObject(self.handle, 130))

    def cerrar(self):
        """Close the Windows job and stop any remaining children."""
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
