"""One-time migration script to populate routine.db from data/kuet_cse_real.json.

Reads through the existing routine/loader.py functions and populates:
- teachers (confirm 51)
- rooms (confirm 21)
- batches (confirm 5)
- courses (confirm 47)
- assignments
- teacher_unavailable
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to sys.path so app and routine can be imported
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import (
    Assignment,
    Base,
    Batch,
    Course,
    Room,
    SessionLocal,
    Teacher,
    TeacherUnavailable,
    engine,
)
from routine.loader import load_problem

# Explicit department mapping for service/non-departmental teachers
NON_CSE_DEPARTMENTS: dict[str, str] = {
    # ECE
    "md_faruque_hossain": "ECE",
    "md_faisal_hossain": "ECE",
    "mushfiqur_rahman_masuk": "ECE",
    "md_minhajul_islam_arnab": "ECE",
    # EEE
    "md_rejvi_kaysir": "EEE",
    "akash_biswas": "EEE",
    "robin_sarker": "EEE",
    "jeesun_patra_papon": "EEE",
    # ME
    "md_mahbubur_rahman": "ME",
    "miir_anjirin_tazrin": "ME",
    "md_zaidur_rahman": "ME",
    # MATH
    "arm_jalal_uddin_jamali": "MATH",
    "md_hasanuzzaman": "MATH",
    "sm_arif_hossen": "MATH",
    "md_dulal_hossain": "MATH",
    "sunny_khatun": "MATH",
    # PHY
    "sujit_kumer_shil": "PHY",
    "md_alamgir_hossain": "PHY",
    "md_sohag_hossain": "PHY",
    "md_afsar_ali": "PHY",
    # HUM
    "sm_rabiul_alam": "HUM",
    "farhana_afroj": "HUM",
    "munshi_tauhiduzzaman": "HUM",
    "md_shahinur_alam_sarker": "HUM",
    "maria_bhuiyan": "HUM",
}


def get_teacher_department(teacher_id: str) -> str:
    return NON_CSE_DEPARTMENTS.get(teacher_id, "CSE")


def migrate():
    json_path = ROOT / "data" / "kuet_cse_real.json"
    if not json_path.exists():
        print(f"Error: {json_path} does not exist.")
        sys.exit(1)

    # Use existing routine/loader.py function to read data
    problem = load_problem(json_path)
    raw_data = json.loads(json_path.read_text(encoding="utf-8"))

    # Recreate tables cleanly
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        # 1. Teachers
        # Lookup table for raw teacher attributes
        raw_teachers_by_id = {t["id"]: t for t in raw_data.get("teachers", [])}
        for tid, t in problem.teachers.items():
            raw_t = raw_teachers_by_id.get(tid, {})
            dept = get_teacher_department(tid)
            teacher_rec = Teacher(
                id=tid,
                full_name=t.name,
                short_code=t.short,
                department=dept,
                status="active",
                max_periods_per_day=t.max_periods_per_day,
            )
            session.add(teacher_rec)

            # Check raw unavailable data if any exists
            for unavail in raw_t.get("unavailable", []):
                periods = unavail.get("periods", "all")
                if isinstance(periods, list):
                    periods_str = ",".join(periods)
                else:
                    periods_str = str(periods)
                session.add(
                    TeacherUnavailable(
                        teacher_id=tid,
                        day=unavail["day"],
                        periods=periods_str,
                    )
                )

        # 2. Rooms
        for rid, r in problem.rooms.items():
            session.add(
                Room(
                    id=rid,
                    name=r.name,
                    kind=r.kind,
                    capacity=r.capacity,
                )
            )

        # 3. Batches
        for bid, b in problem.batches.items():
            session.add(
                Batch(
                    id=bid,
                    name=b.name,
                    sections=",".join(b.sections),
                    groups=",".join(b.groups),
                    section_size=b.section_size,
                    group_size=b.group_size,
                )
            )

        # 4. Courses and Assignments
        for c in problem.courses:
            session.add(
                Course(
                    id=c.code,
                    title=c.title,
                    batch_id=c.batch,
                    kind=c.kind,
                    room_kind=c.room_kind,
                    periods_per_week=c.periods_per_week if c.is_theory else None,
                    blocks_per_week=c.blocks_per_week if not c.is_theory else None,
                )
            )

            # Assignments
            if c.is_theory:
                for section, tid in c.teachers.items():
                    session.add(
                        Assignment(
                            course_id=c.code,
                            section=section,
                            group=None,
                            teacher_id=tid,
                        )
                    )
            else:
                for section, grps in c.teachers.items():
                    for grp, tids in grps.items():
                        if isinstance(tids, str):
                            tids = [tids]
                        for tid in tids:
                            session.add(
                                Assignment(
                                    course_id=c.code,
                                    section=section,
                                    group=grp,
                                    teacher_id=tid,
                                )
                            )

        session.commit()

        # Query back and verify row counts
        teacher_count = session.query(Teacher).count()
        room_count = session.query(Room).count()
        batch_count = session.query(Batch).count()
        course_count = session.query(Course).count()
        assignment_count = session.query(Assignment).count()
        unavailable_count = session.query(TeacherUnavailable).count()

        print("=== Database Migration Complete ===")
        print(f"Teachers:            {teacher_count}")
        print(f"Rooms:               {room_count}")
        print(f"Batches:             {batch_count}")
        print(f"Courses:             {course_count}")
        print(f"Assignments:         {assignment_count}")
        print(f"Teacher Unavailable: {unavailable_count}")

        assert teacher_count == 51, f"Expected 51 teachers, got {teacher_count}"
        assert room_count == 21, f"Expected 21 rooms, got {room_count}"
        assert batch_count == 5, f"Expected 5 batches, got {batch_count}"
        assert course_count == 47, f"Expected 47 courses, got {course_count}"
        print("\nAll row count confirmations passed!")

    except Exception as e:
        session.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
