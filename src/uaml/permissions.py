"""Read-only privacy audit of the local Registry and known private artifacts."""
import os
import stat
from itertools import islice

from .errors import UamlError
from .paths import inside, require_private_registry

PRIVATE_DIRS = ("backups", "transactions", "proposals", "forks", "supersessions", "cache")
MAX_TARGETS = 1024


class WindowsAcl:
    """Read security descriptors without shell commands or changing privileges."""
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c = c
        self.adv = c.WinDLL("advapi32", use_last_error=True)
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        pointer = c.POINTER(c.c_void_p)
        signatures = (
            (self.adv.GetNamedSecurityInfoW, [w.LPCWSTR, w.DWORD, w.DWORD, pointer, pointer, pointer, pointer, pointer], w.DWORD),
            (self.adv.GetAce, [c.c_void_p, w.DWORD, pointer], w.BOOL),
            (self.adv.ConvertSidToStringSidW, [c.c_void_p, pointer], w.BOOL),
            (self.adv.OpenProcessToken, [w.HANDLE, w.DWORD, pointer], w.BOOL),
            (self.adv.GetTokenInformation, [w.HANDLE, w.DWORD, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
            (self.kernel.GetCurrentProcess, [], w.HANDLE),
            (self.kernel.CloseHandle, [w.HANDLE], w.BOOL),
            (self.kernel.LocalFree, [c.c_void_p], c.c_void_p),
        )
        for function, args, result in signatures:
            function.argtypes, function.restype = args, result
        token = c.c_void_p()
        if not self.adv.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x8, c.byref(token)):  # TOKEN_QUERY
            raise OSError("Cannot inspect current Windows token.")
        try:
            needed = w.DWORD()
            self.adv.GetTokenInformation(token, 1, None, 0, c.byref(needed))  # TokenUser
            if not 0 < needed.value <= 65536:
                raise OSError("Unexpected Windows token size.")
            buffer = c.create_string_buffer(needed.value)
            if not self.adv.GetTokenInformation(token, 1, buffer, needed, c.byref(needed)):
                raise OSError("Cannot read current Windows token.")
            self.current_sid = self.sid(c.cast(buffer, c.POINTER(c.c_void_p))[0])
        finally:
            self.kernel.CloseHandle(token)

    def sid(self, pointer):
        c = self.c
        output = c.c_void_p()
        if not pointer or not self.adv.ConvertSidToStringSidW(pointer, c.byref(output)):
            raise OSError("Cannot decode security principal.")
        try:
            return c.wstring_at(output)
        finally:
            self.kernel.LocalFree(output)

    def snapshot(self, path):
        c = self.c
        from ctypes import wintypes as w
        owner, dacl, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
        code = self.adv.GetNamedSecurityInfoW(str(path), 1, 0x5, c.byref(owner), None, c.byref(dacl), None, c.byref(descriptor))
        if code:
            raise OSError("Cannot inspect Windows owner/DACL.")
        try:
            result = {"owner_sid": self.sid(owner), "dacl_null": not bool(dacl), "aces": []}
            if not dacl:
                return result

            class AclHeader(c.Structure):
                _fields_ = [("revision", c.c_ubyte), ("reserved", c.c_ubyte), ("size", c.c_ushort),
                            ("count", c.c_ushort), ("reserved2", c.c_ushort)]
            header = c.cast(dacl, c.POINTER(AclHeader)).contents
            if header.count > 1024:
                raise OSError("ACL entry budget exceeded.")
            for index in range(header.count):
                ace = c.c_void_p()
                if not self.adv.GetAce(dacl, index, c.byref(ace)):
                    raise OSError("Cannot inspect ACE.")
                kind = c.c_ubyte.from_address(ace.value).value
                flags = c.c_ubyte.from_address(ace.value + 1).value
                size = c.c_ushort.from_address(ace.value + 2).value
                if kind not in (0, 1) or size < 12:
                    result["aces"].append({"type": "unknown", "ace_type": kind})
                    continue
                result["aces"].append({"type": "allow" if kind == 0 else "deny",
                                       "sid": self.sid(ace.value + 8), "mask": w.DWORD.from_address(ace.value + 4).value,
                                       "inherit_only": bool(flags & 0x8)})
            return result
        finally:
            self.kernel.LocalFree(descriptor)

    def inspect(self, path):
        return evaluate_windows(self.snapshot(path), self.current_sid)


def evaluate_windows(value, current_sid):
    # Conservative grant audit, not a Windows effective-access calculation.
    trusted = {current_sid, "S-1-5-18", "S-1-5-32-544"}  # current user, SYSTEM, Administrators
    issues = []
    if value["owner_sid"] not in trusted:
        issues.append({"code": "OTHER_OWNER", "principal": value["owner_sid"]})
    if value["dacl_null"]:
        issues.append({"code": "NULL_DACL"})
    for ace in value["aces"]:
        if ace["type"] == "unknown":
            issues.append({"code": "ACE_UNSUPPORTED"})
        elif ace["type"] == "allow" and ace["mask"] and ace["sid"] not in trusted:
            issues.append({"code": "OTHER_PRINCIPAL_ALLOW", "principal": ace["sid"],
                           "mask": ace["mask"], "inherit_only": ace["inherit_only"]})
    if not value["dacl_null"] and not value["aces"]:
        issues.append({"code": "EMPTY_DACL_NO_ACCESS"})
    risky = any(i["code"] in ("OTHER_OWNER", "NULL_DACL", "OTHER_PRINCIPAL_ALLOW") for i in issues)
    return {"state": "RISK" if risky else ("UNVERIFIED" if issues else "RESTRICTED"), "issues": issues}


def posix_inspect(path):
    info = path.stat()
    issues = []
    if info.st_uid != os.geteuid():
        issues.append({"code": "OTHER_OWNER"})
    if stat.S_IMODE(info.st_mode) & 0o077:
        issues.append({"code": "GROUP_OR_OTHER_MODE", "mode": oct(stat.S_IMODE(info.st_mode))})
    if not hasattr(os, "listxattr"):
        issues.append({"code": "EXTENDED_ACL_UNVERIFIED"})
    elif any(name in ("system.posix_acl_access", "system.posix_acl_default") for name in os.listxattr(path)):
        issues.append({"code": "EXTENDED_ACL_UNVERIFIED"})
    risky = any(i["code"] != "EXTENDED_ACL_UNVERIFIED" for i in issues)
    return {"state": "RISK" if risky else ("UNVERIFIED" if issues else "RESTRICTED"), "issues": issues}


def audit(registry_path, inspector=None):
    require_private_registry(registry_path)
    if not registry_path.exists():
        raise UamlError("REGISTRY_MISSING", "No Registry exists; audit does not create one.")
    root = registry_path.parent
    if inspector is None:
        try:
            inspector = WindowsAcl().inspect if os.name == "nt" else posix_inspect
        except OSError as exc:
            raise UamlError("ACL_UNAVAILABLE", "Cannot inspect the current security token; no permissions were changed.") from exc
    targets = [root, registry_path]
    diagnostics, entries = [], []
    for name in PRIVATE_DIRS:
        folder = root / name
        if folder.exists() or folder.is_symlink():
            targets.append(folder)
            info = folder.lstat()
            if folder.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                continue
            if not folder.is_dir():
                diagnostics.append({"code": "PRIVATE_LAYOUT_INVALID", "message": f"Expected private artifact directory: {name}."})
                continue
            try:
                with os.scandir(folder) as stream:
                    children = list(islice(stream, max(0, MAX_TARGETS - len(targets)) + 1))
            except OSError:
                diagnostics.append({"code": "ARTIFACT_ENUMERATION_FAILED", "message": f"Cannot enumerate {name}; audit is incomplete."})
                continue
            targets.extend(folder / child.name for child in sorted(children, key=lambda child: child.name))
            if len(targets) > MAX_TARGETS:
                diagnostics.append({"code": "AUDIT_LIMIT", "message": "Private artifact audit exceeded 1024 entries; results are incomplete."})
                break
    for path in targets[:MAX_TARGETS]:
        relative = "." if path == root else path.relative_to(root).as_posix()
        try:
            if path != root:
                inside(root, relative)
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400 or (path != root and path.is_dir() and path.parent != root):
                raise UamlError("AUDIT_LINK_OR_NESTING", "Linked or nested artifact requires manual inspection; it was not traversed.")
            if path.is_file() and info.st_nlink > 1:
                raise UamlError("AUDIT_HARDLINK", "Multiple hard links require manual inspection.")
            result = inspector(path)
            entries.append({"path": relative, **result})
        except (OSError, UamlError) as exc:
            entries.append({"path": relative, "state": "UNVERIFIED", "issues": [{"code": exc.code if isinstance(exc, UamlError) else "ACL_READ_DENIED_OR_FAILED"}]})
    complete = not diagnostics and all(item["state"] != "UNVERIFIED" for item in entries)
    return {"status": "PERMISSIONS_RESTRICTED" if complete and all(item["state"] == "RESTRICTED" for item in entries) else "PERMISSION_ISSUES",
            "registry_path": str(registry_path), "platform": os.name, "complete": complete, "entries": entries, "diagnostics": diagnostics,
            "limitations": ["Read-only grant/mode audit; no ACL, owner, file content or configuration was changed.",
                            "SYSTEM and local Administrators are privileged trusted principals; this does not isolate them or the same user.",
                            "Deny/order/group/conditional ACE evaluation is not an effective-access test. Review flagged grants manually.",
                            "Only the Registry directory/file and known artifact subdirectories are inspected, with a 1024-entry limit."]}
