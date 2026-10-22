from pathlib import Path

from . import registry
from .errors import UamlError
from .formats import digest, frontmatter, now, parse_yaml, project, project_link, read_bytes, text
from .git_state import Git
from .paths import inside, local_key, require_local_registry


def load_project(git: Git):
    raw = read_bytes(inside(git.root, ".uaml/project.yaml"), "BINDING_MISSING")
    return project(parse_yaml(text(raw))), raw


def link_path(vault_path, vault_data, manifest):
    return inside(vault_path, f"{vault_data['layout']['projects']}/{manifest['binding']['project_memory_id']}/PROJECT.md")


def verify_vault(value, manifest):
    path = registry.selected(value, manifest["binding"]["vault_id"])
    data = registry.read_vault(path)
    if data["vault"]["id"] != manifest["binding"]["vault_id"]:
        raise UamlError("VAULT_ID_MISMATCH", "Selected directory belongs to a different Vault.")
    return path, data


def verify_link(path, data, manifest):
    file = link_path(path, data, manifest)
    header, _ = frontmatter(read_bytes(file, "PROJECT_LINK_MISSING"))
    project_link(header, manifest)
    return file


def trust(git: Git, registry_path: Path):
    require_local_registry(registry_path, git.root)
    manifest, raw = load_project(git)
    value = registry.load(registry_path)
    path, data = verify_vault(value, manifest)
    verify_link(path, data, manifest)
    grant = {**git.identity(), "binding_fingerprint": digest(raw),
             "vault_fingerprint": digest(read_bytes(inside(path, ".uaml/vault.yaml"))),
             "project_id": manifest["project"]["id"], **manifest["binding"],
             "access": "read", "scope": "project_link", "approved_at": now()}

    def change(current):
        # Revalidate the selected candidate and its identity under Registry lock.
        new_path, new_data = verify_vault(current, manifest)
        if local_key(new_path) != local_key(path) or new_data != data:
            raise UamlError("WRITE_CONFLICT", "Vault selection changed while approving.")
        current["checkout_grants"] = [g for g in current["checkout_grants"]
                                       if local_key(Path(g["repository_root"])) != local_key(git.root)]
        current["checkout_grants"].append(grant)

    registry.update(registry_path, change)
    return {"status": "TRUSTED", "project_id": manifest["project"]["id"], "access": "read", "scope": "project_link"}


def resolve(git: Git, registry_path: Path):
    manifest, raw = load_project(git)
    result = {"status": "UNRESOLVED", "project": manifest["project"],
              "binding": manifest["binding"], "repository_root": str(git.root),
              "access": {"read": False, "write": "unknown"}, "diagnostics": []}
    try:
        require_local_registry(registry_path, git.root)
        value = registry.load(registry_path)
        identity = git.identity()
        grant = next((g for g in value["checkout_grants"]
                      if local_key(Path(g["repository_root"])) == local_key(git.root)), None)
        expected = {**identity, "binding_fingerprint": digest(raw), "project_id": manifest["project"]["id"], **manifest["binding"]}
        if grant is None or any(grant[key] != val for key, val in expected.items()):
            raise UamlError("CHECKOUT_UNTRUSTED", "Run project trust after reviewing this checkout and binding.")
        path, data = verify_vault(value, manifest)
        if grant["vault_fingerprint"] != digest(read_bytes(inside(path, ".uaml/vault.yaml"))):
            raise UamlError("CHECKOUT_UNTRUSTED", "Vault layout or identity metadata changed; review and trust again.")
        file = verify_link(path, data, manifest)
        # Check containment of repository memory, but keep recovery integrity separate.
        for key in ("project_state", "handoff", "checkpoint"):
            inside(git.root, manifest["memory"][key])
        result.update(status="RESOLVED", vault_path=str(path), project_link=str(file),
                      access={"read": True, "write": "unknown", "scope": "project_link"})
    except UamlError as exc:
        result["status"] = exc.code
        result["diagnostics"].append(exc.diagnostic())
    return result
