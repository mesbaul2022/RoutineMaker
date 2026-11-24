import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import urllib.request
import urllib.parse
import urllib.error
from app.db import SessionLocal, init_db, Course as CourseModel
from app.db_loader import load_problem_from_db
from routine.scheduler import solve_routine
from tools.verify import verify

BASE_URL = "http://127.0.0.1:8000"

def api_get(endpoint):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def api_put(endpoint, data):
    url = f"{BASE_URL}{urllib.parse.quote(endpoint)}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("1. Fetching courses via API...")
    courses = api_get("/api/courses")
    print(f"Loaded {len(courses)} courses.")
    assert "allowed_rooms" in courses[0], "allowed_rooms missing from CourseOut!"

    # Find an active theory course from loaded problem
    db = SessionLocal()
    problem = load_problem_from_db(db)
    active_theory_codes = [c.code for c in problem.courses if c.kind == "theory"]
    active_lab_codes = [c.code for c in problem.courses if c.kind == "sessional" and c.room_kind == "cse_lab"]
    print("Active theory courses:", active_theory_codes[:5])
    print("Active lab courses:", active_lab_codes[:5])

    test_th_code = "CSE1203" if "CSE1203" in active_theory_codes else active_theory_codes[0]
    test_lab_code = "CSE1206" if "CSE1206" in active_lab_codes else active_lab_codes[0]

    theory_course = next(c for c in courses if c["id"].replace(' ', '') == test_th_code.replace(' ', ''))
    lab_course = next(c for c in courses if c["id"].replace(' ', '') == test_lab_code.replace(' ', ''))
    print(f"Selected theory course: {theory_course['id']} ({theory_course['title']})")
    print(f"Selected departmental lab course: {lab_course['id']} ({lab_course['title']})")

    # Update theory course with specific rooms: CSE-101 and CSE-102
    print(f"Assigning specific rooms ['CSE-101', 'CSE-102'] to {theory_course['id']}...")
    update_payload_th = {
        "allowed_rooms": ["CSE-101", "CSE-102"]
    }
    updated_theory = api_put(f"/api/courses/{theory_course['id']}", update_payload_th)
    assert updated_theory["allowed_rooms"] == ["CSE-101", "CSE-102"], f"Mismatch in allowed_rooms: {updated_theory['allowed_rooms']}"
    print(f"Theory course updated successfully with allowed_rooms: {updated_theory['allowed_rooms']}")

    # Update lab course with specific labs: CSE-103 and CSE-104
    print(f"Assigning specific rooms ['CSE-103', 'CSE-104'] to {lab_course['id']}...")
    update_payload_lab = {
        "allowed_rooms": ["CSE-103", "CSE-104"]
    }
    updated_lab = api_put(f"/api/courses/{lab_course['id']}", update_payload_lab)
    assert updated_lab["allowed_rooms"] == ["CSE-103", "CSE-104"], f"Mismatch in allowed_rooms: {updated_lab['allowed_rooms']}"
    print(f"Lab course updated successfully with allowed_rooms: {updated_lab['allowed_rooms']}")

    # Now verify DB problem loading and solver constraint formulation
    print("\n2. Verifying problem loader from DB...")
    db = SessionLocal()
    try:
        problem = load_problem_from_db(db)
        print("Loaded problem course codes:", [c.code for c in problem.courses[:10]])
        # Check that theory_course and lab_course have allowed_rooms properly loaded
        c_th = next((c for c in problem.courses if c.code.replace(' ', '') == theory_course["id"].replace(' ', '')), None)
        assert c_th is not None, f"Course {theory_course['id']} not in loaded problem"
        assert c_th.allowed_rooms == ["CSE-101", "CSE-102"], f"c_th.allowed_rooms is {c_th.allowed_rooms}"
        print(f"Loaded problem course {c_th.code} has allowed_rooms: {c_th.allowed_rooms}")

        c_lab = next((c for c in problem.courses if c.code.replace(' ', '') == lab_course["id"].replace(' ', '')), None)
        assert c_lab is not None, f"Course {lab_course['id']} not in loaded problem"
        assert c_lab.allowed_rooms == ["CSE-103", "CSE-104"], f"c_lab.allowed_rooms is {c_lab.allowed_rooms}"
        print(f"Loaded problem course {c_lab.code} has allowed_rooms: {c_lab.allowed_rooms}")

        # Check feasible_rooms for their events
        th_events = [ev for ev in problem.events if ev.course.code.replace(' ', '') == theory_course["id"].replace(' ', '')]
        for ev in th_events:
            feas = problem.feasible_rooms(ev)
            feas_ids = [r.id for r in feas]
            assert set(feas_ids) == {"CSE-101", "CSE-102"}, f"Expected ['CSE-101', 'CSE-102'], got {feas_ids}"
        print(f"All {len(th_events)} events for {theory_course['id']} have strictly feasible rooms: {feas_ids}")

        lab_events = [ev for ev in problem.events if ev.course.code.replace(' ', '') == lab_course["id"].replace(' ', '')]
        for ev in lab_events:
            feas = problem.feasible_rooms(ev)
            feas_ids = [r.id for r in feas]
            assert set(feas_ids) == {"CSE-103", "CSE-104"}, f"Expected ['CSE-103', 'CSE-104'], got {feas_ids}"
        print(f"All {len(lab_events)} events for {lab_course['id']} have strictly feasible rooms: {feas_ids}")

        print("\n3. Testing solver run with specific room constraints...")
        problem.options["solver"]["max_seconds"] = 15
        sol = solve_routine(problem, two_phase=False)
        print(f"Solver result: status={sol.status}, {len(sol.assignments)} assignments")
        assert sol.ok, f"Solve failed: {sol.status}"

        # Verify placement of theory_course and lab_course
        for a in sol.assignments:
            if a.event.course.code.replace(' ', '') == theory_course["id"].replace(' ', ''):
                assert a.room_id in ("CSE-101", "CSE-102"), f"Theory event placed in wrong room: {a.room_id}"
            if a.event.course.code.replace(' ', '') == lab_course["id"].replace(' ', ''):
                assert a.room_id in ("CSE-103", "CSE-104"), f"Lab event placed in wrong room: {a.room_id}"

        # Run full verifier
        faults = verify(problem, sol)
        h5_faults = [f for f in faults if f.startswith("H5")]
        print(f"Verification complete: {len(faults)} faults, {len(h5_faults)} H5 room faults.")
        assert len(h5_faults) == 0, f"H5 faults found: {h5_faults}"
        print("All assignments verified strictly compliant with specific rooms!")

    finally:
        db.close()

if __name__ == "__main__":
    main()
