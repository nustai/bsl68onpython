from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FingerprintEntry:
    file: str
    sha: str
    download: str = ""
    defer: bool = False


@dataclass(frozen=True, slots=True)
class VerificationResult:
    checked: int
    missing: tuple[str, ...]
    mismatched: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing and not self.mismatched


class ContentFingerprint:
    """Parser and verifier for the fingerprint.json bundled with the APK."""

    def __init__(self, version: str, sha: str, entries: tuple[FingerprintEntry, ...]):
        self.version = version
        self.sha = sha
        self.entries = entries
        self._by_file = {entry.file.replace("\\", "/"): entry for entry in entries}

    @classmethod
    def load(cls, path: str | Path) -> ContentFingerprint:
        path = Path(path)
        if path.is_dir():
            path = path / "fingerprint.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("files"), list):
            raise TypeError("invalid fingerprint document")
        entries = []
        for item in raw["files"]:
            if not isinstance(item, dict):
                continue
            file, sha = item.get("file"), item.get("sha")
            if not isinstance(file, str) or not isinstance(sha, str):
                continue
            if len(sha) != 40 or any(char not in "0123456789abcdefABCDEF" for char in sha):
                continue
            entries.append(
                FingerprintEntry(
                    file.replace("\\", "/"),
                    sha.casefold(),
                    str(item.get("download", "")),
                    bool(item.get("defer", False)),
                )
            )
        return cls(str(raw.get("version", "")), str(raw.get("sha", "")), tuple(entries))

    def get(self, file: str) -> FingerprintEntry | None:
        return self._by_file.get(file.replace("\\", "/"))

    def verify_file(self, asset_root: str | Path, file: str) -> bool:
        entry = self.get(file)
        if entry is None:
            raise KeyError(file)
        path = Path(asset_root).joinpath(*entry.file.split("/"))
        if not path.is_file():
            return False
        digest = hashlib.sha1(path.read_bytes()).hexdigest()
        return digest == entry.sha

    def verify(
        self,
        asset_root: str | Path,
        prefixes: tuple[str, ...] = (),
    ) -> VerificationResult:
        root = Path(asset_root)
        normalized = tuple(prefix.replace("\\", "/") for prefix in prefixes)
        entries = (
            entry for entry in self.entries
            if not normalized or entry.file.startswith(normalized)
        )
        missing: list[str] = []
        mismatched: list[str] = []
        checked = 0
        for entry in entries:
            checked += 1
            path = root.joinpath(*entry.file.split("/"))
            if not path.is_file():
                missing.append(entry.file)
            elif hashlib.sha1(path.read_bytes()).hexdigest() != entry.sha:
                mismatched.append(entry.file)
        return VerificationResult(checked, tuple(missing), tuple(mismatched))
