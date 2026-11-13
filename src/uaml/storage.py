"""Cooperative single-machine writes. Never steal an existing lock."""
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .errors import UamlError, file_access_error, windows_sharing_error
from .formats import digest, json_bytes, now, read_bytes
from .private_storage import ensure_private_directory, verify_private_permissions


@contextmanager
def lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    token = str(uuid4())
    payload = json_bytes({"owner": token, "pid": os.getpid(), "created_at": now()})
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as exc:
        raise UamlError("WRITE_CONFLICT", "A write lock exists; inspect its owner before recovery.") from exc
    try:
        yield
    finally:
        # Do not remove a lock replaced by another writer or recovery operation.
        if path.exists() and path.read_bytes() == payload:
            path.unlink()


def write(path: Path, data: bytes, expected: str | None, backups: Path | None = None, *, private=False):
    """Caller holds the resource lock. None means create, never overwrite.

    Private payloads use a permission-checked staging file. Backups always do.
    """
    try:
        _write(path, data, expected, backups, private)
    except OSError as exc:
        diagnostic = file_access_error(exc, "WRITE_DENIED")
        if diagnostic is not None:
            raise diagnostic from exc
        raise


def _write(path, data, expected, backups, private):
    path.parent.mkdir(parents=True, exist_ok=True)
    old = None
    try:
        old = read_bytes(path)
    except UamlError as exc:
        if exc.code != "MEMORY_MISSING":
            raise
    if (old is None and expected is not None) or (old is not None and digest(old) != expected):
        raise UamlError("WRITE_CONFLICT", "The target changed or already exists; no overwrite performed.")
    if old is not None and backups is not None:
        ensure_private_directory(backups)
        write(backups / f"{uuid4()}.bak", old, None, private=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=".uaml-", suffix=".tmp", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if private:
                verify_private_permissions(temporary)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Check again after preparation; noncooperative writers can still race.
        if old is None:
            try:
                os.link(temporary, path)  # atomically publish, fail if target exists
            except FileExistsError as exc:
                raise UamlError("WRITE_CONFLICT", "Target appeared during creation.") from exc
        else:
            if digest(read_bytes(path)) != expected:
                raise UamlError("WRITE_CONFLICT", "Target changed during preparation.")
            try:
                os.replace(temporary, path)
            except PermissionError as exc:
                if getattr(exc, "winerror", None) == 5:
                    sharing_error = windows_sharing_error(path, "WRITE_DENIED")
                    if sharing_error is not None:
                        raise sharing_error from exc
                raise
        if digest(read_bytes(path)) != digest(data):
            raise UamlError("WRITE_CONFLICT", "Target changed after publication; inspect backups.")
    finally:
        temporary.unlink(missing_ok=True)
