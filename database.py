import sqlite3

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fio TEXT NOT NULL,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fio TEXT NOT NULL,
            class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            lesson_date TEXT NOT NULL,
            topic TEXT,
            homework TEXT,
            is_held INTEGER DEFAULT 1,
            lesson_type TEXT DEFAULT 'lesson'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
            grade TEXT NOT NULL,
            grade_type TEXT NOT NULL DEFAULT 'class',
            weight INTEGER DEFAULT 1,
            comment TEXT
        )
    """)

    cur.execute("SELECT id FROM users WHERE login = ?", ('admin',))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (fio, login, password, role)
            VALUES (?, ?, ?, ?)
        """, ('Главный Администратор', 'admin', '17825862', 'admin'))
        
        cur.execute("""
            INSERT INTO users (fio, login, password, role)
            VALUES (?, ?, ?, ?)
        """, ('Иван Сергеевич (Учитель)', 'teacher', '123', 'teacher'))

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    init_db()
