"""Read-only structural/integrity checks; never certify technical correctness."""
import re
from pathlib import Path

from . import knowledge
from .binding import load_project
from .errors import UamlError
from .formats import frontmatter, read_bytes
from .paths import inside
from .recovery import recover

SECTIONS = {
    "project_state": [("目標",), ("已完成",), ("未完成",), ("Blockers",), ("下一步",)],
    "handoff": [("當前任務",), ("已完成",), ("未完成",), ("主要變更檔案",),
                ("Git 與 Working Tree",), ("測試和驗證", "測試與驗證"), ("Blockers",),
                ("下一步",), ("風險與未確認假設",), ("未保存或無法恢復的資訊",)],
}


def sections(body, kind, path):
    headings, current, fence = {}, None, None
    for line in body.splitlines():
        fenced = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fenced:
            marker, rest = fenced.groups()
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1] and not rest.strip():
                fence = None
            if current:
                headings[current][-1].append(line)
            continue
        if fence:
            if current and line.strip():
                headings[current][-1].append(line)
            continue
        heading = re.match(r"^ {0,3}##\s+(.+?)\s*#*\s*$", line)
        if heading:
            current = heading[1].strip()
            headings.setdefault(current, []).append([])
        elif current and line.strip():
            headings[current][-1].append(line)
    issues = []
    for aliases in SECTIONS[kind]:
        matches = [body for alias in aliases for body in headings.get(alias, [])]
        if len(matches) != 1 or not matches[0]:
            issues.append({"code": "MEMORY_SECTION_INVALID", "path": path,
                           "message": f"Expected one nonempty section: {aliases[0]}."})
    return issues


def relations(notes):
    by_id = {note["metadata"]["id"]: note["metadata"] for note in notes}
    issues = []
    for note in notes:
        header, path = note["metadata"], note["path"]
        refs = header["related_ids"] + header["supersedes"]
        if header.get("superseded_by"):
            refs = refs + [header["superseded_by"]]
        if any(ref not in by_id for ref in refs):
            issues.append({"code": "KNOWLEDGE_LINK_MISSING", "path": path, "message": "A referenced knowledge ID is missing."})
        for old_id in header["supersedes"]:
            old = by_id.get(old_id)
            if old and (old["status"] != "superseded" or old.get("superseded_by") != header["id"]):
                issues.append({"code": "SUPERSESSION_MISMATCH", "path": path, "message": "Supersession requires a matching reverse association."})
        if header["status"] == "superseded":
            replacement = by_id.get(header["superseded_by"])
            if replacement and header["id"] not in replacement["supersedes"]:
                issues.append({"code": "SUPERSESSION_MISMATCH", "path": path, "message": "Replacement does not reference the superseded note."})
    visiting, finished = set(), set()

    def cyclic(note_id):
        if note_id in visiting:
            return True
        if note_id in finished or note_id not in by_id:
            return False
        visiting.add(note_id)
        if any(cyclic(old_id) for old_id in by_id[note_id]["supersedes"]):
            return True
        visiting.remove(note_id)
        finished.add(note_id)
        return False

    if any(cyclic(note_id) for note_id in by_id):
        issues.append({"code": "SUPERSESSION_CYCLE", "message": "Supersession graph contains a cycle."})
    return issues


def validate(git, registry_path, include_knowledge=False):
    recovery = recover(git, registry_path)
    diagnostics = list(recovery["diagnostics"])
    checks = [{"area": "binding", "status": recovery["binding"]["status"]}]
    checked_files = []
    try:
        manifest, _ = load_project(git)
        for source in recovery["sources"]:
            kind = source["metadata"]["kind"]
            try:
                _, body = frontmatter(read_bytes(inside(git.root, source["path"])))
                issues = sections(body, kind, source["path"])
                diagnostics.extend(issues)
                checks.append({"area": kind, "status": "ISSUES" if issues or not source["checkpoint_verified"] else "VALID",
                               "path": source["path"], "sha256": source["sha256"]})
                checked_files.append(source["path"])
            except UamlError as exc:
                diagnostics.append({**exc.diagnostic(), "path": source["path"]})
        for key in ("project_state", "handoff"):
            if manifest["memory"][key] not in checked_files:
                checks.append({"area": key, "status": "UNVERIFIED", "path": manifest["memory"][key]})
    except UamlError:
        # Recovery already reports the binding/schema failure.
        manifest = None
    checks.append({"area": "checkpoint", "status": "VALID" if len(recovery["sources"]) == 2 and
                   all(source["checkpoint_verified"] for source in recovery["sources"]) else "UNVERIFIED"})
    if include_knowledge:
        try:
            _, _, root = knowledge.authorize(git, registry_path)
            notes, issues, complete = knowledge.scan(root)
            diagnostics.extend(issues)
            if complete:
                before_count = len(diagnostics)
                link_issues = relations(notes)
                diagnostics.extend(link_issues)
                if recovery["binding"].get("project_link"):
                    # Use the exact resolver-provided path, never infer another Vault root.
                    vault_path = Path(recovery["binding"]["vault_path"])
                    relative_link = Path(recovery["binding"]["project_link"]).relative_to(vault_path).as_posix()
                    link_header, _ = frontmatter(read_bytes(inside(vault_path, relative_link)))
                    existing_ids = {note["metadata"]["id"] for note in notes}
                    if any(item not in existing_ids for item in link_header["knowledge_ids"]):
                        diagnostics.append({"code": "PROJECT_KNOWLEDGE_LINK_MISSING", "message": "Project index references missing knowledge."})
                checks.append({"area": "knowledge", "status": "ISSUES" if len(diagnostics) > before_count else "VALID", "scanned": len(notes)})
            else:
                checks.append({"area": "knowledge", "status": "INCOMPLETE", "scanned": len(notes)})
        except UamlError as exc:
            diagnostics.append(exc.diagnostic())
            checks.append({"area": "knowledge", "status": "UNVERIFIED"})
    else:
        checks.append({"area": "knowledge", "status": "NOT_REQUESTED"})
    return {"status": "VALIDATED" if not diagnostics else "VALIDATION_ISSUES", "checks": checks,
            "diagnostics": diagnostics, "git": recovery["git"],
            "limitations": ["Valid structure and hashes do not prove historical claims or technical solutions.",
                            "Validation is read-only and never repairs, executes notes or grants access."]}
