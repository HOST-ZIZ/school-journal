from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db, init_db
import datetime

app = Flask(__name__)
app.secret_key = "asu_rso_local_secure_key"

try:
    init_db()
except Exception as e:
    print(f"Ошибка при инициализации базы: {e}")

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") == "admin":
        return redirect(url_for("admin_panel"))
    return redirect(url_for("teacher_panel"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_val = request.form.get("login", "").strip()
        pass_val = request.form.get("password", "").strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE login = %s AND password = %s", (login_val, pass_val))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session["user_id"] = user["id"]
            session["fio"] = user["fio"]
            session["role"] = user["role"]
            return redirect(url_for("index"))
        else:
            flash("Неверный логин или пароль!", "error")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- ПАНЕЛЬ АДМИНИСТРАТОРА ---
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_class":
            c_name = request.form.get("class_name", "").strip()
            if c_name:
                try:
                    cur.execute("INSERT INTO classes (name) VALUES (%s)", (c_name,))
                    conn.commit()
                    flash(f"Класс «{c_name}» создан!", "success")
                except:
                    conn.rollback()
                    flash("Такой класс уже существует!", "error")

        elif action == "add_student":
            fio = request.form.get("fio", "").strip()
            class_id = request.form.get("class_id")
            if fio and class_id:
                cur.execute("INSERT INTO students (fio, class_id) VALUES (%s, %s)", (fio, class_id))
                conn.commit()
                flash(f"Ученик {fio} добавлен!", "success")

        elif action == "transfer_student":
            student_id = request.form.get("student_id")
            new_class_id = request.form.get("new_class_id")
            if student_id and new_class_id:
                cur.execute("UPDATE students SET class_id = %s WHERE id = %s", (new_class_id, student_id))
                conn.commit()
                flash("Ученик переведён!", "success")

        elif action == "delete_student":
            student_id = request.form.get("student_id")
            cur.execute("DELETE FROM grades WHERE student_id = %s", (student_id,))
            cur.execute("DELETE FROM students WHERE id = %s", (student_id,))
            conn.commit()
            flash("Ученик удален!", "success")

        elif action == "add_subject":
            s_name = request.form.get("subject_name", "").strip()
            if s_name:
                try:
                    cur.execute("INSERT INTO subjects (name) VALUES (%s)", (s_name,))
                    conn.commit()
                    flash("Предмет добавлен!", "success")
                except:
                    conn.rollback()
                    flash("Такой предмет уже есть!", "error")

        elif action == "delete_subject":
            sub_id = request.form.get("subject_id")
            cur.execute("DELETE FROM lessons WHERE subject_id = %s", (sub_id,))
            cur.execute("DELETE FROM subjects WHERE id = %s", (sub_id,))
            conn.commit()
            flash("Предмет удален!", "success")

        elif action == "add_teacher":
            fio = request.form.get("fio", "").strip()
            login_u = request.form.get("login", "").strip()
            pass_u = request.form.get("password", "").strip()
            if fio and login_u and pass_u:
                try:
                    cur.execute("INSERT INTO users (fio, login, password, role) VALUES (%s, %s, %s, 'teacher')", (fio, login_u, pass_u))
                    conn.commit()
                    flash(f"Учитель {fio} зарегистрирован!", "success")
                except:
                    conn.rollback()
                    flash("Логин занят!", "error")

        elif action == "add_period":
            p_name = request.form.get("period_name", "").strip()
            start_d = request.form.get("start_date")
            end_d = request.form.get("end_date")
            if p_name and start_d and end_d:
                cur.execute("INSERT INTO periods (name, start_date, end_date) VALUES (%s, %s, %s)", (p_name, start_d, end_d))
                conn.commit()
                flash(f"Период «{p_name}» настроен!", "success")

        cur.close()
        conn.close()
        return redirect(url_for("admin_panel"))

    cur.execute("SELECT * FROM classes ORDER BY name")
    classes = cur.fetchall()
    cur.execute("SELECT s.*, c.name as class_name FROM students s JOIN classes c ON s.class_id = c.id ORDER BY c.name, s.fio")
    students = cur.fetchall()
    cur.execute("SELECT * FROM subjects ORDER BY name")
    subjects = cur.fetchall()
    cur.execute("SELECT * FROM users WHERE role = 'teacher' ORDER BY fio")
    teachers = cur.fetchall()
    cur.execute("SELECT * FROM periods ORDER BY start_date")
    periods = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("admin.html", fio=session.get("fio"), classes=classes, students=students, subjects=subjects, teachers=teachers, periods=periods)

# --- УПРАВЛЕНИЕ РАСПИСАНИЕМ (5-дневка, уроки 1-7) ---
@app.route("/schedule", methods=["GET", "POST"])
def schedule_panel():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    class_id = request.args.get("class_id", type=int)
    subject_id = request.args.get("subject_id", type=int)
    period_id = request.args.get("period_id", type=int)

    if request.method == "POST":
        c_id = request.form.get("class_id")
        s_id = request.form.get("subject_id")
        p_id = request.form.get("period_id")

        cur.execute("SELECT start_date, end_date FROM periods WHERE id = %s", (p_id,))
        period = cur.fetchone()

        if period:
            start_dt = datetime.datetime.strptime(period["start_date"], "%Y-%m-%d").date()
            end_dt = datetime.datetime.strptime(period["end_date"], "%Y-%m-%d").date()

            cur_date = start_dt
            while cur_date <= end_dt:
                # 5-дневка: понедельник (0) - пятница (4)
                if cur_date.weekday() < 5:
                    d_str = cur_date.isoformat()
                    field_name = f"lesson_num_{d_str}"
                    lesson_num = request.form.get(field_name)

                    if lesson_num and lesson_num.isdigit() and int(lesson_num) > 0:
                        l_num = int(lesson_num)
                        cur.execute("""
                            SELECT id FROM lessons 
                            WHERE class_id = %s AND subject_id = %s AND lesson_date = %s
                        """, (c_id, s_id, d_str))
                        existing = cur.fetchone()

                        if existing:
                            cur.execute("UPDATE lessons SET lesson_number = %s WHERE id = %s", (l_num, existing["id"]))
                        else:
                            cur.execute("""
                                INSERT INTO lessons (class_id, subject_id, lesson_date, lesson_number, topic, homework, is_held, lesson_type)
                                VALUES (%s, %s, %s, %s, 'Урок', '', 1, 'lesson')
                            """, (c_id, s_id, d_str, l_num))
                    else:
                        # Если поле очистили — удаляем урок этого предмета на этот день
                        cur.execute("""
                            DELETE FROM lessons 
                            WHERE class_id = %s AND subject_id = %s AND lesson_date = %s
                        """, (c_id, s_id, d_str))

                cur_date += datetime.timedelta(days=1)
            conn.commit()
            flash("Расписание успешно сохранено!", "success")

        cur.close()
        conn.close()
        return redirect(url_for("schedule_panel", class_id=c_id, subject_id=s_id, period_id=p_id))

    cur.execute("SELECT * FROM classes ORDER BY name")
    classes = cur.fetchall()
    cur.execute("SELECT * FROM subjects ORDER BY name")
    subjects = cur.fetchall()
    cur.execute("SELECT * FROM periods ORDER BY start_date")
    periods = cur.fetchall()

    days_list = []
    lessons_map = {}

    if class_id and subject_id and period_id:
        cur.execute("SELECT * FROM periods WHERE id = %s", (period_id,))
        period = cur.fetchone()
        if period:
            start_dt = datetime.datetime.strptime(period["start_date"], "%Y-%m-%d").date()
            end_dt = datetime.datetime.strptime(period["end_date"], "%Y-%m-%d").date()

            cur.execute("""
                SELECT lesson_date, lesson_number FROM lessons 
                WHERE class_id = %s AND subject_id = %s AND lesson_date BETWEEN %s AND %s
            """, (class_id, subject_id, period["start_date"], period["end_date"]))
            for row in cur.fetchall():
                lessons_map[row["lesson_date"]] = row["lesson_number"]

            weekdays_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"]
            cur_date = start_dt
            while cur_date <= end_dt:
                if cur_date.weekday() < 5:
                    d_str = cur_date.isoformat()
                    days_list.append({
                        "date": d_str,
                        "day_name": weekdays_ru[cur_date.weekday()],
                        "current_num": lessons_map.get(d_str, "")
                    })
                cur_date += datetime.timedelta(days=1)

    cur.close()
    conn.close()
    return render_template(
        "schedule.html",
        fio=session.get("fio"),
        classes=classes,
        subjects=subjects,
        periods=periods,
        selected_class=class_id,
        selected_subject=subject_id,
        selected_period=period_id,
        days_list=days_list
    )

# --- ЭЛЕКТРОННЫЙ ДНЕВНИК УЧЕНИКА ---
@app.route("/diary")
def student_diary():
    conn = get_db()
    cur = conn.cursor()

    class_id = request.args.get("class_id", type=int)
    student_id = request.args.get("student_id", type=int)
    selected_date = request.args.get("date", datetime.date.today().isoformat())

    cur.execute("SELECT * FROM classes ORDER BY name")
    classes = cur.fetchall()

    students = []
    if class_id:
        cur.execute("SELECT * FROM students WHERE class_id = %s ORDER BY fio", (class_id,))
        students = cur.fetchall()

    timetable = []
    if class_id and selected_date:
        # Извлекаем все уроки класса на эту дату, упорядоченные с 1 по 7
        cur.execute("""
            SELECT l.id, l.lesson_number, l.lesson_date, l.topic, l.homework, l.lesson_type, s.name as subject_name
            FROM lessons l
            JOIN subjects s ON l.subject_id = s.id
            WHERE l.class_id = %s AND l.lesson_date = %s
            ORDER BY l.lesson_number ASC
        """, (class_id, selected_date))
        lessons = cur.fetchall()

        grades_by_lesson = {}
        if student_id:
            cur.execute("""
                SELECT lesson_id, grade, grade_type, comment, weight 
                FROM grades 
                WHERE student_id = %s
            """, (student_id,))
            for g in cur.fetchall():
                les_id = g["lesson_id"]
                if les_id not in grades_by_lesson:
                    grades_by_lesson[les_id] = {}
                grades_by_lesson[les_id][g["grade_type"]] = g

        for les in lessons:
            les_id = les["id"]
            l_grades = grades_by_lesson.get(les_id, {})
            timetable.append({
                "lesson_id": les_id,
                "number": les["lesson_number"],
                "subject": les["subject_name"],
                "topic": les["topic"] or "Тема не указана",
                "homework": les["homework"] or "Нет домашнего задания",
                "grade_class": l_grades.get("class", {}).get("grade", ""),
                "grade_homework": l_grades.get("homework", {}).get("grade", ""),
                "grade_test": l_grades.get("test", {}).get("grade", "") or l_grades.get("control", {}).get("grade", ""),
                "comment": l_grades.get("class", {}).get("comment", "")
            })

    cur.close()
    conn.close()

    return render_template(
        "diary.html",
        fio=session.get("fio"),
        classes=classes,
        students=students,
        selected_class=class_id,
        selected_student=student_id,
        selected_date=selected_date,
        timetable=timetable
    )

# --- ЖУРНАЛ УЧИТЕЛЯ ---
@app.route("/teacher", methods=["GET", "POST"])
def teacher_panel():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    class_id = request.args.get("class_id", type=int)
    subject_id = request.args.get("subject_id", type=int)
    period_id = request.args.get("period_id", type=int)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_journal":
            c_id = request.form.get("class_id")
            s_id = request.form.get("subject_id")
            p_id = request.form.get("period_id")

            cur.execute("SELECT id FROM lessons WHERE class_id = %s AND subject_id = %s", (c_id, s_id))
            all_lessons = cur.fetchall()
            for les in all_lessons:
                les_id = les["id"]
                is_checked = 1 if request.form.get(f"held_{les_id}") == "on" else 0
                cur.execute("UPDATE lessons SET is_held = %s WHERE id = %s", (is_checked, les_id))

            for key, val in request.form.items():
                if key.startswith("grade_"):
                    parts = key.split("_")
                    if len(parts) == 4:
                        g_type = parts[1]
                        st_id, les_id = parts[2], parts[3]
                        grade_val = val.strip().upper()

                        if grade_val in ["2", "3", "4", "5", "Н", "У", "О", ""]:
                            cur.execute("SELECT lesson_type FROM lessons WHERE id = %s", (les_id,))
                            les_info = cur.fetchone()
                            weight = 1
                            if les_info and les_info["lesson_type"] == 'control': weight = 3
                            elif les_info and les_info["lesson_type"] == 'test': weight = 2

                            cur.execute("SELECT id FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = %s", (st_id, les_id, g_type))
                            existing = cur.fetchone()
                            if existing:
                                if grade_val:
                                    cur.execute("UPDATE grades SET grade = %s, weight = %s WHERE id = %s", (grade_val, weight, existing["id"]))
                                else:
                                    cur.execute("DELETE FROM grades WHERE id = %s", (existing["id"],))
                            elif grade_val:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, %s, %s)", (st_id, les_id, grade_val, g_type, weight))

            conn.commit()
            cur.close()
            conn.close()
            flash("Журнал сохранен!", "success")
            return redirect(url_for("teacher_panel", class_id=c_id, subject_id=s_id, period_id=p_id))

    cur.execute("SELECT * FROM classes ORDER BY name")
    classes = cur.fetchall()
    cur.execute("SELECT * FROM subjects ORDER BY name")
    subjects = cur.fetchall()
    cur.execute("SELECT * FROM periods ORDER BY start_date")
    periods = cur.fetchall()

    students = []
    lessons = []
    grades_map = {}
    student_stats = {}

    if class_id and subject_id and period_id:
        cur.execute("SELECT * FROM students WHERE class_id = %s ORDER BY fio", (class_id,))
        students = cur.fetchall()
        cur.execute("SELECT * FROM periods WHERE id = %s", (period_id,))
        period = cur.fetchone()

        if period:
            cur.execute("""
                SELECT * FROM lessons 
                WHERE class_id = %s AND subject_id = %s AND lesson_date BETWEEN %s AND %s 
                ORDER BY lesson_date, lesson_number ASC, id ASC
            """, (class_id, subject_id, period["start_date"], period["end_date"]))
            lessons = cur.fetchall()

        cur.execute("""
            SELECT g.* FROM grades g JOIN lessons l ON g.lesson_id = l.id WHERE l.class_id = %s AND l.subject_id = %s
        """, (class_id, subject_id))
        raw_grades = cur.fetchall()

        for g in raw_grades:
            try:
                g_type = g["grade_type"] if "grade_type" in g.keys() and g["grade_type"] else "class"
            except:
                g_type = "class"
            grades_map[(g["student_id"], g["lesson_id"], g_type)] = g["grade"]

        valid_lesson_ids = {l["id"] for l in lessons}
        for st in students:
            total_score = 0.0
            total_weight = 0
            n_count = 0

            for l_id in valid_lesson_ids:
                for g_t in ['class', 'homework', 'extra']:
                    val = grades_map.get((st["id"], l_id, g_t), "")
                    if val in ["2", "3", "4", "5"]:
                        cur.execute("SELECT weight FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = %s", (st["id"], l_id, g_t))
                        g_row = cur.fetchone()
                        w = g_row["weight"] if g_row and g_row["weight"] else 1
                        total_score += int(val) * w
                        total_weight += w
                    elif val == "Н":
                        n_count += 1
            
            avg = round(total_score / total_weight, 2) if total_weight > 0 else 0.0
            
            period_grade = ""
            if avg >= 4.5: period_grade = "5"
            elif avg >= 3.5: period_grade = "4"
            elif avg >= 2.5: period_grade = "3"
            elif avg > 0: period_grade = "2"

            student_stats[st["id"]] = {"avg": avg, "period_grade": period_grade, "missed_n": n_count}

    cur.close()
    conn.close()

    return render_template(
        "teacher.html",
        fio=session.get("fio"),
        role=session.get("role"),
        classes=classes,
        subjects=subjects,
        periods=periods,
        selected_class=class_id,
        selected_subject=subject_id,
        selected_period=period_id,
        students=students,
        lessons=lessons,
        grades_map=grades_map,
        student_stats=student_stats
    )

# --- СВОДНАЯ ВЕДОМОСТЬ КЛАССА ---
@app.route("/report")
def class_report():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    class_id = request.args.get("class_id", type=int)
    period_id = request.args.get("period_id", type=int)

    cur.execute("SELECT * FROM classes ORDER BY name")
    classes = cur.fetchall()
    cur.execute("SELECT * FROM periods ORDER BY start_date")
    periods = cur.fetchall()
    
    report_data = []
    subjects = []
    
    if class_id and period_id:
        cur.execute("SELECT * FROM students WHERE class_id = %s ORDER BY fio", (class_id,))
        students = cur.fetchall()
        cur.execute("SELECT * FROM subjects ORDER BY name")
        subjects = cur.fetchall()
        cur.execute("SELECT * FROM periods WHERE id = %s", (period_id,))
        period = cur.fetchone()

        for st in students:
            st_row = {"fio": st["fio"], "marks": {}}
            for sub in subjects:
                cur.execute("""
                    SELECT g.grade, g.weight FROM grades g 
                    JOIN lessons l ON g.lesson_id = l.id 
                    WHERE g.student_id = %s AND l.class_id = %s AND l.subject_id = %s AND l.lesson_date BETWEEN %s AND %s
                """, (st["id"], class_id, sub["id"], period["start_date"], period["end_date"]))
                raw = cur.fetchall()

                sc, wt = 0.0, 0
                for r in raw:
                    if r["grade"] in ["2", "3", "4", "5"]:
                        w = r["weight"] if r["weight"] else 1
                        sc += int(r["grade"]) * w
                        wt += w
                
                avg_sub = round(sc / wt, 2) if wt > 0 else "-"
                st_row["marks"][sub["id"]] = avg_sub
            report_data.append(st_row)

    cur.close()
    conn.close()
    return render_template("report.html", fio=session.get("fio"), classes=classes, periods=periods, subjects=subjects, report_data=report_data, selected_class=class_id, selected_period=period_id)

# --- КАРТОЧКА УРОКА ---
@app.route("/lesson/<int:lesson_id>", methods=["GET", "POST"])
def edit_lesson(lesson_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT l.*, c.name as class_name, s.name as subject_name 
        FROM lessons l 
        JOIN classes c ON l.class_id = c.id 
        JOIN subjects s ON l.subject_id = s.id 
        WHERE l.id = %s
    """, (lesson_id,))
    lesson = cur.fetchone()

    if not lesson:
        cur.close()
        conn.close()
        return "Урок не найден", 404

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_info":
            topic = request.form.get("topic", "").strip()
            homework = request.form.get("homework", "").strip()
            is_held = 1 if request.form.get("is_held") == "on" else 0
            
            cur.execute("UPDATE lessons SET topic = %s, homework = %s, is_held = %s WHERE id = %s", (topic, homework, is_held, lesson_id))
            conn.commit()
            flash("Информация об уроке обновлена!", "success")

        elif action == "save_lesson_grades":
            for key, val in request.form.items():
                if key.startswith("lesgrade_"):
                    parts = key.split("_")
                    if len(parts) == 3:
                        g_type, st_id = parts[1], parts[2]
                        grade_val = val.strip().upper()
                        comment = request.form.get(f"comment_{g_type}_{st_id}", "").strip()

                        if grade_val in ["2", "3", "4", "5", "Н", "У", "О", ""]:
                            weight = 3 if lesson["lesson_type"] == 'control' else (2 if lesson["lesson_type"] == 'test' else 1)
                            
                            cur.execute("SELECT id FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = %s", (st_id, lesson_id, g_type))
                            existing = cur.fetchone()
                            if existing:
                                if grade_val:
                                    cur.execute("UPDATE grades SET grade = %s, weight = %s, comment = %s WHERE id = %s", (grade_val, weight, comment, existing["id"]))
                                else:
                                    cur.execute("DELETE FROM grades WHERE id = %s", (existing["id"],))
                            elif grade_val:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight, comment) VALUES (%s, %s, %s, %s, %s, %s)", (st_id, lesson_id, grade_val, g_type, weight, comment))
            conn.commit()
            flash("Оценки и комментарии сохранены!", "success")

        elif action == "add_class_column":
            col_type = request.form.get("col_type") 
            col_title = "Контрольная работа" if col_type == "control" else "Самостоятельная работа"
            
            cur.execute("""
                INSERT INTO lessons (class_id, subject_id, lesson_date, topic, homework, is_held, lesson_type)
                VALUES (%s, %s, %s, %s, '', 1, %s)
            """, (lesson["class_id"], lesson["subject_id"], lesson["lesson_date"], col_title, col_type))
            conn.commit()
            flash("Дополнительная колонка работы добавлена в журнал!", "success")

        cur.close()
        conn.close()
        return redirect(url_for("edit_lesson", lesson_id=lesson_id))

    cur.execute("SELECT * FROM students WHERE class_id = %s ORDER BY fio", (lesson["class_id"],))
    students = cur.fetchall()
    cur.execute("SELECT * FROM grades WHERE lesson_id = %s", (lesson_id,))
    raw_grades = cur.fetchall()
    
    lesson_grades = {}
    for g in raw_grades:
        try:
            g_type = g["grade_type"] if "grade_type" in g.keys() and g["grade_type"] else "class"
        except:
            g_type = "class"
        lesson_grades[(g["student_id"], g_type)] = {"val": g["grade"], "comment": g["comment"] or ""}

    cur.close()
    conn.close()
    return render_template("lesson_card.html", fio=session.get("fio"), lesson=lesson, students=students, lesson_grades=lesson_grades)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
