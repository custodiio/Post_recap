import sqlite3

def main():
    db_path = "/home/ubuntu/apps/Post_recap/posts.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- POST LOGS ---")
    cursor.execute("SELECT id, tiktok_title, tiktok_status, error_message, created_at FROM post_logs ORDER BY id DESC LIMIT 5")
    for row in cursor.fetchall():
        print(f"ID: {row[0]}\nTITLE: {row[1]}\nSTATUS: {row[2]}\nERR: {row[3]}\nDATE: {row[4]}\n")
        
    conn.close()

if __name__ == "__main__":
    main()
