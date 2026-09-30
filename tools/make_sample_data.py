"""Generate a sample instance shaped like a CSE department at a BD engineering
university, and write it to data/kuet_cse.json.

Replace this with your real department data. It is also useful on its own: by
varying the knobs below (batches, room supply, teacher availability density)
you can produce a family of instances for benchmarking experiments.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 2207075
random.seed(SEED)

ROOT = Path(__file__).resolve().parents[1]

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]

PERIODS = [
    {"name": "P1", "start": "08:00", "end": "08:50"},
    {"name": "P2", "start": "08:50", "end": "09:40"},
    {"name": "P3", "start": "09:40", "end": "10:30"},
    {"name": "P4", "start": "10:40", "end": "11:30"},
    {"name": "P5", "start": "11:30", "end": "12:20"},
    {"name": "P6", "start": "12:20", "end": "13:10"},
    {"name": "P7", "start": "14:30", "end": "15:20"},
    {"name": "P8", "start": "15:20", "end": "16:10"},
    {"name": "P9", "start": "16:10", "end": "17:00"},
]

BREAKS = [
    {"name": "Snack break", "after_period": "P3", "start": "10:30", "end": "10:40"},
    {"name": "Lunch & prayer", "after_period": "P6", "start": "13:10", "end": "14:30"},
]

BATCHES = [
    ("1-1", "1st Year 1st Semester"),
    ("2-1", "2nd Year 1st Semester"),
    ("3-1", "3rd Year 1st Semester"),
    ("4-1", "4th Year 1st Semester"),
    ("4-2", "4th Year 2nd Semester"),
]

# (theory code, title, weekly periods) and the sessional paired with it
CURRICULUM = {
    "1-1": [
        ("CSE 1101", "Structured Programming", 3, "CSE 1102", "software"),
        ("MATH 1101", "Differential Calculus", 3, None, None),
        ("PHY 1101", "Physics", 3, "PHY 1102", "hardware"),
        ("EEE 1101", "Basic Electrical Engineering", 3, "EEE 1102", "hardware"),
        ("HUM 1101", "English", 2, None, None),
    ],
    "2-1": [
        ("CSE 2101", "Data Structures", 3, "CSE 2102", "software"),
        ("CSE 2103", "Digital Logic Design", 3, "CSE 2104", "hardware"),
        ("CSE 2105", "Object Oriented Programming", 3, "CSE 2106", "software"),
        ("MATH 2101", "Linear Algebra", 3, None, None),
        ("EEE 2101", "Electronic Devices", 2, None, None),
    ],
    "3-1": [
        ("CSE 3101", "Database Systems", 3, "CSE 3102", "software"),
        ("CSE 3103", "Computer Networks", 3, "CSE 3104", "network"),
        ("CSE 3105", "Operating Systems", 3, "CSE 3106", "software"),
        ("CSE 3107", "Microprocessors", 3, "CSE 3108", "hardware"),
        ("MATH 3101", "Numerical Methods", 2, None, None),
    ],
    "4-1": [
        ("CSE 4101", "Machine Learning", 3, "CSE 4102", "software"),
        ("CSE 4103", "Compiler Design", 3, "CSE 4104", "software"),
        ("CSE 4105", "Computer Graphics", 3, "CSE 4106", "software"),
        ("CSE 4107", "Software Engineering", 3, None, None),
        ("HUM 4101", "Industrial Management", 2, None, None),
    ],
    "4-2": [
        ("CSE 4201", "Artificial Intelligence", 3, "CSE 4202", "software"),
        ("CSE 4203", "Distributed Systems", 3, "CSE 4204", "network"),
        ("CSE 4205", "Information Security", 3, None, None),
        ("CSE 4207", "Digital Image Processing", 3, "CSE 4208", "software"),
        ("HUM 4201", "Professional Ethics", 2, None, None),
    ],
}

FIRST = [
    "Rahman", "Hossain", "Ahmed", "Chowdhury", "Islam", "Karim", "Sarker", "Mondal",
    "Biswas", "Roy", "Das", "Saha", "Talukder", "Mridha", "Bhuiyan", "Alam",
    "Siddique", "Haque", "Mahmud", "Kabir", "Nasrin", "Sultana", "Parvin", "Akter",
    "Jahan", "Ferdous", "Rashid", "Uddin", "Mollah", "Sheikh", "Barua", "Dutta",
]


def build_teachers(n: int = 32) -> list[dict]:
    teachers = []
    for i in range(n):
        tid = f"T{i + 1:02d}"
        surname = FIRST[i % len(FIRST)]
        title = "Dr." if i < 14 else "Mr." if i % 2 == 0 else "Ms."
        unavailable = []
        # Roughly a third of staff have a standing commitment somewhere.
        if random.random() < 0.35:
            day = random.choice(DAYS)
            block = random.choice([["P1", "P2", "P3"], ["P4", "P5", "P6"], ["P7", "P8", "P9"]])
            unavailable.append({"day": day, "periods": block})
        teachers.append(
            {
                "id": tid,
                "name": f"{title} {surname}",
                "short": tid,
                "unavailable": unavailable,
                "max_periods_per_day": 5,
            }
        )
    return teachers


def build_rooms() -> list[dict]:
    rooms = []
    for i in range(1, 9):
        rooms.append(
            {
                "id": f"R{300 + i}",
                "name": f"Room {300 + i}",
                "kind": "theory",
                "capacity": 70,
            }
        )
    for i in range(1, 5):
        rooms.append(
            {"id": f"SL{i}", "name": f"Software Lab {i}", "kind": "software", "capacity": 35}
        )
    for i in range(1, 4):
        rooms.append(
            {"id": f"HL{i}", "name": f"Hardware Lab {i}", "kind": "hardware", "capacity": 35}
        )
    for i in range(1, 3):
        rooms.append(
            {"id": f"NL{i}", "name": f"Network Lab {i}", "kind": "network", "capacity": 35}
        )
    return rooms


def build_courses(teacher_ids: list[str]) -> list[dict]:
    """Assign teachers under the department rule.

    One teacher holds at most ONE theory course, but takes it for both
    sections. That same teacher may additionally supervise a lab group, which
    is the '1 theory + 1 lab' case from the requirements.
    """
    courses: list[dict] = []
    pool = list(teacher_ids)
    random.shuffle(pool)
    theory_cursor = 0
    lab_pool: list[str] = []

    for batch_id, _ in BATCHES:
        for code, title, weekly, lab_code, lab_kind in CURRICULUM[batch_id]:
            owner = pool[theory_cursor % len(pool)]
            theory_cursor += 1
            courses.append(
                {
                    "code": code,
                    "title": title,
                    "batch": batch_id,
                    "kind": "theory",
                    "room_kind": "theory",
                    "periods_per_week": weekly,
                    "teachers": {"A": owner, "B": owner},
                }
            )
            if lab_code:
                lab_pool.append(owner)
                courses.append(
                    {
                        "code": lab_code,
                        "title": f"{title} Sessional",
                        "batch": batch_id,
                        "kind": "sessional",
                        "room_kind": lab_kind,
                        "blocks_per_week": 1,
                        "teachers": {
                            "A": {"G1": owner, "G2": _partner(pool, owner)},
                            "B": {"G1": _partner(pool, owner, 2), "G2": _partner(pool, owner, 3)},
                        },
                    }
                )
    return courses


def _partner(pool: list[str], owner: str, offset: int = 1) -> str:
    i = pool.index(owner)
    return pool[(i + offset * 7) % len(pool)]


def main() -> None:
    teachers = build_teachers()
    rooms = build_rooms()
    courses = build_courses([t["id"] for t in teachers])

    instance = {
        "meta": {
            "name": "Sample CSE department instance",
            "note": "Synthetic data. Replace with your real department records.",
            "seed": SEED,
        },
        "config": {
            "days": DAYS,
            "periods": PERIODS,
            "breaks": BREAKS,
            "lab_periods": 3,
            "options": {
                "sync_group_labs": True,
                "max_consecutive_periods": 3,
                "weights": {
                    "cohort_gap": 8,
                    "teacher_gap": 4,
                    "last_period": 2,
                    "teacher_daily_overload": 6,
                    "consecutive_overrun": 5,
                    "room_churn": 1,
                },
                "solver": {"max_seconds": 120, "workers": 8, "log": False},
            },
        },
        "rooms": rooms,
        "teachers": teachers,
        "batches": [
            {
                "id": bid,
                "name": name,
                "sections": ["A", "B"],
                "groups": ["G1", "G2"],
                "section_size": 60,
                "group_size": 30,
            }
            for bid, name in BATCHES
        ],
        "courses": courses,
    }

    out = ROOT / "data" / "kuet_cse.json"
    out.write_text(json.dumps(instance, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  {len(teachers)} teachers, {len(rooms)} rooms, {len(courses)} courses")


if __name__ == "__main__":
    main()
