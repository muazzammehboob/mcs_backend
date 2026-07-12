import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'mcs.db')
conn = sqlite3.connect(db_path)
conn.execute('PRAGMA foreign_keys = ON;')
cursor = conn.cursor()

cursor.execute('DELETE FROM branches;')
cursor.execute("DELETE FROM nodes WHERE type='summary';")

conn.commit()
conn.close()

print("Successfully deleted all chat history from the database.")
