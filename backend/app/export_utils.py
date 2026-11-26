"""CSV and Excel export of a generated week.

CSV is the portable format (opens in Excel/Sheets, imports into
other tools). Excel adds a second sheet with per-employee hours,
because that is what a manager actually checks before posting a rota.
"""
import csv
import io

from .config import DAYS


def schedule_to_csv(assignments, week_start):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["week_start", "day", "shift", "employee", "role"])
    for a in sorted(assignments, key=lambda x: (DAYS.index(x["day"]), x["shift"], x["role"])):
        w.writerow([week_start, a["day"], a["shift"], a["employee_name"], a["role"]])
    return buf.getvalue()


def schedule_to_excel(assignments, week_start):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Schedule"
    ws.append(["Week starting", week_start])
    ws.append([])
    ws.append(["Day", "Shift", "Employee", "Role"])
    for c in ws[3]:
        c.font = Font(bold=True)
    for a in sorted(assignments, key=lambda x: (DAYS.index(x["day"]), x["shift"], x["role"])):
        ws.append([a["day"], a["shift"], a["employee_name"], a["role"]])
    hours: dict[str, int] = {}
    for a in assignments:
        hours[a["employee_name"]] = hours.get(a["employee_name"], 0) + 4
    ws2 = wb.create_sheet("Hours")
    ws2.append(["Employee", "Hours"])
    for c in ws2[1]:
        c.font = Font(bold=True)
    for name, h in sorted(hours.items(), key=lambda kv: -kv[1]):
        ws2.append([name, h])
    for ws_ in (ws, ws2):
        for col in ws_.columns:
            ws_.column_dimensions[col[0].column_letter].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
