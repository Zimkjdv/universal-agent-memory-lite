"""Bounded, scope-aware replica comparisons and explicit authority decisions."""
from pathlib import Path

from . import registry
from .binding import link_path, load_project, resolve
from .dedup import catalog_hash
from .errors import UamlError
from .formats import digest, frontmatter, json_bytes, now, project_link, read_bytes
from .paths import inside, local_key

MAX_COPIES = 8


def entry_for(manifest, value):
    entry = next((item for item in value["vaults"] if item["vault_id"] == manifest["binding"]["vault_id"]), None)
    if entry is None:
        raise UamlError("VAULT_UNREGISTERED", "Expected Vault is no longer registered.")
    return entry


def collect(manifest, value, expected_vault_hash, include_knowledge=False):
    entry = entry_for(manifest, value)
    if len(entry["candidates"]) > MAX_COPIES:
        raise UamlError("REPLICA_UNVERIFIED", "Too many registered copies for a bounded comparison; review the Registry.")
    observations, diagnostics = [], []
    for candidate in sorted(entry["candidates"], key=lambda c: c["candidate_id"]):
        path = Path(candidate["path"])
        observation = {"candidate_id": candidate["candidate_id"], "path": str(path), "status": "AVAILABLE",
                       "metadata_hash": None, "project_link_hash": None, "knowledge_hash": None}
        try:
            metadata = registry.read_vault(path)
            if metadata["vault"]["id"] != manifest["binding"]["vault_id"]:
                raise UamlError("VAULT_ID_MISMATCH", "Registered path now belongs to another Vault.")
            observation["metadata_hash"] = digest(read_bytes(inside(path, ".uaml/vault.yaml")))
            # A copied UUID cannot redirect an existing grant to a different layout.
            if observation["metadata_hash"] != expected_vault_hash:
                raise UamlError("REPLICA_IDENTITY_CHANGED", "Replica identity/layout metadata differs from the approved grant.")
            link = link_path(path, metadata, manifest)
            try:
                raw = read_bytes(link, "PROJECT_LINK_MISSING")
                header, _ = frontmatter(raw)
                project_link(header, manifest)
                observation["project_link_hash"] = digest(raw)
            except UamlError as exc:
                if exc.code != "PROJECT_LINK_MISSING":
                    raise
                # Absence in one available copy is a real divergence, not an empty replacement.
                observation["project_link_hash"] = "missing"
            if include_knowledge:
                from .knowledge import scan
                notes, issues, complete = scan(inside(path, metadata["layout"]["knowledge"]))
                if not complete:
                    raise UamlError("REPLICA_UNVERIFIED", "A replica knowledge scan is incomplete; resolve its errors before selection.")
                observation["knowledge_hash"] = catalog_hash(notes)
        except UamlError as exc:
            if exc.code == "VAULT_MISSING":
                observation["status"] = "MISSING"
            else:
                observation["status"] = "ERROR"
                diagnostics.append({**exc.diagnostic(), "candidate_id": candidate["candidate_id"]})
        observations.append(observation)
    available = [o for o in observations if o["status"] == "AVAILABLE"]
    if not any(o["candidate_id"] == entry["selected_candidate_id"] for o in available):
        diagnostics.append({"code": "REPLICA_UNVERIFIED", "message": "Selected replica is unavailable or unverified."})
    basis = {"project_id": manifest["project"]["id"], "project_memory_id": manifest["binding"]["project_memory_id"],
             "copies": [{key: val for key, val in observation.items() if key != "knowledge_hash"} for observation in observations]}
    project_hash = digest(json_bytes(basis))
    knowledge_hash = digest(json_bytes({"project_hash": project_hash, "copies": observations})) if include_knowledge else None
    project_diverged = len({o["project_link_hash"] for o in available}) > 1
    knowledge_diverged = include_knowledge and len({o["knowledge_hash"] for o in available}) > 1
    status = "REPLICA_UNVERIFIED" if diagnostics else ("REPLICA_CONFLICT" if project_diverged or knowledge_diverged else "REPLICA_EQUIVALENT")
    return {"status": status, "comparison_hash": knowledge_hash or project_hash,
            "project_comparison_hash": project_hash, "knowledge_comparison_hash": knowledge_hash,
            "include_knowledge": include_knowledge, "project_diverged": project_diverged,
            "knowledge_diverged": bool(knowledge_diverged), "complete": not diagnostics,
            "available_count": len(available), "missing_count": sum(o["status"] == "MISSING" for o in observations),
            "copies": observations, "diagnostics": diagnostics}


def guard(manifest, value, expected_vault_hash, include_knowledge=False):
    entry = entry_for(manifest, value)
    if len(entry["candidates"]) == 1:
        return None
    report = collect(manifest, value, expected_vault_hash, include_knowledge)
    if not report["complete"]:
        raise UamlError("REPLICA_UNVERIFIED", "Known copies cannot be fully checked; run vault compare and review diagnostics.")
    if report["status"] == "REPLICA_CONFLICT":
        approved = next((r for r in entry.get("replica_resolutions", [])
                         if r["project_id"] == manifest["project"]["id"] and r["project_memory_id"] == manifest["binding"]["project_memory_id"]
                         and r["selected_candidate_id"] == entry["selected_candidate_id"]
                         and r["project_comparison_hash"] == report["project_comparison_hash"]
                         and (not include_knowledge or r["knowledge_comparison_hash"] == report["knowledge_comparison_hash"])), None)
        if not approved:
            raise UamlError("REPLICA_CONFLICT", "Known copies diverge; compare them and explicitly select authority for this project.")
        return {"status": "REPLICA_AUTHORITY_CONFIRMED", "comparison_hash": report["comparison_hash"], "missing_count": report["missing_count"]}
    return {"status": report["status"], "comparison_hash": report["comparison_hash"], "missing_count": report["missing_count"]}


def compare(git, registry_path, include_knowledge=False):
    # Bypass ONLY the conflict guard to permit diagnosis; never bypass grants,
    # Vault identity/layout verification or the selected project's association.
    binding = resolve(git, registry_path, check_replicas=False)
    if binding["status"] != "RESOLVED":
        raise UamlError(binding["status"], "Approve a valid selected checkout before comparing its copies.")
    if include_knowledge and binding["access"]["knowledge_access"] == "none":
        raise UamlError("KNOWLEDGE_ACCESS_DENIED", "Knowledge comparison needs an explicit knowledge read/write grant.")
    manifest, _ = load_project(git)
    value = registry.load(registry_path)
    path = registry.selected(value, manifest["binding"]["vault_id"])
    if local_key(path) != local_key(Path(binding["vault_path"])):
        raise UamlError("WRITE_CONFLICT", "Replica selection changed during comparison.")
    return collect(manifest, value, binding["vault_fingerprint"], include_knowledge)


def select(git, registry_path, path, expected_comparison, include_knowledge=False):
    if not expected_comparison:
        raise UamlError("PLAN_REQUIRED", "Run vault compare and pass its --expect-comparison hash.")
    manifest, _ = load_project(git)
    current_report = compare(git, registry_path, include_knowledge)
    if not current_report["complete"]:
        raise UamlError("REPLICA_UNVERIFIED", "Unverified copies cannot be acknowledged as a complete comparison.")
    if current_report["comparison_hash"] != expected_comparison:
        raise UamlError("WRITE_CONFLICT", "Replica contents changed after comparison; review again.")

    def change(value):
        checked = compare(git, registry_path, include_knowledge)
        if checked["comparison_hash"] != expected_comparison or not checked["complete"]:
            raise UamlError("WRITE_CONFLICT", "Replica comparison changed before selection.")
        entry = entry_for(manifest, value)
        candidate = next((c for c in entry["candidates"] if local_key(Path(c["path"])) == local_key(path)), None)
        if candidate is None or not any(o["candidate_id"] == candidate["candidate_id"] and o["status"] == "AVAILABLE" for o in checked["copies"]):
            raise UamlError("VAULT_UNREGISTERED", "Select one of the registered, available, verified copies.")
        if any(o["candidate_id"] == candidate["candidate_id"] and o["project_link_hash"] == "missing" for o in checked["copies"]):
            raise UamlError("PROJECT_LINK_MISSING", "An authority needs this project's valid reverse association.")
        entry["selected_candidate_id"] = candidate["candidate_id"]
        decisions = [r for r in entry.get("replica_resolutions", []) if r["project_id"] != manifest["project"]["id"] or
                     r["project_memory_id"] != manifest["binding"]["project_memory_id"]]
        decisions.append({"project_id": manifest["project"]["id"], "project_memory_id": manifest["binding"]["project_memory_id"],
                          "selected_candidate_id": candidate["candidate_id"], "project_comparison_hash": checked["project_comparison_hash"],
                          "knowledge_comparison_hash": checked["knowledge_comparison_hash"], "accepted_at": now()})
        entry["replica_resolutions"] = decisions

    registry.update(registry_path, change)
    return {"status": "REPLICA_SELECTED", "comparison_hash": expected_comparison,
            "next_step": "Only local authority was selected; no notes were merged, deleted or synchronized."}
