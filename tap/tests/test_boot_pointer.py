"""Bootstrap pointer parsing + stage-0 fetch tests (spec-tap-boot-bootstrap).

The fetch tests build a real local git repo fixture (a plugin package with in-package boot
records + a ``[[boot.records]]`` manifest) and drive ``stage0_fetch`` against a ``git+file://``
source-ref — exercising the actual blobless clone / ``git show`` / integrity-verify path with
no network. Pure stdlib + git; no Django, no DB.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tap import boot_pointer
from tap.boot_pointer import BootPointerError, parse_git_ref, parse_pointer, stage0_fetch
from tap.boot_records import canonical_digest_bytes

# --- parsing ----------------------------------------------------------------


def test_parse_pointer_record_only() -> None:
    p = parse_pointer("git+https://h/r@v0.1.0#soak")
    assert p.source_ref == "git+https://h/r@v0.1.0"
    assert p.record == "soak"
    assert p.digest is None


def test_parse_pointer_default_record() -> None:
    p = parse_pointer("git+https://h/r@v0.1.0")
    assert p.record is None and p.digest is None


def test_parse_pointer_digest() -> None:
    p = parse_pointer("foo#soak@sha256:abc123")
    assert p.record == "soak" and p.digest == "sha256:abc123"


def test_parse_git_ref_ok() -> None:
    ref = parse_git_ref("git+https://github.com/o/r@v0.1.0")
    assert ref is not None and ref.url == "https://github.com/o/r" and ref.rev == "v0.1.0"


def test_parse_git_ref_non_git_is_none() -> None:
    assert parse_git_ref("/some/local.boot.json") is None


def test_parse_git_ref_malformed_raises() -> None:
    with pytest.raises(BootPointerError):
        parse_git_ref("git+https://github.com/o/r")  # no @rev


# --- fixture: a real local git artifact -------------------------------------


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _make_git_artifact(tmp_path: Path, slug: str, records: dict[str, bytes], *, declare_default: bool = False) -> Path:
    """Create a git repo with tap_plugin/<slug>/boot/*.boot.json + a coherent tap-plugin.toml, tagged v0.1.0."""
    repo = tmp_path / f"repo-{slug}"
    pkg = repo / "tap_plugin" / slug
    boot = pkg / "boot"
    boot.mkdir(parents=True)
    for name, body in records.items():
        (boot / f"{name}.boot.json").write_bytes(body)

    toml_lines = [f'slug = "{slug}"\n', 'manifest_version = "0"\n']
    for name, body in records.items():
        toml_lines += [
            "\n[[boot.records]]\n",
            f'name = "{name}"\n',
            'description = "d"\n',
            f'sha256 = "{canonical_digest_bytes(body)}"\n',
        ]
    (pkg / "tap-plugin.toml").write_text("".join(toml_lines), encoding="utf-8")

    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@t"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", "seed"], repo)
    _run(["git", "tag", "v0.1.0"], repo)
    return repo


def _ptr(repo: Path, record: str | None) -> boot_pointer.Pointer:
    frag = f"#{record}" if record else ""
    return parse_pointer(f"git+file://{repo}@v0.1.0{frag}")


def test_stage0_fetches_named_record(tmp_path: Path) -> None:
    play = b'{"version": 1, "flavor": "playground"}'
    soak = b'{"version": 1, "flavor": "soak"}'
    repo = _make_git_artifact(tmp_path, "foo", {"playground": play, "soak": soak})
    out = tmp_path / "out"

    staged = stage0_fetch(_ptr(repo, "soak"), out)
    assert staged == out / "soak.boot.json"
    # Byte-identical recipe fetched; and only the staged record persists (clone discarded).
    assert canonical_digest_bytes(staged.read_bytes()) == canonical_digest_bytes(soak)
    assert not list(out.glob("tap-stage0-*"))


def test_stage0_missing_record_fails_closed_with_available(tmp_path: Path) -> None:
    repo = _make_git_artifact(tmp_path, "foo", {"playground": b'{"a":1}', "soak": b'{"a":2}'})
    with pytest.raises(BootPointerError) as exc:
        stage0_fetch(_ptr(repo, "nope"), tmp_path / "out")
    assert "playground" in str(exc.value) and "soak" in str(exc.value)


def test_stage0_no_default_fails_closed(tmp_path: Path) -> None:
    repo = _make_git_artifact(tmp_path, "foo", {"playground": b'{"a":1}'})
    with pytest.raises(BootPointerError) as exc:
        stage0_fetch(_ptr(repo, None), tmp_path / "out")
    assert "no default record" in str(exc.value)


def test_stage0_integrity_mismatch_fails_closed(tmp_path: Path) -> None:
    """If the artifact's declared sha256 disagrees with the record content, fail closed."""
    repo = _make_git_artifact(tmp_path, "foo", {"soak": b'{"a":1}'})
    # Corrupt the committed record content so it no longer matches the declared digest.
    rec = repo / "tap_plugin" / "foo" / "boot" / "soak.boot.json"
    rec.write_bytes(b'{"a":999}')
    _run(["git", "commit", "-q", "-am", "tamper"], repo)
    _run(["git", "tag", "-f", "v0.1.0"], repo)
    with pytest.raises(BootPointerError) as exc:
        stage0_fetch(_ptr(repo, "soak"), tmp_path / "out")
    assert "integrity check FAILED" in str(exc.value)


def test_stage0_digest_reserved(tmp_path: Path) -> None:
    with pytest.raises(BootPointerError) as exc:
        stage0_fetch(parse_pointer("git+https://h/r@v0.1.0#soak@sha256:abc"), tmp_path / "out")
    assert "reserved" in str(exc.value)


def test_stage0_local_path_arm_returns_as_is(tmp_path: Path) -> None:
    local = tmp_path / "scratch.boot.json"
    local.write_bytes(b'{"version": 1}')
    staged = stage0_fetch(parse_pointer(str(local)), tmp_path / "out")
    assert staged == local
