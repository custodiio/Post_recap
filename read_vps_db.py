import sqlite3
import os

def read_db(db_path, name):
    if not os.path.exists(db_path):
        print(f"Banco {name} não encontrado em {db_path}")
        return
    print(f"\n--- POST LOGS ({name}) ---")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Verifica dinamicamente as colunas da tabela post_logs
    cursor.execute("PRAGMA table_info(post_logs)")
    columns = [c[1] for c in cursor.fetchall()]
    title_col = "title" if "title" in columns else "tiktok_title"
    
    cursor.execute(f"SELECT id, {title_col}, tiktok_status, error_message, created_at FROM post_logs ORDER BY id DESC LIMIT 5")
    for row in cursor.fetchall():
        print(f"ID: {row[0]}\nTITLE: {row[1]}\nSTATUS: {row[2]}\nERR: {row[3]}\nDATE: {row[4]}\n")
    conn.close()

def main():
    read_db("/home/ubuntu/apps/Post_recap/posts.db", "Kuma Recaps")
    read_db("/home/ubuntu/apps/database/dramas.db", "Dramas")

if __name__ == "__main__":
    main()
