"""Item 150: 2.6.d's backup, and the half of it that is the deliverable.

2.6.d, confirmed: "Nightly encrypted snapshot of database and object storage,
30-day retention, restore verified quarterly. **An untested backup is not a
backup.**"

Two of those four are deployment mechanisms and are not implemented here:
*nightly* is a scheduler and *encrypted* is storage-layer or transport
encryption, which 20.2's note says this application must not implement itself.
What is implemented is the part an application can own and the part that is
usually skipped:

  `snapshot`  a self-describing archive with a manifest naming every file and
              its SHA-256, so a restore can be checked rather than assumed.
  `verify`    restore into a scratch directory, re-hash every file, and
              compare against the manifest -- the quarterly test, as code that
              runs in the test suite on every commit rather than as a calendar
              entry somebody honours.

**The manifest is what makes a restore checkable.** A tar file that extracts
without error proves the tar file is well-formed, not that the bytes inside it
are the bytes that went in. Re-hashing is the difference, and it is the same
check `SourceStore.read` already performs on every read (rule 1.12) -- applied
to the backup instead of to the store.

**A source PDF's bytes are in the archive and that is the point**, so the
archive inherits the filing's confidentiality (20.1). `snapshot` writes where
it is told and says so; choosing an encrypted destination is the deployment's
job, and `describe` says that in the manifest itself rather than leaving a
reader to assume the file is protected.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = "1"

#: 2.6.d. Thirty days of nightly snapshots, enforced by the deployment's
#: retention on the destination rather than by this module deleting things.
BACKUP_RETENTION_DAYS = 30

#: Directories that are derivatives rather than evidence, and are rebuilt
#: rather than restored. Backing up a render cache costs space and restores
#: nothing that a re-render would not produce.
EXCLUDED = ("renders",)


class RestoreFailed(Exception):
    """A restore did not reproduce what was backed up, and this says where."""


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


@dataclass(frozen=True)
class Manifest:
    """What went into one snapshot, and how to tell if it came back."""

    version: str
    created_at: str
    source_root: str
    #: `relative path -> sha256`, sorted, so two snapshots of one state match.
    files: dict[str, str] = field(default_factory=dict)
    note: str = ""

    @property
    def file_count(self) -> int:
        return len(self.files)

    def as_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "created_at": self.created_at,
                "source_root": self.source_root,
                "note": self.note,
                "files": dict(sorted(self.files.items())),
            },
            indent=2,
        )

    @classmethod
    def parse(cls, text: str) -> Manifest:
        body = json.loads(text)
        return cls(
            version=body["version"],
            created_at=body["created_at"],
            source_root=body["source_root"],
            files=body["files"],
            note=body.get("note", ""),
        )


#: Written into every manifest, because a reader finding an archive on a disk
#: should not have to work out what it is or how sensitive it is.
NOTE = (
    "A snapshot of one Three-Statement DCF source store. It CONTAINS THE "
    "SOURCE PDFs, which are confidential financial filings (20.1). It is not "
    "encrypted by the process that wrote it; encryption is the storage "
    "layer's (20.2, 2.6.d). Verify a restore with "
    "`apps.api.app.security.backup.verify`."
)


def _files_under(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in EXCLUDED for part in path.relative_to(root).parts)
    )


def snapshot(storage_root: str | Path, destination: str | Path) -> Manifest:
    """Write one archive, with its manifest inside it."""
    root = Path(storage_root)
    if not root.exists():
        raise FileNotFoundError(f"nothing to back up: {root} does not exist")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)

    files = _files_under(root)
    manifest = Manifest(
        version=MANIFEST_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source_root=str(root.resolve()),
        files={str(path.relative_to(root)): _digest(path) for path in files},
        note=NOTE,
    )

    with tarfile.open(target, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(root)))
        body = manifest.as_json().encode("utf-8")
        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    return manifest


def restore(archive: str | Path, destination: str | Path) -> Manifest:
    """Extract one archive and return the manifest it carried."""
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            # Path traversal, 20.12: a member naming `../` writes outside the
            # destination. Refused rather than sanitized, because an archive
            # containing one is not an archive this wrote.
            resolved = (target / member.name).resolve()
            if not str(resolved).startswith(str(target.resolve())):
                raise RestoreFailed(
                    f"the archive contains a member that would write outside "
                    f"the destination: {member.name!r}"
                )
        _extract(tar, target)

    manifest_path = target / MANIFEST_NAME
    if not manifest_path.exists():
        raise RestoreFailed(
            f"the archive has no {MANIFEST_NAME}, so nothing can check what "
            "came back. It was not written by this module."
        )
    return Manifest.parse(manifest_path.read_text())


def _extract(tar: tarfile.TarFile, target: Path) -> None:
    # `filter="data"` refuses absolute paths, links outside the tree and
    # device nodes. Passed explicitly rather than relying on the interpreter's
    # default, which differs by version.
    try:
        tar.extractall(target, filter="data")
    except TypeError:  # pragma: no cover - Python < 3.12
        tar.extractall(target)


def verify(archive: str | Path, *, scratch: str | Path | None = None) -> Manifest:
    """Restore into a scratch directory and re-hash everything. 2.6.d.

    This is the quarterly restore test, written as a function so it runs in
    CI on every commit instead of on a calendar. An archive that extracts is
    not a backup; an archive whose bytes still hash to what went in is.
    """
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        target = Path(temporary)
        manifest = restore(archive, target)

        missing = []
        changed = []
        for relative, expected in manifest.files.items():
            path = target / relative
            if not path.exists():
                missing.append(relative)
            elif _digest(path) != expected:
                changed.append(relative)

        extra = sorted(
            str(path.relative_to(target))
            for path in _files_under(target)
            if str(path.relative_to(target)) not in manifest.files
            and path.name != MANIFEST_NAME
        )

        if missing or changed or extra:
            raise RestoreFailed(
                "the restore did not reproduce the snapshot: "
                f"{len(missing)} missing {missing[:3]}, "
                f"{len(changed)} changed {changed[:3]}, "
                f"{len(extra)} unexpected {extra[:3]}"
            )
        return manifest


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Snapshot a source store, or verify an existing snapshot. "
                    "2.6.d: an untested backup is not a backup.",
    )
    parser.add_argument("--store", type=Path, help="the source store to snapshot")
    parser.add_argument("--out", type=Path, help="where to write the archive")
    parser.add_argument("--verify", type=Path, help="an archive to verify instead")
    args = parser.parse_args(argv)

    if args.verify:
        try:
            manifest = verify(args.verify)
        except (RestoreFailed, FileNotFoundError) as exc:
            print(f"RESTORE FAILED: {exc}")
            return 1
        print(
            f"Restored and re-hashed {manifest.file_count} file(s) from "
            f"{args.verify}, taken {manifest.created_at}. Every byte matches."
        )
        return 0

    if not (args.store and args.out):
        parser.error("--store and --out are both needed to take a snapshot")
    manifest = snapshot(args.store, args.out)
    print(f"Wrote {args.out} -- {manifest.file_count} file(s).")
    print(f"Verify it now: python3 -m {__name__} --verify {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
