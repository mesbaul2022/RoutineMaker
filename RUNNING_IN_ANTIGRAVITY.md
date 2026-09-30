# Running this project in Antigravity

Antigravity is built on the same editor as VS Code, so this is the same
workflow as any Python project there — open the folder, open a terminal,
run commands. Nothing Antigravity-specific is required for the parts below;
its AI agent (the **Manager** view) is optional and only useful once you
start *changing* the project, covered at the end.

## 1. Get the project into a folder Antigravity can open

Unzip `routine_maker.zip` wherever you keep projects, e.g.:

```
C:\Users\<you>\Projects\routine_maker        (Windows)
~/Projects/routine_maker                     (Mac/Linux)
```

You should see this inside:

```
routine_maker/
  routine/       the scheduling engine (5 files)
  tools/         data generators and checkers
  data/          input files (your real department data lives here)
  out/           where results get written
  run.py         the command you'll actually run
  README.md      full documentation of how the model works
```

## 2. Open it in Antigravity

- Launch **Antigravity**.
- **File → Open Folder…** and select the `routine_maker` folder you unzipped.
- Give it a few seconds — Antigravity indexes the project. You'll see the
  file tree on the left, same as VS Code.

## 3. Open a terminal inside Antigravity

- Menu: **Terminal → New Terminal** (or the shortcut `` Ctrl+` `` /
  `` Cmd+` `` on Mac).
- A terminal panel opens at the bottom, already sitting **inside the
  `routine_maker` folder** — you don't need to `cd` anywhere.

Everything from here is typed into that terminal panel.

## 4. Check Python is installed

```bash
python3 --version
```

If that prints something like `Python 3.11.4`, you're set — skip to step 5.
If you get "command not found":

- **Windows:** download Python from python.org, run the installer, and
  **tick "Add Python to PATH"** on the first screen. Restart Antigravity
  after installing.
- **Mac:** run `brew install python3` in the terminal (needs
  [Homebrew](https://brew.sh)).
- **Linux:** `sudo apt install python3 python3-pip` (Debian/Ubuntu) or the
  equivalent for your distribution.

Then re-run `python3 --version` to confirm.

## 5. Create a virtual environment (keeps this project's packages separate)

```bash
python3 -m venv .venv
```

Activate it — you'll do this **every time you open a new terminal** in this
project:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (Command Prompt)
.venv\Scripts\activate.bat

# Mac / Linux
source .venv/bin/activate
```

Your terminal prompt should now start with `(.venv)`. That means it worked.

If PowerShell refuses to run the activation script with a "running scripts
is disabled" error, run this once, then retry:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 6. Install the one dependency

```bash
pip install ortools
```

This pulls in Google's OR-Tools, which contains the CP-SAT solver the whole
project is built on. Takes under a minute.

## 7. Run it on your real department data

```bash
python run.py --data data/kuet_cse_real.json --seconds 180
```

What happens:
- Prints your teaching-day grid and a data validation check.
- Solves in two phases — first "is this even possible" (a few seconds),
  then "make it good" (up to 180 seconds, you can raise this).
- Writes two files into `out/`:
  - **`out/routine.csv`** — one row per class, open it in Excel/Sheets.
  - **`out/routine.html`** — open this in a browser; it's the same
    navy/gold tabbed view from before, one tab per batch plus a teacher view.

To open the HTML result: right-click `out/routine.html` in Antigravity's
file tree → **Reveal in File Explorer / Finder** → double-click it, or just
drag the file onto any open browser window.

## 8. Check the result is actually valid

Don't just trust the solver — this re-checks every hard rule from scratch,
independently, straight from the file it wrote:

```bash
python tools/verify_real_csv.py
```

You want to see:
```
all hard constraints satisfied on the delivered real_routine.csv
```

## 9. Rebuild just one batch (e.g. a mid-semester change)

```bash
python run.py --data data/kuet_cse_real.json --seconds 60 --reschedule 3-2
```

Freezes every other batch's placements and only moves 3rd Year 2nd Term.

## 10. Editing the input data

Open `data/kuet_cse_real.json` directly in Antigravity's editor (click it in
the file tree) — it's a normal JSON file, editable like any text file.

For anything beyond a quick tweak, it's easier to edit
**`tools/from_real_routines.py`** instead — it's the plain-Python source
that *generates* the JSON, with comments, and re-running it regenerates
`data/kuet_cse_real.json` from scratch:

```bash
python tools/from_real_routines.py
```

**Before you trust this data for anything official, open
`tools/from_real_routines.py` and read every line marked `# VERIFY`** — it
lists exactly which teacher-course pairings I read with confidence versus
which ones had ambiguous overlapping codes in your scanned routine and I
had to pick one reading. The chat message that came with this project lists
every one of those in plain language too.

## 11. Using Antigravity's AI agent to extend the project

This is the part that makes Antigravity worth using over plain VS Code. In
the **Manager** view (separate from the code editor — look for it in the
left sidebar or the toggle at the top), you can describe a change in plain
English and it will plan and write the code itself, e.g.:

> Add a 4th year 1st term batch to data/kuet_cse_real.json with these
> courses and teachers: [paste your data]

> Add an option to export the routine as a PDF instead of HTML

It will show you a plan before touching anything — read it, then approve.
For a project this size, always review its diff before accepting; the
`tools/verify_real_csv.py` script is exactly what you should re-run after
any agent-made change, since it will tell you immediately if a "fix"
actually broke a hard constraint.

## If something goes wrong

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'ortools'` | You forgot step 6, or the `(.venv)` isn't active — redo step 5's activate command |
| `python: command not found` | Use `python` instead of `python3` (Windows often uses this) |
| Solver prints `INFEASIBLE` | Run `python run.py --data data/kuet_cse_real.json --check` first — it explains exactly which rule can't be satisfied, in plain language |
| Terminal opened in the wrong folder | Close it and open a fresh one — Antigravity opens terminals rooted at whichever folder is open in the editor |
