"""Verify out/real_routine.csv (real KUET data) against every hard constraint,
reconstructed straight from the delivered CSV -- not a fresh solve."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routine.loader import load_problem
from tools.verify import verify
from tools.verify_csv import reconstruct


def main():
    problem = load_problem("data/kuet_cse_real.json")
    sol = reconstruct(problem, "out/real_routine.csv")
    print(f"reconstructed {len(sol.assignments)} / {len(problem.events)} meetings")
    faults = verify(problem, sol)
    if faults:
        print(f"{len(faults)} violations")
        for f in faults[:30]:
            print(" ", f)
        return 1
    print("all hard constraints satisfied on the delivered real_routine.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
