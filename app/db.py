"""Database setup and SQLAlchemy models for Routine Maker."""

from pathlib import Path
from sqlalchemy import Column, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

DB_PATH = Path(__file__).resolve().parents[1] / "routine.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String, primary_key=True)  # slug, e.g. "mma_hashem"
    full_name = Column(String, nullable=False)
    short_code = Column(String, nullable=False)
    department = Column(String, nullable=False, default="CSE")
    status = Column(String, nullable=False, default="active")  # "active" or "on_leave"
    max_periods_per_day = Column(Integer, nullable=False, default=5)

    assignments = relationship("Assignment", back_populates="teacher", cascade="all, delete-orphan")
    unavailable = relationship("TeacherUnavailable", back_populates="teacher", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)


class Batch(Base):
    __tablename__ = "batches"

    id = Column(String, primary_key=True)  # e.g. "3-2"
    name = Column(String, nullable=False)
    sections = Column(String, nullable=False)  # comma-separated, e.g. "A,B"
    groups = Column(String, nullable=False)  # comma-separated, e.g. "G1,G2"
    section_size = Column(Integer, nullable=False, default=60)
    group_size = Column(Integer, nullable=False, default=30)

    status = Column(String, nullable=False, default="on")  # "on" or "off"

    courses = relationship("Course", back_populates="batch")


class Course(Base):
    __tablename__ = "courses"

    id = Column(String, primary_key=True)  # course code, e.g. "CSE1101"
    title = Column(String, nullable=False)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=False)
    kind = Column(String, nullable=False)  # "theory" or "sessional"
    room_kind = Column(String, nullable=False, default="theory")
    periods_per_week = Column(Integer, nullable=True)
    blocks_per_week = Column(Integer, nullable=True)

    credit = Column(Float, nullable=True, default=3.0)
    category = Column(String, nullable=True, default=None)  # "core", "optional_ii", "optional_iii"
    paired_course_id = Column(String, ForeignKey("courses.id"), nullable=True)
    teacher1_id = Column(String, ForeignKey("teachers.id"), nullable=True)
    teacher2_id = Column(String, ForeignKey("teachers.id"), nullable=True)

    batch = relationship("Batch", back_populates="courses")
    assignments = relationship("Assignment", back_populates="course", cascade="all, delete-orphan")
    teacher1 = relationship("Teacher", foreign_keys=[teacher1_id])
    teacher2 = relationship("Teacher", foreign_keys=[teacher2_id])


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(String, ForeignKey("courses.id"), nullable=False)
    section = Column(String, nullable=False)
    group = Column("group", String, nullable=True)  # null for theory
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=False)

    course = relationship("Course", back_populates="assignments")
    teacher = relationship("Teacher", back_populates="assignments")


class TeacherUnavailable(Base):
    __tablename__ = "teacher_unavailable"

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(String, ForeignKey("teachers.id"), nullable=False)
    day = Column(String, nullable=False)
    periods = Column(String, nullable=False)  # comma-separated period names, or "all"
    teacher = relationship("Teacher", back_populates="unavailable")


class ScheduledAssignment(Base):
    __tablename__ = "scheduled_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String, nullable=False, index=True)
    course_code = Column(String, nullable=False, index=True)
    section = Column(String, nullable=False)
    group = Column("group", String, nullable=True)
    meeting_index = Column(Integer, nullable=False, default=0)
    room_id = Column(String, nullable=False)
    start_slot = Column(Integer, nullable=False)


def _migrate_schema():
    """Ensure newly added columns exist in SQLite and backfill from assignments."""
    import sqlite3
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()

        # 1. Batches table migration: add status column
        cur.execute("PRAGMA table_info(batches)")
        batch_cols = {row[1] for row in cur.fetchall()}
        if "status" not in batch_cols:
            cur.execute("ALTER TABLE batches ADD COLUMN status TEXT DEFAULT 'on'")

        # Ensure the 5 running batches have status='on'
        for bid in ["1-1", "2-1", "2-2", "3-2", "4-1"]:
            cur.execute("UPDATE batches SET status = 'on' WHERE id = ? AND (status IS NULL OR status = '')", (bid,))

        # Add the 3 new inactive terms if not already present
        new_batches = [
            ("1-2", "1st Year 2nd Term", "A,B", "G1,G2", 60, 30, "off"),
            ("3-1", "3rd Year 1st Term", "A,B", "G1,G2", 60, 30, "off"),
            ("4-2", "4th Year 2nd Term", "A,B", "G1,G2", 60, 30, "off"),
        ]
        for bid, bname, bsecs, bgrps, ssize, gsize, bstatus in new_batches:
            cur.execute("SELECT id FROM batches WHERE id = ?", (bid,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO batches (id, name, sections, groups, section_size, group_size, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (bid, bname, bsecs, bgrps, ssize, gsize, bstatus),
                )

        # 2. Rooms migration: ensure CHEM-LAB exists
        cur.execute("SELECT id FROM rooms WHERE id = 'CHEM-LAB'")
        if not cur.fetchone():
            cur.execute("INSERT INTO rooms (id, name, kind, capacity) VALUES ('CHEM-LAB', 'Chemistry Lab', 'chem_lab', 35)")

        # 3. Courses table migration: add columns
        cur.execute("PRAGMA table_info(courses)")
        existing_cols = {row[1] for row in cur.fetchall()}

        if "credit" not in existing_cols:
            cur.execute("ALTER TABLE courses ADD COLUMN credit REAL DEFAULT 3.0")
        if "category" not in existing_cols:
            cur.execute("ALTER TABLE courses ADD COLUMN category TEXT")
        if "paired_course_id" not in existing_cols:
            cur.execute("ALTER TABLE courses ADD COLUMN paired_course_id TEXT")
        if "teacher1_id" not in existing_cols:
            cur.execute("ALTER TABLE courses ADD COLUMN teacher1_id TEXT")
        if "teacher2_id" not in existing_cols:
            cur.execute("ALTER TABLE courses ADD COLUMN teacher2_id TEXT")

        # Backfill teacher1_id and teacher2_id from assignments where not yet populated
        cur.execute("SELECT id, kind, blocks_per_week FROM courses")
        courses = cur.fetchall()
        for cid, kind, blocks in courses:
            cur.execute(
                "SELECT DISTINCT teacher_id FROM assignments WHERE course_id = ? ORDER BY id ASC",
                (cid,)
            )
            tids = [r[0] for r in cur.fetchall()]
            t1 = tids[0] if len(tids) > 0 else None
            t2 = tids[1] if len(tids) > 1 else None

            # Default credits
            if kind == "theory":
                cur.execute(
                    "UPDATE courses SET teacher1_id = COALESCE(teacher1_id, ?), teacher2_id = COALESCE(teacher2_id, ?), credit = COALESCE(credit, 3.0) WHERE id = ?",
                    (t1, t2, cid)
                )
            else:
                default_cr = 1.5 if (blocks or 1) == 1 else 3.0
                cur.execute(
                    "UPDATE courses SET teacher1_id = COALESCE(teacher1_id, ?), teacher2_id = COALESCE(teacher2_id, ?), credit = COALESCE(credit, ?) WHERE id = ?",
                    (t1, t2, default_cr, cid)
                )

        # Pair 0.75 cr labs for 1st year 1st term
        cur.execute("UPDATE courses SET credit = 0.75, paired_course_id = 'PHY1108' WHERE id = 'HUM1108'")
        cur.execute("UPDATE courses SET credit = 0.75, paired_course_id = 'HUM1108' WHERE id = 'PHY1108'")

        # 4. Seed courses for the 3 new terms (1-2, 3-1, 4-2) with no teachers assigned
        new_courses = [
            # --- 1st Year 2nd Term (1-2) ---
            ("CSE1203", "Digital Logic Design", "1-2", "theory", "year1_theory", 3, None, 3.0, "core", None),
            ("CSE1204", "Digital Logic Design Laboratory", "1-2", "sessional", "cse_lab", None, 1, 1.5, "core", None),
            ("CSE1205", "Object Oriented Programming", "1-2", "theory", "year1_theory", 3, None, 3.0, "core", None),
            ("CSE1206", "Object Oriented Programming Laboratory", "1-2", "sessional", "cse_lab", None, 1, 1.5, "core", None),
            ("CHEM1207", "Chemistry", "1-2", "theory", "year1_theory", 3, None, 3.0, "core", None),
            ("CHEM1208", "Chemistry Laboratory", "1-2", "sessional", "chem_lab", None, 1, 0.75, "core", None),
            ("EEE1207", "Basic Electrical Engineering", "1-2", "theory", "year1_theory", 3, None, 3.0, "core", None),
            ("EEE1208", "Basic Electrical Engineering Laboratory", "1-2", "sessional", "ece_lab", None, 1, 1.5, "core", None),
            ("MATH1207", "Coordinate Geometry and Differential Equations", "1-2", "theory", "year1_theory", 3, None, 3.0, "core", None),

            # --- 3rd Year 1st Term (3-1) ---
            ("CSE3100", "Web Programming Laboratory", "3-1", "sessional", "cse_lab", None, 1, 1.5, "core", None),
            ("CSE3101", "Operating Systems", "3-1", "theory", "theory", 3, None, 3.0, "core", None),
            ("CSE3102", "Operating Systems Laboratory", "3-1", "sessional", "cse_lab", None, 1, 1.5, "core", None),
            ("CSE3105", "Embedded Systems and Internet of Things", "3-1", "theory", "theory", 3, None, 3.0, "core", None),
            ("CSE3106", "Embedded Systems and Internet of Things Laboratory", "3-1", "sessional", "cse_lab", None, 1, 0.75, "core", "CSE3120"),
            ("CSE3107", "Applied Statistics and Queuing Theory", "3-1", "theory", "theory", 3, None, 3.0, "core", None),
            ("CSE3109", "Database Systems", "3-1", "theory", "theory", 3, None, 3.0, "core", None),
            ("CSE3110", "Database Systems Laboratory", "3-1", "sessional", "cse_lab", None, 1, 1.5, "core", None),
            ("CSE3119", "Information Systems Design", "3-1", "theory", "theory", 3, None, 3.0, "core", None),
            ("CSE3120", "Information Systems Design Laboratory", "3-1", "sessional", "cse_lab", None, 1, 0.75, "core", "CSE3106"),

            # --- 4th Year 2nd Term (4-2) Core ---
            ("CSE4000", "Capstone Project/Thesis", "4-2", "sessional", "cse_lab", None, 2, 3.0, "core", None),
            ("IEM4227", "Industrial Management", "4-2", "theory", "theory", 3, None, 3.0, "core", None),
            ("HUM4207", "Entrepreneurship Development", "4-2", "theory", "theory", 2, None, 2.0, "core", None),

            # --- 4-2 Optional-II Courses (17 Theory Electives) ---
            ("CSE4211", "Algorithm Engineering", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4213", "Fault Tolerant System", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4215", "E-Commerce", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4219", "Distributed Database Systems", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4227", "Human Computer Interaction", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4229", "Digital Forensic", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4231", "Control Systems Engineering", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4233", "Robotics", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4235", "Multimedia Technology", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4237", "Computational Geometry", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4239", "Data Mining", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4241", "Biomedical Engineering", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4243", "Parallel and Distributed Processing", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4245", "Principles of Programming Languages", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4247", "Graph Theory", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4249", "Bioinformatics", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),
            ("CSE4251", "Software Architecture", "4-2", "theory", "theory", 3, None, 3.0, "optional_ii", None),

            # --- 4-2 Optional-III Courses (5 Theory + 5 Laboratory Electives) ---
            ("CSE4203", "Peripherals and Interfacing", "4-2", "theory", "theory", 3, None, 3.0, "optional_iii", None),
            ("CSE4204", "Peripherals and Interfacing Laboratory", "4-2", "sessional", "cse_lab", None, 1, 0.75, "optional_iii", None),
            ("CSE4217", "Computer Vision", "4-2", "theory", "theory", 3, None, 3.0, "optional_iii", None),
            ("CSE4218", "Computer Vision Laboratory", "4-2", "sessional", "ai_lab", None, 1, 0.75, "optional_iii", None),
            ("CSE4221", "High Performance Computing", "4-2", "theory", "theory", 3, None, 3.0, "optional_iii", None),
            ("CSE4222", "High Performance Computing Laboratory", "4-2", "sessional", "network_lab", None, 1, 0.75, "optional_iii", None),
            ("CSE4223", "Digital System Design", "4-2", "theory", "theory", 3, None, 3.0, "optional_iii", None),
            ("CSE4224", "Digital System Design Laboratory", "4-2", "sessional", "cse_lab", None, 1, 0.75, "optional_iii", None),
            ("CSE4225", "Real-time Embedded Systems", "4-2", "theory", "theory", 3, None, 3.0, "optional_iii", None),
            ("CSE4226", "Real-time Embedded Systems Laboratory", "4-2", "sessional", "cse_lab", None, 1, 0.75, "optional_iii", None),
        ]

        for cid, title, bid, kind, rkind, periods, blocks, credit, category, paired in new_courses:
            cur.execute("SELECT id FROM courses WHERE id = ?", (cid,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """INSERT INTO courses
                       (id, title, batch_id, kind, room_kind, periods_per_week, blocks_per_week, credit, category, paired_course_id, teacher1_id, teacher2_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)""",
                    (cid, title, bid, kind, rkind, periods, blocks, credit, category, paired),
                )
            else:
                # Update category and credit if already present
                cur.execute(
                    "UPDATE courses SET category = COALESCE(category, ?), credit = COALESCE(credit, ?) WHERE id = ?",
                    (category, credit, cid),
                )

        # 5. Scheduled assignments table for freeze & incremental routines
        cur.execute("PRAGMA table_info(scheduled_assignments)")
        if not cur.fetchall():
            cur.execute(
                """CREATE TABLE scheduled_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    course_code TEXT NOT NULL,
                    section TEXT NOT NULL,
                    "group" TEXT,
                    meeting_index INTEGER NOT NULL DEFAULT 0,
                    room_id TEXT NOT NULL,
                    start_slot INTEGER NOT NULL,
                    UNIQUE(batch_id, course_code, section, "group", meeting_index)
                )"""
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sched_batch ON scheduled_assignments(batch_id)")

        con.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_solution_assignments(db: Session, assignments, batch_ids_to_replace: list[str] | None = None) -> int:
    """Save solved assignments to scheduled_assignments table.

    If batch_ids_to_replace is provided, only deletes and overwrites assignments
    for those batches. If None, overwrites all assignments present in the solution.
    """
    if not assignments:
        return 0

    if batch_ids_to_replace is None:
        batch_ids_to_replace = list(dict.fromkeys(a.event.batch_id for a in assignments))

    # Remove existing assignments for the batches being updated
    if batch_ids_to_replace:
        db.query(ScheduledAssignment).filter(
            ScheduledAssignment.batch_id.in_(batch_ids_to_replace)
        ).delete(synchronize_session=False)

    saved_count = 0
    for a in assignments:
        ev = a.event
        if ev.batch_id in batch_ids_to_replace:
            rec = ScheduledAssignment(
                batch_id=ev.batch_id,
                course_code=ev.course.code,
                section=ev.section,
                group=ev.group,
                meeting_index=ev.meeting_index,
                room_id=a.room_id,
                start_slot=a.start,
            )
            db.add(rec)
            saved_count += 1

    db.commit()
    return saved_count


def get_scheduled_batches_summary(db: Session) -> dict[str, int]:
    """Return dictionary of batch_id -> count of scheduled classes."""
    from sqlalchemy import func
    rows = (
        db.query(ScheduledAssignment.batch_id, func.count(ScheduledAssignment.id))
        .group_by(ScheduledAssignment.batch_id)
        .all()
    )
    return {r[0]: r[1] for r in rows}


def get_saved_placements_map(db: Session, batch_ids: list[str]) -> dict[tuple, tuple[str, int]]:
    """Return map of (batch_id, course_code, section, group, meeting_index) -> (room_id, start_slot)."""
    rows = (
        db.query(ScheduledAssignment)
        .filter(ScheduledAssignment.batch_id.in_(batch_ids))
        .all()
    )
    return {
        (r.batch_id, r.course_code, r.section, r.group, r.meeting_index): (r.room_id, r.start_slot)
        for r in rows
    }

