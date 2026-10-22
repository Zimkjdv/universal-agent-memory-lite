import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import yaml

from .errors import UamlError
from .paths import relative_path

MAX_DOCUMENT = 256 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: Path, missing="MEMORY_MISSING") -> bytes:
    try:
        with path.open("rb") as stream:
            result = stream.read(MAX_DOCUMENT + 1)
    except FileNotFoundError as exc:
        raise UamlError(missing, "Required file is missing.") from exc
    except PermissionError as exc:
        raise UamlError("READ_DENIED", "Permission denied while reading a required file.") from exc
    except OSError as exc:
        raise UamlError("READ_FAILED", "Cannot read a required file.") from exc
    if len(result) > MAX_DOCUMENT:
        raise UamlError("DOCUMENT_TOO_LARGE", "Document exceeds the 256 KiB prototype limit.")
    return result


def text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise UamlError("MEMORY_CORRUPT", "Expected UTF-8 text.") from exc


def pairs(items):
    result = {}
    for key, value in items:
        if not isinstance(key, str) or key in result:
            raise UamlError("MEMORY_CORRUPT", "Object keys must be unique strings.")
        result[key] = value
    return result


def parse_yaml(data: str) -> dict:
    try:
        depth = 0
        for token in yaml.scan(data):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)):
                raise UamlError("MEMORY_CORRUPT", "YAML tags, anchors and aliases are prohibited.")
            if isinstance(token, (yaml.tokens.BlockMappingStartToken, yaml.tokens.BlockSequenceStartToken,
                                  yaml.tokens.FlowMappingStartToken, yaml.tokens.FlowSequenceStartToken)):
                depth += 1
                if depth > 16:
                    raise UamlError("MEMORY_CORRUPT", "YAML nesting is too deep.")
            elif isinstance(token, (yaml.tokens.BlockEndToken, yaml.tokens.FlowMappingEndToken,
                                    yaml.tokens.FlowSequenceEndToken)):
                depth -= 1

        class Loader(yaml.SafeLoader):
            pass

        def mapping(loader, node):
            # Avoid merge-key flattening, which otherwise hides duplicate keys.
            if any(key.value == "<<" for key, _ in node.value):
                raise UamlError("MEMORY_CORRUPT", "YAML merge keys are prohibited.")
            return pairs((loader.construct_object(k), loader.construct_object(v)) for k, v in node.value)

        Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        value = yaml.load(data, Loader=Loader)
    except (yaml.YAMLError, ValueError, RecursionError) as exc:
        raise UamlError("MEMORY_CORRUPT", "Invalid YAML document.") from exc
    if not isinstance(value, dict):
        raise UamlError("MEMORY_CORRUPT", "Expected a YAML object.")
    return value


def parse_json(data: bytes) -> dict:
    try:
        value = json.loads(text(data), object_pairs_hook=pairs)
    except (ValueError, RecursionError) as exc:
        raise UamlError("MEMORY_CORRUPT", "Invalid JSON document.") from exc
    if not isinstance(value, dict):
        raise UamlError("MEMORY_CORRUPT", "Expected a JSON object.")
    return value


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def yaml_bytes(value: dict) -> bytes:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).encode("utf-8")


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise UamlError("SCHEMA_INVALID", "Missing or unknown schema fields.")


def identifier(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise UamlError("SCHEMA_INVALID", "Expected a canonical UUID.") from exc


def string(value):
    if not isinstance(value, str) or not value.strip() or any(ord(ch) < 32 for ch in value):
        raise UamlError("SCHEMA_INVALID", "Expected a nonempty single-line string.")


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError, AttributeError) as exc:
        raise UamlError("SCHEMA_INVALID", "Expected a timestamp with a timezone.") from exc


def base(value, kind):
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise UamlError("SCHEMA_UNSUPPORTED", "Only schema_version 1 is supported.")
    if value.get("kind") != kind or type(value.get("revision")) is not int or value["revision"] < 1:
        raise UamlError("SCHEMA_INVALID", "Invalid kind or revision.")
    if "extensions" in value and value["extensions"] != {}:
        raise UamlError("SCHEMA_INVALID", "The prototype only accepts empty extensions.")


def safe_metadata(value):
    """Reject path-bearing or credential-like public metadata, not all possible secrets."""
    rendered = json.dumps(value, ensure_ascii=False)
    if re.search(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN .*PRIVATE KEY-----|sk-[A-Za-z0-9_-]{20,})", rendered):
        raise UamlError("SENSITIVE_CONTENT", "Possible credential detected; value omitted.")


def public_name(value):
    string(value)
    if any(ch in value for ch in ("/", "\\", ":")):
        raise UamlError("SCHEMA_INVALID", "Display names cannot contain paths or URLs.")
    safe_metadata(value)


def project(value):
    fields(value, ("schema_version", "kind", "revision", "project", "binding", "memory"),
           ("repository", "extensions"))
    base(value, "uaml_project")
    fields(value["project"], ("id", "name"))
    identifier(value["project"]["id"])
    public_name(value["project"]["name"])
    fields(value["binding"], ("vault_id", "project_memory_id"))
    for val in value["binding"].values():
        identifier(val)
    fields(value["memory"], ("authority", "project_state", "handoff", "checkpoint"))
    if value["memory"]["authority"] != "repository":
        raise UamlError("SCHEMA_INVALID", "Only repository memory authority is supported.")
    memory_paths = [relative_path(value["memory"][key]) for key in ("project_state", "handoff", "checkpoint")]
    if len({p.casefold() for p in memory_paths}) != 3:
        raise UamlError("SCHEMA_INVALID", "Memory paths must be distinct.")
    if memory_paths != ["docs/memory/PROJECT-STATE.md", "docs/memory/HANDOFF.md", "docs/memory/checkpoint.json"]:
        raise UamlError("SCHEMA_INVALID", "The prototype only writes the three standard docs/memory files.")
    if "repository" in value:
        from urllib.parse import urlsplit
        fields(value["repository"], (), ("canonical_url",))
        url = value["repository"].get("canonical_url")
        if url is not None:
            string(url)
            try:
                parsed = urlsplit(url)
            except ValueError as exc:
                raise UamlError("SCHEMA_INVALID", "Invalid repository URL hint.") from exc
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise UamlError("SCHEMA_INVALID", "Use a credential-free HTTPS repository hint.")
    safe_metadata(value)
    return value


def vault(value):
    fields(value, ("schema_version", "kind", "revision", "vault", "layout"), ("extensions",))
    base(value, "uaml_vault")
    fields(value["vault"], ("id", "name"))
    identifier(value["vault"]["id"])
    public_name(value["vault"]["name"])
    fields(value["layout"], ("projects", "knowledge"))
    for val in value["layout"].values():
        relative_path(val)
    a, b = (value["layout"][key].casefold() for key in ("projects", "knowledge"))
    if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
        raise UamlError("SCHEMA_INVALID", "Vault areas must not overlap.")
    safe_metadata(value)
    return value


def frontmatter(data: bytes):
    content = text(data).replace("\r\n", "\n")
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise UamlError("MEMORY_CORRUPT", "Markdown needs delimited YAML frontmatter.")
    header, body = content[4:].split("\n---\n", 1)
    return parse_yaml(header), body


def markdown(header: dict, body: str) -> bytes:
    return b"---\n" + yaml_bytes(header) + b"---\n" + body.encode("utf-8")


def project_link(value, manifest):
    fields(value, ("schema_version", "kind", "revision", "project_id", "project_memory_id", "vault_id", "project_name", "state_authority", "knowledge_ids"), ("repository_url",))
    base(value, "project_link")
    if (value["project_id"] != manifest["project"]["id"]
            or any(value[key] != manifest["binding"][key] for key in ("vault_id", "project_memory_id"))
            or value["state_authority"] != "repository"):
        raise UamlError("PROJECT_LINK_MISMATCH", "Vault project association does not match this repository.")
    public_name(value["project_name"])
    if not isinstance(value["knowledge_ids"], list):
        raise UamlError("SCHEMA_INVALID", "Expected knowledge ID list.")
    for val in value["knowledge_ids"]:
        identifier(val)


def memory(value, kind, project_id):
    fields(value, ("schema_version", "kind", "revision", "project_id", "snapshot_id", "updated_at", "source_agent", "git"))
    base(value, kind)
    identifier(value["snapshot_id"])
    timestamp(value["updated_at"])
    string(value["source_agent"])
    if value["project_id"] != project_id:
        raise UamlError("PROJECT_LINK_MISMATCH", "Memory belongs to a different project.")
    fields(value["git"], ("branch", "head", "object_format", "working_tree", "upstream", "remote_freshness"),
           ("working_tree_fingerprint",))
    git = value["git"]
    if git["object_format"] not in ("sha1", "sha256") or git["working_tree"] not in ("clean", "dirty", "conflicted", "unknown") or git["remote_freshness"] != "unknown":
        raise UamlError("SCHEMA_INVALID", "Invalid Git snapshot.")
    size = 40 if git["object_format"] == "sha1" else 64
    if git["head"] is not None and (not isinstance(git["head"], str) or not re.fullmatch(rf"[0-9a-f]{{{size}}}", git["head"])):
        raise UamlError("SCHEMA_INVALID", "Invalid full Git object ID.")
    for key in ("branch", "upstream"):
        if git[key] is not None:
            string(git[key])
    fingerprint = git.get("working_tree_fingerprint")
    if fingerprint is not None and (not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
        raise UamlError("SCHEMA_INVALID", "Invalid working tree fingerprint.")
