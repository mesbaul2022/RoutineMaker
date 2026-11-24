import urllib.request
import re

html = urllib.request.urlopen("http://127.0.0.1:8000/").read().decode("utf-8")
match = re.search(r'<select id="course-room-kind".*?</select>', html, re.DOTALL)
if match:
    for line in match.group(0).splitlines():
        line = line.strip()
        if "optgroup" in line or "option" in line:
            print(line)

