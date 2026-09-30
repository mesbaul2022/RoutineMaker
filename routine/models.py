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
        val = self.teachers.get(section, {}).get(group, [])
        return [val] if isinstance(val, str) else list(val)


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
        return self.group is not None

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
        if event.group is None:
            return [(event.batch_id, event.section, g) for g in batch.groups]
        return [(event.batch_id, event.section, event.group)]

    def feasible_rooms(self, event: Event) -> list[Room]:
        if not event.is_lab:
            home_rooms = self.options.get("home_rooms", {})
            home_id = home_rooms.get(f"{event.batch_id}|{event.section}")
            if home_id and home_id in self.rooms:
                return [self.rooms[home_id]]

            if event.room_kind in ("theory", "year1_theory"):
                cand = [
                    r
                    for r in self.rooms.values()
                    if r.kind in ("theory", "year1_theory") and r.capacity >= event.size
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
