"""Build data/kuet_cse_real.json from the three real routines you uploaded:

  - 3rd Year 2nd Term, session 2024-2025 (the photo)
  - 2nd Year 2nd Term, session 2024-2025 (PDF)
  - 2nd Year 1st Term, session 2025-2026 (PDF)

WHAT THIS FILE DOES *NOT* NEED FROM THE ORIGINAL ROUTINE
----------------------------------------------------------
Your system doesn't need to know which day/period a class currently sits on
-- that's exactly what the algorithm works out. All it needs is: which
teacher teaches which course, to which section/group, how many times a week.
So this file only encodes course-teacher-section pairings, not the grid.

CONFIDENCE LEVELS -- READ THIS BEFORE TRUSTING THE OUTPUT
-----------------------------------------------------------
Teacher names, course codes/titles, and room footnotes are read from clean
printed reference tables in your PDFs -- high confidence.

Which teacher owns which course, for each section, is read from the dense
grid body. That grid has some real ambiguity a scan can't resolve with
certainty:
  - A few cells carry a 'c' suffix (e.g. "CSE 3209c") next to a plain
    instance of the same course elsewhere -- this usually means "this one
    session is combined across both sections." I did NOT model true
    cross-section combining (it would need a small code change); instead I
    picked ONE primary teacher per course per section. Flagged with
    VERIFY below wherever a course had more than one teacher code attached
    across its instances.
  - CSE 3230 (Technical Writing and Seminar) and CSE 3200 (System
    Development Project) run as a shared A/B session in your routine, not
    per-section. CSE 3230 is modelled here as a per-section sessional with
    the same two teachers on both sections, which schedules it correctly
    for each section separately rather than as one truly joint session.
    CSE 3200 has no fixed classroom teacher in your routine (individually
    supervised), so it's left OUT of the schedulable courses entirely.
  - Section/group head counts (60/30) are assumed, not stated anywhere in
    the routine -- change SECTION_SIZE / GROUP_SIZE below to your real
    numbers.
  - Teacher standing-availability blocks (someone unavailable a fixed slot
    every week) are not visible in a finished routine, only the *outcome*.
    None are set here -- add real ones under `unavailable` per teacher if
    you know of any, otherwise the algorithm assumes everyone is free
    whenever they aren't already teaching something else.
  - Lab room supply for CSE-103 (shared by three different 3rd-year lab
    courses) and the AI/seminar rooms is a reasonable guess at how many
    physical rooms exist, since the footnote names rooms but not counts.
    Check the ROOMS section below against reality.

Every place worth a second look is marked  # VERIFY  in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Same grid as before: your snack break was 10:30-10:50 while P4 started at
# 10:40, so it's shortened to 10:30-10:40; P6 was listed twice, so the
# afternoon is renumbered P7-P9. Matches the photo/PDF times exactly.
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

SECTION_SIZE = 60  # VERIFY: not stated in the routine, adjust to your real intake
GROUP_SIZE = 30    # VERIFY: assumed as half the section

# --------------------------------------------------------------- teachers
#
# id: a stable slug built from the full name, so the SAME person is
# recognised as one teacher even though different term sheets abbreviate
# them differently (e.g. "NHS" in the 3rd-year sheet vs "NS" in the 2nd-year
# sheet are the same Md. Nazirulhasan Shawon). This is what lets the solver
# catch a real double-booking of one teacher across two different batches.
#
# short: whichever 2-4 letter code your own routines use, kept for display.

TEACHERS = [
    # -- 3rd Year 2nd Term sheet --
    {"id": "mma_hashem", "name": "Dr. M. M. A. Hashem", "short": "MMA"},
    {"id": "km_azharul_hasan", "name": "Dr. K. M. Azharul Hasan", "short": "AH"},
    {"id": "md_abdul_awal", "name": "Dr. Md. Abdul Awal", "short": "AAW"},
    {"id": "dola_das", "name": "Ms. Dola Das", "short": "DD"},
    {"id": "kazi_saeed_alam", "name": "Mr. Kazi Saeed Alam", "short": "KSA"},
    {"id": "md_repon_islam", "name": "Mr. Md. Repon Islam", "short": "MRI"},
    {"id": "md_nazirulhasan_shawon", "name": "Mr. Md. Nazirulhasan Shawon", "short": "NHS"},
    {"id": "md_badiuzzaman_shuvo", "name": "Mr. Md. Badiuzzaman Shuvo", "short": "BS"},
    {"id": "safin_ahmmed", "name": "Mr. Safin Ahmmed", "short": "SA"},
    {"id": "kaniz_fatema_isha", "name": "Ms. Most. Kaniz Fatema Isha", "short": "KFI"},
    {"id": "md_tajmilur_rahman", "name": "Mr. Md Tajmilur Rahman", "short": "TR"},
    {"id": "nabil_faiyaz_sadi", "name": "Mr. Nabil Faiyaz Sadi", "short": "NFS"},
    {"id": "waliul_islam_sumon", "name": "Mr. Waliul Islam Sumon", "short": "WIS"},
    {"id": "sadia_islam", "name": "Mst. Sadia Islam", "short": "SI"},
    {"id": "ehsanul_karim", "name": "Mr. Ehsanul Karim", "short": "EK"},
    # -- 2nd Year 2nd Term sheet --
    {"id": "md_milon_islam", "name": "Dr. Md. Milon Islam", "short": "MI"},
    {"id": "md_sakhawat_hossain", "name": "Mr. Md. Sakhawat Hossain", "short": "SH"},
    {"id": "subah_nawar", "name": "Ms. Subah Nawar", "short": "SN"},
    {"id": "md_mubtashim_abrar_nihal", "name": "Mr. Md. Mubtashim Abrar Nihal", "short": "MAN"},
    {"id": "lamisa_bintee_mizan_deya", "name": "Mrs. Lamisa Bintee Mizan Deya", "short": "LBM"},
    {"id": "md_faruque_hossain", "name": "Dr. Md. Faruque Hossain", "short": "FRH"},
    {"id": "md_faisal_hossain", "name": "Dr. Md. Faisal Hossain", "short": "FH"},
    {"id": "mushfiqur_rahman_masuk", "name": "Mr. Mushfiqur Rahman Masuk", "short": "MRM"},
    {"id": "md_minhajul_islam_arnab", "name": "Mr. Md. Minhajul Islam Arnab", "short": "MIA"},
    {"id": "arm_jalal_uddin_jamali", "name": "Dr. A. R. M. Jalal Uddin Jamali", "short": "ARJ"},
    {"id": "md_hasanuzzaman", "name": "Dr. Md. Hasanuzzaman", "short": "HZ"},
    {"id": "sm_rabiul_alam", "name": "Dr. S.M Rabiul Alam", "short": "RA"},
    {"id": "farhana_afroj", "name": "Ms. Farhana Afroj", "short": "FA"},
    # -- 2nd Year 1st Term sheet --
    {"id": "muhammad_sheikh_sadi", "name": "Dr. Muhammad Sheikh Sadi", "short": "SS"},
    {"id": "md_rejvi_kaysir", "name": "Dr. Md Rejvi Kaysir", "short": "RK"},
    {"id": "akash_biswas", "name": "Mr. Akash Biswas", "short": "AB"},
    {"id": "robin_sarker", "name": "Mr. Robin Sarker", "short": "RS"},
    {"id": "jeesun_patra_papon", "name": "Mr. Jeesun Patra Papon", "short": "JP"},
    {"id": "md_mahbubur_rahman", "name": "Dr. Md. Mahbubur Rahman", "short": "MR"},
    {"id": "miir_anjirin_tazrin", "name": "Mr. Miir Anjirin Tazrin", "short": "AT"},
    {"id": "md_zaidur_rahman", "name": "Dr. Md. Zaidur Rahman", "short": "ZR"},
    {"id": "sm_arif_hossen", "name": "Mr. S.M. Arif Hossen", "short": "AH2"},
    # note: "AH" is used for THREE different people across your five sheets --
    # Dr. K. M. Azharul Hasan (3rd year, 4th year), Mr. S.M. Arif Hossen (2nd
    # year, MATH), and Dr. Md. Alamgir Hossain (1st year, PHY, added below).
    # Each is kept as a separate teacher with a full-name id.

    # -- 1st Year 1st Term sheet --
    {"id": "sujit_kumer_shil", "name": "Dr. Sujit Kumer Shil", "short": "SKS"},
    {"id": "md_alamgir_hossain", "name": "Dr. Md. Alamgir Hossain", "short": "AH3"},
    {"id": "md_sohag_hossain", "name": "Mr. Md. Sohag Hossain", "short": "MSH"},
    {"id": "md_afsar_ali", "name": "Mr. Md. Afsar Ali", "short": "AA"},
    {"id": "munshi_tauhiduzzaman", "name": "Mr. Munshi Tauhiduzzaman", "short": "MT"},
    {"id": "md_shahinur_alam_sarker", "name": "Mr. Md. Shahinur Alam Sarker", "short": "SA2"},
    # note: "SA" also collides -- Mr. Safin Ahmmed (2nd/3rd year) vs
    # Mr. Md. Shahinur Alam Sarker (1st year, HUM). Kept separate.
    {"id": "maria_bhuiyan", "name": "Mrs. Maria Bhuiyan", "short": "MB"},
    {"id": "md_dulal_hossain", "name": "Mr. Md. Dulal Hossain", "short": "DH"},
    {"id": "sunny_khatun", "name": "Mst. Sunny Khatun", "short": "MK"},

    # -- 4th Year 1st Term sheet --
    {"id": "kazi_md_rokibul_alam", "name": "Dr. Kazi Md. Rokibul Alam", "short": "RA2"},
    # note: "RA" also collides -- Dr. S.M Rabiul Alam (2nd year, HUM) vs
    # Dr. Kazi Md. Rokibul Alam (4th year). Kept separate.
    {"id": "muhammad_aminul_haque", "name": "Dr. Muhammad Aminul Haque", "short": "MAH"},
    {"id": "sk_md_masudul_ahsan", "name": "Dr. Sk. Md. Masudul Ahsan", "short": "SMA"},
    {"id": "al_mahmud", "name": "Prof. Dr. Al-Mahmud", "short": "AM"},
    {"id": "sk_imran_hossain", "name": "Dr. Sk. Imran Hossain", "short": "IH"},
]

# --------------------------------------------------------------------- rooms
#
# VERIFY room counts -- the footnotes name rooms but not how many identical
# ones exist. Counts below are a reasonable guess to make the instance
# solvable; correct them to your real room inventory.

ROOMS = [
    {"id": "B-306", "name": "Room B-306", "kind": "theory", "capacity": 70},
    {"id": "B-102", "name": "Room B-102", "kind": "theory", "capacity": 70},
    {"id": "B-105", "name": "Room B-105", "kind": "theory", "capacity": 70},
    {"id": "D-401", "name": "Room D-401", "kind": "theory", "capacity": 70},
    {"id": "D-402", "name": "Room D-402", "kind": "theory", "capacity": 70},
    {"id": "CSE-103", "name": "CSE Lab 103", "kind": "cse_lab", "capacity": 35},
    {"id": "CSE-103-2", "name": "CSE Lab 103 (2nd room)", "kind": "cse_lab", "capacity": 35},  # VERIFY: guessed 2nd room
    {"id": "CSE-202", "name": "CSE Lab 202", "kind": "cse_lab", "capacity": 35},
    {"id": "CSE-107", "name": "CSE Lab 107", "kind": "cse_lab", "capacity": 35},
    {"id": "CSE-305", "name": "CSE Lab 305 (AI)", "kind": "ai_lab", "capacity": 35},
    {"id": "CSE-306", "name": "Room CSE-306", "kind": "seminar", "capacity": 70},
    {"id": "CSE-501", "name": "Room CSE-501", "kind": "seminar", "capacity": 70},
    {"id": "ECE-104", "name": "ECE Lab 104", "kind": "ece_lab", "capacity": 35},
    # -- 1st Year 1st Term --
    {"id": "CSE-101", "name": "Room CSE-101 (1st yr homeroom)", "kind": "year1_theory", "capacity": 70},
    {"id": "CSE-102", "name": "Room CSE-102 (1st yr homeroom)", "kind": "year1_theory", "capacity": 70},
    {"id": "CSE-104-1yr", "name": "CSE Lab 104 (1st yr)", "kind": "year1_cse_lab", "capacity": 35},
    {"id": "PHY-LAB", "name": "Physics Lab", "kind": "phy_lab", "capacity": 35},  # VERIFY: not named in footnote
    {"id": "HUM-LAB", "name": "English Language Lab", "kind": "hum_lab", "capacity": 35},  # VERIFY: not named in footnote
    # -- 4th Year 1st Term --
    {"id": "CSE-501", "name": "Room CSE-501", "kind": "theory", "capacity": 70},
    {"id": "CSE-502", "name": "Room CSE-502", "kind": "theory", "capacity": 70},
    {"id": "CSE-201", "name": "CSE Lab 201", "kind": "network_lab", "capacity": 35},
    # CSE4102/CSE4122 (4th year) share the SAME physical CSE-305 as CSE3210
    # (3rd year AI lab) per both footnotes -- reusing the "ai_lab" room above
    # rather than adding a duplicate. CSE4112/CSE4116 (4th year) draw from the
    # shared "cse_lab" pool above rather than a dedicated CSE-104-for-4th-year
    # room, since that pool already has spare capacity.  # VERIFY
]

# ------------------------------------------------------------------- batches

BATCHES = [
    {"id": "1-1", "name": "1st Year 1st Term", "sections": ["A", "B"],
     "groups": ["G1", "G2"], "section_size": SECTION_SIZE, "group_size": GROUP_SIZE},
    {"id": "3-2", "name": "3rd Year 2nd Term", "sections": ["A", "B"],
     "groups": ["G1", "G2"], "section_size": SECTION_SIZE, "group_size": GROUP_SIZE},
    {"id": "2-2", "name": "2nd Year 2nd Term", "sections": ["A", "B"],
     "groups": ["G1", "G2"], "section_size": SECTION_SIZE, "group_size": GROUP_SIZE},
    {"id": "2-1", "name": "2nd Year 1st Term", "sections": ["A", "B"],
     "groups": ["G1", "G2"], "section_size": SECTION_SIZE, "group_size": GROUP_SIZE},
    {"id": "4-1", "name": "4th Year 1st Term", "sections": ["A", "B"],
     "groups": ["G1", "G2"], "section_size": SECTION_SIZE, "group_size": GROUP_SIZE},
]

# ------------------------------------------------------------------ courses
#
# Each theory course: one teacher for both sections (matches what your
# routine shows -- the same person takes a course for section A and B).
# Each sessional: G1/G2 teacher pair, same pair on both sections unless your
# sheet showed otherwise.

def theory(code, title, batch, periods, teacher, room_kind="theory"):
    return {
        "code": code, "title": title, "batch": batch, "kind": "theory",
        "room_kind": room_kind, "periods_per_week": periods,
        "teachers": {"A": teacher, "B": teacher},
    }


def sessional(code, title, batch, room_kind, g1_teacher, g2_teacher, blocks=1):
    pair = {"G1": g1_teacher, "G2": g2_teacher}
    return {
        "code": code, "title": title, "batch": batch, "kind": "sessional",
        "room_kind": room_kind, "blocks_per_week": blocks,
        "teachers": {"A": pair, "B": pair},
    }


COURSES = [
    # ---------------- 1st Year 1st Term ----------------
    # VERIFY: CSE1101 theory and CSE1102 lab both show "(TR+EK)" or "(TR/EK)"
    # -- read as TR+EK co-teaching, TR picked as the theory owner.
    theory("CSE1101", "Structured Programming", "1-1", 3, "md_tajmilur_rahman",
           room_kind="year1_theory"),
    sessional("CSE1102", "Structured Programming Laboratory", "1-1", "year1_cse_lab",
              "md_tajmilur_rahman", "ehsanul_karim"),

    # VERIFY: grid shows "CSE 1107 MI/BS" -- "BS" doesn't match anyone on this
    # sheet's own teacher list, so only MI (Milon Islam) is used here. Check
    # the original PDF for who the second teacher actually is.
    theory("CSE1107", "Discrete Mathematics", "1-1", 3, "md_milon_islam",
           room_kind="year1_theory"),

    # VERIFY: PHY1107 shows both SKS and AH (Alamgir Hossain) attached --
    # SKS picked as owner.
    theory("PHY1107", "Physics", "1-1", 3, "sujit_kumer_shil", room_kind="year1_theory"),
    sessional("PHY1108", "Physics Laboratory", "1-1", "phy_lab",
              "md_sohag_hossain", "md_afsar_ali"),

    theory("MATH1107", "Differential and Integral Calculus", "1-1", 3,
           "md_dulal_hossain", room_kind="year1_theory"),

    # VERIFY: HUM1107 shows a second "Guest Teacher (X)" alongside MT in your
    # sheet -- not a named person, so left out; MT modelled as sole owner.
    # 2 periods/week assumed.
    theory("HUM1107", "English and Human Communication", "1-1", 2,
           "munshi_tauhiduzzaman", room_kind="year1_theory"),
    sessional("HUM1108", "English and Human Communication Lab", "1-1", "hum_lab",
              "md_shahinur_alam_sarker", "maria_bhuiyan"),

    # ---------------- 4th Year 1st Term ----------------
    # VERIFY: CSE4101 shows MAN, MAH, AM and SMA across different instances --
    # MAN picked as owner (appears first, Sunday P4).
    theory("CSE4101", "Computer Graphics and Image Processing", "4-1", 3,
           "md_mubtashim_abrar_nihal"),
    sessional("CSE4102", "Computer Graphics and Image Processing Laboratory",
              "4-1", "ai_lab", "md_tajmilur_rahman", "md_mubtashim_abrar_nihal"),

    # VERIFY: CSE4105 shows SH, NHS and NFS across instances -- SH picked as
    # owner. Note SH already owns CSE2201 in batch 2-2 -- kept, since your
    # real routines show the same person owning theory in two DIFFERENT
    # batches in the same term (see the chat message for why this is now
    # allowed rather than flagged).
    theory("CSE4105", "Computer Networks", "4-1", 3, "md_sakhawat_hossain"),
    sessional("CSE4106", "Computer Networks Laboratory", "4-1", "network_lab",
              "sk_imran_hossain", "md_sakhawat_hossain"),

    # VERIFY: CSE4111 shows MAH, AM and SMA across instances -- MAH picked.
    theory("CSE4111", "Machine Learning", "4-1", 3, "muhammad_aminul_haque"),
    sessional("CSE4112", "Machine Learning Laboratory", "4-1", "cse_lab",
              "muhammad_aminul_haque", "nabil_faiyaz_sadi"),

    # VERIFY: CSE4115 shows DD and RA2 across instances -- DD picked.
    theory("CSE4115", "Computer Security", "4-1", 3, "dola_das"),
    sessional("CSE4116", "Computer Security Laboratory", "4-1", "cse_lab",
              "kazi_md_rokibul_alam", "dola_das"),

    # VERIFY: CSE4121 shows AH (Azharul Hasan) and NHS across instances -- AH
    # picked as owner specifically so NHS (who already owns CSE2209 in
    # batch 2-2) doesn't pick up a second theory course in the same term.
    theory("CSE4121", "Natural Language Processing", "4-1", 3, "km_azharul_hasan"),
    sessional("CSE4122", "Natural Language Processing Laboratory", "4-1", "ai_lab",
              "km_azharul_hasan", "md_nazirulhasan_shawon"),

    # CSE4000 Capstone Project/Thesis: no fixed classroom teacher shown in
    # your routine (individually supervised) -- intentionally left out, same
    # treatment as CSE3200.

    # ---------------- 3rd Year 2nd Term ----------------
    # VERIFY: CSE3209 shows both TR and WIS attached across instances in
    # your sheet ("CSE 3209 (TR)" and "CSE 3209c (TR/WIS)") -- WIS picked as
    # the theory owner since WIS also runs the paired lab.
    theory("CSE3209", "Artificial Intelligence", "3-2", 3, "waliul_islam_sumon"),
    sessional("CSE3210", "Artificial Intelligence Laboratory", "3-2", "ai_lab",
              "waliul_islam_sumon", "sadia_islam"),

    theory("CSE3211", "Compiler Design", "3-2", 3, "md_abdul_awal"),
    sessional("CSE3212", "Compiler Design Laboratory", "3-2", "cse_lab",
              "md_abdul_awal", "dola_das"),

    # VERIFY: KFI and MRI both appear on CSE3217 instances
    # ("CSE 3217 (KFI)" and "CSE3217c* (MRI/KFI)") -- KFI picked as owner.
    theory("CSE3217", "Mobile Computing", "3-2", 3, "kaniz_fatema_isha"),
    sessional("CSE3218", "Mobile Computing Laboratory", "3-2", "cse_lab",
              "md_repon_islam", "kaniz_fatema_isha"),

    # VERIFY: NFS and EK both appear on CSE3219 instances
    # ("CSE 3219 (NFS)" and "CSE3219c (NFS/EK)") -- NFS picked as owner.
    theory("CSE3219", "Software Engineering and Project Management", "3-2", 3,
           "nabil_faiyaz_sadi"),
    sessional("CSE3220", "Software Engineering and Project Management Laboratory",
              "3-2", "cse_lab", "md_nazirulhasan_shawon", "nabil_faiyaz_sadi"),

    # VERIFY: shown as one combined A/B session (AH+KSA) in your routine,
    # not per-section -- modelled here as the same two teachers scheduled
    # separately for A and B rather than one truly joint session.
    sessional("CSE3230", "Technical Writing and Seminar", "3-2", "seminar",
              "km_azharul_hasan", "kazi_saeed_alam"),

    # VERIFY: MMA and SI both appear ("HUM 3247 (MMA)" and
    # "HUM3247c* (MMA/SI)") -- MMA picked as owner. 2 periods/week assumed.
    theory("HUM3247", "Engineers and Society", "3-2", 2, "mma_hashem"),

    # CSE3200 System Development Project: no fixed classroom teacher shown
    # in your routine (individually supervised) -- intentionally left out.

    # ---------------- 2nd Year 2nd Term ----------------
    sessional("CSE2200", "Advanced Programming Laboratory", "2-2", "cse_lab",
              "safin_ahmmed", "ehsanul_karim"),

    # VERIFY: SH and MAN both appear ("CSE 2201 (SH)" and "CSE2201c(SH/MAN)")
    theory("CSE2201", "Algorithm Analysis and Design", "2-2", 3, "md_sakhawat_hossain"),
    sessional("CSE2202", "Algorithm Analysis and Design Laboratory", "2-2", "cse_lab",
              "subah_nawar", "md_mubtashim_abrar_nihal"),

    sessional("CSE2208", "Numerical Methods Laboratory", "2-2", "cse_lab",
              "md_milon_islam", "lamisa_bintee_mizan_deya"),

    theory("CSE2209", "Theory of Computation", "2-2", 3, "md_nazirulhasan_shawon"),

    # VERIFY: FH and FRH both appear on ECE2213 instances
    theory("ECE2213", "Digital Electronics", "2-2", 3, "md_faisal_hossain", room_kind="theory"),
    sessional("ECE2214", "Digital Electronics Laboratory", "2-2", "ece_lab",
              "mushfiqur_rahman_masuk", "md_minhajul_islam_arnab"),

    # VERIFY: ARJ and HZ both appear on MATH2207 instances (this term's sheet)
    theory("MATH2207", "Complex Variable, Vector Analysis and Statistics", "2-2", 3,
           "arm_jalal_uddin_jamali"),

    # VERIFY: RA and FA both appear on HUM2207 instances. 2 periods/week assumed.
    theory("HUM2207", "Economics and Accounting", "2-2", 2, "sm_rabiul_alam"),

    # ---------------- 2nd Year 1st Term ----------------
    theory("CSE2103", "Microprocessors and Microcontrollers", "2-1", 3, "safin_ahmmed"),
    sessional("CSE2104", "Microprocessors and Microcontrollers Laboratory", "2-1",
              "cse_lab", "muhammad_sheikh_sadi", "md_repon_islam"),

    theory("CSE2105", "Data Structures and Algorithms", "2-1", 3,
           "lamisa_bintee_mizan_deya"),
    sessional("CSE2106", "Data Structures and Algorithms Laboratory", "2-1", "cse_lab",
              "subah_nawar", "lamisa_bintee_mizan_deya"),

    theory("CSE2113", "Computer Architecture", "2-1", 3, "sadia_islam"),
    sessional("CSE2114", "Computer Architecture Laboratory", "2-1", "cse_lab",
              "md_rejvi_kaysir", "akash_biswas"),

    theory("EEE2117", "Analog Electronics", "2-1", 3, "jeesun_patra_papon", room_kind="theory"),
    sessional("EEE2118", "Analog Electronics Laboratory", "2-1", "ece_lab",
              "md_rejvi_kaysir", "akash_biswas"),

    sessional("ME2170", "Computer Aided Design Laboratory", "2-1", "cse_lab",
              "md_mahbubur_rahman", "miir_anjirin_tazrin"),

    theory("MATH2107", "Fourier Analysis and Linear Algebra", "2-1", 3, "sm_arif_hossen"),
]


def main() -> None:
    instance = {
        "meta": {
            "name": "Real CSE department data: 1st Year 1st Term, 2nd Year 1st "
                    "Term, 2nd Year 2nd Term, 3rd Year 2nd Term, 4th Year 1st Term",
            "note": "Built from uploaded routine PDFs/photo. Read the VERIFY "
                    "comments in tools/from_real_routines.py before trusting "
                    "this for anything official.",
        },
        "config": {
            "days": DAYS, "periods": PERIODS, "breaks": BREAKS, "lab_periods": 3,
            "options": {
                "sync_group_labs": True,
                "max_consecutive_periods": 3,
                "weights": {
                    "cohort_gap": 8, "teacher_gap": 4, "last_period": 2,
                    "teacher_daily_overload": 6, "consecutive_overrun": 5,
                    "room_churn": 1,
                },
                "solver": {"max_seconds": 180, "workers": 8, "log": False},
            },
        },
        "rooms": ROOMS,
        "teachers": [{**t, "unavailable": [], "max_periods_per_day": 5} for t in TEACHERS],
        "batches": BATCHES,
        "courses": COURSES,
    }

    out = ROOT / "data" / "kuet_cse_real.json"
    out.write_text(json.dumps(instance, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  {len(TEACHERS)} teachers, {len(ROOMS)} rooms, {len(COURSES)} courses, "
          f"{len(BATCHES)} batches")


if __name__ == "__main__":
    main()
