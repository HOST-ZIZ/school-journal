from flask import Flask, render_template, request, redirect, url_for, session, flash
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

# --- РАСПИСАНИЕ УРОКОВ ---
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
                if cur_date.weekday() < 5:
                    d_str = cur_date.isoformat()
                    field_name = f"lesson_num_{d_str}"
                    lesson_num = request.form.get(field_name)

                    if lesson_num and lesson_num.isdigit() and int(lesson_num) > 0:
                        l_num = int(lesson_num)
                        cur.execute("""
                            SELECT id FROM lessons 
                            WHERE class_id = %s AND subject_id = %s AND lesson_date = %s AND lesson_type = 'lesson'
                        """, (c_id, s_id, d_str))
                        existing = cur.fetchone()

                        if existing:
                            cur.execute("UPDATE lessons SET lesson_number = %s WHERE id = %s", (l_num, existing["id"]))
                        else:
                            cur.execute("""
                                INSERT INTO lessons (class_id, subject_id, lesson_date, lesson_number, topic, homework, is_held, lesson_type, weight)
                                VALUES (%s, %s, %s, %s, 'Урок', '', 1, 'lesson', 1)
                            """, (c_id, s_id, d_str, l_num))
                    else:
                        cur.execute("""
                            DELETE FROM lessons 
                            WHERE class_id = %s AND subject_id = %s AND lesson_date = %s
                        """, (c_id, s_id, d_str))

                cur_date += datetime.timedelta(days=1)
            conn.commit()
            flash("Расписание сохранено!", "success")

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
                WHERE class_id = %s AND subject_id = %s AND lesson_type = 'lesson' AND lesson_date BETWEEN %s AND %s
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

            for key, val in request.form.items():
                if key.startswith("cell_"):
                    parts = key.split("_")
                    if len(parts) == 3:
                        st_id, les_id = parts[1], parts[2]
                        raw_val = val.strip().upper().replace("\\", "/")
                        
                        g_parts = [p.strip() for p in raw_val.split("/") if p.strip()] if "/" in raw_val else ([raw_val] if raw_val else [])
                        val_class = g_parts[0] if len(g_parts) > 0 else ""
                        val_hw = g_parts[1] if len(g_parts) > 1 else ""

                        cur.execute("SELECT lesson_type, weight FROM lessons WHERE id = %s", (les_id,))
                        les_info = cur.fetchone()
                        w_class = les_info["weight"] if les_info and les_info.get("weight") else 1
                        w_hw = 1

                        # Первая оценка (урок / проверочная работа)
                        cur.execute("SELECT id FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = 'class'", (st_id, les_id))
                        exist_class = cur.fetchone()
                        if val_class in ["2", "3", "4", "5", "Н", "У", "О", "."]:
                            if exist_class:
                                cur.execute("UPDATE grades SET grade = %s, weight = %s WHERE id = %s", (val_class, w_class, exist_class["id"]))
                            else:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'class', %s)", (st_id, les_id, val_class, w_class))
                        else:
                            if exist_class:
                                cur.execute("DELETE FROM grades WHERE id = %s", (exist_class["id"],))

                        # Вторая оценка (ДЗ)
                        cur.execute("SELECT id FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = 'homework'", (st_id, les_id))
                        exist_hw = cur.fetchone()
                        if val_hw in ["2", "3", "4", "5", "Н", "У", "О", "."]:
                            if exist_hw:
                                cur.execute("UPDATE grades SET grade = %s, weight = %s WHERE id = %s", (val_hw, w_hw, exist_hw["id"]))
                            else:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'homework', %s)", (st_id, les_id, val_hw, w_hw))
                        else:
                            if exist_hw:
                                cur.execute("DELETE FROM grades WHERE id = %s", (exist_hw["id"],))

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
    month_groups = []
    cell_values = {}
    student_stats = {}

    months_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }

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
            lessons_raw = cur.fetchall()
            
            current_m_key = None
            for les in lessons_raw:
                dt = datetime.datetime.strptime(les["lesson_date"], "%Y-%m-%d").date()
                les_dict = dict(les)
                les_dict["day_num"] = dt.day
                lessons.append(les_dict)

                m_key = (dt.year, dt.month)
                if current_m_key != m_key:
                    current_m_key = m_key
                    month_groups.append({
                        "name": months_ru.get(dt.month, ""),
                        "count": 1
                    })
                else:
                    month_groups[-1]["count"] += 1

        cur.execute("""
            SELECT g.* FROM grades g JOIN lessons l ON g.lesson_id = l.id WHERE l.class_id = %s AND l.subject_id = %s
        """, (class_id, subject_id))
        raw_grades = cur.fetchall()

        grades_lookup = {}
        for g in raw_grades:
            key = (g["student_id"], g["lesson_id"])
            if key not in grades_lookup:
                grades_lookup[key] = {}
            grades_lookup[key][g["grade_type"]] = g

        for key, g_dict in grades_lookup.items():
            g_cl = g_dict.get("class", {}).get("grade", "")
            g_hw = g_dict.get("homework", {}).get("grade", "")
            
            if g_cl and g_hw:
                cell_values[key] = f"{g_cl}/{g_hw}"
            elif g_cl:
                cell_values[key] = g_cl
            elif g_hw:
                cell_values[key] = f"/{g_hw}"

        # Подсчёт среднего балла (ТОЧКА '.' ПОЛНОСТЬЮ ИГНОРИРУЕТСЯ И НЕ СЧИТАЕТСЯ ДВОЙКОЙ)
        valid_lesson_ids = {l["id"] for l in lessons}
        for st in students:
            total_score = 0.0
            total_weight = 0

            for l_id in valid_lesson_ids:
                g_dict = grades_lookup.get((st["id"], l_id), {})
                for g_t in ['class', 'homework', 'test', 'control']:
                    g_obj = g_dict.get(g_t)
                    if g_obj and g_obj["grade"] in ["2", "3", "4", "5"]:
                        w = g_obj["weight"] if g_obj["weight"] else 1
                        total_score += int(g_obj["grade"]) * w
                        total_weight += w
            
            avg = round(total_score / total_weight, 2) if total_weight > 0 else 0.0
            
            period_grade = ""
            if avg >= 4.5: period_grade = "5"
            elif avg >= 3.5: period_grade = "4"
            elif avg >= 2.5: period_grade = "3"
            elif avg > 0: period_grade = "2"

            student_stats[st["id"]] = {"avg": f"{avg:.2f}" if avg > 0 else "-", "period_grade": period_grade}

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
        month_groups=month_groups,
        cell_values=cell_values,
        student_stats=student_stats
    )

# --- УДАЛЕНИЕ ПРОВЕРОЧНОЙ КОЛОНКИ (ИЗ ЖУРНАЛА ИЛИ КАРТОЧКИ) ---
@app.route("/lesson/delete/<int:lesson_id>", methods=["POST"])
def delete_lesson_route(lesson_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT class_id, subject_id, lesson_date, parent_id FROM lessons WHERE id = %s", (lesson_id,))
    les = cur.fetchone()

    period_id = request.form.get("period_id", type=int)

    if les:
        if not period_id:
            cur.execute("SELECT id FROM periods WHERE %s BETWEEN start_date AND end_date LIMIT 1", (les["lesson_date"],))
            p_row = cur.fetchone()
            period_id = p_row["id"] if p_row else None

        cur.execute("DELETE FROM grades WHERE lesson_id = %s", (lesson_id,))
        cur.execute("DELETE FROM lessons WHERE id = %s", (lesson_id,))
        conn.commit()
        flash("Колонка работы успешно удалена!", "info")

    cur.close()
    conn.close()

    redirect_to = request.form.get("redirect_to", "teacher")
    if redirect_to == "lesson" and les and les["parent_id"]:
        return redirect(url_for("edit_lesson", lesson_id=les["parent_id"], period_id=period_id))
    elif les:
        return redirect(url_for("teacher_panel", class_id=les["class_id"], subject_id=les["subject_id"], period_id=period_id))
    return redirect(url_for("teacher_panel"))

# --- КАРТОЧКА УРОКА (ВЫСТАВИТЬ ОЦЕНКИ) ---
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

    main_lesson_id = lesson["parent_id"] if lesson.get("parent_id") else lesson["id"]

    # Определяем ID периода (четверти): из GET, POST или по дате урока
    period_id = request.args.get("period_id", type=int)
    if not period_id:
        period_id = request.form.get("period_id", type=int)
    if not period_id:
        cur.execute("SELECT id FROM periods WHERE %s BETWEEN start_date AND end_date LIMIT 1", (lesson["lesson_date"],))
        p_row = cur.fetchone()
        if p_row:
            period_id = p_row["id"]
        else:
            cur.execute("SELECT id FROM periods ORDER BY start_date ASC LIMIT 1")
            first_p = cur.fetchone()
            period_id = first_p["id"] if first_p else None

    if request.method == "POST":
        action = request.form.get("action")
        
        # 1. Создание проверочной колонки
        if action == "add_work_column":
            work_type = request.form.get("work_type", "control")
            work_weight = request.form.get("work_weight", 1, type=int)
            work_title = "Контрольная работа" if work_type == "control" else "Самостоятельная работа"

            cur.execute("""
                INSERT INTO lessons (class_id, subject_id, lesson_date, lesson_number, topic, homework, is_held, lesson_type, weight, parent_id)
                VALUES (%s, %s, %s, %s, %s, '', 1, %s, %s, %s)
            """, (lesson["class_id"], lesson["subject_id"], lesson["lesson_date"], lesson["lesson_number"], work_title, work_type, work_weight, main_lesson_id))
            conn.commit()
            flash(f"Колонка «{work_title}» создана!", "success")
            cur.close()
            conn.close()
            return redirect(url_for("edit_lesson", lesson_id=main_lesson_id, period_id=period_id))

        # 2. Сохранение оценок
        elif action in ["save_all", "save_and_return"]:
            topic = request.form.get("topic", "").strip()
            homework = request.form.get("homework", "").strip()
            is_held = 1 if request.form.get("is_held") == "on" else 0
            
            cur.execute("UPDATE lessons SET topic = %s, homework = %s, is_held = %s WHERE id = %s", (topic, homework, is_held, main_lesson_id))

            cur.execute("""
                SELECT id, lesson_type, weight FROM lessons 
                WHERE id = %s OR parent_id = %s OR (class_id = %s AND subject_id = %s AND lesson_date = %s AND lesson_type != 'lesson')
            """, (main_lesson_id, main_lesson_id, lesson["class_id"], lesson["subject_id"], lesson["lesson_date"]))
            all_work_cols = cur.fetchall()

            cur.execute("SELECT id FROM students WHERE class_id = %s", (lesson["class_id"],))
            class_students = cur.fetchall()

            for st in class_students:
                st_id = st["id"]
                att_val = request.form.get(f"attend_{st_id}", "").strip().upper()

                for col in all_work_cols:
                    col_id = col["id"]
                    c_weight = col["weight"] if col.get("weight") else 1

                    if col_id == main_lesson_id:
                        cl_val = request.form.get(f"class_grade_{st_id}", "").strip().upper()
                        if att_val and not cl_val:
                            cl_val = att_val

                        cur.execute("SELECT id FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = 'class'", (st_id, col_id))
                        exist_cl = cur.fetchone()
                        if cl_val in ["2", "3", "4", "5", "Н", "У", "О", "."]:
                            if exist_cl:
                                cur.execute("UPDATE grades SET grade = %s WHERE id = %s", (cl_val, exist_cl["id"]))
                            else:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'class', 1)", (st_id, col_id, cl_val))
                        elif exist_cl:
                            cur.execute("DELETE FROM grades WHERE id = %s", (exist_cl["id"],))

                        hw_val = request.form.get(f"hw_grade_{st_id}", "").strip().upper()
                        cur.execute("SELECT id FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = 'homework'", (st_id, col_id))
                        exist_hw = cur.fetchone()
                        if hw_val in ["2", "3", "4", "5", "Н", "У", "О", "."]:
                            if exist_hw:
                                cur.execute("UPDATE grades SET grade = %s WHERE id = %s", (hw_val, exist_hw["id"]))
                            else:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'homework', 1)", (st_id, col_id, hw_val))
                        elif exist_hw:
                            cur.execute("DELETE FROM grades WHERE id = %s", (exist_hw["id"],))
                    else:
                        work_val = request.form.get(f"work_grade_{col_id}_{st_id}", "").strip().upper()
                        cur.execute("SELECT id FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = 'class'", (st_id, col_id))
                        exist_w = cur.fetchone()
                        if work_val in ["2", "3", "4", "5", "Н", "У", "О", "."]:
                            if exist_w:
                                cur.execute("UPDATE grades SET grade = %s, weight = %s WHERE id = %s", (work_val, c_weight, exist_w["id"]))
                            else:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'class', %s)", (st_id, col_id, work_val, c_weight))
                        elif exist_w:
                            cur.execute("DELETE FROM grades WHERE id = %s", (exist_w["id"],))

            conn.commit()
            flash("Оценки успешно сохранены!", "success")

            if action == "save_and_return":
                cur.close()
                conn.close()
                return redirect(url_for("teacher_panel", class_id=lesson["class_id"], subject_id=lesson["subject_id"], period_id=period_id))

            cur.close()
            conn.close()
            return redirect(url_for("edit_lesson", lesson_id=main_lesson_id, period_id=period_id))

    cur.execute("""
        SELECT * FROM lessons 
        WHERE (parent_id = %s OR (class_id = %s AND subject_id = %s AND lesson_date = %s AND id != %s))
        ORDER BY id ASC
    """, (main_lesson_id, lesson["class_id"], lesson["subject_id"], lesson["lesson_date"], main_lesson_id))
    extra_works = cur.fetchall()

    cur.execute("SELECT * FROM students WHERE class_id = %s ORDER BY fio", (lesson["class_id"],))
    students = cur.fetchall()

    all_ids = [main_lesson_id] + [w["id"] for w in extra_works]
    cur.execute("SELECT * FROM grades WHERE lesson_id = ANY(%s)", (all_ids,))
    raw_grades = cur.fetchall()
    
    lesson_grades = {}
    for g in raw_grades:
        g_type = g["grade_type"] if "grade_type" in g.keys() and g["grade_type"] else "class"
        lesson_grades[(g["student_id"], g["lesson_id"], g_type)] = g["grade"]

    cur.close()
    conn.close()

    return render_template(
        "lesson_card.html",
        fio=session.get("fio"),
        lesson=lesson,
        extra_works=extra_works,
        students=students,
        lesson_grades=lesson_grades,
        period_id=period_id
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
        cur.execute("""
            SELECT l.id, l.lesson_number, l.lesson_date, l.topic, l.homework, l.lesson_type, s.name as subject_name
            FROM lessons l
            JOIN subjects s ON l.subject_id = s.id
            WHERE l.class_id = %s AND l.lesson_date = %s AND l.lesson_type = 'lesson'
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

# --- СВОДНАЯ ВЕДОМОСТЬ ---
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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
