import subprocess
import time
import requests
import sys
import sqlite3
import os

def main():
    try:
        conn = sqlite3.connect("mcs.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM branches LIMIT 1")
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO projects (name) VALUES ('Test Project')")
            project_id = cursor.lastrowid
            cursor.execute("INSERT INTO branches (project_id, type) VALUES (?, 'root')", (project_id,))
            branch_id = cursor.lastrowid
            conn.commit()
        else:
            branch_id = row[0]
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")
        sys.exit(1)

    print(f"Using branch ID: {branch_id}")

    with open("uvicorn_test.log", "w") as log_file:
        proc = subprocess.Popen([".venv\\Scripts\\python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], stdout=log_file, stderr=subprocess.STDOUT)
    
    time.sleep(3)
    try:
        print(f"Hitting /lineage for branch {branch_id}...")
        r = requests.get(f"http://127.0.0.1:8000/branches/{branch_id}/lineage")
        print(f"Lineage status: {r.status_code}")
        print(f"Lineage response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        proc.terminate()
        time.sleep(1)

if __name__ == "__main__":
    main()
