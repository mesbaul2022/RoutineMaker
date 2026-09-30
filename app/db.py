"""Database setup and SQLAlchemy models for Routine Maker."""

from pathlib import Path
from sqlalchemy import Column, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

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


def _migrate_schema():
    """Ensure newly added columns exist in SQLite and backfill from assignments."""
    import sqlite3
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("PRAGMA table_info(courses)")
        existing_cols = {row[1] for row in cur.fetchall()}

        if "credit" not in existing_cols:
            cur.execute("ALTER TABLE courses ADD COLUMN credit REAL DEFAULT 3.0")
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

        # Pair 0.75 cr labs for 1st year (HUM1108 and PHY1108)
        cur.execute("UPDATE courses SET credit = 0.75, paired_course_id = 'PHY1108' WHERE id = 'HUM1108'")
        cur.execute("UPDATE courses SET credit = 0.75, paired_course_id = 'HUM1108' WHERE id = 'PHY1108'")
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

