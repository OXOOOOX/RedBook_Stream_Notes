"""Distribution boundary and archive integrity tests, without live-stream services."""

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import zipfile

import pytest


SPEC = importlib.util.spec_from_file_location(
    "package_skill", Path(__file__).resolve().parents[1] / "scripts" / "package_skill.py"
)
assert SPEC is not None and SPEC.loader is not None
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def skill_source(tmp_path):
    root = tmp_path / "source"
    write(root, "SKILL.md", """---
name: redbook-live-notes
description: >-
  Listen to Xiaohongshu livestreams and produce notes.
  Use for livestream transcription and cleanup requests.
---
# Livestream notes
Follow the [setup instructions](references/setup.md).
""")
    write(root, "README.md", """# Livestream notes
Read the [skill](SKILL.md) and [sample](assets/example.json).
Example stream: https://example.com/live/...
""")
    write(root, "agents/openai.yaml", """interface:
  display_name: "RedBook Live Notes"
  short_description: "Transcribe livestreams and create clear notes"
  default_prompt: "Use $redbook-live-notes to summarize this stream."
""")
    write(root, "pyproject.toml", '[project]\nname = "redbook-stream-notes"\nversion = "0.1.0"\n')
    write(root, "requirements.txt", "fastapi\n")
    write(root, "references/setup.md", "# Setup\nRead the [project guide](../README.md).\n")
    write(root, "assets/example.json", '{"stream_url": "https://example.com/live/..."}\n')
    write(root, "src/redbook_stream_notes/__init__.py", '"""Stream notes package."""\n')
    write(root, "src/redbook_stream_notes/nested/helper.py", "ANSWER = 42\n")
    write(root, "scripts/redbook.py", 'print("redbook")\n')
    return root


def test_bundle_is_self_contained_and_excludes_private_runtime_files(skill_source, tmp_path):
    excluded = [
        ".env", ".env.example", ".git/config", ".github/workflows/ci.yml",
        "runtime/session.json", "data/transcript.json", "recordings/audio.wav",
        "browser-profile/Default/Cookies", ".venv/lib/auth.py", "tests/test_private.py",
        "src/redbook_stream_notes/__pycache__/helper.pyc",
        "src/redbook_stream_notes/runtime/secret.py",
        "src/redbook_stream_notes/.private/secret.py",
        "src/redbook_stream_notes/credentials.py", "scripts/tokens.py",
        "assets/cookies.txt", "assets/cookies.json", "assets/session.json",
        "scripts/nested/private.py", "references/private.txt",
    ]
    for path in excluded:
        write(skill_source, path, "PRIVATE_SENTINEL\n")
    output = tmp_path / "skill.zip"
    digest = package.create_bundle(skill_source, output)
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = package.verify_bundle(output)
    with zipfile.ZipFile(output) as bundle:
        names = bundle.namelist()
        assert all(name.startswith("redbook-live-notes/") for name in names)
        assert "redbook-live-notes/src/redbook_stream_notes/nested/helper.py" in names
        assert all(f"redbook-live-notes/{path}" not in names for path in excluded)
        assert not any(b"PRIVATE_SENTINEL" in bundle.read(name) for name in names)
        assert len(names) == len(manifest["files"]) + 1
        extracted = tmp_path / "installed"
        bundle.extractall(extracted)
    # Relative links and metadata remain valid after installing the ZIP elsewhere.
    files = package.validate_source(extracted / "redbook-live-notes")
    assert len(files) == len(manifest["files"])


def test_optional_agents_document_keeps_exact_bytes_and_relocated_links(skill_source, tmp_path):
    instructions = "# 项目文件操作约束\r\n\r\n禁止批量删除文件或目录。\r\n".encode("utf-8")
    (skill_source / "AGENTS.md").write_bytes(instructions)
    write(skill_source, "references/handoff.md", "# Handoff\nRead the [project instructions](../AGENTS.md).\n")
    write(skill_source, "README.md", "# Livestream notes\nRead the [handoff guide](references/handoff.md).\n")
    output = tmp_path / "with-agents.zip"
    package.create_bundle(skill_source, output)
    manifest = package.verify_bundle(output)
    agents_entry = next(entry for entry in manifest["files"] if entry["path"] == "AGENTS.md")
    assert agents_entry["sha256"] == hashlib.sha256(instructions).hexdigest()
    with zipfile.ZipFile(output) as bundle:
        assert bundle.read("redbook-live-notes/AGENTS.md") == instructions
        relocated = tmp_path / "new installation directory"
        bundle.extractall(relocated)
    installed = relocated / "redbook-live-notes"
    assert (installed / "AGENTS.md").read_bytes() == instructions
    assert package.validate_source(installed)["AGENTS.md"] == instructions


def test_repeated_build_is_deterministic_and_requires_explicit_overwrite(skill_source, tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    package.create_bundle(skill_source, first)
    original = first.read_bytes()
    package.create_bundle(skill_source, second)
    assert second.read_bytes() == original
    write(skill_source, "README.md", "# Changed project guide\n")
    with pytest.raises(package.PackageError, match="already exists"):
        package.create_bundle(skill_source, first)
    assert first.read_bytes() == original
    package.create_bundle(skill_source, first, force=True)
    assert first.read_bytes() != original
    package.verify_bundle(first)


@pytest.mark.parametrize("destination", ["missing.md", "../outside.md", "tests/private.py", "/tmp/external.md", "file:///tmp/external.md"])
def test_rejects_links_that_cannot_work_inside_the_bundle(skill_source, destination):
    write(skill_source, "README.md", f"# Guide\n[Read more]({destination})\n")
    with pytest.raises(package.PackageError, match="link"):
        package.validate_source(skill_source)


def test_reference_links_are_checked_but_code_examples_and_url_ellipsis_are_allowed(skill_source):
    write(skill_source, "README.md", """# Guide
[Setup][setup]
[setup]: references/setup.md
`[Example](missing.md)`
```markdown
[Example](missing.md)
```
[Stream](https://example.com/live/...)
""")
    package.validate_source(skill_source)
    write(skill_source, "README.md", "# Guide\n[setup]: references/missing.md\n")
    with pytest.raises(package.PackageError, match="missing from the bundle"):
        package.validate_source(skill_source)


@pytest.mark.parametrize("bad_skill", [
    "# Missing frontmatter\n",
    "---\nname: wrong-skill\ndescription: A useful skill\n---\n# Guide\n",
    "---\nname: redbook-live-notes\ndescription: TODO\n---\n# Guide\n",
    "---\nname: redbook-live-notes\ndescription: A useful skill\n---\n",
])
def test_rejects_missing_metadata_and_unfinished_scaffolding(skill_source, bad_skill):
    write(skill_source, "SKILL.md", bad_skill)
    with pytest.raises(package.PackageError):
        package.validate_source(skill_source)


def test_agent_prompt_has_a_real_skill_reference(skill_source):
    write(skill_source, "agents/openai.yaml", """interface:
  display_name: "Livestream notes"
  short_description: "Transcribe livestreams into useful notes"
  default_prompt: "Summarize this stream."
""")
    with pytest.raises(package.PackageError, match="default_prompt"):
        package.validate_source(skill_source)


def test_rejects_symbolic_links_in_package_trees(skill_source, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 'private'\n", encoding="utf-8")
    link = skill_source / "scripts" / "linked.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires additional Windows privileges")
    with pytest.raises(package.PackageError, match="Symlinks"):
        package.validate_source(skill_source)


def rewrite_archive(source: Path, target: Path, *, replacement=None, extra=None):
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w") as new:
        for info in old.infolist():
            data = old.read(info.filename)
            if replacement and info.filename == replacement[0]:
                data = replacement[1]
            new.writestr(info, data)
        if extra:
            new.writestr(*extra)


def test_manifest_detects_changed_file_and_unlisted_file(skill_source, tmp_path):
    original, changed, extra = (tmp_path / name for name in ("original.zip", "changed.zip", "extra.zip"))
    package.create_bundle(skill_source, original)
    rewrite_archive(original, changed, replacement=("redbook-live-notes/README.md", b"tampered\n"))
    with pytest.raises(package.PackageError, match="does not match manifest"):
        package.verify_bundle(changed)
    rewrite_archive(original, extra, extra=("redbook-live-notes/extra.txt", b"unlisted\n"))
    with pytest.raises(package.PackageError, match="absent from the manifest"):
        package.verify_bundle(extra)


def test_a_matching_manifest_cannot_authorize_private_runtime_files(skill_source, tmp_path):
    original, changed = tmp_path / "original.zip", tmp_path / "changed.zip"
    package.create_bundle(skill_source, original)
    manifest_name = "redbook-live-notes/MANIFEST.json"
    with zipfile.ZipFile(original) as bundle:
        manifest = json.loads(bundle.read(manifest_name))
    private = b"private runtime data\n"
    manifest["files"].append({
        "path": "runtime/private.json", "size": len(private),
        "sha256": hashlib.sha256(private).hexdigest(),
    })
    rewrite_archive(
        original, changed,
        replacement=(manifest_name, json.dumps(manifest).encode("utf-8")),
        extra=("redbook-live-notes/runtime/private.json", private),
    )
    with pytest.raises(package.PackageError, match="Invalid or duplicate manifest path"):
        package.verify_bundle(changed)


@pytest.mark.parametrize("unsafe", ["../escape.py", "/absolute.py", "redbook-live-notes/../escape.py", "redbook-live-notes/C:/escape.py"])
def test_archive_verification_rejects_unsafe_paths(skill_source, tmp_path, unsafe):
    original, changed = tmp_path / "original.zip", tmp_path / "changed.zip"
    package.create_bundle(skill_source, original)
    rewrite_archive(original, changed, extra=(unsafe, b"private\n"))
    with pytest.raises(package.PackageError, match="Unsafe archive entry"):
        package.verify_bundle(changed)


def test_archive_verification_rejects_symbolic_link_entries(skill_source, tmp_path):
    original, changed = tmp_path / "original.zip", tmp_path / "changed.zip"
    package.create_bundle(skill_source, original)
    link = zipfile.ZipInfo("redbook-live-notes/link.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    rewrite_archive(original, changed, extra=(link, b"../../outside.py"))
    with pytest.raises(package.PackageError, match="Unsafe archive entry"):
        package.verify_bundle(changed)


def test_check_is_read_only_and_cli_build_verify_work(skill_source, tmp_path, capsys):
    assert package.main(["--source", str(skill_source), "--check"]) == 0
    assert not (skill_source / "dist").exists()
    output = tmp_path / "release.zip"
    assert package.main(["--source", str(skill_source), "--output", str(output)]) == 0
    assert package.main(["--verify", str(output)]) == 0
    assert "SHA256:" in capsys.readouterr().out


def test_missing_required_file_fails_without_creating_output(skill_source, tmp_path):
    # Renaming this one fixture file simulates an incomplete checkout.
    (skill_source / "requirements.txt").rename(skill_source / "requirements.saved")
    output = tmp_path / "new-directory" / "release.zip"
    with pytest.raises(package.PackageError, match="requirements.txt"):
        package.create_bundle(skill_source, output)
    assert not output.parent.exists()
