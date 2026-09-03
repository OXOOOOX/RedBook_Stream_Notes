#!/usr/bin/env python3
"""Validate and package the public skill using only Python's standard library.

The allowlist deliberately excludes recordings, browser profiles, local secrets,
environments, caches, tests, and repository infrastructure. The ZIP contains a
SHA-256 manifest for accidental corruption detection, not a digital signature.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile


SKILL_NAME = "redbook-live-notes"
MANIFEST_NAME = "MANIFEST.json"
REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "agents/openai.yaml",
    "pyproject.toml",
    "requirements.txt",
)
OPTIONAL_FILES = ("LICENSE", "AGENTS.md")
TOP_LEVEL_TREES = {
    "scripts": {".py"},
    "references": {".md"},
    "assets": {".md", ".json"},
}
IGNORED_DIRECTORIES = {
    "__pycache__", "node_modules", "venv", "env", "runtime", "data",
    "logs", "recordings", "output", "outputs", "dist", "build", "tests",
    "browser-profile", "browser_profile", "profile", "profiles", "models",
}
PRIVATE_FILENAMES = {
    "secrets.py", "credentials.py", "tokens.py", "cookies.py",
    "secrets.json", "credentials.json", "tokens.json", "cookies.json",
    "session.json", "storage_state.json", "storage-state.json", "auth.json",
}
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
UNFINISHED_MARKER = re.compile(
    r"\b(?:TODO|TBD|FIXME|REPLACE_ME|PLACEHOLDER|YOUR_[A-Z_]+)\b"
    r"|\[(?:INSERT|FILL IN)\b",
    re.IGNORECASE,
)


class PackageError(ValueError):
    """A source or archive failed an explicit packaging constraint."""


def _allowlisted_path(name: str) -> bool:
    if name in REQUIRED_FILES or name in OPTIONAL_FILES:
        return True
    parts = PurePosixPath(name).parts
    if not parts or parts[-1].startswith(".") or parts[-1].lower() in PRIVATE_FILENAMES:
        return False
    if len(parts) == 2 and parts[0] in TOP_LEVEL_TREES:
        return PurePosixPath(name).suffix in TOP_LEVEL_TREES[parts[0]]
    if len(parts) >= 3 and parts[:2] == ("src", "redbook_stream_notes"):
        return (PurePosixPath(name).suffix == ".py"
                and not any(part.startswith(".") or part.lower() in IGNORED_DIRECTORIES
                            for part in parts[2:-1]))
    return False


def _reject_link(path: Path) -> None:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise PackageError(f"Symlinks and junctions cannot be packaged: {path}")


def _read_file(root: Path, relative: str) -> bytes:
    path = root / relative
    for parent in [path, *path.parents]:
        _reject_link(parent)
        if parent == root:
            break
    if not path.is_file():
        raise PackageError(f"Required package file is missing or not a file: {relative}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise PackageError(f"Package file exceeds {MAX_FILE_BYTES} bytes: {relative}")
    return path.read_bytes()


def collect_bundle_files(root: Path) -> dict[str, bytes]:
    """Read only allowlisted text/source files; never follow directory links."""
    root = Path(root).absolute()
    _reject_link(root)
    files = {name: _read_file(root, name) for name in REQUIRED_FILES}
    for name in OPTIONAL_FILES:
        if (root / name).exists() or (root / name).is_symlink():
            files[name] = _read_file(root, name)

    for dirname, suffixes in TOP_LEVEL_TREES.items():
        directory = root / dirname
        _reject_link(directory)
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise PackageError(f"Expected a directory: {dirname}")
        for path in sorted(directory.iterdir()):
            _reject_link(path)
            if (path.is_file() and path.suffix in suffixes
                    and not path.name.startswith(".")
                    and path.name.lower() not in PRIVATE_FILENAMES):
                name = path.relative_to(root).as_posix()
                files[name] = _read_file(root, name)

    source = root / "src" / "redbook_stream_notes"
    _reject_link(root / "src")
    _reject_link(source)
    if source.exists():
        if not source.is_dir():
            raise PackageError("Expected a directory: src/redbook_stream_notes")
        for current, dirs, names in os.walk(source, followlinks=False):
            current_path = Path(current)
            for name in dirs + names:
                _reject_link(current_path / name)
            dirs[:] = sorted(
                name for name in dirs
                if not name.startswith(".") and name.lower() not in IGNORED_DIRECTORIES
            )
            for name in sorted(names):
                path = current_path / name
                if (path.suffix == ".py" and not name.startswith(".")
                        and name.lower() not in PRIVATE_FILENAMES):
                    relative = path.relative_to(root).as_posix()
                    files[relative] = _read_file(root, relative)

    if sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise PackageError(f"Bundle exceeds {MAX_BUNDLE_BYTES} bytes")
    return dict(sorted(files.items()))


def _yaml_scalar(text: str, key: str, *, indent: int = 0) -> str:
    """Read the small scalar YAML subset used by skill metadata, without PyYAML."""
    lines = text.splitlines()
    matches = [
        (index, re.match(rf"^{' ' * indent}{re.escape(key)}:\s*(.*?)\s*$", line))
        for index, line in enumerate(lines)
    ]
    matches = [(index, match) for index, match in matches if match is not None]
    if len(matches) != 1:
        raise PackageError(f"Metadata must define exactly one {key!r} scalar")
    index, match = matches[0]
    assert match is not None
    value = match.group(1)
    if value in {"|", "|-", "|+", ">", ">-", ">+"}:
        parts = []
        for line in lines[index + 1:]:
            if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
                break
            parts.append(line.strip())
        value = (" " if value.startswith(">") else "\n").join(parts).strip()
    elif value.startswith('"'):
        try:
            value, consumed = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError as exc:
            raise PackageError(f"Invalid quoted metadata scalar {key!r}: {exc}") from exc
        remaining = match.group(1)[consumed:].strip()
        if remaining and not remaining.startswith("#"):
            raise PackageError(f"Unexpected content after {key!r}")
    elif value.startswith("'"):
        single = re.fullmatch(r"'((?:[^']|'')*)'(?:\s+#.*)?", value)
        if single is None:
            raise PackageError(f"Invalid quoted metadata scalar {key!r}")
        value = single.group(1).replace("''", "'")
    else:
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if value.startswith("#"):
            value = ""
        if (value.startswith(("[", "{", "&", "*", "!")) or ": " in value
                or value.lower() in {"null", "~", "true", "false", "yes", "no", "on", "off"}
                or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value)):
            raise PackageError(f"Metadata field {key!r} must be a plain or quoted scalar")
    if not isinstance(value, str) or not value.strip():
        raise PackageError(f"Metadata field {key!r} must be a nonempty string")
    return value


def _validate_metadata(files: dict[str, bytes]) -> None:
    skill = files["SKILL.md"].decode("utf-8-sig")
    frontmatter = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", skill, re.S)
    if frontmatter is None:
        raise PackageError("SKILL.md must begin with YAML frontmatter enclosed by ---")
    metadata = frontmatter.group(1)
    if _yaml_scalar(metadata, "name") != SKILL_NAME:
        raise PackageError(f"SKILL.md name must be {SKILL_NAME!r}")
    description = _yaml_scalar(metadata, "description")
    if len(description) > 1024 or "<" in description or ">" in description:
        raise PackageError("Skill description must be <=1024 characters and contain no angle brackets")
    if not skill[frontmatter.end():].strip():
        raise PackageError("SKILL.md needs workflow instructions after its frontmatter")

    agents = files["agents/openai.yaml"].decode("utf-8-sig")
    interface = re.search(r"^interface:\s*(?:#.*)?$([\s\S]*?)(?=^\S|\Z)", agents, re.M)
    if interface is None or len(re.findall(r"^interface:", agents, re.M)) != 1:
        raise PackageError("agents/openai.yaml must define exactly one interface mapping")
    metadata = interface.group(1)
    _yaml_scalar(metadata, "display_name", indent=2)
    short = _yaml_scalar(metadata, "short_description", indent=2)
    if len(short) > 64:
        raise PackageError("Agent short_description must be <=64 characters")
    prompt = _yaml_scalar(metadata, "default_prompt", indent=2)
    if f"${SKILL_NAME}" not in prompt:
        raise PackageError(f"Agent default_prompt must mention ${SKILL_NAME}")


def _markdown_destinations(text: str) -> list[str]:
    # Fenced examples and inline code are documentation, not navigable links.
    text = re.sub(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[^\n]*(?:\n|$)", "", text)
    text = re.sub(r"(`+).*?\1", "", text, flags=re.S)
    inline = re.findall(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+[^)]*)?\)", text)
    references = re.findall(r"(?m)^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", text)
    return [value[1:-1] if value.startswith("<") else value for value in inline + references]


def _validate_markdown_links(name: str, text: str, files: dict[str, bytes]) -> None:
    for destination in _markdown_destinations(text):
        parsed = urlsplit(destination)
        if (parsed.scheme and parsed.scheme.lower() != "file"
                and not re.match(r"^[A-Za-z]:[\\/]", destination)):
            continue
        if destination.startswith("//"):
            continue
        path = unquote(parsed.path).replace("\\", "/")
        if not path:
            continue
        if parsed.scheme or path.startswith("/"):
            raise PackageError(f"{name}: local link must be relative to the bundle: {destination}")
        parts = list(PurePosixPath(name).parent.parts)
        for component in path.split("/"):
            if component in {"", "."}:
                continue
            if component == "..":
                if not parts:
                    raise PackageError(f"{name}: link escapes the bundle: {destination}")
                parts.pop()
            else:
                parts.append(component)
        target = "/".join(parts)
        if target and target not in files and not any(item.startswith(target + "/") for item in files):
            raise PackageError(f"{name}: local link is missing from the bundle: {destination}")


def _validate_files(files: dict[str, bytes]) -> None:
    for name, content in files.items():
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise PackageError(f"Package files must be UTF-8 text: {name}") from exc
        if not text.strip() and not name.endswith(".py"):
            raise PackageError(f"Package file is empty: {name}")
        if name.endswith((".md", ".yaml")):
            marker = UNFINISHED_MARKER.search(text)
            if marker:
                raise PackageError(f"{name}: unfinished scaffold marker {marker.group(0)!r}")
        if name.endswith(".md"):
            _validate_markdown_links(name, text, files)
        elif name.endswith(".json"):
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise PackageError(f"{name}: invalid JSON: {exc}") from exc
        elif name.endswith(".py"):
            try:
                ast.parse(text, filename=name)
            except SyntaxError as exc:
                raise PackageError(f"{name}: invalid Python syntax: {exc}") from exc
    _validate_metadata(files)


def validate_source(root: Path) -> dict[str, bytes]:
    files = collect_bundle_files(root)
    _validate_files(files)
    return files


def _manifest(files: dict[str, bytes]) -> bytes:
    manifest = {
        "format": 1,
        "skill": SKILL_NAME,
        "files": [
            {"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in sorted(files.items())
        ],
    }
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _safe_archive_path(name: str) -> bool:
    path = PurePosixPath(name)
    return (not path.is_absolute() and ".." not in path.parts and "\\" not in name
            and ":" not in name and str(path) == name)


def verify_bundle(archive: Path) -> dict:
    """Validate the complete archive against its embedded manifest."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(set(names)) != len(names):
                raise PackageError("Archive contains duplicate paths")
            for info in infos:
                if (not _safe_archive_path(info.filename)
                        or not info.filename.startswith(SKILL_NAME + "/")
                        or info.is_dir()
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    raise PackageError(f"Unsafe archive entry: {info.filename}")
                if info.file_size > MAX_FILE_BYTES:
                    raise PackageError(f"Oversized archive entry: {info.filename}")
            if sum(info.file_size for info in infos) > MAX_BUNDLE_BYTES + MAX_FILE_BYTES:
                raise PackageError("Archive exceeds the uncompressed size limit")
            manifest_path = f"{SKILL_NAME}/{MANIFEST_NAME}"
            if manifest_path not in names:
                raise PackageError("Archive has no content manifest")
            manifest = json.loads(bundle.read(manifest_path))
            if (not isinstance(manifest, dict) or manifest.get("format") != 1
                    or manifest.get("skill") != SKILL_NAME
                    or not isinstance(manifest.get("files"), list)):
                raise PackageError("Archive manifest format is invalid")
            expected = {manifest_path}
            files = {}
            for entry in manifest["files"]:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise PackageError("Archive manifest contains an invalid file entry")
                relative = entry["path"]
                name = f"{SKILL_NAME}/{relative}"
                if not _safe_archive_path(relative) or not _allowlisted_path(relative) or name in expected:
                    raise PackageError(f"Invalid or duplicate manifest path: {relative}")
                expected.add(name)
                if name not in names:
                    raise PackageError(f"Archive is missing a manifest file: {relative}")
                content = bundle.read(name)
                if (entry.get("size") != len(content)
                        or entry.get("sha256") != hashlib.sha256(content).hexdigest()):
                    raise PackageError(f"Archive content does not match manifest: {relative}")
                files[relative] = content
            if expected != set(names):
                raise PackageError("Archive contains files absent from the manifest")
            if not {f"{SKILL_NAME}/{name}" for name in REQUIRED_FILES}.issubset(expected):
                raise PackageError("Archive is missing required skill files")
            _validate_files(files)
            return manifest
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, RuntimeError) as exc:
        raise PackageError(f"Cannot verify archive: {exc}") from exc


def create_bundle(root: Path, output: Path, *, force: bool = False) -> str:
    """Build a deterministic ZIP and publish it atomically without implicit overwrite."""
    files = validate_source(root)
    output = Path(output).absolute()
    _reject_link(output)
    if output.suffix.lower() != ".zip":
        raise PackageError("Output must have a .zip extension")
    if output.exists() and (not force or not output.is_file()):
        raise PackageError(f"Output already exists; choose another path or use --force: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False) as temp:
            temp_path = Path(temp.name)
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, content in sorted({**files, MANIFEST_NAME: _manifest(files)}.items()):
                info = zipfile.ZipInfo(f"{SKILL_NAME}/{name}", date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                bundle.writestr(info, content, compresslevel=9)
        verify_bundle(temp_path)
        digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
        if force:
            os.replace(temp_path, output)
            temp_path = None
        else:
            # Hard-link publication is atomic and fails if another writer won the race.
            # The temporary file lives on the same filesystem as its destination.
            try:
                os.link(temp_path, output)
            except FileExistsError as exc:
                raise PackageError(f"Output already exists; no file was overwritten: {output}") from exc
        return digest
    finally:
        if temp_path is not None and temp_path.exists():
            # This is only our single, explicitly named temporary file.
            temp_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="skill source directory (default: this script's repository)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate source without creating an archive")
    mode.add_argument("--verify", type=Path, metavar="ARCHIVE", help="check a ZIP's embedded SHA-256 manifest")
    parser.add_argument("--output", type=Path, help="ZIP destination (default: SOURCE/dist/redbook-live-notes.zip)")
    parser.add_argument("--force", action="store_true", help="explicitly replace the single output ZIP if it exists")
    args = parser.parse_args(argv)
    if (args.check or args.verify) and (args.output is not None or args.force):
        parser.error("--output and --force only apply when building an archive")
    try:
        if args.check:
            files = validate_source(args.source)
            print(f"OK: {len(files)} package files validated ({sum(map(len, files.values()))} bytes)")
        elif args.verify:
            manifest = verify_bundle(args.verify)
            print(f"OK: {len(manifest['files'])} archive files match their SHA-256 manifest")
        else:
            output = args.output or args.source / "dist" / f"{SKILL_NAME}.zip"
            digest = create_bundle(args.source, output, force=args.force)
            print(f"Created: {output.absolute()}")
            print(f"SHA256: {digest}")
        return 0
    except (PackageError, OSError) as exc:
        print(f"Package error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
