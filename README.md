# Departmental class routine builder (CP-SAT)

A complete, runnable timetable generator for an engineering department:
multiple batches, two sections per batch, two lab groups per section,
50-minute theory periods, 2.5-hour lab blocks, and configurable breaks.

Built on Google OR-Tools **CP-SAT**. On the bundled 5-batch, 204-meeting
sample instance it finds a legal routine in about 10 seconds and a good one in
two to five minutes.

```
pip install ortools
python tools/make_sample_data.py     # writes data/kuet_cse.json
python run.py --seconds 300          # solve and export
python tools/verify.py               # independent hard-constraint check
```

Outputs land in `out/`: `routine.csv` (flat, one row per meeting) and
`routine.html` (per-section grids, per-teacher grids, print-ready).

---

## Web UI (Database-backed Interface)

A local web application built on **FastAPI**, **SQLAlchemy** (SQLite `routine.db`), and **vanilla HTML/JS** that enables administrators to manage teachers, courses, assignments, and generate routines without editing JSON files or running terminal scripts.

### 1. Starting the Web Server

```bash
# Activate your virtual environment
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/Mac

# Install dependencies (if not already done)
pip install -r requirements.txt

# Start the web app
python run_app.py
```

Alternatively, run uvicorn directly:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Open **http://localhost:8000** in your browser.

### 2. Database Migration & Storage

All department records reside in `routine.db` (SQLite) in the project root. To re-seed or migrate from `data/kuet_cse_real.json`:
```bash
python tools/migrate_json_to_db.py
```
This populates:
- **51 teachers** (CSE faculty plus ECE, EEE, ME, MATH, PHY, and HUM service teachers)
- **21 rooms**
- **5 batches** (1-1, 2-1, 2-2, 3-2, 4-1)
- **47 courses**
- **138 course-teacher assignments**

### 3. What Each Tab Does

- **👨‍🏫 Teachers Tab**:
  - Full CRUD management of departmental and service teachers (name, short code, department, status, max periods/day).
  - Quick search box and department filter with an explicit **"All departments"** option, ensuring service teachers (MATH, PHY, HUM, EEE, ECE, ME) are as visible and selectable as CSE's own.
  - Interactive status toggle (`Active` ↔ `On Leave`).

- **📚 Courses Tab**:
  - Courses organized and grouped by batch.
  - Add / edit course dialog with a dynamic type selector (`Theory` shows *periods per week*; `Sessional` shows *blocks per week*).
  - Configurable room kind specifications (`theory`, `cse_lab`, `ai_lab`, `network_lab`, `ece_lab`, `year1_theory`, `year1_cse_lab`, `phy_lab`, `hum_lab`, `seminar`).

- **📋 Assignments Tab (Core Matrix)**:
  - For each batch and course, lists all sections (A and B) and lab groups (G1 and G2).
  - Teacher dropdowns default to active teachers grouped by department.
  - **"Show on-leave teachers too"** checkbox to filter availability.
  - **On-leave safety warning**: If an on-leave teacher is currently assigned to a course, a prominent warning badge (`⚠️ Warning: ... is marked ON LEAVE!`) is displayed directly rather than being silently hidden.
  - **Instant auto-save**: Any selection in a dropdown saves immediately to the database via `/api/assignments/save-slot`.

- **⚡ Generate Tab**:
  - **"Generate Routine"** button triggers CP-SAT optimization directly from current SQLite contents via `app/db_loader.py`.
  - Built-in data validation surfaces errors and warnings before solving.
  - Live progress indicator during optimization.
  - Displays solver status (`OPTIMAL` / `FEASIBLE`), penalty objective score, solve time, and independent hard-constraint verification faults (verified via `tools/verify.py` with 0 faults).
  - Provides a direct download link for `out/routine.csv` and an embedded interactive viewer for `out/routine.html`.

---

## The one idea the whole thing rests on

Everything runs on a single atomic unit: **one 50-minute period**.

A theory class is 1 period. A 2.5-hour lab is 3 periods. Breaks are *not*
periods — they are gaps between period indices, and they split the day into
**contiguous blocks**. A lab may only start where it fits entirely inside one
block, which is what stops labs being scheduled across lunch.

With your grid the blocks come out as `[P1 P2 P3] [P4 P5 P6] [P7 P8 P9]`, so a
3-period lab has exactly three legal starts per day. That is a very small
domain, and it is why labs are cheap to schedule here.

Change the periods or move a break in `data/*.json` and the blocks recompute
themselves. Nothing else needs touching.

### The time grid as shipped

| Period | Time |
|---|---|
| P1 | 08:00–08:50 |
| P2 | 08:50–09:40 |
| P3 | 09:40–10:30 |
| — | **Snack break 10:30–10:40** |
| P4 | 10:40–11:30 |
| P5 | 11:30–12:20 |
| P6 | 12:20–13:10 |
| — | **Lunch & prayer 13:10–14:30** |
| P7 | 14:30–15:20 |
| P8 | 15:20–16:10 |
| P9 | 16:10–17:00 |

Two notes on the grid you gave me. Your snack break read 10:30–10:50 while P4
started at 10:40, so I shortened the break to 10:30–10:40. And P6 was listed
twice, before and after lunch, so the afternoon is renumbered P7–P9. Both are
one-line edits in `tools/make_sample_data.py` or directly in the JSON.

Teaching days default to Sunday–Thursday. Change `config.days` for your
department's week.

---

## How the model is encoded

For every meeting `e` there is one boolean per legal `(room, start slot)` pair:

```
x[e][(room, start)] = 1   <=>   meeting e runs in `room` starting at `start`
```

Exactly one is true per meeting. A *slot* is a flat index over the whole week
(`day * n_periods + period`), which turns every conflict rule into a
one-dimensional sum — the shape CP-SAT is fastest on.

Coverage indexes (`cover`, `cover_room`) are precomputed once per meeting, so
building all the constraints is linear in the number of variables rather than
quadratic. Without that the Python-side model build becomes the bottleneck
long before the solver does.

### Hard constraints

| | Rule |
|---|---|
| H1 | A student cohort attends one thing at a time. A cohort is `(batch, section, group)`; a theory class occupies **every** group of its section |
| H2 | A teacher is in one place at a time — your requirement 6 |
| H3 | A room hosts one class at a time |
| H4 | The weekly meetings of one theory course fall on **distinct days** |
| H5 | Room kind matches the course, and capacity covers the head count |
| H6 | A lab occupies 3 contiguous periods inside one break-free block |
| H7 | Teachers are never scheduled into their blocked slots |
| H8 | One teacher holds at most **one theory course** (checked at load time, since it is a property of the assignment, not the timetable) |
| H9 | Optional: both groups of a section take their lab simultaneously |

H4 also breaks symmetry: sibling meetings of a course are forced into
increasing slot order. Without that the solver wastes its budget exploring
`k!` identical permutations of the same timetable.

**H9 auto-adapts to room supply.** Syncing two groups needs two simultaneous
rooms of that lab's kind. If a room kind only has one physical room (a
specialised AI lab, say), the scheduler detects that automatically and
staggers that course's groups across different times instead of forcing an
impossible simultaneous booking — exactly what a department does by hand
when a specialised room is scarce. `console_summary()` lists which courses
got auto-staggered and why, so it's never a silent decision.

**H9 is worth a moment beyond that.** With `sync_group_labs: true`, G1 and G2 of a section
do their lab in the same three periods, in different rooms with different
instructors. The section's timetable stays uniform and no group sits idle
while the other is in the lab. Set it to `false` if your department genuinely
staggers them — the cohort model handles both, but staggering roughly doubles
the search space and leaves half-sections with dead periods.

### Soft constraints (the objective)

All weights live in `config.options.weights`. Set a weight to `0` and its
variables are not built at all, so switching something off costs nothing.

| Weight | What it penalises | Default |
|---|---|---|
| `cohort_gap` | free period sandwiched between two classes, for students | 8 |
| `teacher_gap` | same, for teachers | 4 |
| `last_period` | anything scheduled in the final period of a day | 2 |
| `teacher_daily_overload` | periods beyond a teacher's `max_periods_per_day` | 6 |
| `consecutive_overrun` | more than `max_consecutive_periods` back to back | 5 |
| `room_churn` | a section using more theory rooms than it needs | 1 |

Gaps and runs are counted **within** the day but never across a break —
teaching either side of lunch is not back-to-back. With the shipped grid,
blocks are exactly 3 periods and `max_consecutive_periods` is 3, so
`consecutive_overrun` can never fire. It will start mattering the moment you
lengthen a block.

These weights encode a policy choice, not a fact. Deciding that a student's
idle hour is worth twice a teacher's is exactly the sort of thing to argue
explicitly in a thesis rather than leave buried in a config file.

### Two-phase solving

`solve_routine()` runs feasibility first with every soft weight zeroed, then
restores the objective and warm-starts from that solution. Finding *a* legal
routine is easy; finding a good one is not, and this way the optimiser spends
its whole budget improving rather than searching for a first solution. You
always come away with a usable routine even if the clock runs out.

---

## Rebuilding one batch

```bash
python run.py --reschedule 3-1
```

Solves the whole department, then frees only 3rd year's meetings and re-solves
with everything else pinned. On the sample instance that sub-problem is proven
**optimal in about 6 seconds**, because 160 of the 204 meetings are frozen.

`reschedule_batch()` in `routine/scheduler.py` is the general hook. Freeze any
subset you like — a teacher going on leave, a lab room closing, an extra
section opening mid-semester.

---

## Files

```
routine/timegrid.py   periods, breaks, contiguous blocks, slot arithmetic
routine/models.py     teachers, rooms, batches, courses, meetings, cohorts
routine/loader.py     JSON in, plus pre-solve validation
routine/scheduler.py  the CP-SAT model
routine/report.py     console summary, CSV, printable HTML
tools/make_sample_data.py  generates a sample department instance
tools/verify.py       independent hard-constraint checker
run.py                command line
```

### Put your own data in

`data/kuet_cse.json` is synthetic. Replace it with real records in the same
shape:

```json
{"code": "CSE 3101", "title": "Database Systems", "batch": "3-1",
 "kind": "theory", "periods_per_week": 3,
 "teachers": {"A": "T05", "B": "T05"}}

{"code": "CSE 3102", "title": "Database Systems Sessional", "batch": "3-1",
 "kind": "sessional", "room_kind": "software", "blocks_per_week": 1,
 "teachers": {"A": {"G1": "T05", "G2": "T12"},
              "B": {"G1": "T19", "G2": "T26"}}}
```

Teacher availability:

```json
{"id": "T05", "name": "Dr. Sadi", "max_periods_per_day": 5,
 "unavailable": [{"day": "Tuesday", "periods": ["P1", "P2", "P3"]},
                 {"day": "Thursday", "periods": "all"}]}
```

Run `python run.py --check` first. The validator catches the usual causes of a
mysterious `INFEASIBLE` — a teacher holding two theory courses, a lab with no
room of the right kind, a cohort booked for more periods than the week has,
room demand exceeding supply — and reports them in plain language instead of
leaving you to guess.

---

## If it will not solve

Work down this list:

1. `python run.py --check`. Fix every error before anything else.
2. Give it longer: `--seconds 600`.
3. Loosen teacher unavailability. Blocked slots are the most common cause of
   genuine infeasibility, and one teacher blocking an entire day can sink the
   whole instance.
4. Add rooms of whichever kind the validator flags as heavily utilised. Lab
   rooms bite first, because labs can only start at three points per day.
5. Turn off `sync_group_labs` if lab room supply is the binding constraint.
6. Relax H4 (distinct days) for courses meeting more times per week than you
   have teaching days.

`--seconds` controls the total budget; a quarter of it goes to phase 1.

---

## Where the research goes from here

The system as it stands is engineering, not yet a contribution. Four
extension points, each already scaffolded in the code:

**Minimal-perturbation rescheduling.** `reschedule_batch()` currently lets the
freed batch move anywhere. Add a penalty on *movement* — a term counting how
many meetings changed slot or room against the published routine — and you can
trade timetable quality against stability and plot the Pareto front. Then
inject real disruptions (teacher leave, room closure, added section) and
measure the cost of each. This is the strongest and least crowded angle.

**A benchmark instance family.** `tools/make_sample_data.py` is already a
generator. Parameterise it over batch count, room supply, and availability
density, publish anonymised real instances from your department alongside the
synthetic ones, and ship `tools/verify.py` as the validator. The nested
batch → section → group hierarchy with mixed 1-period and 3-period events is
not present in the ITC benchmarks, so this is a genuine gap.

**Fairness objectives.** `teacher_daily_overload` minimises aggregate excess,
which happily dumps every 8 AM slot on one junior lecturer. Replace it with a
dispersion measure — Jain's index or a Gini coefficient over per-teacher gaps,
early and late slots, and consecutive load — and study the fairness/efficiency
trade-off.

**Solver comparison.** Set `two_phase=False` and you have a clean single-model
baseline. Implement a genetic algorithm or simulated annealing against the
same instances and the same verifier, and report solution quality against wall
time. Modest as contributions go, but it is honest empirical work and it makes
the CP-SAT choice defensible rather than asserted.

One warning that applies to all four: **validate against the routine your
department already uses by hand.** If the solver cannot match what the head of
department produces with a pencil, no amount of algorithmic sophistication
will rescue the paper.
