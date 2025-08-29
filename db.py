import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
import hashlib

# ---------------------- CONNECTION ------------------------

def get_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ---------------------- AUTH ------------------------

def signup_user(name, email, password):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Create user with validator role
        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            (name, email, hash_password(password), 'validator')
        )
        conn.commit()

        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user_id = cursor.fetchone()[0]

        # Create validator-specific tables
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS dynamic_cmds_user_{user_id} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                command_id INT,
                command_text TEXT,
                processed_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS static_cmds_user_{user_id} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                command_id INT,
                command_text TEXT,
                processed_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        return True
    except mysql.connector.Error as e:
        print("Signup Error:", e)
        return False
    finally:
        cursor.close()
        conn.close()

def login_user(email, password):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM users WHERE email=%s AND password=%s",
        (email, hash_password(password))
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

# -------------------- COMMANDS --------------------

def get_commands_with_contexts():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT 
            a.id AS argument_id,
            c.id AS command_id,
            a.full_command_line,
            ctx.context_lines
        FROM commands c
        JOIN arguments a ON c.id = a.command_id
        LEFT JOIN contexts ctx ON ctx.argument_id = a.id
        ORDER BY c.id;
    """
    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    for row in results:
        if row["context_lines"]:
            row["context_lines"] = row["context_lines"].replace("\\n", "\n").replace("\\\\", "\\")
    return results


def insert_dynamic_command(user_id, cmd_id, command_text):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        INSERT INTO dynamic_cmds_user_{user_id} (command_id, command_text)
        VALUES (%s, %s)
    """, (cmd_id, command_text))
    update_last_seen(user_id)  # ✅ Update last seen here
    conn.commit()
    cursor.close()
    conn.close()

def insert_static_command(user_id, cmd_id, command_text):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        INSERT INTO static_cmds_user_{user_id} (command_id, command_text)
        VALUES (%s, %s)
    """, (cmd_id, command_text))
    update_last_seen(user_id)  # ✅ Update last seen here
    conn.commit()
    cursor.close()
    conn.close()

def get_recently_active_validators():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT name, last_seen FROM users
        WHERE role = 'validator'
        ORDER BY last_seen DESC
        LIMIT 10
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

def get_last_processed_cmd_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_processed_cmd_id FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result and result[0] else 0

def update_last_processed_cmd(user_id, cmd_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_processed_cmd_id = %s WHERE id = %s", (cmd_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()

# ---------------------- ADMIN ----------------------
def get_users():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, username, role FROM users")
        users = cursor.fetchall()
        return users
    finally:
        cursor.close()
        conn.close()


def get_all_validators():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM users WHERE role = 'validator'")
    validators = cursor.fetchall()
    cursor.close()
    conn.close()
    return validators

def get_user_counts_by_role():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE role='validator'")
    validator_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE role='viewer'")
    viewer_count = cursor.fetchone()[0]

    cursor.execute("SELECT name FROM users WHERE role='validator'")
    validator_names = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT name FROM users WHERE role='viewer'")
    viewer_names = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return validator_count, viewer_count, validator_names, viewer_names
from datetime import datetime

def update_last_seen(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_seen = %s WHERE id = %s", (datetime.now(), user_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_validator_stats(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Dynamic count
        try:
            cursor.execute(f"SELECT COUNT(*) FROM dynamic_cmds_user_{user_id}")
            dynamic_count = cursor.fetchone()[0]
        except:
            dynamic_count = 0

        # Static count
        try:
            cursor.execute(f"SELECT COUNT(*) FROM static_cmds_user_{user_id}")
            static_count = cursor.fetchone()[0]
        except:
            static_count = 0

        processed = dynamic_count + static_count

        # Total available commands
        cursor.execute("SELECT COUNT(DISTINCT id) FROM commands")
        total_commands = cursor.fetchone()[0]
        remaining = total_commands - processed

        return {
            "dynamic": dynamic_count,
            "static": static_count,
            "processed": processed,
            "remaining": remaining,
            "total": total_commands
        }

    except Exception as e:
        print("Error in get_validator_stats:", e)
        return {
            "dynamic": 0,
            "static": 0,
            "processed": 0,
            "remaining": 0,
            "total": 0
        }
    finally:
        cursor.close()
        conn.close()
