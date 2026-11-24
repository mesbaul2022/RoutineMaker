import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_db, SessionLocal, CourseSlotRule, set_course_slot_rules
from app.db_loader import load_problem_from_db
from routine.scheduler import RoutineScheduler

def test_group_rules():
    db = SessionLocal()
    try:
        # Test course: CSE1206 (1.5 cr OOP Lab)
        course_id = "CSE1206"
        print(f"Setting group-level rules for {course_id}...")

        # Rule 1: Group A1 on Sunday Block 1 (P1-P3, slots 0,1,2) in CSE Lab 103
        # Rule 2: Group A2 on Tuesday Block 1 (P1-P3, slots 18,19,20) in CSE Lab 104
        rules = [
            {
                "day": "Sunday",
                "periods": "P1,P2,P3",
                "rule_type": "allowed",
                "section": "A1",
                "room_id": "CSE-103",
                "note": "Fixed for Group A1",
            },
            {
                "day": "Tuesday",
                "periods": "P1,P2,P3",
                "rule_type": "allowed",
                "section": "A2",
                "room_id": "CSE-104",
                "note": "Fixed for Group A2",
            },
        ]
        set_course_slot_rules(db, course_id, rules)

        # Load problem from DB
        problem = load_problem_from_db(db)

        # Check events
        ev_a1 = next((e for e in problem.events if e.course.code == course_id and e.section == "A" and e.group in ("G1", "1", "A1")), None)
        ev_a2 = next((e for e in problem.events if e.course.code == course_id and e.section == "A" and e.group in ("G2", "2", "A2")), None)

        assert ev_a1 is not None, "Event for Group A1 not found"
        assert ev_a2 is not None, "Event for Group A2 not found"

        print(f"Group A1 Event {ev_a1.eid}: allowed_slots={ev_a1.allowed_slots}, slot_room_rules={ev_a1.slot_room_rules}")
        print(f"Group A2 Event {ev_a2.eid}: allowed_slots={ev_a2.allowed_slots}, slot_room_rules={ev_a2.slot_room_rules}")

        assert ev_a1.allowed_slots == {0, 1, 2}, f"Expected {{0, 1, 2}} for A1, got {ev_a1.allowed_slots}"
        assert ev_a2.allowed_slots == {18, 19, 20}, f"Expected {{18, 19, 20}} for A2, got {ev_a2.allowed_slots}"
        assert ev_a1.slot_room_rules.get(0) == "CSE-103", f"Expected CSE-103 for A1, got {ev_a1.slot_room_rules}"
        assert ev_a2.slot_room_rules.get(18) == "CSE-104", f"Expected CSE-104 for A2, got {ev_a2.slot_room_rules}"

        print("Backend rule application verified successfully!")

        # Solve routine
        print("Solving routine to verify solver placement...")
        problem.options["solver"]["max_seconds"] = 15
        scheduler = RoutineScheduler(problem)
        scheduler.build()
        sol = scheduler.solve()
        print(f"Solve status: {sol.status}")
        assert sol.status in ("OPTIMAL", "FEASIBLE"), f"Expected OPTIMAL/FEASIBLE, got {sol.status}"

        # Check assignments
        a1_assign = next((a for a in sol.assignments if a.event_id == ev_a1.eid), None)
        a2_assign = next((a for a in sol.assignments if a.event_id == ev_a2.eid), None)

        assert a1_assign is not None, "A1 was not scheduled!"
        assert a2_assign is not None, "A2 was not scheduled!"

        print(f"SUCCESS: A1 scheduled at start_slot={a1_assign.start_slot} in room={a1_assign.room_id}")
        print(f"SUCCESS: A2 scheduled at start_slot={a2_assign.start_slot} in room={a2_assign.room_id}")

        assert a1_assign.start_slot == 0, f"Expected slot 0 (Sunday P1-P3) for A1, got {a1_assign.start_slot}"
        assert a2_assign.start_slot == 18, f"Expected slot 18 (Tuesday P1-P3) for A2, got {a2_assign.start_slot}"
        assert a1_assign.room_id == "CSE-103", f"Expected CSE-103 for A1, got {a1_assign.room_id}"
        assert a2_assign.room_id == "CSE-104", f"Expected CSE-104 for A2, got {a2_assign.room_id}"

        print("\nALL VERIFICATIONS PASSED! Group-level slot and room fixing works perfectly!")
    finally:
        db.close()

if __name__ == "__main__":
    test_group_rules()
