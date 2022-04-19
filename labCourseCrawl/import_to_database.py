import json
import sqlite3

# 数据库地址
DB_PATH = "../ClassSchedule_debug.db"
conn = sqlite3.connect(DB_PATH)

with open("labCourseAll.json", "r") as f:
    labCourseAll = json.load(f)

for info in labCourseAll:
    for course in info["courseList"]:
        print(course)
        c = conn.cursor()
        c.execute(
            "INSERT INTO labs (name, semester, teacher, week, dayOfWeek, section, className, classroom) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                info["name"],
                info["semester"],
                info["teacher"],
                course["week"],
                course["dayOfWeek"],
                course["section"],
                course["className"],
                course["classroom"],
            ),
        )
        c.close()
    conn.commit()