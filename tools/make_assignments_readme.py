"""Generate TEACHER_COURSE_ASSIGNMENTS.md straight from the loaded problem --
so the document always matches whatever data/kuet_cse_real.json actually
contains, rather than being hand-typed and silently drifting out of sync."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routine.loader import load_problem

BATCH_ORDER = ["1-1", "2-1", "2-2", "3-2", "4-1"]


def main():
    p = load_problem("data/kuet_cse_real.json")

    lines = [
        "# Teacher -> Course Assignments",
        "",
        "Generated from `data/kuet_cse_real.json`, which was built from your five",
        "uploaded routine sheets (1st Year 1st Term, 2nd Year 1st Term, 2nd Year",
        "2nd Term, 3rd Year 2nd Term, 4th Year 1st Term). This is the input data",
        "as the system actually sees it -- use it to check the assignments below",
        "against your original PDFs/photos before trusting this for anything",
        "official.",
        "",
        "**Every line marked `VERIFY` in `tools/from_real_routines.py` is a place",
        "I picked one teacher between two or more codes that appeared attached to",
        "the same course in your scanned routine (e.g. `CSE 3209` vs",
        "`CSE 3209c (TR/WIS)`) -- those are listed again at the bottom of this",
        "file in one place.**",
        "",
    ]

    by_batch: dict[str, list] = defaultdict(list)
    for c in p.courses:
        by_batch[c.batch].append(c)

    for batch_id in BATCH_ORDER:
        if batch_id not in by_batch:
            continue
        batch = p.batches[batch_id]
        lines.append(f"## {batch.name} (`{batch_id}`)")
        lines.append("")
        lines.append("| Course | Title | Type | Teacher(s) |")
        lines.append("|---|---|---|---|")
        for c in sorted(by_batch[batch_id], key=lambda c: c.code):
            if c.is_theory:
                owner = c.theory_teacher("A")
                lines.append(
                    f"| {c.code} | {c.title} | Theory, "
                    f"{c.periods_per_week}/week | {p.teachers[owner].name} |"
                )
            else:
                pair = c.teachers["A"]
                names = " + ".join(p.teachers[t].name for t in dict.fromkeys(pair.values()))
                lines.append(f"| {c.code} | {c.title} | Lab | {names} |")
        lines.append("")

    # Reverse index: what does each teacher actually teach, across every batch?
    load: dict[str, list[str]] = defaultdict(list)
    for c in p.courses:
        if c.is_theory:
            load[c.theory_teacher("A")].append(f"{c.code} (theory, {p.batches[c.batch].name})")
        else:
            for tid in dict.fromkeys(c.teachers["A"].values()):
                load[tid].append(f"{c.code} (lab, {p.batches[c.batch].name})")

    lines.append("## By teacher")
    lines.append("")
    lines.append("Use this to sanity-check for anyone overloaded, or anyone this")
    lines.append("system thinks teaches something they no longer teach.")
    lines.append("")
    for tid in sorted(load, key=lambda t: p.teachers[t].name):
        lines.append(f"- **{p.teachers[tid].name}** (`{tid}`)")
        for item in load[tid]:
            lines.append(f"  - {item}")
    lines.append("")

    lines.append("## Name collisions resolved")
    lines.append("")
    lines.append("Your five sheets reuse short codes for different real people.")
    lines.append("These were kept as separate teachers so the system never merges")
    lines.append("them into one person by mistake:")
    lines.append("")
    lines.append("| Code | Person A | Person B | Person C |")
    lines.append("|---|---|---|---|")
    lines.append("| AH | Dr. K. M. Azharul Hasan (3rd/4th yr) | Mr. S.M. Arif Hossen "
                  "(2nd yr, MATH) | Dr. Md. Alamgir Hossain (1st yr, PHY) |")
    lines.append("| SA | Mr. Safin Ahmmed (2nd/3rd yr) | Mr. Md. Shahinur Alam Sarker "
                  "(1st yr, HUM) | -- |")
    lines.append("| RA | Dr. S.M Rabiul Alam (2nd yr, HUM) | Dr. Kazi Md. Rokibul Alam "
                  "(4th yr) | -- |")
    lines.append("")
    lines.append("People correctly recognised as the SAME person across different")
    lines.append("sheets despite different abbreviations (so the system can catch a")
    lines.append("real double-booking of them across batches):")
    lines.append("")
    lines.append("- Md. Nazirulhasan Shawon -- `NHS` (3rd yr) and `NS` (2nd yr)")
    lines.append("- Mrs. Lamisa Bintee Mizan Deya -- `LBM` (2nd yr 2nd term) and "
                  "`LD` (2nd yr 1st term)")
    lines.append("- Md. Repon Islam -- `MRI` (3rd yr) and `RI` (2nd yr)")
    lines.append("")

    lines.append("## VERIFY -- ambiguous readings, one place")
    lines.append("")
    lines.append("Every course below had more than one teacher code attached to it")
    lines.append("across its instances in your scanned routine. One was picked as")
    lines.append("the owner; check against the original if the specific teacher")
    lines.append("matters for your thesis:")
    lines.append("")
    verify_items = [
        ("CSE3209 (3-2)", "TR vs WIS", "WIS"),
        ("CSE3217 (3-2)", "KFI vs MRI", "KFI"),
        ("CSE3219 (3-2)", "NFS vs EK", "NFS"),
        ("CSE2201 (2-2)", "SH vs MAN", "SH"),
        ("ECE2213 (2-2)", "FH vs FRH", "FH"),
        ("MATH2207 (2-2)", "ARJ vs HZ", "ARJ"),
        ("HUM2207 (2-2)", "RA vs FA", "RA"),
        ("CSE1107 (1-1)", "MI vs an unlisted code 'BS'", "MI"),
        ("PHY1107 (1-1)", "SKS vs AH (Alamgir Hossain)", "SKS"),
        ("HUM1107 (1-1)", "MT vs an unnamed guest teacher", "MT"),
        ("CSE4101 (4-1)", "MAN vs MAH vs AM vs SMA", "MAN"),
        ("CSE4105 (4-1)", "SH vs NHS vs NFS", "SH"),
        ("CSE4111 (4-1)", "MAH vs AM vs SMA", "MAH"),
        ("CSE4115 (4-1)", "DD vs RA2 (Rokibul Alam)", "DD"),
        ("CSE4121 (4-1)", "AH (Azharul Hasan) vs NHS", "AH"),
    ]
    lines.append("| Course | Codes seen | Picked |")
    lines.append("|---|---|---|")
    for course, seen, picked in verify_items:
        lines.append(f"| {course} | {seen} | {picked} |")
    lines.append("")

    lines.append("## Assumptions, not read from any document")
    lines.append("")
    lines.append("- Section size 60, group size 30 -- not stated in any routine")
    lines.append("- No teacher `unavailable` slots are set -- a finished routine "
                  "only shows the outcome, not the constraint that produced it")
    lines.append("- CSE3200 (System Development Project) and CSE4000 "
                  "(Capstone Project/Thesis) have no fixed classroom teacher in "
                  "your routines (individually supervised) -- left out entirely")
    lines.append("- CSE3230 (Technical Writing and Seminar) is shown as one joint "
                  "Section A+B session in your routine; modelled here as the same "
                  "two teachers scheduled separately per section")
    lines.append("- Room counts for shared/specialised labs (CSE-103, CSE-104, "
                  "CSE-306/501/502) are reasonable guesses, not stated counts")
    lines.append("")
    lines.append("## Could not check")
    lines.append("")
    lines.append("The official KUET CSE faculty directory "
                  "(kuet.ac.bd/cse/faculty) blocks automated access, so teacher "
                  "names/status above were NOT cross-checked against who is "
                  "currently listed as active vs. on leave -- only against what's "
                  "printed on your five routine sheets.")

    out = Path("TEACHER_COURSE_ASSIGNMENTS.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
