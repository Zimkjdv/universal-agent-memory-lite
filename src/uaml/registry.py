import stat
from pathlib import Path
from uuid import uuid4

from .errors import UamlError
from .formats import (digest, fields, identifier, json_bytes, now, parse_json,
                      parse_yaml, read_bytes, string, text, timestamp, vault)
from .paths import inside, local_key, require_private_registry
from .storage import lock, write


def empty():
    return {"schema_version": 1, "revision": 1, "vaults": [], "checkout_grants": []}


def validate(value):
    fields(value, ("schema_version", "revision", "vaults", "checkout_grants"))
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise UamlError("SCHEMA_UNSUPPORTED", "Unsupported Registry schema.")
    if type(value["revision"]) is not int or value["revision"] < 1:
        raise UamlError("SCHEMA_INVALID", "Invalid Registry revision.")
    if not isinstance(value["vaults"], list) or not isinstance(value["checkout_grants"], list):
        raise UamlError("SCHEMA_INVALID", "Invalid Registry collections.")
    seen_ids = set()
    for item in value["vaults"]:
        fields(item, ("vault_id", "candidates", "selected_candidate_id"))
        identifier(item["vault_id"])
        if item["vault_id"] in seen_ids or not isinstance(item["candidates"], list) or not item["candidates"]:
            raise UamlError("SCHEMA_INVALID", "Duplicate Vault or invalid candidate list.")
        seen_ids.add(item["vault_id"])
        candidates = set()
        paths = set()
        for candidate in item["candidates"]:
            fields(candidate, ("candidate_id", "path", "last_verified_at"))
            identifier(candidate["candidate_id"])
            string(candidate["path"])
            timestamp(candidate["last_verified_at"])
            if not Path(candidate["path"]).is_absolute() or candidate["candidate_id"] in candidates or local_key(Path(candidate["path"])) in paths:
                raise UamlError("SCHEMA_INVALID", "Duplicate or invalid candidate path.")
            candidates.add(candidate["candidate_id"])
            paths.add(local_key(Path(candidate["path"])))
        selected_id = item["selected_candidate_id"]
        if selected_id is not None and (not isinstance(selected_id, str) or selected_id not in candidates):
            raise UamlError("SCHEMA_INVALID", "Selected candidate is missing.")
    roots = set()
    for grant in value["checkout_grants"]:
        fields(grant, ("repository_root", "git_directory", "remote_fingerprint", "binding_fingerprint",
                       "vault_fingerprint", "project_id", "vault_id", "project_memory_id", "access", "scope", "approved_at"), ("knowledge_access",))
        for key in ("project_id", "vault_id", "project_memory_id"):
            identifier(grant[key])
        for key in ("repository_root", "git_directory"):
            string(grant[key])
            if not Path(grant[key]).is_absolute():
                raise UamlError("SCHEMA_INVALID", "Grant paths must be absolute.")
        for key in ("remote_fingerprint", "binding_fingerprint", "vault_fingerprint"):
            val = grant[key]
            if not isinstance(val, str) or len(val) != 64 or any(c not in "0123456789abcdef" for c in val):
                raise UamlError("SCHEMA_INVALID", "Invalid grant fingerprint.")
        timestamp(grant["approved_at"])
        root = local_key(Path(grant["repository_root"]))
        if root in roots or grant["access"] != "read" or grant["scope"] != "project_link":
            raise UamlError("SCHEMA_INVALID", "Duplicate checkout or unsupported grant scope.")
        if grant.get("knowledge_access", "none") not in ("none", "read", "write"):
            raise UamlError("SCHEMA_INVALID", "Invalid knowledge access grant.")
        roots.add(root)
    return value


def load(path: Path, allow_missing=False):
    require_private_registry(path)
    try:
        return validate(parse_json(read_bytes(path, "REGISTRY_MISSING")))
    except UamlError as exc:
        if allow_missing and exc.code == "REGISTRY_MISSING":
            return empty()
        raise


def update(path: Path, change):
    require_private_registry(path)
    with lock(path.with_name(path.name + ".lock")):
        try:
            old = read_bytes(path, "REGISTRY_MISSING")
            value = validate(parse_json(old))
        except UamlError as exc:
            if exc.code != "REGISTRY_MISSING":
                raise
            old, value = None, empty()
        change(value)
        if old is not None:
            value["revision"] += 1
        validate(value)
        write(path, json_bytes(value), digest(old) if old is not None else None, path.parent / "backups")
    return value


def read_vault(path: Path):
    try:
        if not stat.S_ISDIR(path.stat().st_mode):
            raise UamlError("VAULT_MISSING", "Vault directory is missing.")
        return vault(parse_yaml(text(read_bytes(inside(path, ".uaml/vault.yaml"), "VAULT_IDENTITY_MISSING"))))
    except FileNotFoundError as exc:
        raise UamlError("VAULT_MISSING", "Vault directory is missing.") from exc
    except PermissionError as exc:
        raise UamlError("READ_DENIED", "Vault cannot be read.") from exc


def register(registry_path: Path, path: Path, select=False, expected_id=None):
    path = path.resolve()
    metadata = read_vault(path)
    vault_id = metadata["vault"]["id"]
    if expected_id and expected_id != vault_id:
        raise UamlError("VAULT_ID_MISMATCH", "Relocated Vault has a different ID.")

    def change(value):
        entry = next((item for item in value["vaults"] if item["vault_id"] == vault_id), None)
        if entry is None:
            entry = {"vault_id": vault_id, "candidates": [], "selected_candidate_id": None}
            value["vaults"].append(entry)
        previous_count = len(entry["candidates"])
        candidate = next((c for c in entry["candidates"] if local_key(Path(c["path"])) == local_key(path)), None)
        if candidate is None:
            candidate = {"candidate_id": str(uuid4()), "path": str(path), "last_verified_at": now()}
            entry["candidates"].append(candidate)
            # A new copy invalidates implicit selection, even if another was active.
            entry["selected_candidate_id"] = None
        candidate["last_verified_at"] = now()
        if select or previous_count == 0:
            entry["selected_candidate_id"] = candidate["candidate_id"]

    value = update(registry_path, change)
    return next(item for item in value["vaults"] if item["vault_id"] == vault_id)


def selected(value, vault_id):
    entry = next((item for item in value["vaults"] if item["vault_id"] == vault_id), None)
    if entry is None:
        raise UamlError("VAULT_UNREGISTERED", "Register the expected Vault on this computer.")
    candidate = next((c for c in entry["candidates"] if c["candidate_id"] == entry["selected_candidate_id"]), None)
    if candidate is None:
        raise UamlError("MULTIPLE_CANDIDATES", "Select a Vault copy explicitly with vault register --select.")
    return Path(candidate["path"])
