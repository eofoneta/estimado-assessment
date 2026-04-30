"""
Core data models for the AI takeoff system.
All stages (ingest, extract, evaluate, review) share these schemas.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ProjectType(str, Enum):
    SAMPLE = "sample"       # has gold/expected output
    CHALLENGE = "challenge" # input only, no gold output


class FileRole(str, Enum):
    INPUT = "input"   # AI may read this
    GOLD = "gold"     # held-out reference; never fed to the extraction AI


class FileKind(str, Enum):
    BLUEPRINT = "blueprint"
    MARKUP = "markup"
    SPECIFICATION = "specification"
    PHOTO = "photo"
    CHANGE_ORDER = "change_order"
    GENERAL = "general"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProjectFile(BaseModel):
    file_id: str = Field(default_factory=lambda: str(uuid4()))
    path: str
    relative_path: str
    filename: str
    extension: str
    role: FileRole
    kind: FileKind
    size_bytes: int = 0
    page_count: Optional[int] = None


class ProjectManifest(BaseModel):
    project_id: str
    project_name: str
    project_type: ProjectType
    root_path: str
    files: list[ProjectFile] = []
    input_files: list[ProjectFile] = []
    gold_files: list[ProjectFile] = []
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
    notes: list[str] = []


class TakeoffItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = ""
    project_id: str = ""
    description: str
    category: str = ""
    quantity: Optional[float] = None
    unit: str = ""
    unit_notes: str = ""
    source_sheet: str = ""
    assumptions: list[str] = []
    warnings: list[str] = []
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    raw_text: str = ""


class ExtractionRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    model: str
    provider: str
    pages_processed: int = 0
    items_extracted: int = 0
    items: list[TakeoffItem] = []
    ran_at: datetime = Field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0
    errors: list[str] = []
    is_mock: bool = False


class MatchedItem(BaseModel):
    predicted: TakeoffItem
    gold: TakeoffItem
    description_similarity: float
    quantity_match: bool
    quantity_diff_pct: Optional[float] = None
    unit_match: bool


class EvaluationResult(BaseModel):
    eval_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    run_id: str
    gold_item_count: int
    predicted_item_count: int
    matched: list[MatchedItem] = []
    missed: list[TakeoffItem] = []
    extras: list[TakeoffItem] = []
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    quantity_accuracy: float = 0.0
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    notes: list[str] = []


class CorrectionAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    EDIT = "edit"
    ADD = "add"


class HumanCorrection(BaseModel):
    correction_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    run_id: str
    item_id: Optional[str] = None
    action: CorrectionAction
    original: Optional[TakeoffItem] = None
    corrected: Optional[TakeoffItem] = None
    reviewer_note: str = ""
    corrected_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    run_id: str
    corrections: list[HumanCorrection] = []
    final_items: list[TakeoffItem] = []
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
