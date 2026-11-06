"""Protect newly created private homes; never change an existing directory ACL."""
import os
from pathlib import Path

from .errors import UamlError
from .paths import require_private_registry
from .permissions import WindowsAcl, posix_inspect


class WindowsPrivateDirectory(WindowsAcl):
    def create(self, path):
        c = self.c
        from ctypes import wintypes as w

        class SecurityAttributes(c.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]

        convert = self.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes, convert.restype = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.c_void_p], w.BOOL
        create = self.kernel.CreateDirectoryW
        create.argtypes, create.restype = [w.LPCWSTR, c.POINTER(SecurityAttributes)], w.BOOL
        volume_path = self.kernel.GetVolumePathNameW
        volume_path.argtypes, volume_path.restype = [w.LPCWSTR, w.LPWSTR, w.DWORD], w.BOOL
        volume_info = self.kernel.GetVolumeInformationW
        volume_info.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD, c.c_void_p, c.c_void_p,
                               c.POINTER(w.DWORD), w.LPWSTR, w.DWORD]
        volume_info.restype = w.BOOL
        root, flags = c.create_unicode_buffer(32768), w.DWORD()
        if (not volume_path(str(path.parent), root, len(root))
                or not volume_info(root.value, None, 0, None, None, c.byref(flags), None, 0)
                or not flags.value & 0x8):  # FS_PERSISTENT_ACLS
            raise OSError("Private storage requires a filesystem with persistent ACLs.")
        descriptor = c.c_void_p()
        # Protected DACL, inherited by files/subdirectories. No broad parent grants.
        sddl = f"O:{self.current_sid}D:P(A;OICI;FA;;;{self.current_sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        if not convert(sddl, 1, c.byref(descriptor), None):
            raise OSError("Cannot prepare private directory security descriptor.")
        try:
            attributes = SecurityAttributes(c.sizeof(SecurityAttributes), descriptor, False)
            if not create(str(path), c.byref(attributes)):
                error = c.get_last_error()
                if error in (80, 183):
                    raise FileExistsError("Private directory appeared during creation.")
                raise OSError(error, "Cannot create private directory.")
        finally:
            self.kernel.LocalFree(descriptor)


def ensure_home(registry_path: Path, *, new_only=False):
    """Return newly created directories. Existing homes are kept without certification."""
    require_private_registry(registry_path)
    home = registry_path.parent
    if home.exists():
        if not home.is_dir() or home.is_symlink() or new_only:
            raise UamlError("PRIVATE_HOME_EXISTS", "Choose a new private home; existing directories are never hardened or replaced.")
        return []
    missing, cursor = [], home
    while not cursor.exists():
        if cursor.is_symlink():
            raise UamlError("UNSAFE_PATH", "Private storage cannot follow a dangling directory link.")
        missing.append(cursor)
        cursor = cursor.parent
    if not cursor.is_dir():
        raise UamlError("PRIVATE_HOME_INVALID", "Private storage parent must be a directory.")
    created = []
    try:
        backend = WindowsPrivateDirectory() if os.name == "nt" else None
        for directory in reversed(missing):
            if backend:
                backend.create(directory)
                result = backend.inspect(directory)
            else:
                directory.mkdir(mode=0o700)
                result = posix_inspect(directory)
            created.append(directory)
            if result["state"] != "RESTRICTED":
                raise UamlError("PRIVATE_HOME_UNVERIFIED", "New directory permissions could not be verified; no private payload was written. Inspect the empty directories.")
    except FileExistsError as exc:
        raise UamlError("WRITE_CONFLICT", "Private directory appeared during creation; inspect it before retrying.") from exc
    except OSError as exc:
        raise UamlError("PRIVATE_HOME_UNAVAILABLE", "Cannot establish private directory permissions; no private payload was written. Inspect any newly created empty directories.") from exc
    return created
