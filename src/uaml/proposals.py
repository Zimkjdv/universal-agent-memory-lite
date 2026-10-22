"""Locally persisted, hash-bound proposals for one knowledge note at a time."""
import difflib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .dedup import candidates, catalog_hash
from .errors import UamlError
from .formats import digest, fields, identifier, json_bytes, parse_json, read_bytes
from .knowledge import authorize, record, scan, validate
from .paths import inside
from .storage import lock, write


def validate_change(header, body, old, project_id):
    if project_id not in header["source_project_ids"]:
        raise UamlError("SCHEMA_INVALID", "Record this project as a source of the proposed change.")
    if old is None:
        if header["revision"] != 1 or header["status"] in ("deprecated", "superseded") or header["supersedes"]:
            raise UamlError("SCHEMA_INVALID", "New proposals need active revision 1 with no supersession changes.")
        return
    prior = old["metadata"]
    if (header["revision"] != prior["revision"] + 1 or header["created_at"] != prior["created_at"] or
            not set(prior["source_project_ids"]).issubset(header["source_project_ids"])):
        raise UamlError("SCHEMA_INVALID", "Keep creation time and sources, and increment revision by exactly one.")
    if (header["supersedes"] != prior["supersedes"] or header.get("superseded_by") != prior.get("superseded_by") or
            header.get("supersession_reason") != prior.get("supersession_reason") or
            (header["status"] == "superseded" and prior["status"] != "superseded") or
            (prior["status"] == "superseded" and header["status"] != "superseded")):
        raise UamlError("RELATION_CHANGE_UNSUPPORTED", "Cross-note supersession requires a separate multi-note workflow.")
    def date(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date(header["updated_at"]) < date(prior["updated_at"]):
        raise UamlError("SCHEMA_INVALID", "Update time cannot go backwards.")
    changed = body != old["body"] or header["applicability"] != prior["applicability"]
    if changed and header["status"] == "verified":
        previous_time = prior["verification"]["checked_at"]
        if previous_time and date(header["verification"]["checked_at"]) <= date(previous_time):
            raise UamlError("VERIFICATION_REQUIRED", "Changed steps or environment need fresh verification, or downgrade to experimental.")


def context(git, manifest, vault_path, root):
    return digest(json_bytes({"git": git.identity(), "manifest": manifest,
                              "vault": str(vault_path), "knowledge": str(root)}))


def inventory(root):
    notes, diagnostics, complete = scan(root)
    if not complete:
        raise UamlError("SCAN_INCOMPLETE", "Resolve corrupt notes or scan limits before proposing/applying changes.")
    return notes


def propose(git, registry_path: Path, source: Path):
    manifest, vault_path, root = authorize(git, registry_path)
    after = read_bytes(source)
    header, body = validate(after)
    notes = inventory(root)
    old = next((note for note in notes if note["metadata"]["id"] == header["id"]), None)
    validate_change(header, body, old, manifest["project"]["id"])
    found = candidates(header, body, notes)
    if found["exact"]:
        return {"status": "KNOWLEDGE_DUPLICATE", **found["exact"][0],
                "next_step": "Revise the existing authority instead of creating or converging another copy."}
    proposal_id = str(uuid4())
    value = {"schema_version": 1, "kind": "knowledge_proposal", "id": proposal_id,
             "knowledge_id": header["id"], "context": context(git, manifest, vault_path, root),
             "before_hash": old["sha256"] if old else None, "after_hash": digest(after),
             "catalog_hash": catalog_hash(notes), "similar": found["similar"]}
    # Private local artifacts; the Vault is unchanged until explicit apply.
    payload_path = inside(registry_path.parent, f"proposals/{proposal_id}.md")
    proposal_path = inside(registry_path.parent, f"proposals/{proposal_id}.json")
    write(payload_path, after, None)
    encoded = json_bytes(value)
    write(proposal_path, encoded, None)
    diff = "".join(difflib.unified_diff((old["raw"].decode("utf-8-sig") if old else "").splitlines(True),
                                         after.decode("utf-8-sig").splitlines(True), fromfile="current", tofile="proposed"))
    diff_bytes = diff.encode("utf-8")
    return {"status": "KNOWLEDGE_PROPOSED", "proposal_id": proposal_id, "plan_hash": digest(encoded),
            "knowledge_id": header["id"], "before_hash": value["before_hash"], "after_hash": value["after_hash"],
            "candidates": found["similar"], "untrusted_diff": diff_bytes[:12 * 1024].decode("utf-8", errors="ignore"),
            "diff_truncated": len(diff_bytes) > 12 * 1024, "review_payload": str(payload_path)}


def apply(git, registry_path: Path, proposal_id: str, expected_plan: str, allow_similar=False):
    identifier(proposal_id)
    if not expected_plan:
        raise UamlError("PLAN_REQUIRED", "Pass the plan_hash from the reviewed proposal.")
    manifest, vault_path, root = authorize(git, registry_path, True)
    raw = read_bytes(inside(registry_path.parent, f"proposals/{proposal_id}.json"), "PROPOSAL_MISSING")
    if digest(raw) != expected_plan:
        raise UamlError("WRITE_CONFLICT", "Proposal differs from the reviewed plan.")
    value = parse_json(raw)
    fields(value, ("schema_version", "kind", "id", "knowledge_id", "context", "before_hash", "after_hash", "catalog_hash", "similar"))
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["kind"] != "knowledge_proposal" or value["id"] != proposal_id:
        raise UamlError("SCHEMA_INVALID", "Invalid proposal identity.")
    identifier(value["knowledge_id"])
    after = read_bytes(inside(registry_path.parent, f"proposals/{proposal_id}.md"))
    if digest(after) != value["after_hash"]:
        raise UamlError("WRITE_CONFLICT", "Proposed payload changed after review.")
    header, body = validate(after)
    if header["id"] != value["knowledge_id"]:
        raise UamlError("SCHEMA_INVALID", "Payload and proposal IDs differ.")
    with lock(inside(vault_path, ".uaml/write.lock")):
        manifest, current_vault, current_root = authorize(git, registry_path, True)
        if current_vault != vault_path or current_root != root or context(git, manifest, vault_path, root) != value["context"]:
            raise UamlError("WRITE_CONFLICT", "Checkout, Vault or binding changed after review.")
        notes = inventory(root)
        if catalog_hash(notes) != value["catalog_hash"]:
            raise UamlError("WRITE_CONFLICT", "Knowledge inventory changed; propose again to review current candidates.")
        old = next((note for note in notes if note["metadata"]["id"] == header["id"]), None)
        if (old["sha256"] if old else None) != value["before_hash"]:
            raise UamlError("WRITE_CONFLICT", "Target changed after review.")
        validate_change(header, body, old, manifest["project"]["id"])
        found = candidates(header, body, notes)
        if found["exact"]:
            raise UamlError("KNOWLEDGE_DUPLICATE", "Use the existing authority instead of applying a duplicate.")
        if found["similar"] and not allow_similar:
            raise UamlError("SIMILARITY_REVIEW_REQUIRED", "Review proposal candidates; pass --allow-similar only to retain intentional differences.")
        write(inside(root, f"{header['id']}.md"), after, value["before_hash"], registry_path.parent / "backups")
    return {"status": "KNOWLEDGE_APPLIED", "proposal_id": proposal_id, "id": header["id"],
            "revision": header["revision"], "sha256": digest(after)}
