import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import urllib.request
from app.db import SessionLocal, init_db, set_course_slot_rules, get_course_slot_rules, Course as CourseModel
from app.db_loader import load_problem_from_db
from routine.scheduler import solve_routine
from tools.verify import verify

def test_api():
    print("Testing API /api/courses/CSE1203/availability...")
    base_url = "http://127.0.0.1:8000"
    
    # 1. Check GET availability
    req = urllib.request.Request(f"{base_url}/api/courses/CSE1203/availability")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
    print("GET success. Allowed rooms from course:", data.get("allowed_rooms"))
    
    # 2. Set rule with specific room via PUT
    payload = {
        "rules": [
            {
                "day": "Sunday",
                "periods": "P1",
                "rule_type": "allowed",
                "section": "A",
                "room_id": "CSE-101",
                "note": "Sec A on Sunday P1 in CSE Room 101"
            },
            {
                "day": "Sunday",
                "periods": "P1",
                "rule_type": "allowed",
                "section": "B",
                "room_id": "CSE-102",
                "note": "Sec B on Sunday P1 in CSE Room 102"
            }
        ]
    }
    req = urllib.request.Request(
        f"{base_url}/api/courses/CSE1203/availability",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        saved_data = json.loads(resp.read().decode())
    print("PUT success. Saved rules:")
    for r in saved_data["rules"]:
        print(f"  - [{r['rule_type']}] Sec {r['section']}: {r['day']} {r['periods']} room={r['room_id']} ({r['room_name']}) desc='{r['description']}'")
        assert r["room_id"] in ("CSE-101", "CSE-102")
        assert r["room_name"] is not None

def test_solver_enforcement():
    print("\nTesting solver enforcement of Section + Slot + Room...")
    with SessionLocal() as db:
        # Ensure 1-2 batch is 'on' so CSE1203 is scheduled
        from app.db import Batch as BatchModel
        b = db.query(BatchModel).filter_by(id="1-2").first()
        if b:
            b.status = "on"
            db.commit()

        # Assign teachers to CSE1203 if missing
        c = db.query(CourseModel).filter_by(id="CSE1203").first()
        if not c.teacher1_id:
            c.teacher1_id = "muhammad_sheikh_sadi"
            c.teacher2_id = "kazi_saeed_alam"
            db.commit()

        # Set rules: Sec A Sunday P1 in CSE-101; Sec B Sunday P2 in CSE-102
        rules = [
            {
                "day": "Sunday",
                "periods": "P1",
                "rule_type": "allowed",
                "section": "A",
                "room_id": "CSE-101",
                "note": "Test Sec A in CSE-101"
            },
            {
                "day": "Sunday",
                "periods": "P2",
                "rule_type": "allowed",
                "section": "B",
                "room_id": "CSE-102",
                "note": "Test Sec B in CSE-102"
            }
        ]
        set_course_slot_rules(db, "CSE1203", rules)
        problem = load_problem_from_db(db)

    print(f"Loaded problem: {len(problem.courses)} courses, {len(problem.events)} events")
    
    # Check events for CSE1203
    c1203_events = [ev for ev in problem.events if ev.course.code == "CSE1203"]
    print(f"CSE1203 has {len(c1203_events)} events:")
    for ev in c1203_events:
        print(f"  {ev.label}: teachers={ev.teacher_ids}, allowed_slots={ev.allowed_slots}, blocked_slots={ev.blocked_slots}, slot_room_rules={ev.slot_room_rules}")

    # Solve routine
    problem.options["solver"]["max_seconds"] = 30
    problem.options["solver"]["workers"] = 4
    solution = solve_routine(problem)
    assert solution is not None, "Solver failed to find a solution!"
    print(f"Solution status: {solution.status}")

    # Verify assignments for CSE1203
    secA_sun_p1 = [a for a in solution.assignments if a.event.course.code == "CSE1203" and a.event.section == "A" and a.start == 0]
    secB_sun_p2 = [a for a in solution.assignments if a.event.course.code == "CSE1203" and a.event.section == "B" and a.start == 1]

    assert len(secA_sun_p1) == 1, f"Expected 1 Sec A class at Sunday P1, got {len(secA_sun_p1)}"
    assert len(secB_sun_p2) == 1, f"Expected 1 Sec B class at Sunday P2, got {len(secB_sun_p2)}"

    print(f"SUCCESS: CSE1203 Sec A Sunday P1 room: {secA_sun_p1[0].room_id} (Expected CSE-101)")
    print(f"SUCCESS: CSE1203 Sec B Sunday P2 room: {secB_sun_p2[0].room_id} (Expected CSE-102)")

    assert secA_sun_p1[0].room_id == "CSE-101", f"Wrong room for Sec A: {secA_sun_p1[0].room_id}"
    assert secB_sun_p2[0].room_id == "CSE-102", f"Wrong room for Sec B: {secB_sun_p2[0].room_id}"

    # Verify all constraints with verify()
    faults = verify(problem, solution)
    print(f"Total verification faults: {len(faults)}")
    if faults:
        for f in faults[:10]:
            print(f"  FAULT: {f}")
    assert len(faults) == 0, f"Found {len(faults)} verification faults!"
    # Test 3: Custom non-homeroom assignment
    print("\nTesting custom non-homeroom assignment (Sec A in CSE-105, Sec B in CSE-306)...")
    with SessionLocal() as db:
        rules = [
            {
                "day": "Sunday",
                "periods": "P1",
                "rule_type": "allowed",
                "section": "A",
                "room_id": "CSE-105",
                "note": "Sec A custom room CSE-105"
            },
            {
                "day": "Sunday",
                "periods": "P2",
                "rule_type": "allowed",
                "section": "B",
                "room_id": "CSE-306",
                "note": "Sec B custom room CSE-306"
            }
        ]
        set_course_slot_rules(db, "CSE1203", rules)
        problem = load_problem_from_db(db)

    problem.options["solver"]["max_seconds"] = 30
    problem.options["solver"]["workers"] = 4
    solution = solve_routine(problem)
    assert solution is not None, "Solver failed to find a solution!"
    assert solution.status in ("OPTIMAL", "FEASIBLE")

    secA_custom = [a for a in solution.assignments if a.event.course.code == "CSE1203" and a.event.section == "A" and a.start == 0]
    secB_custom = [a for a in solution.assignments if a.event.course.code == "CSE1203" and a.event.section == "B" and a.start == 1]

    print(f"Sec A Sunday P1 room: {secA_custom[0].room_id} (Expected CSE-105)")
    print(f"Sec B Sunday P2 room: {secB_custom[0].room_id} (Expected CSE-306)")

    assert secA_custom[0].room_id == "CSE-105", f"Wrong room: {secA_custom[0].room_id}"
    assert secB_custom[0].room_id == "CSE-306", f"Wrong room: {secB_custom[0].room_id}"

    faults = verify(problem, solution)
    assert len(faults) == 0, f"Found faults: {faults}"
    print("SUCCESS: Custom non-homeroom slot assignment verified with 0 faults!")

    print("\nALL BACKEND & SOLVER TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_api()
    test_solver_enforcement()
