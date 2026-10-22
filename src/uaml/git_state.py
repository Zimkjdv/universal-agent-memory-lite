import os
import subprocess
from pathlib import Path

from .errors import UamlError
from .formats import digest
from .paths import inside


class Git:
    def __init__(self, path: Path):
        self.cwd = path.resolve()
        # Discard inherited repository selectors; never trust an ambient GIT_DIR.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
        self.root = Path(self.run("rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()

    def run(self, *args, optional=False):
        try:
            process = subprocess.run(
                ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                 "-c", "core.untrackedCache=false", "-c", "core.quotePath=false", *args],
                cwd=self.cwd, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30, check=False,
            )
        except FileNotFoundError as exc:
            raise UamlError("GIT_UNAVAILABLE", "Install Git and make it available on PATH.") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UamlError("GIT_FAILED", "Git could not complete within 30 seconds.") from exc
        if process.returncode:
            if optional:
                return None
            if b"dubious ownership" in process.stderr:
                raise UamlError("GIT_UNTRUSTED", "Git rejected repository ownership; run this CLI as the repository owner or review Git trust settings yourself.")
            raise UamlError("GIT_FAILED", "Git command failed; verify this is an accessible worktree.")
        return process.stdout

    def identity(self):
        directory = self.run("rev-parse", "--absolute-git-dir").decode("utf-8").strip()
        # Do not expose URLs that may contain credentials. Hash remote configuration.
        remotes = self.run("config", "--local", "--get-regexp", r"^remote\..*\.url$", optional=True) or b""
        return {"repository_root": str(self.root), "git_directory": str(Path(directory).resolve()),
                "remote_fingerprint": digest(remotes)}

    def observe(self, excluded=()):
        def decode(raw):
            return raw.decode("utf-8", errors="replace").strip() if raw is not None else None

        head = decode(self.run("rev-parse", "--verify", "HEAD", optional=True))
        branch = decode(self.run("symbolic-ref", "--quiet", "--short", "HEAD", optional=True))
        upstream = decode(self.run("rev-parse", "--abbrev-ref", "@{upstream}", optional=True))
        raw = self.run("status", "--porcelain=v1", "-z", "--untracked-files=all")
        records = raw.decode("utf-8", errors="replace").split("\0")
        entries = []
        index = 0
        while index < len(records) and records[index]:
            record = records[index]
            status, path = record[:2], record[3:]
            index += 1
            entry = {"status": status, "path": path}
            if "R" in status or "C" in status:
                entry["original_path"] = records[index]
                index += 1
            entries.append(entry)
        conflicts = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
        def ignored(path):
            return any(path == item or path.startswith(item + "/") for item in excluded)
        relevant = [item for item in entries if not ignored(item["path"]) or
                    ("original_path" in item and not ignored(item["original_path"]))]
        fingerprint = None
        warning = None
        # Fingerprint full content of changed files; never emit their contents.
        parts = []
        total = 0
        if relevant:
            parts.append(self.run("ls-files", "--stage", "-z", "--",
                                  *(f":(literal){item['path']}" for item in relevant)))
        for item in relevant:
            parts.append(repr(sorted(item.items())).encode("utf-8"))
            try:
                target = inside(self.root, item["path"])
                if target.name.lower().startswith(".env") or target.suffix.lower() in (".pem", ".key", ".pfx"):
                    warning = "Potential credential files were not read for fingerprinting."
                    break
                if target.is_symlink() or target.is_dir():
                    warning = "Fingerprint excludes links/submodules; inspect them separately."
                    break
                if target.exists():
                    with target.open("rb") as stream:
                        content = stream.read(4 * 1024 * 1024 + 1)
                    total += len(content)
                    if len(content) > 4 * 1024 * 1024 or total > 16 * 1024 * 1024:
                        warning = "Fingerprint budget exceeded; inspect changed content separately."
                        break
                    parts.append(digest(content).encode("ascii"))
            except (OSError, UamlError):
                warning = "Some changed paths cannot be fingerprinted safely."
                break
        if warning is None:
            fingerprint = digest(b"\0".join(parts))
        snapshot = {
            "branch": branch, "head": head,
            "object_format": decode(self.run("rev-parse", "--show-object-format")),
            "working_tree": "conflicted" if any(e["status"] in conflicts for e in relevant) else ("dirty" if relevant else "clean"),
            "upstream": upstream, "remote_freshness": "unknown",
            "working_tree_fingerprint": fingerprint,
        }
        return {"snapshot": snapshot, "changes": entries, "fingerprint_excluded": list(excluded),
                "fingerprint_warning": warning, "remote_freshness": "unknown"}
