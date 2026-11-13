import errno


class UamlError(Exception):
    """A stable diagnostic code without echoing potentially sensitive input."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def diagnostic(self) -> dict:
        return {"code": self.code, "message": self.message}


def file_access_error(error: OSError, denied_code: str):
    if getattr(error, "winerror", None) in (32, 33):
        return UamlError("FILE_IN_USE", "A file is in use or locked. Close the application holding it and inspect any pending transaction before retrying.")
    if isinstance(error, PermissionError) or (denied_code == "WRITE_DENIED" and error.errno == errno.EROFS):
        return UamlError(denied_code, "Filesystem access was denied. Check permissions and read-only attributes before retrying.")
    return None


def windows_sharing_error(path, denied_code: str):
    """Probe sharing when a Windows file operation reports ambiguous access denial."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = (wintypes.HANDLE,), wintypes.BOOL
    access = 0x80000000 if denied_code == "READ_DENIED" else 0x10000  # GENERIC_READ or DELETE
    # Share all operations, OPEN_EXISTING, open the reparse point itself.
    handle = create(str(path), access, 7, None, 3, 0x00200000, None)
    if handle != ctypes.c_void_p(-1).value:
        close(handle)
        return None
    error = ctypes.get_last_error()
    return file_access_error(ctypes.WinError(error), denied_code) if error in (32, 33) else None
