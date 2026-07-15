import os
import sqlite3

def main():
    # Caminho do banco na VPS
    db_path = "/home/ubuntu/apps/database/users.db"
    
    # Se rodar localmente (fallback)
    if not os.path.exists(db_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "tiktok_approval", "database", "users.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
    print(f"Conectando ao banco de dados em: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Garantir tabelas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS approved_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        approved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tiktok_connections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        access_token TEXT NOT NULL,
        refresh_token TEXT,
        open_id TEXT,
        username TEXT,
        avatar TEXT,
        connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(email) REFERENCES approved_users(email)
    )
    """)
    
    # 2. Tentar adicionar coluna refresh_token caso a tabela tenha sido criada sem ela
    try:
        cursor.execute("ALTER TABLE tiktok_connections ADD COLUMN refresh_token TEXT")
        print("Coluna 'refresh_token' adicionada com sucesso.")
    except sqlite3.OperationalError:
        print("Coluna 'refresh_token' já existe.")
        
    # 3. Aprovar o usuário alecust123@gmail.com
    email = "alecust123@gmail.com"
    print(f"Aprovando o usuário: {email}")
    cursor.execute("INSERT OR REPLACE INTO approved_users (email, approved) VALUES (?, 1)", (email,))
    
    conn.commit()
    conn.close()
    print("Migração concluída com sucesso no banco de dados!")

if __name__ == "__main__":
    main()
