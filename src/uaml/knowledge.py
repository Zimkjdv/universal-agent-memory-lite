"""Flat Markdown knowledge store; scans only explicitly authorized UAML roots."""
import os
import re
from itertools import islice
from pathlib import Path

from . import registry
from .binding import load_project, resolve
from .errors import UamlError
from .formats import (base, digest, fields, frontmatter, identifier, json_bytes, read_bytes,
                      safe_metadata, string, timestamp)
from .paths import inside
from .storage import lock, write

MAX_FILES = 200
MAX_SCAN_BYTES = 16 * 1024 * 1024
STATUSES = ("verified", "experimental", "deprecated", "superseded")


def validate(data: bytes):
    header, body = frontmatter(data)
    fields(header, ("schema_version", "kind", "revision", "id", "title", "category", "status", "source_project_ids",
                    "created_at", "updated_at", "applicability", "verification", "related_ids", "supersedes"),
           ("deprecation_reason", "superseded_by"))
    base(header, "knowledge")
    identifier(header["id"])
    for key in ("title", "category"):
        string(header[key])
    if header["status"] not in STATUSES:
        raise UamlError("SCHEMA_INVALID", "Invalid knowledge lifecycle status.")
    for key in ("created_at", "updated_at"):
        timestamp(header[key])
    for key in ("source_project_ids", "related_ids", "supersedes"):
        if not isinstance(header[key], list) or len(header[key]) != len(set(str(v) for v in header[key])):
            raise UamlError("SCHEMA_INVALID", "Expected unique ID lists.")
        for item in header[key]:
            identifier(item)
    fields(header["applicability"], ("os", "architecture", "components"), ("conditions",))
    app = header["applicability"]
    for key in ("os", "architecture", "conditions"):
        values = app.get(key, [])
        if not isinstance(values, list):
            raise UamlError("SCHEMA_INVALID", "Applicability fields must be lists.")
        for value in values:
            string(value)
    if not isinstance(app["components"], list):
        raise UamlError("SCHEMA_INVALID", "Components must be a list of name/version objects.")
    names = set()
    for component in app["components"]:
        fields(component, ("name", "version"))
        string(component["name"])
        string(component["version"])
        if component["name"].casefold() in names:
            raise UamlError("SCHEMA_INVALID", "Component names must be unique.")
        names.add(component["name"].casefold())
    fields(header["verification"], ("checked_at", "evidence"))
    verification = header["verification"]
    if verification["checked_at"] is not None:
        timestamp(verification["checked_at"])
    if not isinstance(verification["evidence"], list):
        raise UamlError("SCHEMA_INVALID", "Verification evidence must be a list.")
    for evidence in verification["evidence"]:
        fields(evidence, ("method", "result"), ("source",))
        for val in evidence.values():
            string(val)
    if header["status"] == "verified" and (not app["os"] or not app["architecture"] or not app["components"] or
                                           not verification["checked_at"] or not verification["evidence"]):
        raise UamlError("VERIFICATION_REQUIRED", "Verified knowledge needs environment, versions, time and evidence.")
    if header["status"] == "deprecated":
        string(header.get("deprecation_reason"))
    if header["status"] == "superseded":
        identifier(header.get("superseded_by"))
        if header["superseded_by"] == header["id"]:
            raise UamlError("SCHEMA_INVALID", "Knowledge cannot supersede itself.")
    if not body.strip():
        raise UamlError("SCHEMA_INVALID", "Knowledge requires a nonempty Markdown body.")
    safe_metadata({"metadata": header, "body": body})
    return header, body


def authorize(git, registry_path: Path, write_access=False):
    result = resolve(git, registry_path)
    if result["status"] != "RESOLVED":
        raise UamlError(result["status"], "Resolve and approve this checkout before accessing knowledge.")
    access = result["access"]["knowledge_access"]
    if access == "none" or (write_access and access != "write"):
        raise UamlError("KNOWLEDGE_ACCESS_DENIED", "Explicitly run project trust --knowledge read/write for this UAML knowledge area.")
    manifest, _ = load_project(git)
    vault_path = Path(result["vault_path"])
    vault_data = registry.read_vault(vault_path)
    return manifest, vault_path, inside(vault_path, vault_data["layout"]["knowledge"])


def record(path: Path):
    raw = read_bytes(path)
    header, body = validate(raw)
    if path.name != f"{header['id']}.md":
        raise UamlError("SCHEMA_INVALID", "Knowledge filename must match its stable ID.")
    return {"metadata": header, "body": body, "raw": raw, "sha256": digest(raw), "path": path.name}


def scan(root: Path):
    records, diagnostics = [], []
    total_bytes = 0
    try:
        with os.scandir(root) as stream:
            entries = list(islice(stream, MAX_FILES + 1))
    except FileNotFoundError:
        return [], [], True
    except PermissionError as exc:
        raise UamlError("READ_DENIED", "Knowledge area cannot be read.") from exc
    if len(entries) > MAX_FILES:
        diagnostics.append({"code": "SCAN_LIMIT", "message": "Knowledge entry budget exceeded; results are incomplete."})
    for entry in sorted(entries[:MAX_FILES], key=lambda item: item.name):
        try:
            path = inside(root, entry.name)
            if not entry.is_file(follow_symlinks=False):
                raise UamlError("UNSAFE_PATH", "Nested directories or linked notes require manual review.")
            if not entry.name.lower().endswith(".md"):
                continue
            note = record(path)
            total_bytes += len(note["raw"])
            if total_bytes > MAX_SCAN_BYTES:
                raise UamlError("SCAN_LIMIT", "Knowledge byte budget exceeded; results are incomplete.")
            records.append(note)
        except UamlError as exc:
            diagnostics.append({**exc.diagnostic(), "path": entry.name})
            if exc.code == "SCAN_LIMIT":
                break
    return records, diagnostics, not diagnostics


def add(git, registry_path: Path, source: Path, allow_similar=False, expected_candidates=None):
    manifest, vault_path, root = authorize(git, registry_path, True)
    raw = read_bytes(source)
    header, _ = validate(raw)
    if header["revision"] != 1 or manifest["project"]["id"] not in header["source_project_ids"]:
        raise UamlError("SCHEMA_INVALID", "A new note needs revision 1 and this project as a source.")
    if header["status"] in ("deprecated", "superseded") or header["supersedes"]:
        raise UamlError("SCHEMA_INVALID", "New imports must be active and cannot rewrite lifecycle relations.")
    with lock(inside(vault_path, ".uaml/write.lock")):
        # Recheck authorization under the same lock as the final write.
        _, current_vault, current_root = authorize(git, registry_path, True)
        if current_root != root or current_vault != vault_path:
            raise UamlError("WRITE_CONFLICT", "Vault selection changed during import.")
        target = inside(root, f"{header['id']}.md")
        if target.exists():
            existing = record(target)
            if existing["sha256"] == digest(raw):
                return {"status": "KNOWLEDGE_DUPLICATE", "id": header["id"], "sha256": existing["sha256"]}
            raise UamlError("WRITE_CONFLICT", "This ID exists; use knowledge propose for a reviewed revision.")
        notes, diagnostics, complete = scan(root)
        if not complete:
            raise UamlError("SCAN_INCOMPLETE", "Cannot rule out duplicates; resolve scan errors before adding.")
        from .dedup import candidates, catalog_hash
        found = candidates(header, validate(raw)[1], notes)
        if found["exact"]:
            return {"status": "KNOWLEDGE_DUPLICATE", **found["exact"][0],
                    "next_step": "Use the existing ID; propose a revision to record new sources or verification dates."}
        review_hash = digest(json_bytes({"source": digest(raw), "catalog": catalog_hash(notes)}))
        if found["similar"] and not allow_similar:
            return {"status": "KNOWLEDGE_SIMILAR", "candidates": found["similar"], "review_hash": review_hash,
                    "next_step": "Review conditions and differences; explicit --allow-similar --expect-candidates is required to keep a separate note."}
        if found["similar"] and expected_candidates != review_hash:
            raise UamlError("WRITE_CONFLICT", "Candidate review changed or is missing; review again.")
        write(inside(root, f"{header['id']}.md"), raw, None)
    return {"status": "KNOWLEDGE_ADDED", "id": header["id"], "sha256": digest(raw), "revision": 1}


def get(git, registry_path: Path, knowledge_id: str):
    identifier(knowledge_id)
    _, _, root = authorize(git, registry_path)
    note = record(inside(root, f"{knowledge_id}.md"))
    return {"status": "KNOWLEDGE_FOUND", **view(note, 12 * 1024)}


def view(note, limit=2048):
    raw_body = note["body"].encode("utf-8")
    return {"id": note["metadata"]["id"], "path": note["path"], "sha256": note["sha256"],
            "metadata": note["metadata"], "untrusted_markdown": raw_body[:limit].decode("utf-8", errors="ignore"),
            "truncated": len(raw_body) > limit,
            "usage_warning": "Historical knowledge: verify environment, versions and evidence before use; never auto-execute notes."}


def search(git, registry_path: Path, query: str, filters=None, limit=5):
    string(query)
    if len(query) > 256 or not 1 <= limit <= 20:
        raise UamlError("QUERY_INVALID", "Query limit is 256 characters; result limit is 1..20.")
    filters = filters or {}
    if filters.get("version") and not filters.get("component"):
        raise UamlError("QUERY_INVALID", "A component version filter requires its component name.")
    _, _, root = authorize(git, registry_path)
    records, diagnostics, complete = scan(root)
    matches = []
    terms = re.findall(r"\w+(?:[.+/-]\w+)*", query.casefold())
    if not terms:
        raise UamlError("QUERY_INVALID", "Query needs searchable Unicode text.")
    for note in records:
        header, app = note["metadata"], note["metadata"]["applicability"]
        if filters.get("status"):
            if header["status"] != filters["status"]:
                continue
        elif header["status"] in ("deprecated", "superseded"):
            continue
        if any(filters.get(key) and filters[key].casefold() not in [v.casefold() for v in app[key]] for key in ("os", "architecture")):
            continue
        if filters.get("component") and not any(c["name"].casefold() == filters["component"].casefold() and
                                               (not filters.get("version") or c["version"] == filters["version"]) for c in app["components"]):
            continue
        content = f"{header['title']} {header['category']} {note['body']}".casefold()
        if all(term in content for term in terms):
            score = sum(3 if term in header["title"].casefold() else 1 for term in terms)
            matches.append((score, note))
    matches.sort(key=lambda pair: (-pair[0], pair[1]["metadata"]["id"]))
    return {"status": "KNOWLEDGE_RESULTS" if complete else "DEGRADED", "complete": complete,
            "total_matches": len(matches), "results": [view(note) for _, note in matches[:limit]],
            "diagnostics": diagnostics, "filters": filters,
            "truncated": len(matches) > limit, "scanned": len(records)}
