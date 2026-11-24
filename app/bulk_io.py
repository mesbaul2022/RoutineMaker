"""
Bulk Import and Export Engine for Routine Maker.
Supports Teachers, Courses, Rooms, and All-in-One Multi-sheet Excel / CSV files.
"""

import io
import csv
import re
from typing import Optional, List, Dict, Any, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.db import (
    Teacher as TeacherModel,
    Course as CourseModel,
    Room as RoomModel,
    Batch as BatchModel,
    Assignment as AssignmentModel,
)

# Standard styling for generated Excel files
HEADER_FILL = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
REQ_HEADER_FILL = PatternFill(start_color="1D4ED8", end_color="1D4ED8", fill_type="solid")
SAMPLE_ROW_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
INSTRUCTION_HEADER_FILL = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin", color="CBD5E1"),
    right=Side(style="thin", color="CBD5E1"),
    top=Side(style="thin", color="CBD5E1"),
    bottom=Side(style="thin", color="CBD5E1"),
)

ROOM_KIND_NORMALIZATION = {
    "year1_theory": "theory",
    "seminar": "seminar_501",
    "seminar_room": "seminar_501",
    "ai_lab": "cse_lab",
    "network_lab": "cse_lab",
    "year1_cse_lab": "cse_lab",
    "hardware_lab": "hardware_lab_107",
    "none": "no_room",
    "no room": "no_room",
    "": "no_room",
}

VALID_DEPTS = ["CSE", "ECE", "EEE", "ME", "MATH", "PHY", "HUM", "CHEM"]
VALID_BATCHES = ["1-1", "1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]
VALID_ROOM_KINDS = [
    "theory",
    "cse_lab",
    "hardware_lab_107",
    "hardware_lab_108",
    "seminar_501",
    "chem_lab",
    "phy_lab",
    "hum_lab",
    "ece_lab",
    "eee_lab",
    "mecha_lab",
    "no_room",
]

def slugify(text: str) -> str:
    """Generate a clean slug for teacher/room IDs."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return s.strip("_")


# =============================================================================
# 1. FIELD SCHEMAS AND INSTRUCTIONS
# =============================================================================

TEACHER_COLUMNS = [
    {
        "key": "full_name",
        "header": "Full Name *",
        "desc": "Official teacher name (e.g. 'Dr. M. M. A. Hashem'). Required.",
        "sample": "Dr. M. M. A. Hashem",
    },
    {
        "key": "short_code",
        "header": "Short Code *",
        "desc": "2-4 letter uppercase teacher short code (e.g. 'MMA', 'AAW', 'SS'). Required and unique.",
        "sample": "MMA",
    },
    {
        "key": "department",
        "header": "Department",
        "desc": "Academic department: CSE, ECE, EEE, ME, MATH, PHY, HUM, CHEM. Default: CSE.",
        "sample": "CSE",
    },
    {
        "key": "status",
        "header": "Status",
        "desc": "Teacher status: 'Active' or 'On Leave'. Default: Active.",
        "sample": "Active",
    },
    {
        "key": "max_periods_per_day",
        "header": "Max Periods / Day",
        "desc": "Daily maximum class periods (1 to 9). Institutional default: 5 (or 8 for senior teachers).",
        "sample": "5",
    },
]

COURSE_COLUMNS = [
    {
        "key": "code",
        "header": "Course Code *",
        "desc": "Official course code (e.g. 'CSE1101', 'CSE1204', 'CHEM1207'). Required and unique.",
        "sample": "CSE1203",
    },
    {
        "key": "title",
        "header": "Course Title *",
        "desc": "Full descriptive course title. Required.",
        "sample": "Digital Logic Design",
    },
    {
        "key": "batch",
        "header": "Batch / Term *",
        "desc": "Academic term code: 1-1, 1-2, 2-1, 2-2, 3-1, 3-2, 4-1, 4-2. Required.",
        "sample": "1-2",
    },
    {
        "key": "type",
        "header": "Course Type *",
        "desc": "'Theory' or 'Sessional'. Required.",
        "sample": "Theory",
    },
    {
        "key": "credit",
        "header": "Credit",
        "desc": "Course credit: 3.0 (Theory), 1.5 (Full weekly lab), 0.75 (Bi-weekly lab). Default: 3.0/1.5.",
        "sample": "3.0",
    },
    {
        "key": "room_kind",
        "header": "Required Room Kind",
        "desc": "theory, cse_lab, hardware_lab_107, hardware_lab_108, seminar_501, chem_lab, phy_lab, hum_lab, ece_lab, eee_lab, mecha_lab, no_room.",
        "sample": "theory",
    },
    {
        "key": "allowed_rooms",
        "header": "Allowed Specific Rooms",
        "desc": "Comma-separated specific room codes/IDs (e.g. 'CSE-101, CSE-102') or blank to use category default.",
        "sample": "CSE-101, CSE-102",
    },
    {
        "key": "category",
        "header": "Course Category",
        "desc": "Core Course, Optional II, Optional III. Default: Core Course.",
        "sample": "Core Course",
    },
    {
        "key": "periods_per_week",
        "header": "Periods Per Week",
        "desc": "Weekly lectures for Theory courses (typically 3 or 2). Leave blank for Sessional.",
        "sample": "3",
    },
    {
        "key": "teacher1_short",
        "header": "Teacher 1 (Short Code)",
        "desc": "Short code of 1st assigned teacher (e.g. 'IH', 'MMA', 'AAW'). Optional.",
        "sample": "IH",
    },
    {
        "key": "teacher2_short",
        "header": "Teacher 2 (Short Code)",
        "desc": "Short code of 2nd assigned co-teacher (e.g. 'BS', 'DD', 'KSA'). Optional.",
        "sample": "BS",
    },
]

ROOM_COLUMNS = [
    {
        "key": "room_code",
        "header": "Room Code *",
        "desc": "Unique room code / ID (e.g. 'CSE-101', 'CSE-103', 'CHEM-LAB'). Required.",
        "sample": "CSE-101",
    },
    {
        "key": "name",
        "header": "Room Name *",
        "desc": "Full display room title (e.g. 'CSE Room 101', 'CSE Lab 103'). Required.",
        "sample": "CSE Room 101",
    },
    {
        "key": "category",
        "header": "Category",
        "desc": "Theory Classrooms, Departmental Labs, Non-Departmental Labs. Default: auto-detected.",
        "sample": "Theory Classrooms",
    },
    {
        "key": "kind",
        "header": "Room Kind *",
        "desc": "theory, cse_lab, hardware_lab_107, hardware_lab_108, seminar_501, chem_lab, phy_lab, hum_lab, ece_lab, eee_lab, mecha_lab, no_room. Required.",
        "sample": "theory",
    },
    {
        "key": "capacity",
        "header": "Capacity",
        "desc": "Seating capacity: typically 70 for theory classrooms, 35 for labs. Default: 70/35.",
        "sample": "70",
    },
]


# =============================================================================
# 2. TEMPLATE GENERATION
# =============================================================================

def generate_csv_template(entity: str) -> bytes:
    """Generate a clean CSV template with header and sample rows."""
    output = io.StringIO()
    writer = csv.writer(output)

    if entity == "teachers":
        headers = [c["header"] for c in TEACHER_COLUMNS]
        writer.writerow(headers)
        writer.writerow(["Dr. M. M. A. Hashem", "MMA", "CSE", "Active", 8])
        writer.writerow(["Dr. Md. Abdul Awal", "AAW", "CSE", "Active", 8])
        writer.writerow(["Ms. Dola Das", "DD", "CSE", "Active", 5])
        writer.writerow(["Dr. Md. Dulal Hossain", "DH", "MATH", "Active", 5])
        writer.writerow(["Mr. Md. Sohag Hossain", "SH", "PHY", "Active", 5])
    elif entity == "courses":
        headers = [c["header"] for c in COURSE_COLUMNS]
        writer.writerow(headers)
        writer.writerow(["CSE1203", "Digital Logic Design", "1-2", "Theory", 3.0, "theory", "Core Course", 3, "IH", "BS"])
        writer.writerow(["CSE1204", "Digital Logic Design Laboratory", "1-2", "Sessional", 1.5, "hardware_lab_108", "Core Course", "", "IH", "BS"])
        writer.writerow(["CHEM1207", "Chemistry", "1-2", "Theory", 3.0, "theory", "Core Course", 3, "MHM", "MJ"])
        writer.writerow(["CHEM1208", "Chemistry Laboratory", "1-2", "Sessional", 0.75, "chem_lab", "Core Course", "", "AM", "RA"])
        writer.writerow(["CSE3200", "System Development Project", "3-2", "Sessional", 1.5, "no_room", "Core Course", "", "", ""])
    elif entity == "rooms":
        headers = [c["header"] for c in ROOM_COLUMNS]
        writer.writerow(headers)
        writer.writerow(["CSE-101", "CSE Room 101", "Theory Classrooms", "theory", 70])
        writer.writerow(["CSE-102", "CSE Room 102", "Theory Classrooms", "theory", 70])
        writer.writerow(["CSE-103", "CSE Lab 103", "Departmental Labs", "cse_lab", 35])
        writer.writerow(["CSE-107", "CSE Lab 107", "Departmental Labs", "hardware_lab_107", 35])
        writer.writerow(["CHEM-LAB", "Chemistry Lab", "Non-Departmental Labs", "chem_lab", 35])
        writer.writerow(["PHY-LAB", "Physics Lab", "Non-Departmental Labs", "phy_lab", 35])
    else:
        raise ValueError(f"Unknown entity '{entity}'")

    return output.getvalue().encode("utf-8-sig")


def _style_excel_sheet(ws, headers: List[str], sample_rows: List[List[Any]], col_meta: List[Dict[str, Any]]):
    """Apply styling, auto-column widths, and header decoration to an Excel worksheet."""
    # Write header
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = REQ_HEADER_FILL if "*" in headers[col_idx - 1] else HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER

    ws.row_dimensions[1].height = 28

    # Write sample rows
    for r_idx, row in enumerate(sample_rows, start=2):
        ws.append(row)
        ws.row_dimensions[r_idx].height = 20
        for col_idx in range(1, len(row) + 1):
            cell = ws.cell(row=r_idx, column=col_idx)
            cell.fill = SAMPLE_ROW_FILL
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center")

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)


def _add_instruction_sheet(wb: openpyxl.Workbook, title: str, col_meta: List[Dict[str, Any]], extra_notes: List[str] = None):
    """Add a documentation sheet explaining the columns and acceptable formats."""
    ws = wb.create_sheet(title=f"Instructions ({title})")
    ws.views.sheetView[0].showGridLines = True

    # Title Banner
    ws.merge_cells("A1:D1")
    t_cell = ws.cell(row=1, column=1, value=f"Data Input Format & Field Specification: {title}")
    t_cell.font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    ws.row_dimensions[1].height = 30

    # Header
    doc_headers = ["Column Header", "Requirement", "Allowed Values / Format", "Description & Usage Instructions"]
    ws.append(doc_headers)
    for col_idx in range(1, 5):
        cell = ws.cell(row=2, column=col_idx)
        cell.fill = INSTRUCTION_HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER
    ws.row_dimensions[2].height = 24

    for r_idx, item in enumerate(col_meta, start=3):
        is_req = "Required" if "*" in item["header"] else "Optional"
        allowed = item.get("allowed", "Any valid text / number")
        row = [item["header"], is_req, allowed, item["desc"]]
        ws.append(row)
        ws.row_dimensions[r_idx].height = 22
        for col_idx in range(1, 5):
            cell = ws.cell(row=r_idx, column=col_idx)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    if extra_notes:
        curr_row = len(col_meta) + 4
        ws.cell(row=curr_row, column=1, value="Important Notes:").font = Font(bold=True, size=11, color="0F172A")
        curr_row += 1
        for note in extra_notes:
            ws.cell(row=curr_row, column=1, value=f"• {note}").font = Font(size=10, color="475569")
            curr_row += 1

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 28
    ws.column_dimensions["D"].width = 55


def generate_excel_template(entity: str) -> bytes:
    """Generate a stylized Excel workbook (.xlsx) with template and documentation sheets."""
    wb = openpyxl.Workbook()
    ws = wb.active

    if entity == "teachers":
        ws.title = "Teachers"
        headers = [c["header"] for c in TEACHER_COLUMNS]
        sample_rows = [
            ["Dr. M. M. A. Hashem", "MMA", "CSE", "Active", 8],
            ["Dr. Md. Abdul Awal", "AAW", "CSE", "Active", 8],
            ["Ms. Dola Das", "DD", "CSE", "Active", 5],
            ["Dr. Md. Dulal Hossain", "DH", "MATH", "Active", 5],
            ["Mr. Md. Sohag Hossain", "SH", "PHY", "Active", 5],
        ]
        _style_excel_sheet(ws, headers, sample_rows, TEACHER_COLUMNS)
        _add_instruction_sheet(
            wb,
            "Teachers",
            [
                {**c, "allowed": "CSE, ECE, EEE, ME, MATH, PHY, HUM, CHEM" if c["key"] == "department" else ("Active, On Leave" if c["key"] == "status" else ("1 to 9" if c["key"] == "max_periods_per_day" else "Unique code"))}
                for c in TEACHER_COLUMNS
            ],
            [
                "Short Code must be unique for each teacher. It is displayed on the printed master routine and batch schedules.",
                "If an existing Short Code is found, the system will update that teacher's profile (upsert).",
                "Teachers marked 'On Leave' will have all timetable slots automatically blocked.",
            ],
        )

    elif entity == "courses":
        ws.title = "Courses"
        headers = [c["header"] for c in COURSE_COLUMNS]
        sample_rows = [
            ["CSE1203", "Digital Logic Design", "1-2", "Theory", 3.0, "theory", "Core Course", 3, "IH", "BS"],
            ["CSE1204", "Digital Logic Design Laboratory", "1-2", "Sessional", 1.5, "hardware_lab_108", "Core Course", "", "IH", "BS"],
            ["CHEM1207", "Chemistry", "1-2", "Theory", 3.0, "theory", "Core Course", 3, "MHM", "MJ"],
            ["CHEM1208", "Chemistry Laboratory", "1-2", "Sessional", 0.75, "chem_lab", "Core Course", "", "AM", "RA"],
            ["CSE3200", "System Development Project", "3-2", "Sessional", 1.5, "no_room", "Core Course", "", "", ""],
        ]
        _style_excel_sheet(ws, headers, sample_rows, COURSE_COLUMNS)
        _add_instruction_sheet(
            wb,
            "Courses",
            [
                {**c, "allowed": "1-1, 1-2, 2-1, 2-2, 3-1, 3-2, 4-1, 4-2" if c["key"] == "batch" else ("Theory, Sessional" if c["key"] == "type" else ("theory, cse_lab, hardware_lab_107, hardware_lab_108, seminar_501, chem_lab, phy_lab, hum_lab, ece_lab, eee_lab, mecha_lab, no_room" if c["key"] == "room_kind" else ("3.0, 1.5, 0.75" if c["key"] == "credit" else "Teacher Short Code")))}
                for c in COURSE_COLUMNS
            ],
            [
                "Batch must match one of the 8 academic terms (1-1 through 4-2).",
                "Teacher 1 and Teacher 2 can be given by teacher Short Code (e.g. 'MMA', 'DD') or full name.",
                "For Theory courses: 'Periods Per Week' is typically 3 (or 2).",
                "For Sessional courses: Leave 'Periods Per Week' empty; the system automatically allocates contiguous 3-period lab sessions.",
                "For Project / Thesis courses (e.g. CSE 3200, CSE 4000): Set 'Required Room Kind' to 'no_room'.",
            ],
        )

    elif entity == "rooms":
        ws.title = "Rooms"
        headers = [c["header"] for c in ROOM_COLUMNS]
        sample_rows = [
            ["CSE-101", "CSE Room 101", "Theory Classrooms", "theory", 70],
            ["CSE-102", "CSE Room 102", "Theory Classrooms", "theory", 70],
            ["CSE-103", "CSE Lab 103", "Departmental Labs", "cse_lab", 35],
            ["CSE-107", "CSE Lab 107", "Departmental Labs", "hardware_lab_107", 35],
            ["CHEM-LAB", "Chemistry Lab", "Non-Departmental Labs", "chem_lab", 35],
            ["PHY-LAB", "Physics Lab", "Non-Departmental Labs", "phy_lab", 35],
        ]
        _style_excel_sheet(ws, headers, sample_rows, ROOM_COLUMNS)
        _add_instruction_sheet(
            wb,
            "Rooms",
            [
                {**c, "allowed": "theory, cse_lab, hardware_lab_107, hardware_lab_108, seminar_501, chem_lab, phy_lab, hum_lab, ece_lab, eee_lab, mecha_lab, no_room" if c["key"] == "kind" else "Any positive number"}
                for c in ROOM_COLUMNS
            ],
            [
                "Room Code must be unique (e.g. 'CSE-101', 'CSE-103', 'CHEM-LAB').",
                "Room Kind connects the physical room to course room requirements.",
                "Standard lecture homerooms should have Room Kind set to 'theory' with capacity 70.",
                "Computer labs should have Room Kind set to 'cse_lab' with capacity 35.",
            ],
        )

    elif entity == "all":
        # All-in-one workbook with Teachers, Courses, and Rooms
        ws.title = "Overview & Guide"
        ws.views.sheetView[0].showGridLines = True
        ws.merge_cells("A1:E1")
        ws.cell(row=1, column=1, value="KUET CSE Routine Maker - Department Bulk Input Master Workbook").font = Font(name="Calibri", size=15, bold=True, color="1E3A8A")
        ws.row_dimensions[1].height = 32

        intro_lines = [
            "Welcome to the Routine Maker Bulk Data Management Workbook!",
            "",
            "This workbook contains 3 data sheets where you can define the department's scheduling resources:",
            "  1. 'Teachers' sheet: Faculty members, short codes, departments, statuses, and maximum daily load.",
            "  2. 'Courses' sheet: Theory and Laboratory courses across all 8 terms (1-1 to 4-2) with assigned teachers.",
            "  3. 'Rooms' sheet: Classrooms and laboratories for departmental and non-departmental sessions.",
            "",
            "Instructions:",
            "  • Fill out or update the data in the respective sheets maintaining the column headers.",
            "  • Save this file and upload it via the 'Import Master Workbook' option in the web interface.",
            "  • The system will automatically validate and import all resources in the correct dependency order.",
        ]
        for idx, line in enumerate(intro_lines, start=3):
            cell = ws.cell(row=idx, column=1, value=line)
            cell.font = Font(name="Calibri", size=11, bold=(idx == 3 or "sheet:" in line), color="0F172A")
            ws.row_dimensions[idx].height = 20

        # Add Teachers sheet
        ws_t = wb.create_sheet(title="Teachers")
        _style_excel_sheet(ws_t, [c["header"] for c in TEACHER_COLUMNS], [
            ["Dr. M. M. A. Hashem", "MMA", "CSE", "Active", 8],
            ["Dr. Md. Abdul Awal", "AAW", "CSE", "Active", 8],
            ["Ms. Dola Das", "DD", "CSE", "Active", 5],
            ["Dr. Md. Dulal Hossain", "DH", "MATH", "Active", 5],
            ["Mr. Md. Sohag Hossain", "SH", "PHY", "Active", 5],
        ], TEACHER_COLUMNS)

        # Add Courses sheet
        ws_c = wb.create_sheet(title="Courses")
        _style_excel_sheet(ws_c, [c["header"] for c in COURSE_COLUMNS], [
            ["CSE1203", "Digital Logic Design", "1-2", "Theory", 3.0, "theory", "Core Course", 3, "IH", "BS"],
            ["CSE1204", "Digital Logic Design Laboratory", "1-2", "Sessional", 1.5, "hardware_lab_108", "Core Course", "", "IH", "BS"],
            ["CHEM1207", "Chemistry", "1-2", "Theory", 3.0, "theory", "Core Course", 3, "MHM", "MJ"],
            ["CHEM1208", "Chemistry Laboratory", "1-2", "Sessional", 0.75, "chem_lab", "Core Course", "", "AM", "RA"],
            ["CSE3200", "System Development Project", "3-2", "Sessional", 1.5, "no_room", "Core Course", "", "", ""],
        ], COURSE_COLUMNS)

        # Add Rooms sheet
        ws_r = wb.create_sheet(title="Rooms")
        _style_excel_sheet(ws_r, [c["header"] for c in ROOM_COLUMNS], [
            ["CSE-101", "CSE Room 101", "Theory Classrooms", "theory", 70],
            ["CSE-102", "CSE Room 102", "Theory Classrooms", "theory", 70],
            ["CSE-103", "CSE Lab 103", "Departmental Labs", "cse_lab", 35],
            ["CSE-107", "CSE Lab 107", "Departmental Labs", "hardware_lab_107", 35],
            ["CHEM-LAB", "Chemistry Lab", "Non-Departmental Labs", "chem_lab", 35],
            ["PHY-LAB", "Physics Lab", "Non-Departmental Labs", "phy_lab", 35],
        ], ROOM_COLUMNS)

    else:
        raise ValueError(f"Unknown entity '{entity}'")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =============================================================================
# 3. LIVE DATA EXPORT
# =============================================================================

def export_teachers(db: Session, fmt: str = "xlsx") -> Tuple[bytes, str, str]:
    """Export all teachers in database to CSV or Excel."""
    teachers = db.query(TeacherModel).order_by(TeacherModel.department, TeacherModel.short_code).all()

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([c["header"] for c in TEACHER_COLUMNS])
        for t in teachers:
            writer.writerow([t.full_name, t.short_code, t.department, t.status.replace("_", " ").title(), t.max_periods_per_day])
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "teachers_export.csv"

    # Excel format
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Teachers"
    headers = [c["header"] for c in TEACHER_COLUMNS]
    rows = [
        [t.full_name, t.short_code, t.department, t.status.replace("_", " ").title(), t.max_periods_per_day]
        for t in teachers
    ]
    _style_excel_sheet(ws, headers, rows, TEACHER_COLUMNS)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "teachers_export.xlsx"


def export_courses(db: Session, fmt: str = "xlsx", batch_id: Optional[str] = None) -> Tuple[bytes, str, str]:
    """Export courses across all terms (or a specific term) to CSV or Excel."""
    query = db.query(CourseModel)
    if batch_id:
        query = query.filter_by(batch_id=batch_id)
    courses = query.order_by(CourseModel.batch_id, CourseModel.id).all()

    teacher_map = {t.id: t.short_code for t in db.query(TeacherModel).all()}

    rows = []
    for c in courses:
        t1_short = teacher_map.get(c.teacher1_id, "")
        t2_short = teacher_map.get(c.teacher2_id, "")
        cat_disp = c.category.replace("_", " ").title() if c.category else "Core Course"
        rows.append([
            c.id,
            c.title,
            c.batch_id,
            c.kind.title(),
            c.credit,
            c.room_kind,
            c.allowed_rooms or "",
            cat_disp,
            c.periods_per_week if c.kind == "theory" else "",
            t1_short,
            t2_short,
        ])

    filename_suffix = f"_{batch_id}" if batch_id else "_all_terms"

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([col["header"] for col in COURSE_COLUMNS])
        for r in rows:
            writer.writerow(r)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", f"courses{filename_suffix}.csv"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Courses"
    _style_excel_sheet(ws, [col["header"] for col in COURSE_COLUMNS], rows, COURSE_COLUMNS)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"courses{filename_suffix}.xlsx"


def export_rooms(db: Session, fmt: str = "xlsx") -> Tuple[bytes, str, str]:
    """Export rooms to CSV or Excel."""
    rooms = db.query(RoomModel).order_by(RoomModel.kind, RoomModel.id).all()

    rows = []
    for r in rooms:
        if r.kind == "theory":
            cat = "Theory Classrooms"
        elif "lab" in r.kind:
            cat = "Departmental Labs" if "cse" in r.kind or "hardware" in r.kind else "Non-Departmental Labs"
        else:
            cat = "General Facilities"
        rows.append([r.id, r.name, cat, r.kind, r.capacity])

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([col["header"] for col in ROOM_COLUMNS])
        for row in rows:
            writer.writerow(row)
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "rooms_export.csv"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rooms"
    _style_excel_sheet(ws, [col["header"] for col in ROOM_COLUMNS], rows, ROOM_COLUMNS)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "rooms_export.xlsx"


def export_all_in_one(db: Session) -> Tuple[bytes, str, str]:
    """Export Teachers, Courses, and Rooms in one cohesive Excel workbook."""
    wb = openpyxl.Workbook()

    # Sheet 1: Teachers
    ws_t = wb.active
    ws_t.title = "Teachers"
    teachers = db.query(TeacherModel).order_by(TeacherModel.department, TeacherModel.short_code).all()
    t_rows = [
        [t.full_name, t.short_code, t.department, t.status.replace("_", " ").title(), t.max_periods_per_day]
        for t in teachers
    ]
    _style_excel_sheet(ws_t, [c["header"] for c in TEACHER_COLUMNS], t_rows, TEACHER_COLUMNS)

    # Sheet 2: Courses
    ws_c = wb.create_sheet(title="Courses")
    courses = db.query(CourseModel).order_by(CourseModel.batch_id, CourseModel.id).all()
    teacher_map = {t.id: t.short_code for t in db.query(TeacherModel).all()}
    c_rows = []
    for c in courses:
        t1_short = teacher_map.get(c.teacher1_id, "")
        t2_short = teacher_map.get(c.teacher2_id, "")
        cat_disp = c.category.replace("_", " ").title() if c.category else "Core Course"
        c_rows.append([
            c.id,
            c.title,
            c.batch_id,
            c.kind.title(),
            c.credit,
            c.room_kind,
            c.allowed_rooms or "",
            cat_disp,
            c.periods_per_week if c.kind == "theory" else "",
            t1_short,
            t2_short,
        ])
    _style_excel_sheet(ws_c, [col["header"] for col in COURSE_COLUMNS], c_rows, COURSE_COLUMNS)

    # Sheet 3: Rooms
    ws_r = wb.create_sheet(title="Rooms")
    rooms = db.query(RoomModel).order_by(RoomModel.kind, RoomModel.id).all()
    r_rows = []
    for r in rooms:
        if r.kind == "theory":
            cat = "Theory Classrooms"
        elif "lab" in r.kind:
            cat = "Departmental Labs" if "cse" in r.kind or "hardware" in r.kind else "Non-Departmental Labs"
        else:
            cat = "General Facilities"
        r_rows.append([r.id, r.name, cat, r.kind, r.capacity])
    _style_excel_sheet(ws_r, [col["header"] for col in ROOM_COLUMNS], r_rows, ROOM_COLUMNS)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "routine_master_all_data.xlsx"


# =============================================================================
# 4. FILE PARSING HELPER
# =============================================================================

def _normalize_key(k: str) -> str:
    """Normalize column header keys for flexible matching."""
    s = k.lower().strip()
    s = re.sub(r"[\*\(\)\/\-]", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s


def parse_raw_rows(file_bytes: bytes, filename: str, target_sheet: Optional[str] = None) -> List[Dict[str, Any]]:
    """Parse CSV or Excel file bytes into a list of normalized key/value dicts."""
    lower_fn = filename.lower()
    rows = []

    if lower_fn.endswith(".csv") or lower_fn.endswith(".txt"):
        # Try UTF-8-sig first, fallback to latin-1
        text = ""
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            normalized_row = {_normalize_key(k): str(v).strip() for k, v in r.items() if k}
            if any(normalized_row.values()):
                rows.append(normalized_row)

    elif lower_fn.endswith(".xlsx") or lower_fn.endswith(".xlsm"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet_names = wb.sheetnames

        # Pick sheet: target_sheet or first sheet that isn't instructions
        ws = None
        if target_sheet and target_sheet in sheet_names:
            ws = wb[target_sheet]
        else:
            for sname in sheet_names:
                if "instruction" not in sname.lower() and "guide" not in sname.lower():
                    ws = wb[sname]
                    break
            if ws is None:
                ws = wb.active

        all_values = list(ws.iter_rows(values_only=True))
        if not all_values:
            return []

        # First row is headers
        raw_headers = all_values[0]
        headers = [_normalize_key(str(h or "")) for h in raw_headers]

        for r_values in all_values[1:]:
            row_dict = {}
            has_val = False
            for h, v in zip(headers, r_values):
                if not h:
                    continue
                val_str = str(v).strip() if v is not None else ""
                row_dict[h] = val_str
                if val_str:
                    has_val = True
            if has_val:
                rows.append(row_dict)

    else:
        raise ValueError(f"Unsupported file extension in '{filename}'. Please provide an Excel (.xlsx) or CSV (.csv) file.")

    return rows


# =============================================================================
# 5. BULK IMPORTERS
# =============================================================================

def import_teachers_data(file_bytes: bytes, filename: str, db: Session) -> Dict[str, Any]:
    """Import teachers from CSV or Excel."""
    rows = parse_raw_rows(file_bytes, filename, target_sheet="Teachers")
    if not rows:
        return {"status": "error", "message": "No data found in uploaded file."}

    created = 0
    updated = 0
    errors = []

    # Map existing teachers by ID and short_code (case-insensitive)
    existing_by_id = {t.id.lower(): t for t in db.query(TeacherModel).all()}
    existing_by_code = {t.short_code.upper(): t for t in db.query(TeacherModel).all()}

    for row_idx, r in enumerate(rows, start=2):
        # Extract full_name
        full_name = r.get("full_name") or r.get("name") or r.get("teacher_name") or ""
        # Extract short_code
        short_code = (r.get("short_code") or r.get("short") or r.get("code") or "").upper().strip()

        if not full_name:
            errors.append(f"Row {row_idx}: Missing required teacher Full Name.")
            continue
        if not short_code:
            errors.append(f"Row {row_idx}: Missing required Short Code for '{full_name}'.")
            continue

        dept = (r.get("department") or r.get("dept") or "CSE").upper().strip()
        status_val = (r.get("status") or "active").lower().strip()
        status = "on_leave" if "leave" in status_val else "active"

        max_p_raw = r.get("max_periods_per_day") or r.get("max_periods") or r.get("max_load") or "5"
        try:
            max_periods = int(float(max_p_raw))
            max_periods = max(1, min(9, max_periods))
        except (ValueError, TypeError):
            max_periods = 5

        # Check existing teacher
        teacher = existing_by_code.get(short_code)
        if not teacher:
            # Check by generated ID
            cand_id = slugify(full_name)
            teacher = existing_by_id.get(cand_id)

        if teacher:
            # Update existing
            teacher.full_name = full_name
            teacher.short_code = short_code
            teacher.department = dept
            teacher.status = status
            teacher.max_periods_per_day = max_periods
            updated += 1
        else:
            # Create new
            tid = slugify(full_name)
            if tid in existing_by_id:
                tid = f"{tid}_{short_code.lower()}"

            new_teacher = TeacherModel(
                id=tid,
                full_name=full_name,
                short_code=short_code,
                department=dept,
                status=status,
                max_periods_per_day=max_periods,
            )
            db.add(new_teacher)
            existing_by_id[tid] = new_teacher
            existing_by_code[short_code] = new_teacher
            created += 1

    db.commit()
    return {
        "status": "success" if not errors or (created + updated > 0) else "error",
        "entity": "teachers",
        "total_rows": len(rows),
        "created": created,
        "updated": updated,
        "errors": errors,
        "message": f"Successfully processed {created + updated} teacher(s) ({created} created, {updated} updated)." + (f" {len(errors)} error(s) encountered." if errors else ""),
    }


def import_courses_data(file_bytes: bytes, filename: str, db: Session, sync_assignments_fn=None) -> Dict[str, Any]:
    """Import courses across any term from CSV or Excel."""
    rows = parse_raw_rows(file_bytes, filename, target_sheet="Courses")
    if not rows:
        return {"status": "error", "message": "No data found in uploaded file."}

    created = 0
    updated = 0
    errors = []

    # Pre-index teachers and batches for fast validation
    teachers_by_code = {t.short_code.upper(): t for t in db.query(TeacherModel).all()}
    teachers_by_id = {t.id.lower(): t for t in db.query(TeacherModel).all()}
    teachers_by_name = {t.full_name.lower(): t for t in db.query(TeacherModel).all()}
    valid_batches = {b.id: b for b in db.query(BatchModel).all()}
    existing_courses = {c.id.upper(): c for c in db.query(CourseModel).all()}

    def resolve_teacher(val: str) -> Optional[str]:
        if not val:
            return None
        v_upper = val.upper().strip()
        if v_upper in teachers_by_code:
            return teachers_by_code[v_upper].id
        v_lower = val.lower().strip()
        if v_lower in teachers_by_id:
            return teachers_by_id[v_lower].id
        if v_lower in teachers_by_name:
            return teachers_by_name[v_lower].id
        return None

    courses_to_sync = []

    for row_idx, r in enumerate(rows, start=2):
        code = (r.get("course_code") or r.get("code") or "").upper().replace(" ", "").strip()
        title = r.get("course_title") or r.get("title") or ""
        batch_raw = (r.get("batch_term") or r.get("batch") or r.get("term") or "").strip()

        if not code:
            errors.append(f"Row {row_idx}: Missing required Course Code.")
            continue
        if not title:
            errors.append(f"Row {row_idx}: Missing required Course Title for '{code}'.")
            continue

        # Normalize batch
        batch_id = None
        for b_cand in valid_batches:
            if b_cand in batch_raw or batch_raw == b_cand:
                batch_id = b_cand
                break
        if not batch_id:
            # Try matching names like "3-2" or "3rd Year 2nd Term"
            for b_cand, b_obj in valid_batches.items():
                if b_obj.name.lower() in batch_raw.lower():
                    batch_id = b_cand
                    break
        if not batch_id:
            errors.append(f"Row {row_idx}: Unknown batch/term '{batch_raw}' for course '{code}'. Valid: 1-1, 1-2, 2-1, 2-2, 3-1, 3-2, 4-1, 4-2.")
            continue

        # Type (Theory vs Sessional)
        type_raw = (r.get("course_type") or r.get("type") or r.get("kind") or "Theory").lower().strip()
        kind = "sessional" if "sess" in type_raw or "lab" in type_raw else "theory"

        # Room kind
        raw_rk = (r.get("required_room_kind") or r.get("room_kind") or r.get("room") or ("theory" if kind == "theory" else "cse_lab")).lower().strip()
        room_kind = ROOM_KIND_NORMALIZATION.get(raw_rk, raw_rk)

        # Credit
        credit_raw = r.get("credit")
        try:
            credit = float(credit_raw) if credit_raw else (3.0 if kind == "theory" else 1.5)
        except (ValueError, TypeError):
            credit = 3.0 if kind == "theory" else 1.5

        # Specific allowed rooms (if specified)
        allowed_rooms_raw = (r.get("allowed_specific_rooms") or r.get("allowed_rooms") or r.get("specific_rooms") or "").strip()
        allowed_rooms = ",".join([r_id.strip() for r_id in allowed_rooms_raw.split(",") if r_id.strip()]) if allowed_rooms_raw else None

        # Category
        cat_raw = (r.get("course_category") or r.get("category") or "core").lower().strip()
        if "opt" in cat_raw and "3" in cat_raw:
            category = "optional_iii"
        elif "opt" in cat_raw and "2" in cat_raw:
            category = "optional_ii"
        else:
            category = "core"

        # Periods per week (Theory)
        periods_raw = r.get("periods_per_week") or r.get("periods")
        try:
            periods_per_week = int(float(periods_raw)) if periods_raw and kind == "theory" else (3 if kind == "theory" else None)
        except (ValueError, TypeError):
            periods_per_week = 3 if kind == "theory" else None

        blocks_per_week = 1 if kind == "sessional" else None

        # Resolve teachers
        t1_raw = r.get("teacher_1_short_code") or r.get("teacher_1") or r.get("teacher1") or ""
        t2_raw = r.get("teacher_2_short_code") or r.get("teacher_2") or r.get("teacher2") or ""
        t1_id = resolve_teacher(t1_raw)
        t2_id = resolve_teacher(t2_raw)
        if t1_id and t2_id == t1_id:
            t2_id = None

        course = existing_courses.get(code)
        if course:
            course.title = title
            course.batch_id = batch_id
            course.kind = kind
            course.room_kind = room_kind
            course.credit = credit
            course.category = category
            if allowed_rooms is not None or "allowed_rooms" in r or "allowed_specific_rooms" in r:
                course.allowed_rooms = allowed_rooms
            course.periods_per_week = periods_per_week
            course.blocks_per_week = blocks_per_week
            if t1_id or t1_raw == "":
                course.teacher1_id = t1_id
            if t2_id or t2_raw == "":
                course.teacher2_id = t2_id
            updated += 1
            courses_to_sync.append(course)
        else:
            new_course = CourseModel(
                id=code,
                title=title,
                batch_id=batch_id,
                kind=kind,
                room_kind=room_kind,
                credit=credit,
                category=category,
                allowed_rooms=allowed_rooms,
                periods_per_week=periods_per_week,
                blocks_per_week=blocks_per_week,
                teacher1_id=t1_id,
                teacher2_id=t2_id,
            )
            db.add(new_course)
            existing_courses[code] = new_course
            created += 1
            courses_to_sync.append(new_course)

    db.commit()

    # Sync assignments for updated/created courses
    if sync_assignments_fn:
        for c in courses_to_sync:
            try:
                sync_assignments_fn(c, db)
            except Exception as e:
                print(f"Warning: failed syncing assignments for {c.id}: {e}")
        db.commit()

    return {
        "status": "success" if not errors or (created + updated > 0) else "error",
        "entity": "courses",
        "total_rows": len(rows),
        "created": created,
        "updated": updated,
        "errors": errors,
        "message": f"Successfully processed {created + updated} course(s) ({created} created, {updated} updated)." + (f" {len(errors)} error(s) encountered." if errors else ""),
    }


def import_rooms_data(file_bytes: bytes, filename: str, db: Session) -> Dict[str, Any]:
    """Import rooms from CSV or Excel."""
    rows = parse_raw_rows(file_bytes, filename, target_sheet="Rooms")
    if not rows:
        return {"status": "error", "message": "No data found in uploaded file."}

    created = 0
    updated = 0
    errors = []

    existing_rooms = {r.id.upper(): r for r in db.query(RoomModel).all()}

    for row_idx, r in enumerate(rows, start=2):
        room_code = (r.get("room_code") or r.get("room_id") or r.get("code") or r.get("id") or "").upper().strip()
        name = r.get("room_name") or r.get("name") or ""
        kind_raw = (r.get("room_kind") or r.get("kind") or "theory").lower().strip()
        kind = ROOM_KIND_NORMALIZATION.get(kind_raw, kind_raw)

        if not room_code:
            errors.append(f"Row {row_idx}: Missing required Room Code.")
            continue
        if not name:
            errors.append(f"Row {row_idx}: Missing required Room Name for '{room_code}'.")
            continue

        cap_raw = r.get("capacity") or ("70" if kind == "theory" else "35")
        try:
            capacity = int(float(cap_raw))
        except (ValueError, TypeError):
            capacity = 70 if kind == "theory" else 35

        room = existing_rooms.get(room_code)
        if room:
            room.name = name
            room.kind = kind
            room.capacity = capacity
            updated += 1
        else:
            new_room = RoomModel(
                id=room_code,
                name=name,
                kind=kind,
                capacity=capacity,
            )
            db.add(new_room)
            existing_rooms[room_code] = new_room
            created += 1

    db.commit()
    return {
        "status": "success" if not errors or (created + updated > 0) else "error",
        "entity": "rooms",
        "total_rows": len(rows),
        "created": created,
        "updated": updated,
        "errors": errors,
        "message": f"Successfully processed {created + updated} room(s) ({created} created, {updated} updated)." + (f" {len(errors)} error(s) encountered." if errors else ""),
    }


def import_all_in_one_workbook(file_bytes: bytes, filename: str, db: Session, sync_assignments_fn=None) -> Dict[str, Any]:
    """Import multi-sheet Excel master workbook in proper dependency order: Rooms -> Teachers -> Courses."""
    lower_fn = filename.lower()
    if not (lower_fn.endswith(".xlsx") or lower_fn.endswith(".xlsm")):
        return {"status": "error", "message": "Master workbook must be an Excel file (.xlsx)."}

    # Step 1: Rooms
    rooms_res = import_rooms_data(file_bytes, filename, db)
    # Step 2: Teachers
    teachers_res = import_teachers_data(file_bytes, filename, db)
    # Step 3: Courses
    courses_res = import_courses_data(file_bytes, filename, db, sync_assignments_fn=sync_assignments_fn)

    all_errors = rooms_res.get("errors", []) + teachers_res.get("errors", []) + courses_res.get("errors", [])

    return {
        "status": "success",
        "entity": "all",
        "summary": {
            "rooms": {"created": rooms_res.get("created", 0), "updated": rooms_res.get("updated", 0)},
            "teachers": {"created": teachers_res.get("created", 0), "updated": teachers_res.get("updated", 0)},
            "courses": {"created": courses_res.get("created", 0), "updated": courses_res.get("updated", 0)},
        },
        "errors": all_errors,
        "message": f"Master Workbook Imported: {teachers_res.get('created',0) + teachers_res.get('updated',0)} Teachers, {courses_res.get('created',0) + courses_res.get('updated',0)} Courses, and {rooms_res.get('created',0) + rooms_res.get('updated',0)} Rooms processed.",
    }

