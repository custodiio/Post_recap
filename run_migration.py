import sys
import os
import sqlite3

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(base_dir, "tiktok_approval", "backend")
    sys.path.append(backend_dir)
    
    import db_helper
    print("Initializing database...")
    db_helper.init_db()
    
    db_path = os.path.join(base_dir, "tiktok_approval", "database", "users.db")
    print(f"Connecting to database at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Approve user
    email = "alecust123@gmail.com"
    print(f"Approving user: {email}")
    cursor.execute("INSERT OR REPLACE INTO approved_users (email, approved) VALUES (?, 1)", (email,))
    
    conn.commit()
    conn.close()
    print("Database migration and user approval completed successfully!")

if __name__ == "__main__":
    main()
