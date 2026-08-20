import sqlite3
import os
import glob

DATA_DIR = os.path.join(os.environ["USERPROFILE"], ".local", "share", "opencode")
DB_PATH = os.path.join(DATA_DIR, "opencode.db")
LOG_DIR = os.path.join(DATA_DIR, "log")

print("Cleaning opencode history...")

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

before = con.execute("SELECT COUNT(*) FROM session").fetchone()[0]
print(f"sessions before: {before}")

# Delete all parts, messages, sessions (full history wipe)
del_parts = cur.execute("DELETE FROM part").rowcount
del_msgs = cur.execute("DELETE FROM message").rowcount
del_ses = cur.execute("DELETE FROM session").rowcount
cur.execute("DELETE FROM session_share")
cur.execute("DELETE FROM todo")
cur.execute("DELETE FROM permission")

con.commit()
print(f"deleted parts={del_parts} messages={del_msgs} sessions={del_ses}")

# Compact the database
print("VACUUM...")
con.execute("VACUUM")
con.close()

# Clean log directory
removed = 0
for f in glob.glob(os.path.join(LOG_DIR, "*.log")):
    os.remove(f)
    removed += 1
print(f"removed log files: {removed}")

print("Done.")
