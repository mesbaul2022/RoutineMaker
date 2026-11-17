"""FastAPI Backend Application for Class Routine Generator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from routine.report import write_csv, write_html
from routine.scheduler import diagnose_infeasibility, solve_routine
from tools.verify import verify

from .db import (
    Assignment as AssignmentModel,
    Batch as BatchModel,
    Course as CourseModel,
    CourseSlotRule as CourseSlotRuleModel,
    Room as RoomModel,
    ScheduledAssignment as ScheduledAssignmentModel,
    Teacher as TeacherModel,
    TeacherUnavailable as TeacherUnavailableModel,
    clear_course_slot_rules,
    clear_teacher_unavailability,
    delete_course_slot_rule,
    delete_teacher_unavailability_rule,
    get_course_slot_rules,
    get_db,
    get_db_time_grid_config,
    get_saved_placements_map,
    get_scheduled_batches_summary,
    get_teacher_unavailability_records,
    init_db,
    reset_db_time_grid_config,
    save_db_time_grid_config,
    save_solution_assignments,
    set_course_slot_rules,
    set_teacher_unavailability_rules,
)
from .db_loader import _load_config, load_problem_from_db, validate_db_problem
from routine.timegrid import (
    DEFAULT_TIME_GRID_CONFIG,
    compute_time_grid_details,
    build_time_grid_from_config,
)

BATCH_ORDER = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
STATIC_DIR = ROOT / "app" / "static"

app = FastAPI(title="KUET CSE Routine Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for latest generation result
latest_generation_result: Optional[dict] = None


@app.on_event("startup")
def on_startup():
    init_db()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------


class TeacherBase(BaseModel):
    full_name: str
    short_code: str
    department: str = "CSE"
    status: str = "active"  # "active" or "on_leave"
    max_periods_per_day: int = Field(default=5, ge=1, le=9)


class TeacherCreate(TeacherBase):
    id: Optional[str] = None


class TeacherUpdate(BaseModel):
    full_name: Optional[str] = None
    short_code: Optional[str] = None
    department: Optional[str] = None
    status: Optional[str] = None
    max_periods_per_day: Optional[int] = Field(default=None, ge=1, le=9)


class TeacherStatusUpdate(BaseModel):
    status: str


class TeacherAvailabilityRuleOut(BaseModel):
    id: Optional[int] = None
    day: str
    periods: str
    description: Optional[str] = None


class TeacherAvailabilityRuleIn(BaseModel):
    id: Optional[int] = None
    day: str
    periods: str


class TeacherAvailabilitySaveRequest(BaseModel):
    rules: List[TeacherAvailabilityRuleIn] = []


class TeacherAvailabilityOut(BaseModel):
    teacher_id: str
    teacher_name: str
    short_code: str
    department: str
    status: str
    rules: List[TeacherAvailabilityRuleOut] = []
    blocked_slots: List[int] = []
    total_blocked_periods: int = 0


class TeacherOut(TeacherBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    unavailable_count: int = 0
    unavailable_summary: str = "Full Week"


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    sections: list[str]
    groups: list[str]
    section_size: int
    group_size: int
    status: str = "on"
    has_routine: bool = False


class BatchStatusUpdate(BaseModel):
    status: str  # "on" or "off"


class CourseBase(BaseModel):
    title: str
    batch_id: str
    kind: str  # "theory" or "sessional"
    room_kind: str = "theory"
    periods_per_week: Optional[int] = None
    blocks_per_week: Optional[int] = None
    credit: Optional[float] = 3.0
    category: Optional[str] = None  # "core", "optional_ii", "optional_iii"
    paired_course_id: Optional[str] = None
    teacher1_id: Optional[str] = None
    teacher2_id: Optional[str] = None


class CourseCreate(CourseBase):
    id: str  # e.g. "CSE1101"


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    batch_id: Optional[str] = None
    kind: Optional[str] = None
    room_kind: Optional[str] = None
    periods_per_week: Optional[int] = None
    blocks_per_week: Optional[int] = None
    credit: Optional[float] = None
    category: Optional[str] = None
    paired_course_id: Optional[str] = None
    teacher1_id: Optional[str] = None
    teacher2_id: Optional[str] = None


class CourseOut(CourseBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    display_code: Optional[str] = None
    teacher1_name: Optional[str] = None
    teacher1_short: Optional[str] = None
    teacher2_name: Optional[str] = None
    teacher2_short: Optional[str] = None
    slot_rule_count: int = 0
    slot_rule_summary: str = "Unrestricted"


class CourseSlotRuleIn(BaseModel):
    id: Optional[int] = None
    day: str
    periods: str
    rule_type: str = "allowed"  # "allowed" or "blocked"
    section: Optional[str] = None  # None/empty for all sections, or "A", "B"
    note: Optional[str] = None


class CourseSlotRuleOut(BaseModel):
    id: int
    course_id: str
    day: str
    periods: str
    rule_type: str  # "allowed" or "blocked"
    section: Optional[str] = None
    note: Optional[str] = None
    description: Optional[str] = None


class CourseAvailabilitySaveRequest(BaseModel):
    rules: List[CourseSlotRuleIn] = []


class CourseAvailabilityOut(BaseModel):
    course_id: str
    course_title: str
    batch_id: str
    kind: str
    credit: float
    sections: List[str] = []
    rules: List[CourseSlotRuleOut] = []
    allowed_slots: List[int] = []
    blocked_slots: List[int] = []
    section_allowed_slots: dict[str, List[int]] = {}
    section_blocked_slots: dict[str, List[int]] = {}
    summary: str = "Unrestricted"
    rule_count: int = 0


class CourseTeachersSave(BaseModel):
    teacher1_id: Optional[str] = None
    teacher2_id: Optional[str] = None


class AssignmentCreate(BaseModel):
    course_id: str
    section: str
    group: Optional[str] = None
    teacher_id: str


class AssignmentSlotSave(BaseModel):
    course_id: str
    section: str
    group: Optional[str] = None
    teacher_ids: list[str]


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: str
    section: str
    group: Optional[str] = None
    teacher_id: str
    teacher_name: Optional[str] = None
    teacher_short: Optional[str] = None
    teacher_status: Optional[str] = None
    teacher_department: Optional[str] = None


class GenerateRequest(BaseModel):
    seconds: Optional[float] = None
    mode: Optional[str] = "incremental"  # "incremental" or "full"
    frozen_batches: Optional[List[str]] = None


class BreakConfig(BaseModel):
    name: str = "Break"
    after_period: str = "P3"
    duration_minutes: int = 15


class TimeGridConfigPayload(BaseModel):
    day_start: str = "08:00"
    period_duration_minutes: int = 50
    periods_per_day: int = 9
    lab_periods: int = 3
    days: List[str] = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
    breaks: List[BreakConfig] = []


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def slugify(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return cleaned or "teacher"


def describe_availability_rule(day: str, periods: str) -> str:
    d = (day or "").strip()
    p = (periods or "").strip()
    d_lower = d.lower()
    p_lower = p.lower()
    day_label = "Daily" if d_lower in ("daily", "all", "*") else d.capitalize()

    if p_lower in ("all", "*"):
        per_label = "All Periods (Full Day)"
    elif p_lower in ("p1,p2,p3", "p1, p2, p3"):
        per_label = "08:00 AM – 10:30 AM (P1–P3)"
    elif p_lower in ("p4,p5,p6", "p4, p5, p6"):
        per_label = "10:40 AM – 01:10 PM (P4–P6)"
    elif p_lower in ("p7,p8,p9", "p7, p8, p9"):
        per_label = "02:30 PM – 05:00 PM (P7–P9)"
    else:
        per_label = p.upper()

    return f"{day_label}: {per_label}"


def compute_teacher_unavailable_info(
    teacher: TeacherModel, db: Session, grid=None
) -> tuple[int, str, list[TeacherAvailabilityRuleOut], list[int]]:
    rules_raw = (
        db.query(TeacherUnavailableModel)
        .filter(TeacherUnavailableModel.teacher_id == teacher.id)
        .order_by(TeacherUnavailableModel.id.asc())
        .all()
    )
    if grid is None:
        grid, _ = _load_config()

    day_name_map = {d.lower(): i for i, d in enumerate(grid.days)}
    period_name_map = {p.name.lower(): i for i, p in enumerate(grid.periods)}

    blocked_slots: set[int] = set()
    if teacher.status == "on_leave":
        blocked_slots.update(range(grid.n_slots))

    rule_outs: list[TeacherAvailabilityRuleOut] = []
    for r in rules_raw:
        desc = describe_availability_rule(r.day, r.periods)
        rule_outs.append(TeacherAvailabilityRuleOut(id=r.id, day=r.day, periods=r.periods, description=desc))

        day_str = (r.day or "").strip().lower()
        if day_str in ("all", "daily", "*"):
            day_indices = list(range(grid.n_days))
        elif day_str in day_name_map:
            day_indices = [day_name_map[day_str]]
        else:
            match = None
            for d_idx, d_name in enumerate(grid.days):
                if d_name.lower() == day_str:
                    match = d_idx
                    break
            day_indices = [match] if match is not None else []
            if not day_indices:
                try:
                    day_indices = [grid.day_index(r.day.strip())]
                except Exception:
                    pass

        periods_str = (r.periods or "").strip().lower()
        if periods_str in ("all", "*"):
            period_indices = list(range(grid.n_periods))
        else:
            period_indices = []
            for token in periods_str.split(","):
                token = token.strip().lower()
                if not token:
                    continue
                if token in period_name_map:
                    period_indices.append(period_name_map[token])
                else:
                    try:
                        period_indices.append(grid.period_index(token.upper()))
                    except Exception:
                        pass

        for day_i in day_indices:
            for p_i in period_indices:
                blocked_slots.add(grid.slot(day_i, p_i))

    total_blocked = len(blocked_slots)
    if teacher.status == "on_leave":
        summary = "On Leave (All slots blocked)"
    elif total_blocked == 0:
        summary = "Full Week (Available)"
    elif len(rule_outs) == 1:
        summary = rule_outs[0].description or f"Restricted ({total_blocked} slots)"
    else:
        summary = f"{len(rule_outs)} rules ({total_blocked} slots blocked)"

    return total_blocked, summary, rule_outs, sorted(list(blocked_slots))


def _teacher_to_out(teacher: TeacherModel, db: Session, grid=None) -> TeacherOut:
    total_blocked, summary, _, _ = compute_teacher_unavailable_info(teacher, db, grid)
    return TeacherOut(
        id=teacher.id,
        full_name=teacher.full_name,
        short_code=teacher.short_code,
        department=teacher.department,
        status=teacher.status,
        max_periods_per_day=teacher.max_periods_per_day,
        unavailable_count=total_blocked,
        unavailable_summary=summary,
    )


# -----------------------------------------------------------------------------
# Time Grid & Class Schedule Customizer API
# -----------------------------------------------------------------------------


@app.get("/api/time-grid")
def get_time_grid(db: Session = Depends(get_db)):
    """Retrieve currently active department time grid configuration and computed timeline."""
    config = get_db_time_grid_config(db)
    computed = compute_time_grid_details(config)
    return {
        "config": config,
        "computed": computed,
        "is_default": config == DEFAULT_TIME_GRID_CONFIG,
    }


@app.post("/api/time-grid")
def save_time_grid(payload: TimeGridConfigPayload, db: Session = Depends(get_db)):
    """Save custom department-wide time grid parameters (class number, duration, breaks)."""
    config = payload.model_dump()
    if config["period_duration_minutes"] <= 0:
        raise HTTPException(status_code=400, detail="Period duration must be greater than 0.")
    if config["periods_per_day"] < 4 or config["periods_per_day"] > 16:
        raise HTTPException(status_code=400, detail="Periods per day must be between 4 and 16.")
    if not config["days"]:
        raise HTTPException(status_code=400, detail="At least one working day must be selected.")

    saved_cfg = save_db_time_grid_config(db, config)
    computed = compute_time_grid_details(saved_cfg)
    return {
        "config": saved_cfg,
        "computed": computed,
        "is_default": saved_cfg == DEFAULT_TIME_GRID_CONFIG,
        "message": "Department time slots successfully updated.",
    }


@app.post("/api/time-grid/preview")
def preview_time_grid(payload: TimeGridConfigPayload):
    """Calculate and preview daily timeline from candidate settings without saving."""
    config = payload.model_dump()
    computed = compute_time_grid_details(config)
    return {
        "config": config,
        "computed": computed,
    }


@app.post("/api/time-grid/reset")
def reset_time_grid(db: Session = Depends(get_db)):
    """Reset department time slots to KUET CSE institutional defaults (8:00 AM – 5:00 PM)."""
    reset_cfg = reset_db_time_grid_config(db)
    computed = compute_time_grid_details(reset_cfg)
    return {
        "config": reset_cfg,
        "computed": computed,
        "is_default": True,
        "message": "Time slots successfully reset to default schedule.",
    }


# -----------------------------------------------------------------------------
# Teachers API
# -----------------------------------------------------------------------------


@app.get("/api/teachers", response_model=List[TeacherOut])
def list_teachers(
    department: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(TeacherModel)
    if department:
        query = query.filter(TeacherModel.department == department)
    if status:
        query = query.filter(TeacherModel.status == status)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (TeacherModel.full_name.ilike(term))
            | (TeacherModel.short_code.ilike(term))
            | (TeacherModel.id.ilike(term))
        )
    teachers = query.order_by(TeacherModel.department, TeacherModel.full_name).all()
    grid, _ = _load_config()
    return [_teacher_to_out(t, db, grid) for t in teachers]


@app.post("/api/teachers", response_model=TeacherOut, status_code=status.HTTP_201_CREATED)
def create_teacher(payload: TeacherCreate, db: Session = Depends(get_db)):
    tid = payload.id
    if not tid:
        base_slug = slugify(payload.full_name)
        tid = base_slug
        idx = 1
        while db.query(TeacherModel).filter_by(id=tid).first():
            tid = f"{base_slug}_{idx}"
            idx += 1

    if db.query(TeacherModel).filter_by(id=tid).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Teacher with id '{tid}' already exists.",
        )

    teacher = TeacherModel(
        id=tid,
        full_name=payload.full_name.strip(),
        short_code=payload.short_code.strip().upper(),
        department=payload.department.strip().upper(),
        status=payload.status,
        max_periods_per_day=payload.max_periods_per_day,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return _teacher_to_out(teacher, db)


@app.get("/api/teachers/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: str, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return _teacher_to_out(teacher, db)


@app.put("/api/teachers/{teacher_id}", response_model=TeacherOut)
def update_teacher(teacher_id: str, payload: TeacherUpdate, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    if payload.full_name is not None:
        teacher.full_name = payload.full_name.strip()
    if payload.short_code is not None:
        teacher.short_code = payload.short_code.strip().upper()
    if payload.department is not None:
        teacher.department = payload.department.strip().upper()
    if payload.status is not None:
        if payload.status not in ("active", "on_leave"):
            raise HTTPException(status_code=400, detail="Status must be 'active' or 'on_leave'")
        teacher.status = payload.status
    if payload.max_periods_per_day is not None:
        teacher.max_periods_per_day = payload.max_periods_per_day

    db.commit()
    db.refresh(teacher)
    return _teacher_to_out(teacher, db)


@app.patch("/api/teachers/{teacher_id}/status", response_model=TeacherOut)
def set_teacher_status(teacher_id: str, payload: TeacherStatusUpdate, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    if payload.status not in ("active", "on_leave"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'on_leave'")

    teacher.status = payload.status
    db.commit()
    db.refresh(teacher)
    return _teacher_to_out(teacher, db)


@app.delete("/api/teachers/{teacher_id}")
def delete_teacher(teacher_id: str, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    db.delete(teacher)
    db.commit()
    return {"ok": True, "message": f"Teacher '{teacher_id}' deleted."}


# -----------------------------------------------------------------------------
# Teacher Availability & Unavailability API
# -----------------------------------------------------------------------------


@app.get("/api/teachers/{teacher_id}/availability", response_model=TeacherAvailabilityOut)
def get_teacher_availability(teacher_id: str, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    grid, _ = _load_config()
    total_blocked, _, rule_outs, blocked_slots = compute_teacher_unavailable_info(teacher, db, grid)
    return TeacherAvailabilityOut(
        teacher_id=teacher.id,
        teacher_name=teacher.full_name,
        short_code=teacher.short_code,
        department=teacher.department,
        status=teacher.status,
        rules=rule_outs,
        blocked_slots=blocked_slots,
        total_blocked_periods=total_blocked,
    )


@app.put("/api/teachers/{teacher_id}/availability", response_model=TeacherAvailabilityOut)
def update_teacher_availability(
    teacher_id: str, payload: TeacherAvailabilitySaveRequest, db: Session = Depends(get_db)
):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    raw_rules = [{"day": r.day, "periods": r.periods} for r in payload.rules]
    set_teacher_unavailability_rules(db, teacher_id, raw_rules)

    grid, _ = _load_config()
    total_blocked, _, rule_outs, blocked_slots = compute_teacher_unavailable_info(teacher, db, grid)
    return TeacherAvailabilityOut(
        teacher_id=teacher.id,
        teacher_name=teacher.full_name,
        short_code=teacher.short_code,
        department=teacher.department,
        status=teacher.status,
        rules=rule_outs,
        blocked_slots=blocked_slots,
        total_blocked_periods=total_blocked,
    )


@app.post("/api/teachers/{teacher_id}/availability/rule", response_model=TeacherAvailabilityOut)
def add_teacher_availability_rule(
    teacher_id: str, payload: TeacherAvailabilityRuleIn, db: Session = Depends(get_db)
):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    day = (payload.day or "").strip()
    periods = (payload.periods or "").strip()
    if not day or not periods:
        raise HTTPException(status_code=400, detail="Day and periods are required")

    rec = TeacherUnavailableModel(teacher_id=teacher_id, day=day, periods=periods)
    db.add(rec)
    db.commit()

    grid, _ = _load_config()
    total_blocked, _, rule_outs, blocked_slots = compute_teacher_unavailable_info(teacher, db, grid)
    return TeacherAvailabilityOut(
        teacher_id=teacher.id,
        teacher_name=teacher.full_name,
        short_code=teacher.short_code,
        department=teacher.department,
        status=teacher.status,
        rules=rule_outs,
        blocked_slots=blocked_slots,
        total_blocked_periods=total_blocked,
    )


@app.delete("/api/teachers/{teacher_id}/availability/rule/{rule_id}", response_model=TeacherAvailabilityOut)
def delete_single_teacher_rule(teacher_id: str, rule_id: int, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    delete_teacher_unavailability_rule(db, rule_id)
    grid, _ = _load_config()
    total_blocked, _, rule_outs, blocked_slots = compute_teacher_unavailable_info(teacher, db, grid)
    return TeacherAvailabilityOut(
        teacher_id=teacher.id,
        teacher_name=teacher.full_name,
        short_code=teacher.short_code,
        department=teacher.department,
        status=teacher.status,
        rules=rule_outs,
        blocked_slots=blocked_slots,
        total_blocked_periods=total_blocked,
    )


@app.delete("/api/teachers/{teacher_id}/availability", response_model=TeacherAvailabilityOut)
def clear_all_teacher_rules(teacher_id: str, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    clear_teacher_unavailability(db, teacher_id)
    grid, _ = _load_config()
    total_blocked, _, rule_outs, blocked_slots = compute_teacher_unavailable_info(teacher, db, grid)
    return TeacherAvailabilityOut(
        teacher_id=teacher.id,
        teacher_name=teacher.full_name,
        short_code=teacher.short_code,
        department=teacher.department,
        status=teacher.status,
        rules=rule_outs,
        blocked_slots=blocked_slots,
        total_blocked_periods=total_blocked,
    )


# -----------------------------------------------------------------------------
# Courses API
# -----------------------------------------------------------------------------


def compute_course_slot_rules_info(course: CourseModel, db: Session, grid=None):
    if grid is None:
        grid, _ = _load_config()

    rules = get_course_slot_rules(db, course.id)
    day_name_map = {d.lower(): i for i, d in enumerate(grid.days)}
    period_name_map = {p.name.lower(): i for i, p in enumerate(grid.periods)}

    rule_outs: List[CourseSlotRuleOut] = []
    c_allowed: set[int] = set()
    c_blocked: set[int] = set()
    c_sec_allowed: dict[str, set[int]] = {}
    c_sec_blocked: dict[str, set[int]] = {}

    for r in rules:
        day_str = (r.day or "").strip().lower()
        if day_str in ("all", "daily", "*"):
            day_indices = list(range(grid.n_days))
            day_label = "Daily"
        elif day_str in day_name_map:
            day_indices = [day_name_map[day_str]]
            day_label = grid.days[day_indices[0]]
        else:
            match = None
            for d_idx, d_name in enumerate(grid.days):
                if d_name.lower() == day_str:
                    match = d_idx
                    break
            day_indices = [match] if match is not None else [grid.day_index(r.day.strip())]
            day_label = grid.days[day_indices[0]] if day_indices else r.day

        periods_str = (r.periods or "").strip().lower()
        if periods_str in ("all", "*"):
            period_indices = list(range(grid.n_periods))
            period_label = "All Periods"
        else:
            period_indices = []
            for token in periods_str.split(","):
                token = token.strip().lower()
                if not token:
                    continue
                if token in period_name_map:
                    period_indices.append(period_name_map[token])
                else:
                    try:
                        period_indices.append(grid.period_index(token.upper()))
                    except Exception:
                        pass
            period_label = ",".join(grid.periods[p].name for p in period_indices)

        slots = set()
        for day_i in day_indices:
            for p_i in period_indices:
                slots.add(grid.slot(day_i, p_i))

        rtype = (r.rule_type or "allowed").strip().lower()
        sec = (r.section or "").strip()
        sec_prefix = f"Sec {sec}: " if sec and sec.upper() != "ALL" else ""
        type_prefix = "Allowed" if rtype == "allowed" else "Blocked"
        desc = f"[{type_prefix}] {sec_prefix}{day_label} ({period_label})"

        rule_outs.append(
            CourseSlotRuleOut(
                id=r.id,
                course_id=r.course_id,
                day=r.day,
                periods=r.periods,
                rule_type=rtype,
                section=sec or None,
                note=r.note,
                description=desc,
            )
        )

        if not sec or sec.upper() == "ALL":
            if rtype == "allowed":
                c_allowed.update(slots)
            else:
                c_blocked.update(slots)
        else:
            if rtype == "allowed":
                c_sec_allowed.setdefault(sec, set()).update(slots)
            else:
                c_sec_blocked.setdefault(sec, set()).update(slots)

    rule_count = len(rules)
    if rule_count == 0:
        summary = "Unrestricted"
    elif all((r.rule_type or "allowed").lower() == "allowed" for r in rules):
        short_descs = []
        for r in rules:
            sec_p = f"{r.section} " if r.section and r.section.upper() != "ALL" else ""
            short_descs.append(f"{sec_p}{r.day} {r.periods}")
        summary = "Fixed: " + ", ".join(short_descs)
    elif all((r.rule_type or "allowed").lower() == "blocked" for r in rules):
        summary = f"Blocked ({len(rules)} rules)"
    else:
        summary = f"{len(rules)} rules configured"

    sec_allowed_dict = {k: sorted(list(v)) for k, v in c_sec_allowed.items()}
    sec_blocked_dict = {k: sorted(list(v)) for k, v in c_sec_blocked.items()}

    return (
        rule_count,
        summary,
        rule_outs,
        sorted(list(c_allowed)),
        sorted(list(c_blocked)),
        sec_allowed_dict,
        sec_blocked_dict,
    )


def _course_to_out(c: CourseModel, db: Session) -> CourseOut:
    t1 = db.query(TeacherModel).filter_by(id=c.teacher1_id).first() if c.teacher1_id else None
    t2 = db.query(TeacherModel).filter_by(id=c.teacher2_id).first() if c.teacher2_id else None
    clean_id = c.id.replace(" ", "").upper()
    if clean_id.startswith("CSE3200"):
        disp = "CSE 3200"
    elif clean_id.startswith("CSE4000"):
        disp = "CSE 4000"
    else:
        disp = c.id

    rule_count, summary, _, _, _, _, _ = compute_course_slot_rules_info(c, db)

    return CourseOut(
        id=c.id,
        display_code=disp,
        title=c.title,
        batch_id=c.batch_id,
        kind=c.kind,
        room_kind=c.room_kind,
        periods_per_week=c.periods_per_week,
        blocks_per_week=c.blocks_per_week,
        credit=c.credit,
        category=c.category,
        paired_course_id=c.paired_course_id,
        teacher1_id=c.teacher1_id,
        teacher2_id=c.teacher2_id,
        teacher1_name=t1.full_name if t1 else None,
        teacher1_short=t1.short_code if t1 else None,
        teacher2_name=t2.full_name if t2 else None,
        teacher2_short=t2.short_code if t2 else None,
        slot_rule_count=rule_count,
        slot_rule_summary=summary,
    )


def _sync_course_assignments(course: CourseModel, db: Session):
    clean_id = course.id.replace(" ", "").upper()
    if clean_id in ("CSE3200", "CSE4000") or clean_id.startswith("CSE4000"):
        db.query(AssignmentModel).filter_by(course_id=course.id).delete()
        return

    batch = db.query(BatchModel).filter_by(id=course.batch_id).first()
    sections = [s.strip() for s in batch.sections.split(",") if s.strip()] if batch else ["A", "B"]
    groups = [g.strip() for g in batch.groups.split(",") if g.strip()] if batch else ["G1", "G2"]

    db.query(AssignmentModel).filter_by(course_id=course.id).delete()
    tids = [t for t in [course.teacher1_id, course.teacher2_id] if t]
    for s in sections:
        if course.kind == "theory":
            for tid in tids:
                db.add(AssignmentModel(course_id=course.id, section=s, group=None, teacher_id=tid))
        else:
            for g in groups:
                for tid in tids:
                    db.add(AssignmentModel(course_id=course.id, section=s, group=g, teacher_id=tid))


@app.get("/api/courses", response_model=List[CourseOut])
def list_courses(batch_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(CourseModel)
    if batch_id:
        query = query.filter(CourseModel.batch_id == batch_id)
    courses = query.all()
    courses.sort(key=lambda c: (BATCH_ORDER.index(c.batch_id) if c.batch_id in BATCH_ORDER else 99, c.id))
    return [_course_to_out(c, db) for c in courses]


ROOM_KIND_NORMALIZATION = {
    "year1_theory": "theory",
    "seminar": "seminar_501",
    "ai_lab": "cse_lab",
    "network_lab": "cse_lab",
    "year1_cse_lab": "cse_lab",
    "none": "no_room",
    "": "no_room",
}


@app.post("/api/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    cid = payload.id.strip().upper()
    if db.query(CourseModel).filter_by(id=cid).first():
        raise HTTPException(status_code=400, detail=f"Course '{cid}' already exists.")

    batch = db.query(BatchModel).filter_by(id=payload.batch_id).first()
    if not batch:
        raise HTTPException(status_code=400, detail=f"Batch '{payload.batch_id}' does not exist.")

    kind = payload.kind.strip().lower()
    if kind not in ("theory", "sessional"):
        raise HTTPException(status_code=400, detail="Kind must be 'theory' or 'sessional'.")

    raw_rk = (payload.room_kind or ("theory" if kind == "theory" else "cse_lab")).strip().lower()
    room_kind = ROOM_KIND_NORMALIZATION.get(raw_rk, raw_rk)

    t1_val = payload.teacher1_id.strip() if payload.teacher1_id else None
    t2_val = payload.teacher2_id.strip() if payload.teacher2_id else None
    if t1_val and t2_val == t1_val:
        t2_val = None

    course = CourseModel(
        id=cid,
        title=payload.title.strip(),
        batch_id=payload.batch_id,
        kind=kind,
        room_kind=room_kind,
        periods_per_week=payload.periods_per_week if kind == "theory" else None,
        blocks_per_week=payload.blocks_per_week if kind == "sessional" else None,
        credit=payload.credit or (3.0 if kind == "theory" else 1.5),
        category=payload.category,
        paired_course_id=payload.paired_course_id,
        teacher1_id=t1_val,
        teacher2_id=t2_val,
    )
    db.add(course)

    if payload.paired_course_id:
        partner = db.query(CourseModel).filter_by(id=payload.paired_course_id).first()
        if partner:
            partner.paired_course_id = cid

    db.commit()
    db.refresh(course)
    _sync_course_assignments(course, db)
    db.commit()
    return _course_to_out(course, db)


@app.get("/api/courses/{course_id}", response_model=CourseOut)
def get_course(course_id: str, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _course_to_out(course, db)


@app.put("/api/courses/{course_id}", response_model=CourseOut)
def update_course(course_id: str, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if payload.title is not None:
        course.title = payload.title.strip()
    if payload.batch_id is not None:
        if not db.query(BatchModel).filter_by(id=payload.batch_id).first():
            raise HTTPException(status_code=400, detail="Invalid batch_id")
        course.batch_id = payload.batch_id
    if payload.kind is not None:
        kind = payload.kind.strip().lower()
        if kind not in ("theory", "sessional"):
            raise HTTPException(status_code=400, detail="Kind must be 'theory' or 'sessional'")
        course.kind = kind
    if payload.room_kind is not None:
        rk = payload.room_kind.strip().lower()
        course.room_kind = ROOM_KIND_NORMALIZATION.get(rk, rk)
    if payload.periods_per_week is not None:
        course.periods_per_week = payload.periods_per_week
    if payload.blocks_per_week is not None:
        course.blocks_per_week = payload.blocks_per_week
    if payload.credit is not None:
        course.credit = payload.credit
    if payload.category is not None:
        course.category = payload.category or None
    if payload.paired_course_id is not None:
        course.paired_course_id = payload.paired_course_id or None
        if payload.paired_course_id:
            partner = db.query(CourseModel).filter_by(id=payload.paired_course_id).first()
            if partner:
                partner.paired_course_id = course.id
    if payload.teacher1_id is not None:
        course.teacher1_id = payload.teacher1_id or None
    if payload.teacher2_id is not None:
        course.teacher2_id = payload.teacher2_id or None
    if course.teacher1_id and course.teacher2_id == course.teacher1_id:
        course.teacher2_id = None

    _sync_course_assignments(course, db)
    db.commit()
    db.refresh(course)
    return _course_to_out(course, db)


@app.post("/api/courses/{course_id}/assign-teachers")
def assign_course_teachers(course_id: str, payload: CourseTeachersSave, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    course.teacher1_id = payload.teacher1_id.strip() if payload.teacher1_id else None
    course.teacher2_id = payload.teacher2_id.strip() if payload.teacher2_id else None
    if course.teacher1_id and course.teacher2_id == course.teacher1_id:
        course.teacher2_id = None

    _sync_course_assignments(course, db)
    db.commit()
    return {
        "ok": True,
        "course_id": course.id,
        "teacher1_id": course.teacher1_id,
        "teacher2_id": course.teacher2_id,
    }


@app.delete("/api/courses/{course_id}")
def delete_course(course_id: str, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    db.delete(course)
    db.commit()
    return {"ok": True, "message": f"Course '{course_id}' deleted."}


# -----------------------------------------------------------------------------
# Course Slot Availability & Fixed Slots API (Constraint 3)
# -----------------------------------------------------------------------------


@app.get("/api/courses/{course_id}/availability", response_model=CourseAvailabilityOut)
def get_course_availability(course_id: str, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    batch = db.query(BatchModel).filter_by(id=course.batch_id).first()
    sections = [s.strip() for s in batch.sections.split(",") if s.strip()] if batch else ["A", "B"]

    grid, _ = _load_config()
    (
        rule_count,
        summary,
        rule_outs,
        allowed_slots,
        blocked_slots,
        sec_allowed,
        sec_blocked,
    ) = compute_course_slot_rules_info(course, db, grid)

    return CourseAvailabilityOut(
        course_id=course.id,
        course_title=course.title,
        batch_id=course.batch_id,
        kind=course.kind,
        credit=course.credit or 3.0,
        sections=sections,
        rules=rule_outs,
        allowed_slots=allowed_slots,
        blocked_slots=blocked_slots,
        section_allowed_slots=sec_allowed,
        section_blocked_slots=sec_blocked,
        summary=summary,
        rule_count=rule_count,
    )


@app.put("/api/courses/{course_id}/availability", response_model=CourseAvailabilityOut)
def update_course_availability(
    course_id: str, payload: CourseAvailabilitySaveRequest, db: Session = Depends(get_db)
):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    raw_rules = [
        {
            "day": r.day,
            "periods": r.periods,
            "rule_type": r.rule_type,
            "section": r.section,
            "note": r.note,
        }
        for r in payload.rules
    ]
    set_course_slot_rules(db, course_id, raw_rules)

    batch = db.query(BatchModel).filter_by(id=course.batch_id).first()
    sections = [s.strip() for s in batch.sections.split(",") if s.strip()] if batch else ["A", "B"]

    grid, _ = _load_config()
    (
        rule_count,
        summary,
        rule_outs,
        allowed_slots,
        blocked_slots,
        sec_allowed,
        sec_blocked,
    ) = compute_course_slot_rules_info(course, db, grid)

    return CourseAvailabilityOut(
        course_id=course.id,
        course_title=course.title,
        batch_id=course.batch_id,
        kind=course.kind,
        credit=course.credit or 3.0,
        sections=sections,
        rules=rule_outs,
        allowed_slots=allowed_slots,
        blocked_slots=blocked_slots,
        section_allowed_slots=sec_allowed,
        section_blocked_slots=sec_blocked,
        summary=summary,
        rule_count=rule_count,
    )


@app.post("/api/courses/{course_id}/availability/rule", response_model=CourseAvailabilityOut)
def add_course_availability_rule(
    course_id: str, payload: CourseSlotRuleIn, db: Session = Depends(get_db)
):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    current_rules = get_course_slot_rules(db, course_id)
    raw_rules = [
        {
            "day": r.day,
            "periods": r.periods,
            "rule_type": r.rule_type,
            "section": r.section,
            "note": r.note,
        }
        for r in current_rules
    ]
    raw_rules.append(
        {
            "day": payload.day,
            "periods": payload.periods,
            "rule_type": payload.rule_type,
            "section": payload.section,
            "note": payload.note,
        }
    )
    set_course_slot_rules(db, course_id, raw_rules)

    batch = db.query(BatchModel).filter_by(id=course.batch_id).first()
    sections = [s.strip() for s in batch.sections.split(",") if s.strip()] if batch else ["A", "B"]

    grid, _ = _load_config()
    (
        rule_count,
        summary,
        rule_outs,
        allowed_slots,
        blocked_slots,
        sec_allowed,
        sec_blocked,
    ) = compute_course_slot_rules_info(course, db, grid)

    return CourseAvailabilityOut(
        course_id=course.id,
        course_title=course.title,
        batch_id=course.batch_id,
        kind=course.kind,
        credit=course.credit or 3.0,
        sections=sections,
        rules=rule_outs,
        allowed_slots=allowed_slots,
        blocked_slots=blocked_slots,
        section_allowed_slots=sec_allowed,
        section_blocked_slots=sec_blocked,
        summary=summary,
        rule_count=rule_count,
    )


@app.delete("/api/courses/{course_id}/availability/rule/{rule_id}", response_model=CourseAvailabilityOut)
def remove_course_availability_rule(
    course_id: str, rule_id: int, db: Session = Depends(get_db)
):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    delete_course_slot_rule(db, rule_id)

    batch = db.query(BatchModel).filter_by(id=course.batch_id).first()
    sections = [s.strip() for s in batch.sections.split(",") if s.strip()] if batch else ["A", "B"]

    grid, _ = _load_config()
    (
        rule_count,
        summary,
        rule_outs,
        allowed_slots,
        blocked_slots,
        sec_allowed,
        sec_blocked,
    ) = compute_course_slot_rules_info(course, db, grid)

    return CourseAvailabilityOut(
        course_id=course.id,
        course_title=course.title,
        batch_id=course.batch_id,
        kind=course.kind,
        credit=course.credit or 3.0,
        sections=sections,
        rules=rule_outs,
        allowed_slots=allowed_slots,
        blocked_slots=blocked_slots,
        section_allowed_slots=sec_allowed,
        section_blocked_slots=sec_blocked,
        summary=summary,
        rule_count=rule_count,
    )


@app.delete("/api/courses/{course_id}/availability", response_model=CourseAvailabilityOut)
def clear_all_course_rules(course_id: str, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter_by(id=course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    clear_course_slot_rules(db, course_id)

    batch = db.query(BatchModel).filter_by(id=course.batch_id).first()
    sections = [s.strip() for s in batch.sections.split(",") if s.strip()] if batch else ["A", "B"]

    grid, _ = _load_config()
    (
        rule_count,
        summary,
        rule_outs,
        allowed_slots,
        blocked_slots,
        sec_allowed,
        sec_blocked,
    ) = compute_course_slot_rules_info(course, db, grid)

    return CourseAvailabilityOut(
        course_id=course.id,
        course_title=course.title,
        batch_id=course.batch_id,
        kind=course.kind,
        credit=course.credit or 3.0,
        sections=sections,
        rules=rule_outs,
        allowed_slots=allowed_slots,
        blocked_slots=blocked_slots,
        section_allowed_slots=sec_allowed,
        section_blocked_slots=sec_blocked,
        summary=summary,
        rule_count=rule_count,
    )


# -----------------------------------------------------------------------------
# Batches API
# -----------------------------------------------------------------------------

@app.get("/api/batches", response_model=List[BatchOut])
def list_batches(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(BatchModel)
    if status:
        query = query.filter(BatchModel.status == status)
    batches = query.all()
    batches.sort(key=lambda b: BATCH_ORDER.index(b.id) if b.id in BATCH_ORDER else 99)
    summary = get_scheduled_batches_summary(db)
    out = []
    for b in batches:
        out.append(
            BatchOut(
                id=b.id,
                name=b.name,
                sections=[s.strip() for s in b.sections.split(",") if s.strip()],
                groups=[g.strip() for g in b.groups.split(",") if g.strip()],
                section_size=b.section_size,
                group_size=b.group_size,
                status=b.status or "on",
                has_routine=(b.id in summary and summary[b.id] > 0),
            )
        )
    return out


@app.patch("/api/batches/{batch_id}/status", response_model=BatchOut)
def update_batch_status(batch_id: str, payload: BatchStatusUpdate, db: Session = Depends(get_db)):
    batch = db.query(BatchModel).filter_by(id=batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    new_status = payload.status.strip().lower()
    if new_status not in ("on", "off"):
        raise HTTPException(status_code=400, detail="Status must be 'on' or 'off'")
    batch.status = new_status
    db.commit()
    db.refresh(batch)
    return BatchOut(
        id=batch.id,
        name=batch.name,
        sections=[s.strip() for s in batch.sections.split(",") if s.strip()],
        groups=[g.strip() for g in batch.groups.split(",") if g.strip()],
        section_size=batch.section_size,
        group_size=batch.group_size,
        status=batch.status,
    )


# -----------------------------------------------------------------------------
# Assignments API
# -----------------------------------------------------------------------------


@app.get("/api/assignments", response_model=List[AssignmentOut])
def list_assignments(
    course_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            AssignmentModel,
            TeacherModel.full_name.label("t_name"),
            TeacherModel.short_code.label("t_short"),
            TeacherModel.status.label("t_status"),
            TeacherModel.department.label("t_dept"),
        )
        .join(TeacherModel, AssignmentModel.teacher_id == TeacherModel.id)
    )

    if course_id:
        query = query.filter(AssignmentModel.course_id == course_id)
    if batch_id:
        query = query.join(CourseModel, AssignmentModel.course_id == CourseModel.id).filter(
            CourseModel.batch_id == batch_id
        )

    results = query.order_by(AssignmentModel.course_id, AssignmentModel.section, AssignmentModel.group).all()

    out = []
    for assign, t_name, t_short, t_status, t_dept in results:
        out.append(
            AssignmentOut(
                id=assign.id,
                course_id=assign.course_id,
                section=assign.section,
                group=assign.group,
                teacher_id=assign.teacher_id,
                teacher_name=t_name,
                teacher_short=t_short,
                teacher_status=t_status,
                teacher_department=t_dept,
            )
        )
    return out


@app.post("/api/assignments", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(payload: AssignmentCreate, db: Session = Depends(get_db)):
    course = db.query(CourseModel).filter_by(id=payload.course_id).first()
    if not course:
        raise HTTPException(status_code=400, detail="Course not found")

    teacher = db.query(TeacherModel).filter_by(id=payload.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=400, detail="Teacher not found")

    # If duplicate assignment exists, return it
    existing = (
        db.query(AssignmentModel)
        .filter_by(
            course_id=payload.course_id,
            section=payload.section,
            group=payload.group,
            teacher_id=payload.teacher_id,
        )
        .first()
    )
    if existing:
        return AssignmentOut(
            id=existing.id,
            course_id=existing.course_id,
            section=existing.section,
            group=existing.group,
            teacher_id=existing.teacher_id,
            teacher_name=teacher.full_name,
            teacher_short=teacher.short_code,
            teacher_status=teacher.status,
            teacher_department=teacher.department,
        )

    assignment = AssignmentModel(
        course_id=payload.course_id,
        section=payload.section,
        group=payload.group,
        teacher_id=payload.teacher_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return AssignmentOut(
        id=assignment.id,
        course_id=assignment.course_id,
        section=assignment.section,
        group=assignment.group,
        teacher_id=assignment.teacher_id,
        teacher_name=teacher.full_name,
        teacher_short=teacher.short_code,
        teacher_status=teacher.status,
        teacher_department=teacher.department,
    )


@app.post("/api/assignments/save-slot")
def save_assignment_slot(payload: AssignmentSlotSave, db: Session = Depends(get_db)):
    """Convenient endpoint to atomically set/replace the teacher(s) for a course+section(+group)."""
    course = db.query(CourseModel).filter_by(id=payload.course_id).first()
    if not course:
        raise HTTPException(status_code=400, detail="Course not found")

    # Delete existing assignments for this exact slot
    db.query(AssignmentModel).filter(
        AssignmentModel.course_id == payload.course_id,
        AssignmentModel.section == payload.section,
        AssignmentModel.group == payload.group,
    ).delete()

    # Insert new assignments
    for tid in payload.teacher_ids:
        tid = tid.strip()
        if not tid:
            continue
        teacher = db.query(TeacherModel).filter_by(id=tid).first()
        if teacher:
            db.add(
                AssignmentModel(
                    course_id=payload.course_id,
                    section=payload.section,
                    group=payload.group,
                    teacher_id=tid,
                )
            )

    if course.kind == "theory":
        assigns = db.query(AssignmentModel).filter_by(course_id=course.id).all()
        tids = list(dict.fromkeys(a.teacher_id for a in assigns if a.teacher_id))
        course.teacher1_id = tids[0] if len(tids) > 0 else None
        course.teacher2_id = tids[1] if len(tids) > 1 else None
        _sync_course_assignments(course, db)

    db.commit()
    return {"ok": True, "course_id": payload.course_id, "section": payload.section, "group": payload.group}


@app.delete("/api/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, db: Session = Depends(get_db)):
    assignment = db.query(AssignmentModel).filter_by(id=assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()
    return {"ok": True, "message": f"Assignment {assignment_id} deleted."}


@app.get("/api/routine/scheduled-batches")
def get_scheduled_batches(db: Session = Depends(get_db)):
    summary = get_scheduled_batches_summary(db)
    active_batches = [
        b.id for b in db.query(BatchModel).filter(BatchModel.status == "on").all()
    ]
    active_batches.sort(key=lambda b: BATCH_ORDER.index(b) if b in BATCH_ORDER else 99)
    return {
        "scheduled_batches": summary,
        "active_batches": active_batches,
    }


@app.post("/api/generate-routine")
def generate_routine(payload: Optional[GenerateRequest] = None, db: Session = Depends(get_db)):
    global latest_generation_result

    # 1. Load problem from current database contents
    override_opts = {}
    if payload and payload.seconds:
        override_opts = {"solver": {"max_seconds": payload.seconds}}

    problem = load_problem_from_db(db, options_override=override_opts)

    # 2. Run loader validation
    errors, warnings = validate_db_problem(problem, db)
    if errors:
        return {
            "ok": False,
            "status": "VALIDATION_FAILED",
            "errors": errors,
            "warnings": warnings,
            "faults": [],
            "objective": None,
            "csv_url": None,
            "html_url": None,
        }

    # 3. Determine incremental freeze constraints
    mode = payload.mode if payload and payload.mode in ("incremental", "full") else "incremental"
    requested_frozen = list(payload.frozen_batches) if payload and payload.frozen_batches else []
    active_batch_ids = list(problem.batches.keys())

    freeze_map: dict[int, tuple[str, int]] = {}
    actual_frozen_batches: list[str] = []

    if mode == "incremental" and requested_frozen:
        valid_frozen = [bid for bid in requested_frozen if bid in problem.batches]
        if valid_frozen:
            saved_map = get_saved_placements_map(db, valid_frozen)
            missing_frozen = []
            for ev in problem.events:
                if ev.batch_id in valid_frozen:
                    key = (ev.batch_id, ev.course.code, ev.section, ev.group, ev.meeting_index)
                    if key in saved_map:
                        freeze_map[ev.eid] = saved_map[key]
                    else:
                        missing_frozen.append(f"{ev.label} (m{ev.meeting_index})")

            if freeze_map:
                actual_frozen_batches = valid_frozen
            if missing_frozen:
                warnings.append(
                    f"{len(missing_frozen)} classes for frozen batches were not found in saved routine; they will be scheduled fresh."
                )

    # 4. Solve routine using CP-SAT routine scheduler
    active_freeze = freeze_map if freeze_map else None
    try:
        solution = solve_routine(problem, freeze=active_freeze)
    except ValueError as exc:
        result = {
            "ok": False,
            "status": "FREEZE_CONFLICT",
            "mode": mode,
            "frozen_batches": actual_frozen_batches,
            "scheduled_batches": [b for b in active_batch_ids if b not in actual_frozen_batches],
            "objective": None,
            "faults": [
                str(exc),
                "Tip: Switch to 'Full Generation Mode' or unfreeze terms whose teacher/course rules changed.",
            ],
            "warnings": warnings,
            "csv_url": None,
            "html_url": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        latest_generation_result = result
        return result

    if not solution.ok:
        diagnostics = diagnose_infeasibility(problem, freeze=active_freeze)
        result = {
            "ok": False,
            "status": solution.status,
            "mode": mode,
            "frozen_batches": actual_frozen_batches,
            "scheduled_batches": [b for b in active_batch_ids if b not in actual_frozen_batches],
            "objective": None,
            "faults": diagnostics,
            "warnings": warnings,
            "csv_url": None,
            "html_url": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        latest_generation_result = result
        return result

    # 5. Save solution assignments into scheduled_assignments table
    save_solution_assignments(db, solution.assignments, batch_ids_to_replace=active_batch_ids)

    # 6. Independent hard constraint verification using tools/verify.py
    faults = verify(problem, solution)

    # 7. Write outputs using routine/report.py
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_file = OUT_DIR / "routine.csv"
    html_file = OUT_DIR / "routine.html"

    write_csv(problem, solution, csv_file)
    write_html(
        problem,
        solution,
        html_file,
        title="Department of Computer Science and Engineering",
        subtitle="Weekly class routine · generated with CP-SAT",
    )

    scheduled_new = [b for b in active_batch_ids if b not in actual_frozen_batches]

    same_consec_count = solution.penalties.get("same_course_consecutive", 0)
    extra_lab_days = solution.penalties.get("teacher_extra_lab_day", 0)

    teacher_day_lab_counts: dict[tuple[str, int], int] = {}
    for a in solution.assignments:
        ev = a.event
        if not ev.is_lab:
            continue
        clean_c = ev.course.code.replace(" ", "").upper()
        if clean_c in ("CSE3200", "CSE4000") or clean_c.startswith("CSE4000"):
            continue
        d = problem.grid.day_of(a.start)
        for tid in dict.fromkeys(ev.teacher_ids):
            if tid:
                teacher_day_lab_counts[(tid, d)] = teacher_day_lab_counts.get((tid, d), 0) + 1
    max_teacher_labs_day = max(teacher_day_lab_counts.values(), default=0)
    double_lab_teacher_days = sum(1 for c in teacher_day_lab_counts.values() if c >= 2)

    result = {
        "ok": True,
        "status": solution.status,
        "mode": mode,
        "frozen_batches": actual_frozen_batches,
        "scheduled_batches": scheduled_new,
        "objective": solution.objective,
        "solve_time_seconds": round(solution.wall_seconds, 1),
        "same_course_consecutive_count": same_consec_count,
        "max_teacher_labs_day": max_teacher_labs_day,
        "extra_lab_days": extra_lab_days,
        "double_lab_teacher_days": double_lab_teacher_days,
        "faults": faults,
        "warnings": warnings,
        "csv_url": "/api/routine/download/csv",
        "html_url": "/api/routine/download/html",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    latest_generation_result = result
    return result


@app.get("/api/routine/latest")
def get_latest_routine():
    global latest_generation_result
    if latest_generation_result:
        return latest_generation_result

    # Check if files already exist on disk
    csv_file = OUT_DIR / "routine.csv"
    html_file = OUT_DIR / "routine.html"
    if html_file.exists():
        return {
            "ok": True,
            "status": "CACHED",
            "objective": None,
            "faults": [],
            "warnings": [],
            "csv_url": "/api/routine/download/csv",
            "html_url": "/api/routine/download/html",
            "timestamp": datetime.fromtimestamp(html_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }

    return {
        "ok": False,
        "status": "NONE",
        "message": "No routine has been generated yet.",
    }


@app.get("/api/routine/download/csv")
def download_csv():
    csv_file = OUT_DIR / "routine.csv"
    if not csv_file.exists():
        raise HTTPException(status_code=404, detail="routine.csv not generated yet")
    return FileResponse(csv_file, media_type="text/csv", filename="routine.csv")


@app.get("/api/routine/download/html")
def download_html():
    html_file = OUT_DIR / "routine.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="routine.html not generated yet")
    return FileResponse(html_file, media_type="text/html")


# Mount /out for direct file access
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")

# Mount /static for frontend CSS and JS
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Routine Maker</h2><p>Static files loading...</p>")
