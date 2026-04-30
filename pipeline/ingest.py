"""
Ingestion — deterministic filesystem walker.
Classifies every file as INPUT or GOLD and by kind, then writes ProjectManifest JSONs.
No AI calls here — fully auditable rule-based logic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from models.schemas import (
    FileKind, FileRole, ProjectFile, ProjectManifest, ProjectType,
)

GOLD_FOLDER_KEYWORDS = {
    "expected manual output", "gold", "reference output",
    "manual output", "expected output",
}

EXT_KIND_MAP: dict[str, FileKind] = {
    ".pdf": FileKind.BLUEPRINT,
    ".tif": FileKind.BLUEPRINT,
    ".tiff": FileKind.BLUEPRINT,
    ".dwg": FileKind.BLUEPRINT,
    ".jpg": FileKind.PHOTO,
    ".jpeg": FileKind.PHOTO,
    ".png": FileKind.PHOTO,
}

NAME_KIND_PATTERNS: list[tuple[re.Pattern, FileKind]] = [
    (re.compile(r"markup", re.I), FileKind.MARKUP),
    (re.compile(r"specification|spec\b", re.I), FileKind.SPECIFICATION),
    (re.compile(r"change.?order|co[-_\s]?\d", re.I), FileKind.CHANGE_ORDER),
    (re.compile(r"photo", re.I), FileKind.PHOTO),
]

SUPPORTED_EXTS = {".pdf", ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".dwg"}


def _classify_kind(filename: str, ext: str) -> FileKind:
    for pattern, kind in NAME_KIND_PATTERNS:
        if pattern.search(filename):
            return kind
    return EXT_KIND_MAP.get(ext.lower(), FileKind.GENERAL)


def _classify_role(path: Path, project_root: Path) -> FileRole:
    parts = path.relative_to(project_root).parts
    for part in parts[:-1]:
        if part.lower() in GOLD_FOLDER_KEYWORDS:
            return FileRole.GOLD
    return FileRole.INPUT


def _project_id_from_name(folder_name: str) -> tuple[str, str]:
    m = re.match(r"(TAKEOFF-\d+)\s*-\s*(.+)", folder_name, re.I)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return folder_name, folder_name


def _page_count(path: Path) -> Optional[int]:
    if path.suffix.lower() != ".pdf":
        return None
    try:
        import fitz
        doc = fitz.open(str(path))
        count = doc.page_count
        doc.close()
        return count
    except Exception:
        return None


def ingest_project(project_folder: Path, project_type: ProjectType) -> ProjectManifest:
    project_id, project_name = _project_id_from_name(project_folder.name)
    manifest = ProjectManifest(
        project_id=project_id,
        project_name=project_name,
        project_type=project_type,
        root_path=str(project_folder),
    )

    for file_path in sorted(project_folder.rglob("*")):
        if not file_path.is_file():
            continue
        ext = file_path.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            continue

        role = _classify_role(file_path, project_folder)
        kind = _classify_kind(file_path.name, ext)
        pf = ProjectFile(
            path=str(file_path),
            relative_path=str(file_path.relative_to(project_folder)),
            filename=file_path.name,
            extension=ext,
            role=role,
            kind=kind,
            size_bytes=file_path.stat().st_size,
            page_count=_page_count(file_path),
        )
        manifest.files.append(pf)
        if role == FileRole.GOLD:
            manifest.gold_files.append(pf)
        else:
            manifest.input_files.append(pf)

    if not manifest.gold_files and project_type == ProjectType.SAMPLE:
        manifest.notes.append("WARNING: sample project but no gold files detected.")
    if not manifest.input_files:
        manifest.notes.append("WARNING: no input files found.")

    return manifest


def ingest_dataset(dataset_root: Path) -> list[ProjectManifest]:
    manifests: list[ProjectManifest] = []
    for folder, ptype in [
        (dataset_root / "01_Sample_Projects_With_Expected_Output", ProjectType.SAMPLE),
        (dataset_root / "02_Challenge_Projects_Project_Files_Only", ProjectType.CHALLENGE),
    ]:
        if not folder.exists():
            continue
        for project_folder in sorted(folder.iterdir()):
            if project_folder.is_dir():
                manifests.append(ingest_project(project_folder, ptype))
    return manifests


def save_manifests(manifests: list[ProjectManifest], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for m in manifests:
        (output_dir / f"{m.project_id}_manifest.json").write_text(m.model_dump_json(indent=2))
    print(f"[ingest] Saved {len(manifests)} manifests → {output_dir}")
