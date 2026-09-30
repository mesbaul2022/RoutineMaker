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
from routine.scheduler import solve_routine
from tools.verify import verify

from .db import (
    Assignment as AssignmentModel,
    Batch as BatchModel,
    Course as CourseModel,
    Room as RoomModel,
    Teacher as TeacherModel,
    TeacherUnavailable as TeacherUnavailableModel,
    get_db,
    init_db,
)
from .db_loader import load_problem_from_db, validate_db_problem

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


class TeacherOut(TeacherBase):
    model_config = ConfigDict(from_attributes=True)
    id: str


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    sections: list[str]
    groups: list[str]
    section_size: int
    group_size: int


class CourseBase(BaseModel):
    title: str
    batch_id: str
    kind: str  # "theory" or "sessional"
    room_kind: str = "theory"
    periods_per_week: Optional[int] = None
    blocks_per_week: Optional[int] = None
    credit: Optional[float] = 3.0
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
    paired_course_id: Optional[str] = None
    teacher1_id: Optional[str] = None
    teacher2_id: Optional[str] = None


class CourseOut(CourseBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    teacher1_name: Optional[str] = None
    teacher1_short: Optional[str] = None
    teacher2_name: Optional[str] = None
    teacher2_short: Optional[str] = None


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


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def slugify(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return cleaned or "teacher"


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
    return query.order_by(TeacherModel.department, TeacherModel.full_name).all()


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
    return teacher


@app.get("/api/teachers/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: str, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return teacher


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
    return teacher


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
    return teacher


@app.delete("/api/teachers/{teacher_id}")
def delete_teacher(teacher_id: str, db: Session = Depends(get_db)):
    teacher = db.query(TeacherModel).filter_by(id=teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    db.delete(teacher)
    db.commit()
    return {"ok": True, "message": f"Teacher '{teacher_id}' deleted."}


# -----------------------------------------------------------------------------
# Courses API
# -----------------------------------------------------------------------------


def _course_to_out(c: CourseModel, db: Session) -> CourseOut:
    t1 = db.query(TeacherModel).filter_by(id=c.teacher1_id).first() if c.teacher1_id else None
    t2 = db.query(TeacherModel).filter_by(id=c.teacher2_id).first() if c.teacher2_id else None
    return CourseOut(
        id=c.id,
        title=c.title,
        batch_id=c.batch_id,
        kind=c.kind,
        room_kind=c.room_kind,
        periods_per_week=c.periods_per_week,
        blocks_per_week=c.blocks_per_week,
        credit=c.credit,
        paired_course_id=c.paired_course_id,
        teacher1_id=c.teacher1_id,
        teacher2_id=c.teacher2_id,
        teacher1_name=t1.full_name if t1 else None,
        teacher1_short=t1.short_code if t1 else None,
        teacher2_name=t2.full_name if t2 else None,
        teacher2_short=t2.short_code if t2 else None,
    )


def _sync_course_assignments(course: CourseModel, db: Session):
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
    courses = query.order_by(CourseModel.batch_id, CourseModel.id).all()
    return [_course_to_out(c, db) for c in courses]


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

    # If 1-1 theory course, default room kind to year1_theory
    room_kind = payload.room_kind.strip().lower()
    if payload.batch_id == "1-1" and kind == "theory" and room_kind == "theory":
        room_kind = "year1_theory"

    course = CourseModel(
        id=cid,
        title=payload.title.strip(),
        batch_id=payload.batch_id,
        kind=kind,
        room_kind=room_kind,
        periods_per_week=payload.periods_per_week if kind == "theory" else None,
        blocks_per_week=payload.blocks_per_week if kind == "sessional" else None,
        credit=payload.credit or (3.0 if kind == "theory" else 1.5),
        paired_course_id=payload.paired_course_id,
        teacher1_id=payload.teacher1_id,
        teacher2_id=payload.teacher2_id,
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
        course.room_kind = payload.room_kind.strip().lower()
    if payload.periods_per_week is not None:
        course.periods_per_week = payload.periods_per_week
    if payload.blocks_per_week is not None:
        course.blocks_per_week = payload.blocks_per_week
    if payload.credit is not None:
        course.credit = payload.credit
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
# Batches API
# -----------------------------------------------------------------------------


@app.get("/api/batches", response_model=List[BatchOut])
def list_batches(db: Session = Depends(get_db)):
    batches = db.query(BatchModel).all()
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
            )
        )
    return out


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
        if len(tids) > 0:
            course.teacher1_id = tids[0]
        if len(tids) > 1:
            course.teacher2_id = tids[1]
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


# -----------------------------------------------------------------------------
# Generate Routine & Routine Info
# -----------------------------------------------------------------------------


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

    # 3. Solve routine using existing CP-SAT routine scheduler
    solution = solve_routine(problem)

    if not solution.ok:
        result = {
            "ok": False,
            "status": solution.status,
            "objective": None,
            "faults": ["No feasible solution could be found with the current constraints."],
            "warnings": warnings,
            "csv_url": None,
            "html_url": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        latest_generation_result = result
        return result

    # 4. Independent hard constraint verification using tools/verify.py
    faults = verify(problem, solution)

    # 5. Write outputs using existing routine/report.py functions
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

    result = {
        "ok": True,
        "status": solution.status,
        "objective": solution.objective,
        "solve_time_seconds": round(solution.wall_seconds, 1),
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
