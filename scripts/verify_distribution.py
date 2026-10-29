"""Audit built artifacts, then test an offline wheel install in a disposable venv."""
import argparse
import configparser
import email
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def safe_names(names):
    for name in names:
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or
                any(part in (".git", ".venv", ".uaml-local", "__pycache__") for part in path.parts)):
            raise ValueError("Unsafe/private archive path: " + name)


def requirement(value):
    name, specs = re.fullmatch(r"([A-Za-z0-9_.-]+)(.*)", value.strip()).groups()
    return name.lower().replace("_", "-"), tuple(sorted(s.strip() for s in specs.split(",") if s.strip()))


def audit_wheel(path, root=ROOT):
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        safe_names(names)
        if len(names) != len(set(names)) or len(names) > 4096 or sum(i.file_size for i in archive.infolist()) > MAX_ARCHIVE_BYTES:
            raise ValueError("Duplicate/oversized wheel inventory.")
        expected = {"uaml/" + source.name for source in (root / "src/uaml").glob("*.py")}
        actual = {name for name in names if name.startswith("uaml/")}
        if actual != expected or any(not (name in expected or ".dist-info/" in name) for name in names):
            raise ValueError("Wheel is missing modules or contains unexpected payloads.")
        metadata_paths = [n for n in names if n.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError("Wheel must contain one metadata directory.")
        prefix = metadata_paths[0].removesuffix("METADATA")
        if any(".dist-info/" in n and not n.startswith(prefix) for n in names):
            raise ValueError("Unexpected additional wheel metadata directory.")
        metadata = email.message_from_bytes(archive.read(metadata_paths[0]))
        if (metadata["Name"] != project["name"] or metadata["Version"] != project["version"] or
                metadata["Requires-Python"] != project["requires-python"] or metadata["License-Expression"] != "MIT"):
            raise ValueError("Wheel name/version/Python/license metadata differs from project configuration.")
        runtime = [req for req in metadata.get_all("Requires-Dist", []) if "extra ==" not in req]
        if {requirement(req) for req in runtime} != {requirement(req) for req in project["dependencies"]}:
            raise ValueError("Wheel runtime dependencies differ from the approved project dependencies.")
        if archive.read(prefix + "licenses/LICENSE") != (root / "LICENSE").read_bytes():
            raise ValueError("Wheel license text differs from the repository license.")
        entry = configparser.ConfigParser()
        entry.read_string(archive.read(prefix + "entry_points.txt").decode("utf-8"))
        if not entry.has_option("console_scripts", "uaml") or entry.get("console_scripts", "uaml") != "uaml.cli:main":
            raise ValueError("Missing installed uaml console entry point.")
    return project["version"]


def audit_sdist(path, root=ROOT):
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        safe_names(m.name for m in members)
        if len(members) > 4096 or sum(m.size for m in members) > MAX_ARCHIVE_BYTES or any(not (m.isfile() or m.isdir()) for m in members):
            raise ValueError("Unsupported links or oversized source archive.")
        tops = {PurePosixPath(m.name).parts[0] for m in members}
        if len(tops) != 1 or len({m.name for m in members}) != len(members):
            raise ValueError("Source archive must have one unique root.")
        names = {PurePosixPath(m.name).relative_to(next(iter(tops))).as_posix() for m in members}
        required = {"pyproject.toml", "LICENSE", "README.md", "INSTALL.md", "ROADMAP.MD", "CHANGELOG.md",
                    "examples/demo.py", "scripts/verify_distribution.py", "tests/support.py", "docs/MIGRATION-GUIDE.md"}
        required |= {p.relative_to(root).as_posix() for p in (root / "src/uaml").glob("*.py")}
        required |= {p.relative_to(root).as_posix() for p in (root / "tests").glob("*.py")}
        if not required.issubset(names):
            raise ValueError("Source archive omits code, tests, verification script or required guides.")
        if any("registry.json" == PurePosixPath(name).name or ".uaml" in PurePosixPath(name).parts for name in names):
            raise ValueError("Source archive contains machine-private UAML data.")


def run(command, cwd, env):
    result = subprocess.run([str(arg) for arg in command], cwd=cwd, env=env, capture_output=True, timeout=600)
    if result.returncode:
        sys.stderr.write(result.stdout.decode("utf-8", errors="replace"))
        sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
        raise ValueError("Distribution validation command failed: " + str(command[0]))
    return result


def verify(dist, wheelhouse):
    wheels, sources = list(dist.glob("*.whl")), list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Use a fresh dist directory containing exactly one wheel and one sdist.")
    version = audit_wheel(wheels[0])
    audit_sdist(sources[0])
    environment = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "GIT_", "PIP_")) and k != "UAML_HOME"}
    environment.update(PIP_NO_INDEX="1", PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONIOENCODING="utf-8")
    with tempfile.TemporaryDirectory(prefix="uaml-wheel-check-") as folder:
        workspace = Path(folder)
        isolated = workspace / "venv"
        venv.EnvBuilder(with_pip=True).create(isolated)
        binary = isolated / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([binary, "-I", "-m", "pip", "install", "--no-index", "--find-links", wheelhouse.resolve(), wheels[0].resolve()], workspace, environment)
        run([binary, "-I", "-m", "pip", "check"], workspace, environment)
        probe = ("import importlib.metadata,json,sys; from pathlib import Path; import uaml; "
                 "assert Path(uaml.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
                 "assert importlib.metadata.version('universal-agent-memory-lite')==sys.argv[1]; "
                 "assert uaml.__version__==sys.argv[1]; print(json.dumps({'version':uaml.__version__,'origin':'isolated-wheel'}))")
        run([binary, "-I", "-c", probe, version], workspace, environment)
        console = isolated / ("Scripts/uaml.exe" if os.name == "nt" else "bin/uaml")
        if run([console, "--version"], workspace, environment).stdout.decode().strip() != version:
            raise ValueError("Installed console version differs from wheel metadata.")
        run([binary, "-I", "-m", "uaml", "--help"], workspace, environment)
        demo = run([binary, "-I", ROOT / "examples/demo.py"], workspace, environment)
        suite = run([binary, "-I", "-m", "unittest", "discover", "-s", ROOT / "tests", "-t", ROOT], workspace, environment)
        print(demo.stdout.decode("utf-8", errors="replace").strip())
        print(suite.stderr.decode("utf-8", errors="replace").strip())
    result = {"status": "DISTRIBUTION_VERIFIED", "version": version, "origin": "isolated-wheel",
              "wheel_sha256": hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
              "sdist_sha256": hashlib.sha256(sources[0].read_bytes()).hexdigest(),
              "installation_network": "disabled", "published": False}
    print(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True, help="pre-downloaded runtime wheels for offline installation")
    args = parser.parse_args()
    try:
        verify(args.dist.resolve(), args.wheelhouse.resolve())
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, tarfile.TarError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "DISTRIBUTION_FAILED", "message": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
