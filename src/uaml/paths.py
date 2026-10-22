import os
import re
from pathlib import Path, PureWindowsPath

from .errors import UamlError


def relative_path(value: str) -> str:
    if (not isinstance(value, str) or not value or "\\" in value
            or PureWindowsPath(value).drive or value.startswith("/")
            or any(part in ("", ".", "..") for part in value.split("/"))
            or re.search(r'[\x00-\x1f<>:"|?*]', value)):
        raise UamlError("UNSAFE_PATH", "Expected a portable relative path within its root.")
    for part in value.split("/"):
        if part.endswith((" ", ".")) or part.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            raise UamlError("UNSAFE_PATH", "Path contains a Windows reserved name.")
    return value


def inside(root: Path, relative: str) -> Path:
    relative_path(relative)
    root = root.resolve()
    target = root.joinpath(*relative.split("/"))
    try:
        target.resolve().relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise UamlError("UNSAFE_PATH", "Path or filesystem link leaves its allowed root.") from exc
    return target


def local_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def registry_location(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.environ.get("UAML_HOME"):
        return Path(os.environ["UAML_HOME"]).expanduser().resolve() / "registry.json"
    if os.name == "nt":
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        # CSIDL_LOCAL_APPDATA; consult Windows instead of constructing a user path.
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x1C, None, 0, buffer) != 0:
            raise UamlError("REGISTRY_UNAVAILABLE", "Windows local application data is unavailable.")
        return Path(buffer.value) / "UAML" / "registry.json"
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return base.expanduser().resolve() / "uaml" / "registry.json"


def require_local_registry(path: Path, repository_root: Path) -> None:
    try:
        path.resolve().relative_to(repository_root.resolve())
    except ValueError:
        return
    raise UamlError("REGISTRY_IN_REPOSITORY", "Keep the private registry outside the Git repository.")


def require_private_registry(path: Path) -> None:
    """Do not allow even an explicit Registry path into another repo or Vault."""
    for parent in path.resolve().parents:
        if (parent / ".git").exists():
            raise UamlError("REGISTRY_IN_REPOSITORY", "Keep the private registry outside all Git repositories.")
        if (parent / ".uaml/vault.yaml").exists():
            raise UamlError("REGISTRY_IN_VAULT", "Keep the machine-specific registry outside the portable Vault.")
