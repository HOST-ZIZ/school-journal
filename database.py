import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if not DATABASE_URL:
        raise ValueError("Ошибка: переменная окружения DATABASE_URL не задана!")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

def init_db():
    if not DATABASE_URL:
        print("Внимание: DATABASE_URL не задана!")
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            fio TEXT NOT NULL,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            fio TEXT NOT NULL,
            class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS periods (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            id SERIAL PRIMARY KEY,
            class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            lesson_date TEXT NOT NULL,
            lesson_number INTEGER DEFAULT 1,
            topic TEXT,
            homework TEXT,
            is_held INTEGER DEFAULT 1,
            lesson_type TEXT DEFAULT 'lesson',
            weight INTEGER DEFAULT 1,
            parent_id INTEGER
        )
    """)

    # Миграция колонок, если таблица уже существовала в Supabase
    cur.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='lesson_number') THEN
                ALTER TABLE lessons ADD COLUMN lesson_number INTEGER DEFAULT 1;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='weight') THEN
                ALTER TABLE lessons ADD COLUMN weight INTEGER DEFAULT 1;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lessons' AND column_name='parent_id') THEN
                ALTER TABLE lessons ADD COLUMN parent_id INTEGER;
            END IF;
        END $$;
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
            grade TEXT NOT NULL,
            grade_type TEXT NOT NULL DEFAULT 'class',
            weight INTEGER DEFAULT 1,
            comment TEXT
        )
    """)

    cur.execute("SELECT id FROM users WHERE login = %s", ('admin',))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (fio, login, password, role)
            VALUES (%s, %s, %s, %s)
        """, ('Главный Администратор', 'admin', '17825862', 'admin'))
        
        cur.execute("""
            INSERT INTO users (fio, login, password, role)
            VALUES (%s, %s, %s, %s)
        """, ('Иван Сергеевич (Учитель)', 'teacher', '123', 'teacher'))

    conn.commit()
    cur.close()
    conn.close()
    print("Таблицы в Supabase готовы к работе.")

if __name__ == "__main__":
    init_db()
