"""Domain objects for the departmental routine problem."""

from __future__ import annotations

from dataclasses import dataclass, field

from .timegrid import TimeGrid

THEORY = "theory"
SESSIONAL = "sessional"


@dataclass
class Teacher:
    id: str
    name: str
    short: str
    unavailable: set[int] = field(default_factory=set)  # flat slot indices
    max_periods_per_day: int = 4
    department: str = "CSE"

    def is_free(self, slots: list[int]) -> bool:
        return all(s not in self.unavailable for s in slots)


@dataclass
class Room:
    id: str
    name: str
    kind: str  # "theory", or a lab kind such as "software" / "hardware" / "network"
    capacity: int


@dataclass
class Batch:
    id: str
    name: str
    sections: list[str]
    groups: list[str]
    section_size: int
    group_size: int


@dataclass
class Course:
    code: str
    title: str
    batch: str
    kind: str  # THEORY or SESSIONAL
    room_kind: str = "theory"
    periods_per_week: int = 0  # theory only
    blocks_per_week: int = 0  # sessional only
    credit: float = 3.0
    paired_course_id: str | None = None
    teacher1_id: str | None = None
    teacher2_id: str | None = None
    # theory:    {section -> teacher_id}
    # sessional: {section -> {group -> [teacher_id, ...]}}
    teachers: dict = field(default_factory=dict)

    @property
    def is_theory(self) -> bool:
        return self.kind == THEORY

    def theory_teacher(self, section: str) -> str:
        return self.teachers.get(section, "")

    def lab_teachers(self, section: str, group: str) -> list[str]:
        sec_val = self.teachers.get(section, {})
        if isinstance(sec_val, list):
            return list(sec_val)
        if isinstance(sec_val, dict):
            val = sec_val.get(group, [])
            return [val] if isinstance(val, str) else list(val)
        return [sec_val] if isinstance(sec_val, str) else []


@dataclass
class Event:
    """One meeting that must be placed on the grid.

    A theory course meeting 3x/week produces 3 separate Events.
    A sessional produces one Event per (section, group) per weekly block.
    """

    eid: int
    course: Course
    batch_id: str
    section: str
    group: str | None  # None for theory (the whole section attends)
    length: int  # periods
    teacher_ids: list[str]
    room_kind: str
    size: int  # head count, for room capacity
    meeting_index: int  # 0-based index among sibling meetings of same course+section
    display_teacher: str = ""
    is_shared: bool = False
    paired_event_id: int | None = None

    @property
    def is_lab(self) -> bool:
        return self.group is not None or self.length > 1 or not self.course.is_theory

    @property
    def cohort_keys(self) -> list[tuple]:
        """Which student cohorts are occupied by this event.

        A cohort is (batch, section, group). A theory class occupies EVERY
        group of its section, because the whole section sits in that room.
        """
        return []  # filled in by Problem, which knows the group list

    @property
    def label(self) -> str:
        tag = f"{self.batch_id} {self.section}"
        if self.group:
            tag += self.group
        return f"{self.course.code} ({tag})"


@dataclass
class Problem:
    grid: TimeGrid
    teachers: dict[str, Teacher]
    rooms: dict[str, Room]
    batches: dict[str, Batch]
    courses: list[Course]
    events: list[Event]
    options: dict

    def __post_init__(self) -> None:
        if "NO_ROOM" not in self.rooms:
            self.rooms["NO_ROOM"] = Room(id="NO_ROOM", name="", kind="no_room", capacity=999)

    # ------------------------------------------------------------- cohorts

    def cohorts(self) -> list[tuple]:
        keys = []
        for b in self.batches.values():
            for s in b.sections:
                for g in b.groups:
                    keys.append((b.id, s, g))
        return keys

    def cohorts_of(self, event: Event) -> list[tuple]:
        batch = self.batches[event.batch_id]
        if event.section in ("A/B", "ALL", "A+B", "AB"):
            return [(event.batch_id, s, g) for s in batch.sections for g in batch.groups]
        if event.group is None:
            return [(event.batch_id, event.section, g) for g in batch.groups]
        if "/" in event.group or "," in event.group:
            grps = [g.strip() for g in event.group.replace("/", ",").split(",") if g.strip()]
            return [(event.batch_id, event.section, g) for g in grps]
        return [(event.batch_id, event.section, event.group)]

    def feasible_rooms(self, event: Event) -> list[Room]:
        clean_code = event.course.code.replace(" ", "").upper()
        if clean_code in ("CSE3200", "CSE4000") or clean_code.startswith("CSE4000") or event.room_kind in ("no_room", "none", ""):
            return [self.rooms["NO_ROOM"]]

        if not event.is_lab:
            home_rooms = self.options.get("home_rooms", {})
            home_id = home_rooms.get(f"{event.batch_id}|{event.section}")
            if home_id and home_id in self.rooms:
                return [self.rooms[home_id]]

            cand = [
                r
                for r in self.rooms.values()
                if r.kind == "theory" and r.capacity >= event.size
            ]
            if cand:
                return cand

        # Specific hardware labs
        if event.room_kind == "hardware_lab_107" or clean_code in ("CSE3106", "CSE2104"):
            if "CSE-107" in self.rooms:
                return [self.rooms["CSE-107"]]
        if event.room_kind == "hardware_lab_108" or clean_code == "CSE1204":
            if "CSE-108" in self.rooms:
                return [self.rooms["CSE-108"]]

        # Technical Writing and Seminar (CSE 3230) in CSE Room 501
        if event.room_kind == "seminar_501" or clean_code == "CSE3230":
            if "CSE-501" in self.rooms:
                return [self.rooms["CSE-501"]]

        # Non-Departmental Specific Labs
        if event.room_kind == "eee_lab" or clean_code in ("EEE1208", "EEE2118"):
            if "EEE-LAB" in self.rooms:
                return [self.rooms["EEE-LAB"]]
        if event.room_kind == "mecha_lab" or clean_code == "ME2170":
            if "MECHA-LAB" in self.rooms:
                return [self.rooms["MECHA-LAB"]]
        if event.room_kind == "ece_lab" or clean_code in ("ECE2214", "ECE2208"):
            if "ECE-104" in self.rooms:
                return [self.rooms["ECE-104"]]
        if event.room_kind == "chem_lab" or clean_code == "CHEM1208":
            if "CHEM-LAB" in self.rooms:
                return [self.rooms["CHEM-LAB"]]
        if event.room_kind == "hum_lab" or clean_code == "HUM1108":
            if "HUM-LAB" in self.rooms:
                return [self.rooms["HUM-LAB"]]
        if event.room_kind == "phy_lab" or clean_code == "PHY1108":
            if "PHY-LAB" in self.rooms:
                return [self.rooms["PHY-LAB"]]

        # Departmental Software Labs: CSE Lab 103, 104, 201, 202, 305, and dual-use backup CSE Room 306
        if event.room_kind in ("cse_lab", "year1_cse_lab", "ai_lab", "network_lab"):
            software_ids = ["CSE-103", "CSE-104", "CSE-201", "CSE-202", "CSE-305", "CSE-306"]
            cand = [
                self.rooms[rid]
                for rid in software_ids
                if rid in self.rooms and self.rooms[rid].capacity >= event.size
            ]
            if cand:
                return cand

        return [
            r
            for r in self.rooms.values()
            if r.kind == event.room_kind and r.capacity >= event.size
        ]

    def feasible_starts(self, event: Event) -> list[int]:
        """Start slots allowed by the grid AND by every assigned teacher."""
        if event.is_lab:
            candidates = self.grid.lab_start_slots(event.length)
        else:
            candidates = self.grid.theory_start_slots()

        allowed = []
        for s in candidates:
            covered = self.grid.covered_slots(s, event.length)
            if all(self.teachers[t].is_free(covered) for t in event.teacher_ids):
                allowed.append(s)
        return allowed
