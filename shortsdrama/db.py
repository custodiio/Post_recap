import os
import sqlite3
from datetime import datetime

# Define o caminho do banco de dados dependendo se está rodando localmente ou na VPS
if os.path.exists('/home/ubuntu/apps'):
    DB_DIR = '/home/ubuntu/apps/database'
else:
    DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database')

os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'dramas.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabela de Dramas principais minerados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dramas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            telegram_message_id INTEGER,
            telegram_chat_id TEXT,
            duration_sec INTEGER,
            file_size INTEGER,
            caption TEXT,
            original_file_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabela de Partes/Cortes do Drama para postagem
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drama_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drama_id INTEGER,
            part_number INTEGER NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            duration REAL NOT NULL,
            status TEXT DEFAULT 'pending', -- pending, scheduled, processing, posted, failed
            platform TEXT DEFAULT 'both', -- tiktok, youtube, both
            scheduled_time TIMESTAMP,
            tiktok_publish_id TEXT,
            youtube_video_id TEXT,
            posted_at TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (drama_id) REFERENCES dramas (id) ON DELETE CASCADE
        )
    ''')
    
    # Tabela de Configurações gerais
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Insere configurações padrão se não existirem
    default_settings = {
        'tiktok_auto_post': '0',        # 0 = desligado, 1 = ligado
        'youtube_auto_post': '0',       # 0 = desligado, 1 = ligado
        'posts_per_day': '2',
        'scheduled_hours': '12:00,18:00', # Horários base separados por vírgula
        'last_cron_run': '',
        'youtube_default_privacy': 'private' # private, public, unlisted
    }
    
    for key, value in default_settings.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
        
    conn.commit()
    conn.close()
    print(f"[DB] Banco de dados de dramas inicializado em: {DB_PATH}")

# Funções auxiliares para manipulação do banco

def save_drama(title, msg_id, chat_id, duration, file_size, caption, file_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO dramas (title, telegram_message_id, telegram_chat_id, duration_sec, file_size, caption, original_file_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (title, msg_id, chat_id, duration, file_size, caption, file_name))
    drama_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return drama_id

def get_all_dramas():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dramas ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_drama(drama_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dramas WHERE id = ?', (drama_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_drama(drama_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM dramas WHERE id = ?', (drama_id,))
    conn.commit()
    conn.close()

def save_part(drama_id, part_number, start_time, end_time, duration, status='pending', platform='both', scheduled_time=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO drama_parts (drama_id, part_number, start_time, end_time, duration, status, platform, scheduled_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (drama_id, part_number, start_time, end_time, duration, status, platform, scheduled_time))
    part_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return part_id

def update_part(part_id, data):
    conn = get_connection()
    cursor = conn.cursor()
    fields = ", ".join([f"{k} = ?" for k in data.keys()])
    values = list(data.values())
    values.append(part_id)
    cursor.execute(f"UPDATE drama_parts SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()

def get_parts_for_drama(drama_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM drama_parts WHERE drama_id = ? ORDER BY part_number ASC', (drama_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pending_parts(platform=None):
    conn = get_connection()
    cursor = conn.cursor()
    if platform:
        cursor.execute('''
            SELECT dp.*, d.title as drama_title, d.telegram_message_id, d.telegram_chat_id 
            FROM drama_parts dp
            JOIN dramas d ON dp.drama_id = d.id
            WHERE dp.status = 'pending' AND (dp.platform = 'both' OR dp.platform = ?)
            ORDER BY dp.scheduled_time ASC, dp.created_at ASC
        ''', (platform,))
    else:
        cursor.execute('''
            SELECT dp.*, d.title as drama_title, d.telegram_message_id, d.telegram_chat_id 
            FROM drama_parts dp
            JOIN dramas d ON dp.drama_id = d.id
            WHERE dp.status = 'pending'
            ORDER BY dp.scheduled_time ASC, dp.created_at ASC
        ''', )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_setting(key, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def update_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
