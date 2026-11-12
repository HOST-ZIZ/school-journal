from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import get_db, init_db
import datetime
import random

app = Flask(__name__)
app.secret_key = "asu_rso_local_secure_key"

try:
    init_db()
except Exception as e:
    print(f"Ошибка при инициализации базы: {e}")


def check_teacher_access(cur, user_id, role, class_id, subject_id):
    """Возвращает 'full' (полный доступ) или 'attendance_only' (только Н, У, О и просмотр)."""
    if role == "admin":
        return "full"
    cur.execute("SELECT homeroom_class_id FROM users WHERE id = %s", (user_id,))
    u_row = cur.fetchone()
    if u_row and u_row.get("homeroom_class_id") and int(u_row["homeroom_class_id"]) == int(class_id):
        return "full"
    cur.execute("SELECT 1 FROM teacher_subjects WHERE user_id = %s AND subject_id = %s", (user_id, subject_id))
    if cur.fetchone():
        return "full"
    return "attendance_only"


def get_subjects_for_class(cur, class_id):
    """Возвращает предметы, привязанные к классу (если не настроены — все предметы)."""
    if class_id:
        cur.execute("""
            SELECT s.* FROM subjects s
            JOIN class_subjects cs ON s.id = cs.subject_id
            WHERE cs.class_id = %s
            ORDER BY s.name
        """, (class_id,))
        linked = cur.fetchall()
        if linked:
            return linked
    cur.execute("SELECT * FROM subjects ORDER BY name")
    return cur.fetchall()


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin_panel"))
    if role == "student":
        return redirect(url_for("student_diary"))
    return redirect(url_for("teacher_panel"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_val = request.form.get("login", "").strip()
        pass_val = request.form.get("password", "").strip()
        conn = get_db()
        cur = conn.cursor()

        # 1. Проверка среди администраторов и учителей
        cur.execute("SELECT * FROM users WHERE login = %s AND password = %s", (login_val, pass_val))
        user = cur.fetchone()
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["fio"] = user["fio"]
            session["role"] = user["role"]
            cur.close()
            conn.close()
            return redirect(url_for("index"))

        # 2. Проверка среди учеников
        cur.execute("SELECT * FROM students WHERE login = %s AND password = %s", (login_val, pass_val))
        student = cur.fetchone()
        if student:
            session.clear()
            session["user_id"] = student["id"]
            session["student_id"] = student["id"]
            session["class_id"] = student["class_id"]
            session["fio"] = student["fio"]
            session["role"] = "student"
            cur.close()
            conn.close()
            return redirect(url_for("student_diary"))

        cur.close()
        conn.close()
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
            st_login = request.form.get("login", "").strip() or None
            st_pass = request.form.get("password", "").strip() or None
            if fio and class_id:
                try:
                    cur.execute(
                        "INSERT INTO students (fio, class_id, login, password) VALUES (%s, %s, %s, %s)",
                        (fio, class_id, st_login, st_pass)
                    )
                    conn.commit()
                    flash(f"Ученик {fio} добавлен!", "success")
                except:
                    conn.rollback()
                    flash("Ошибка: такой логин ученика уже занят!", "error")

        elif action == "update_student_creds":
            student_id = request.form.get("student_id")
            st_login = request.form.get("login", "").strip() or None
            st_pass = request.form.get("password", "").strip() or None
            if request.form.get("auto_gen") == "1":
                st_login = f"st{student_id}_{random.randint(10, 99)}"
                st_pass = str(random.randint(10000, 99999))
            if student_id:
                try:
                    cur.execute(
                        "UPDATE students SET login = %s, password = %s WHERE id = %s",
                        (st_login, st_pass, student_id)
                    )
                    conn.commit()
                    flash("Логин и пароль ученика обновлены!", "success")
                except:
                    conn.rollback()
                    flash("Этот логин уже используется другим учеником!", "error")

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

        elif action == "save_class_subjects":
            c_id = request.form.get("class_id", type=int)
            selected_subs = request.form.getlist("subject_ids")
            if c_id:
                cur.execute("DELETE FROM class_subjects WHERE class_id = %s", (c_id,))
                for s_id in selected_subs:
                    cur.execute(
                        "INSERT INTO class_subjects (class_id, subject_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (c_id, int(s_id))
                    )
                conn.commit()
                flash("Предметы для класса сохранены!", "success")

        elif action == "add_teacher":
            fio = request.form.get("fio", "").strip()
            login_u = request.form.get("login", "").strip()
            pass_u = request.form.get("password", "").strip()
            homeroom_id = request.form.get("homeroom_class_id") or None
            if fio and login_u and pass_u:
                try:
                    cur.execute(
                        "INSERT INTO users (fio, login, password, role, homeroom_class_id) VALUES (%s, %s, %s, 'teacher', %s)",
                        (fio, login_u, pass_u, homeroom_id)
                    )
                    conn.commit()
                    flash(f"Учитель {fio} зарегистрирован!", "success")
                except:
                    conn.rollback()
                    flash("Логин занят!", "error")

        elif action == "update_teacher":
            t_id = request.form.get("teacher_id", type=int)
            new_pass = request.form.get("new_password", "").strip()
            homeroom_id = request.form.get("homeroom_class_id") or None
            if t_id:
                if new_pass:
                    cur.execute(
                        "UPDATE users SET password = %s, homeroom_class_id = %s WHERE id = %s",
                        (new_pass, homeroom_id, t_id)
                    )
                else:
                    cur.execute(
                        "UPDATE users SET homeroom_class_id = %s WHERE id = %s",
                        (homeroom_id, t_id)
                    )
                conn.commit()
                flash("Данные учителя обновлены!", "success")

        elif action == "add_teacher_subject":
            t_id = request.form.get("teacher_id", type=int)
            s_id = request.form.get("subject_id", type=int)
            if t_id and s_id:
                cur.execute(
                    "INSERT INTO teacher_subjects (user_id, subject_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (t_id, s_id)
                )
                conn.commit()
                flash("Предмет назначен учителю!", "success")

        elif action == "remove_teacher_subject":
            t_id = request.form.get("teacher_id", type=int)
            s_id = request.form.get("subject_id", type=int)
            if t_id and s_id:
                cur.execute("DELETE FROM teacher_subjects WHERE user_id = %s AND subject_id = %s", (t_id, s_id))
                conn.commit()
                flash("Предмет убран у учителя!", "info")

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
    cur.execute("""
        SELECT u.*, c.name as homeroom_class_name 
        FROM users u 
        LEFT JOIN classes c ON u.homeroom_class_id = c.id 
        WHERE u.role = 'teacher' 
        ORDER BY u.fio
    """)
    teachers = cur.fetchall()

    cur.execute("""
        SELECT ts.user_id, s.id as subject_id, s.name as subject_name
        FROM teacher_subjects ts
        JOIN subjects s ON ts.subject_id = s.id
        ORDER BY s.name
    """)
    teacher_subs_map = {}
    for row in cur.fetchall():
        teacher_subs_map.setdefault(row["user_id"], []).append(row)

    cur.execute("SELECT class_id, subject_id FROM class_subjects")
    class_subs_map = {}
    for row in cur.fetchall():
        class_subs_map.setdefault(row["class_id"], set()).add(row["subject_id"])

    cur.execute("SELECT * FROM periods ORDER BY start_date")
    periods = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "admin.html",
        fio=session.get("fio"),
        classes=classes,
        students=students,
        subjects=subjects,
        teachers=teachers,
        teacher_subs_map=teacher_subs_map,
        class_subs_map=class_subs_map,
        periods=periods
    )


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
    subjects = get_subjects_for_class(cur, class_id)
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
    if "user_id" not in session or session.get("role") == "student":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    class_id = request.args.get("class_id", type=int)
    subject_id = request.args.get("subject_id", type=int)
    period_id = request.args.get("period_id", type=int)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_journal":
            c_id = request.form.get("class_id", type=int)
            s_id = request.form.get("subject_id", type=int)
            p_id = request.form.get("period_id", type=int)

            access = check_teacher_access(cur, session.get("user_id"), session.get("role"), c_id, s_id)

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

                        cur.execute("SELECT id, grade FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = 'class'", (st_id, les_id))
                        exist_class = cur.fetchone()

                        if access == "attendance_only":
                            # Чужой предмет: разрешено только ставить/удалять Н, У, О
                            if val_class in ["Н", "У", "О"]:
                                if not exist_class or exist_class["grade"] in ["Н", "У", "О"]:
                                    if exist_class:
                                        cur.execute("UPDATE grades SET grade = %s WHERE id = %s", (val_class, exist_class["id"]))
                                    else:
                                        cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'class', 1)", (st_id, les_id, val_class))
                            elif val_class == "" and exist_class and exist_class["grade"] in ["Н", "У", "О"]:
                                cur.execute("DELETE FROM grades WHERE id = %s", (exist_class["id"],))
                            continue

                        # Полный доступ (предметник по своему предмету, классный руководитель или админ)
                        if val_class in ["2", "3", "4", "5", "Н", "У", "О", "."]:
                            if exist_class:
                                cur.execute("UPDATE grades SET grade = %s, weight = %s WHERE id = %s", (val_class, w_class, exist_class["id"]))
                            else:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'class', %s)", (st_id, les_id, val_class, w_class))
                        else:
                            if exist_class:
                                cur.execute("DELETE FROM grades WHERE id = %s", (exist_class["id"],))

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

                # Сохранение ручных итоговых оценок (четверть, год, экзамен, итоговая)
                elif key.startswith("final_") and access == "full":
                    parts = key.split("_")
                    if len(parts) == 3:
                        f_type, st_id = parts[1], int(parts[2])
                        f_val = val.strip()
                        target_period = p_id if f_type == "period" else 0

                        if f_val:
                            cur.execute("""
                                INSERT INTO final_grades (student_id, subject_id, period_id, grade_type, grade)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (student_id, subject_id, period_id, grade_type)
                                DO UPDATE SET grade = EXCLUDED.grade
                            """, (st_id, s_id, target_period, f_type, f_val))
                        else:
                            cur.execute("""
                                DELETE FROM final_grades 
                                WHERE student_id = %s AND subject_id = %s AND period_id = %s AND grade_type = %s
                            """, (st_id, s_id, target_period, f_type))

            conn.commit()
            cur.close()
            conn.close()
            flash("Журнал и итоговые оценки сохранены!", "success")
            return redirect(url_for("teacher_panel", class_id=c_id, subject_id=s_id, period_id=p_id))

    cur.execute("SELECT * FROM classes ORDER BY name")
    classes = cur.fetchall()
    subjects = get_subjects_for_class(cur, class_id)
    cur.execute("SELECT * FROM periods ORDER BY start_date")
    periods = cur.fetchall()

    # Если выбран класс, но выбранный предмет не входит в предметы этого класса — сбрасываем subject_id
    valid_sub_ids = {s["id"] for s in subjects}
    if subject_id and valid_sub_ids and subject_id not in valid_sub_ids:
        subject_id = None

    students = []
    lessons = []
    month_groups = []
    cell_values = {}
    student_stats = {}
    final_marks = {}
    access_mode = "full"

    months_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }

    if class_id and subject_id and period_id:
        access_mode = check_teacher_access(cur, session.get("user_id"), session.get("role"), class_id, subject_id)

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

        # Загружаем ручные итоговые оценки (за выбранный период и годовые/экзаменационные/итоговые)
        cur.execute("""
            SELECT student_id, grade_type, grade FROM final_grades
            WHERE subject_id = %s AND (period_id = %s OR period_id = 0)
        """, (subject_id, period_id))
        for fg in cur.fetchall():
            final_marks[(fg["student_id"], fg["grade_type"])] = fg["grade"]

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
            suggested = ""
            if avg >= 4.5: suggested = "5"
            elif avg >= 3.5: suggested = "4"
            elif avg >= 2.5: suggested = "3"
            elif avg > 0: suggested = "2"

            student_stats[st["id"]] = {
                "avg": f"{avg:.2f}" if avg > 0 else "-",
                "suggested": suggested
            }

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
        student_stats=student_stats,
        final_marks=final_marks,
        access_mode=access_mode
    )


# --- УДАЛЕНИЕ ПРОВЕРОЧНОЙ КОЛОНКИ ---
@app.route("/lesson/delete/<int:lesson_id>", methods=["POST"])
def delete_lesson_route(lesson_id):
    if "user_id" not in session or session.get("role") == "student":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT class_id, subject_id, lesson_date, parent_id FROM lessons WHERE id = %s", (lesson_id,))
    les = cur.fetchone()

    period_id = request.form.get("period_id", type=int)

    if les:
        access = check_teacher_access(cur, session.get("user_id"), session.get("role"), les["class_id"], les["subject_id"])
        if access != "full":
            flash("У вас нет прав удалять работы по чужому предмету!", "error")
            cur.close()
            conn.close()
            return redirect(url_for("teacher_panel", class_id=les["class_id"], subject_id=les["subject_id"], period_id=period_id))

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


# --- КАРТОЧКА УРОКА ---
@app.route("/lesson/<int:lesson_id>", methods=["GET", "POST"])
def edit_lesson(lesson_id):
    if "user_id" not in session or session.get("role") == "student":
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

    access_mode = check_teacher_access(cur, session.get("user_id"), session.get("role"), lesson["class_id"], lesson["subject_id"])
    main_lesson_id = lesson["parent_id"] if lesson.get("parent_id") else lesson["id"]

    period_id = request.args.get("period_id", type=int) or request.form.get("period_id", type=int)
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
        
        if action == "add_work_column":
            if access_mode != "full":
                flash("Нельзя создавать проверочные работы по чужому предмету!", "error")
                cur.close()
                conn.close()
                return redirect(url_for("edit_lesson", lesson_id=main_lesson_id, period_id=period_id))

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

        elif action in ["save_all", "save_and_return"]:
            if access_mode == "full":
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

                if access_mode == "attendance_only":
                    cur.execute("SELECT id, grade FROM grades WHERE student_id = %s AND lesson_id = %s AND grade_type = 'class'", (st_id, main_lesson_id))
                    exist_cl = cur.fetchone()
                    if att_val in ["Н", "У", "О"]:
                        if not exist_cl or exist_cl["grade"] in ["Н", "У", "О"]:
                            if exist_cl:
                                cur.execute("UPDATE grades SET grade = %s WHERE id = %s", (att_val, exist_cl["id"]))
                            else:
                                cur.execute("INSERT INTO grades (student_id, lesson_id, grade, grade_type, weight) VALUES (%s, %s, %s, 'class', 1)", (st_id, main_lesson_id, att_val))
                    elif att_val == "" and exist_cl and exist_cl["grade"] in ["Н", "У", "О"]:
                        cur.execute("DELETE FROM grades WHERE id = %s", (exist_cl["id"],))
                    continue

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
            flash("Данные сохранены!", "success")

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
        period_id=period_id,
        access_mode=access_mode
    )


# --- ЭЛЕКТРОННЫЙ ДНЕВНИК УЧЕНИКА ---
@app.route("/diary")
def student_diary():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    role = session.get("role")
    if role == "student":
        class_id = session.get("class_id")
        student_id = session.get("student_id")
    else:
        class_id = request.args.get("class_id", type=int)
        student_id = request.args.get("student_id", type=int)

    selected_date = request.args.get("date", datetime.date.today().isoformat())
    selected_period = request.args.get("period_id", type=int)
    active_tab = request.args.get("tab", "diary")  # 'diary' или 'grades'

    cur.execute("SELECT * FROM classes ORDER BY name")
    classes = cur.fetchall()

    cur.execute("SELECT * FROM periods ORDER BY start_date")
    periods = cur.fetchall()
    if not selected_period and periods:
        selected_period = periods[0]["id"]

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

    # Данные для вкладки "Четвертные / Итоговые оценки"
    quarter_summary = []
    if class_id and student_id:
        class_subjects = get_subjects_for_class(cur, class_id)
        period_obj = next((p for p in periods if p["id"] == selected_period), None)

        cur.execute("""
            SELECT subject_id, period_id, grade_type, grade
            FROM final_grades
            WHERE student_id = %s
        """, (student_id,))
        fg_map = {}
        for row in cur.fetchall():
            fg_map[(row["subject_id"], row["period_id"], row["grade_type"])] = row["grade"]

        for sub in class_subjects:
            sub_id = sub["id"]
            # Оценки за выбранную четверть
            cur.execute("""
                SELECT g.grade, g.weight, l.lesson_date
                FROM grades g
                JOIN lessons l ON g.lesson_id = l.id
                WHERE g.student_id = %s AND l.class_id = %s AND l.subject_id = %s
                  AND (%s IS NULL OR l.lesson_date BETWEEN %s AND %s)
                ORDER BY l.lesson_date ASC, l.id ASC
            """, (
                student_id, class_id, sub_id,
                period_obj["start_date"] if period_obj else None,
                period_obj["start_date"] if period_obj else "1900-01-01",
                period_obj["end_date"] if period_obj else "2999-12-31"
            ))
            raw_sub_grades = cur.fetchall()

            sc, wt = 0.0, 0
            marks_list = []
            for r in raw_sub_grades:
                marks_list.append(r["grade"])
                if r["grade"] in ["2", "3", "4", "5"]:
                    w = r["weight"] if r["weight"] else 1
                    sc += int(r["grade"]) * w
                    wt += w

            avg_val = f"{round(sc / wt, 2):.2f}" if wt > 0 else "-"

            quarter_summary.append({
                "subject": sub["name"],
                "marks": marks_list,
                "avg": avg_val,
                "period_grade": fg_map.get((sub_id, selected_period or 0, "period"), ""),
                "year_grade": fg_map.get((sub_id, 0, "year"), ""),
                "exam_grade": fg_map.get((sub_id, 0, "exam"), ""),
                "final_grade": fg_map.get((sub_id, 0, "final"), "")
            })

    cur.close()
    conn.close()

    return render_template(
        "diary.html",
        fio=session.get("fio"),
        role=role,
        classes=classes,
        students=students,
        periods=periods,
        selected_class=class_id,
        selected_student=student_id,
        selected_date=selected_date,
        selected_period=selected_period,
        active_tab=active_tab,
        timetable=timetable,
        quarter_summary=quarter_summary
    )


# --- СВОДНАЯ ВЕДОМОСТЬ ---
@app.route("/report")
def class_report():
    if "user_id" not in session or session.get("role") == "student":
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
        subjects = get_subjects_for_class(cur, class_id)
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
