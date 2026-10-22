"""Two-note lifecycle changes with reviewed payloads and a visible pending marker."""
import copy
import difflib
from datetime import datetime
from uuid import uuid4

from .errors import UamlError
from .dedup import catalog_hash
from .formats import digest, fields, identifier, json_bytes, markdown, now, parse_json, read_bytes, safe_metadata, string, timestamp
from .knowledge import authorize, pending_transaction, validate
from .paths import inside
from .proposals import context, inventory
from .storage import lock, write
from .validation import relations


def transform(before, project_id, reason, updated_at):
    old_header, old_body = validate(before[0])
    new_header, new_body = validate(before[1])
    if old_header["id"] == new_header["id"] or old_header["status"] == "superseded":
        raise UamlError("SUPERSESSION_INVALID", "Choose distinct notes and an old note that is not already superseded.")
    if new_header["status"] not in ("verified", "experimental"):
        raise UamlError("SUPERSESSION_INVALID", "The replacement must be active verified/experimental knowledge.")
    timestamp(updated_at)
    date = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    if any(date(updated_at) < date(header["updated_at"]) for header in (old_header, new_header)):
        raise UamlError("SUPERSESSION_INVALID", "Supersession time cannot precede the original update time.")
    old_header, new_header = copy.deepcopy(old_header), copy.deepcopy(new_header)
    old_header.update(status="superseded", superseded_by=new_header["id"], supersession_reason=reason)
    new_header["supersedes"].append(old_header["id"])
    for header in (old_header, new_header):
        header["revision"] += 1
        header["updated_at"] = updated_at
        if project_id not in header["source_project_ids"]:
            header["source_project_ids"].append(project_id)
    result = [markdown(old_header, old_body), markdown(new_header, new_body)]
    for raw in result:
        validate(raw)
    return result


def replaced(notes, payloads):
    by_id = {}
    for raw in payloads:
        header, body = validate(raw)
        by_id[header["id"]] = {"metadata": header, "body": body, "raw": raw,
                               "sha256": digest(raw), "path": f"{header['id']}.md"}
    return [by_id.get(note["metadata"]["id"], note) for note in notes]


def prepare(git, registry_path, old_id, new_id, reason):
    identifier(old_id)
    identifier(new_id)
    string(reason)
    if len(reason) > 2000:
        raise UamlError("SUPERSESSION_INVALID", "Keep the explicit supersession reason within 2000 characters.")
    safe_metadata(reason)
    manifest, vault_path, root = authorize(git, registry_path)
    notes = inventory(root)
    if relations(notes):
        raise UamlError("KNOWLEDGE_RELATION_INVALID", "Resolve existing missing/inconsistent/cyclic knowledge relations before superseding.")
    by_id = {note["metadata"]["id"]: note for note in notes}
    if old_id not in by_id or new_id not in by_id:
        raise UamlError("KNOWLEDGE_MISSING", "Both explicit knowledge IDs must already exist in this authorized Vault.")
    originals = [by_id[item]["raw"] for item in (old_id, new_id)]
    date = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    time = max([now(), *(by_id[item]["metadata"]["updated_at"] for item in (old_id, new_id))], key=date)
    after = transform(originals, manifest["project"]["id"], reason, time)
    if relations(replaced(notes, after)):
        raise UamlError("KNOWLEDGE_RELATION_INVALID", "The proposed replacement would introduce inconsistent or cyclic relations.")
    transaction_id = str(uuid4())
    entries = []
    for index, item in enumerate((old_id, new_id)):
        for suffix, payload in (("before", originals[index]), ("after", after[index])):
            write(inside(registry_path.parent, f"supersessions/{transaction_id}.{index}.{suffix}"), payload, None)
        entries.append({"id": item, "before_hash": digest(originals[index]), "after_hash": digest(after[index])})
    value = {"schema_version": 1, "kind": "knowledge_supersession", "id": transaction_id,
             "project_id": manifest["project"]["id"], "context": context(git, manifest, vault_path, root),
             "reason": reason, "updated_at": time, "entries": entries,
             "other_catalog_hash": catalog_hash([n for n in notes if n["metadata"]["id"] not in (old_id, new_id)])}
    write(inside(registry_path.parent, f"supersessions/{transaction_id}.json"), json_bytes(value), None)
    return inspect(git, registry_path, transaction_id)[0]


def inspect(git, registry_path, transaction_id, write_access=False):
    identifier(transaction_id)
    manifest, vault_path, root = authorize(git, registry_path, write_access, allow_pending=True)
    raw_plan = read_bytes(inside(registry_path.parent, f"supersessions/{transaction_id}.json"), "SUPERSESSION_MISSING")
    value = parse_json(raw_plan)
    fields(value, ("schema_version", "kind", "id", "project_id", "context", "reason", "updated_at", "entries", "other_catalog_hash"))
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["kind"] != "knowledge_supersession"
            or value["id"] != transaction_id or value["project_id"] != manifest["project"]["id"]
            or value["context"] != context(git, manifest, vault_path, root)):
        raise UamlError("WRITE_CONFLICT", "Supersession checkout, binding or Vault changed after preparation.")
    string(value["reason"])
    if len(value["reason"]) > 2000:
        raise UamlError("SCHEMA_INVALID", "Invalid supersession reason.")
    safe_metadata(value["reason"])
    entries = value["entries"]
    if not isinstance(entries, list) or len(entries) != 2:
        raise UamlError("SCHEMA_INVALID", "Supersession covers exactly two existing notes.")
    originals, after = [], []
    for index, entry in enumerate(entries):
        fields(entry, ("id", "before_hash", "after_hash"))
        identifier(entry["id"])
        for suffix, payloads in (("before", originals), ("after", after)):
            payload = read_bytes(inside(registry_path.parent, f"supersessions/{transaction_id}.{index}.{suffix}"))
            header, _ = validate(payload)
            if digest(payload) != entry[f"{suffix}_hash"] or header["id"] != entry["id"]:
                raise UamlError("WRITE_CONFLICT", "Supersession payload or knowledge identity changed.")
            payloads.append(payload)
    if after != transform(originals, value["project_id"], value["reason"], value["updated_at"]):
        raise UamlError("SCHEMA_INVALID", "Payloads must preserve note bodies, evidence and all unrelated metadata.")
    marker = {"schema_version": 1, "kind": "knowledge_supersession", "id": transaction_id, "plan_hash": digest(raw_plan)}
    current_marker = pending_transaction(vault_path)
    if current_marker is not None and current_marker != marker:
        raise UamlError("KNOWLEDGE_TRANSACTION_PENDING", "Another or changed supersession is pending; preserve its marker.")
    notes = inventory(root)
    ids = {entry["id"] for entry in entries}
    if catalog_hash([n for n in notes if n["metadata"]["id"] not in ids]) != value["other_catalog_hash"]:
        raise UamlError("WRITE_CONFLICT", "Other knowledge changed after preparation; review the full inventory again.")
    actual = {n["metadata"]["id"]: n for n in notes}
    actions, current = [], {}
    for entry in entries:
        prior = actual.get(entry["id"])
        if prior is None or prior["sha256"] not in (entry["before_hash"], entry["after_hash"]):
            raise UamlError("WRITE_CONFLICT", "A note was removed or manually edited; preserve those changes.")
        current[entry["id"]] = prior["sha256"]
        actions.append({"path": f"{entry['id']}.md", "action": "keep" if prior["sha256"] == entry["after_hash"] else "finish"})
    if relations(replaced(notes, originals)) or relations(replaced(notes, after)):
        raise UamlError("KNOWLEDGE_RELATION_INVALID", "Prepared before/after knowledge graphs are inconsistent.")
    done = all(action["action"] == "keep" for action in actions)
    diff = "\n".join("".join(difflib.unified_diff(before.decode("utf-8-sig").splitlines(True),
                                                payload.decode("utf-8-sig").splitlines(True),
                                                fromfile=f"{entries[i]['id']}:before", tofile=f"{entries[i]['id']}:after"))
                     for i, (before, payload) in enumerate(zip(originals, after)))
    diff_raw = diff.encode("utf-8")
    result = {"status": "SUPERSESSION_ALREADY_APPLIED" if done and current_marker is None else "SUPERSESSION_PREVIEW",
              "transaction_id": transaction_id, "plan_hash": digest(raw_plan), "reason": value["reason"], "actions": actions,
              "untrusted_diff": diff_raw[:12 * 1024].decode("utf-8", errors="ignore"), "diff_truncated": len(diff_raw) > 12 * 1024,
              "review_payload": str(inside(registry_path.parent, f"supersessions/{transaction_id}.json")),
              "review_payloads": [str(inside(registry_path.parent, f"supersessions/{transaction_id}.{i}.after")) for i in range(2)],
              "applicability": {"old": validate(originals[0])[0]["applicability"], "replacement": validate(after[1])[0]["applicability"]},
              "replacement_status": validate(after[1])[0]["status"], "pending": current_marker is not None,
              "next_step": "Review both bodies, applicability and evidence. Apply changes links/status only; an experimental replacement is still unverified."}
    return result, value, after, current, vault_path, root, marker


def apply(git, registry_path, transaction_id, expected_plan):
    if not expected_plan:
        raise UamlError("PLAN_REQUIRED", "Inspect the prepared supersession and pass its --expect-plan hash.")
    _, vault_path, _ = authorize(git, registry_path, True, allow_pending=True)
    with lock(inside(git.root, ".uaml/write.lock")), lock(inside(vault_path, ".uaml/write.lock")):
        report, value, after, current, current_vault, root, marker = inspect(git, registry_path, transaction_id, True)
        if current_vault != vault_path or expected_plan != report["plan_hash"]:
            raise UamlError("WRITE_CONFLICT", "Supersession plan or selected Vault changed after review.")
        if report["status"] == "SUPERSESSION_ALREADY_APPLIED":
            return report
        marker_path = inside(vault_path, ".uaml/knowledge-transaction.json")
        if not report["pending"]:
            write(marker_path, json_bytes(marker), None)
        for entry, payload in zip(value["entries"], after):
            if current[entry["id"]] != entry["after_hash"]:
                write(inside(root, f"{entry['id']}.md"), payload, current[entry["id"]], registry_path.parent / "backups")
        # Verify the entire projected catalog before releasing readers. A failed
        # or interrupted operation deliberately leaves the marker in place.
        notes = inventory(root)
        by_id = {n["metadata"]["id"]: n for n in notes}
        ids = {e["id"] for e in value["entries"]}
        if (any(by_id.get(e["id"], {}).get("sha256") != e["after_hash"] for e in value["entries"])
                or catalog_hash([n for n in notes if n["metadata"]["id"] not in ids]) != value["other_catalog_hash"] or relations(notes)):
            raise UamlError("WRITE_CONFLICT", "Knowledge changed during completion; preserve marker and inspect before resuming.")
        if read_bytes(marker_path) != json_bytes(marker):
            raise UamlError("WRITE_CONFLICT", "Transaction marker changed; preserve it and inspect manually.")
        receipt_path = inside(vault_path, ".uaml/knowledge-revision.json")
        receipt = json_bytes({"schema_version": 1, "transaction_id": transaction_id})
        try:
            old_receipt = read_bytes(receipt_path)
        except UamlError as exc:
            if exc.code != "MEMORY_MISSING":
                raise
            old_receipt = None
        if receipt != old_receipt:
            write(receipt_path, receipt, digest(old_receipt) if old_receipt is not None else None, registry_path.parent / "backups")
        marker_path.unlink()  # Only the exact tool-owned marker under the Vault lock.
    return {**report, "status": "SUPERSESSION_APPLIED", "pending": False,
            "next_step": "Both links are saved; originals remain in the private plan/backups. Verify applicability before using the replacement."}
