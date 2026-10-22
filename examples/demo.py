"""Run the installed CLI against disposable files, never an existing Vault."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="uaml-demo-") as folder:
        base = Path(folder)
        repo, vault = base / "demo project", base / "demo vault"
        repo.mkdir()
        vault.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
        registry = base / "local" / "registry.json"

        def cli(*args, expected=0):
            result = subprocess.run([sys.executable, "-m", "uaml", "--repo", str(repo),
                                     "--registry", str(registry), "--json", *args], capture_output=True)
            if result.returncode != expected:
                raise RuntimeError(result.stdout.decode("utf-8", errors="replace"))
            data = json.loads(result.stdout.decode("utf-8"))
            print(f"{' '.join(args[:2])}: {data['status']}")
            return data

        identified = cli("vault", "init", str(vault), "--name", "Demo Vault")
        cli("vault", "register", str(vault))
        cli("project", "init", "--vault", identified["vault_id"], "--name", "Demo Project")
        cli("resolve", expected=1)  # New checkout has not been approved yet.
        cli("project", "trust")
        cli("checkpoint", "--agent", "demo")
        cli("recover")
        (repo / "new-work.txt").write_text("An unsaved development change.\n", encoding="utf-8")
        stale = cli("recover", expected=1)
        if not any(d["code"] == "STALE_MEMORY" for d in stale["diagnostics"]):
            raise RuntimeError("Expected stale memory detection")
        print("Stale memory detected; local work preserved. All demo files are disposable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
