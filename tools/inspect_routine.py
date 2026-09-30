import csv

with open('out/routine.csv', encoding='utf-8') as f:
    rows = [r for r in csv.DictReader(f) if r['batch'] == '1-1']

print(f"Total 1-1 entries: {len(rows)}")
print("\n=== 1-1 Section A ===")
secA = sorted([r for r in rows if r['section'] == 'A'], key=lambda x: (x['day'], x['start_time']))
for r in secA:
    grp = f"[{r['group']}]" if r['group'] else ""
    print(f"{r['day']:<9} {r['start_period']} ({r['start_time']}-{r['end_time']}) | {r['course_code']:<8} {grp:<16} | Room: {r['room']:<32} | Teachers: {r['teachers']}")

print("\n=== 1-1 Section B ===")
secB = sorted([r for r in rows if r['section'] == 'B'], key=lambda x: (x['day'], x['start_time']))
for r in secB:
    grp = f"[{r['group']}]" if r['group'] else ""
    print(f"{r['day']:<9} {r['start_period']} ({r['start_time']}-{r['end_time']}) | {r['course_code']:<8} {grp:<16} | Room: {r['room']:<32} | Teachers: {r['teachers']}")
