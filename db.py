import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabela de posts gerais
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS post_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_path TEXT,
        youtube_title TEXT,
        tiktok_title TEXT,
        instagram_caption TEXT,
        youtube_status TEXT DEFAULT 'skipped',
        tiktok_status TEXT DEFAULT 'skipped',
        instagram_status TEXT DEFAULT 'skipped',
        youtube_url TEXT,
        tiktok_url TEXT,
        instagram_url TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela de fila do Instagram
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS instagram_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_drive_path TEXT,
        caption TEXT,
        cover_drive_path TEXT,
        scheduled_time TEXT, -- Formato YYYY-MM-DD HH:MM:SS
        status TEXT DEFAULT 'pending', -- 'pending', 'completed', 'failed'
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabela de publicações programadas locais (vídeos salvos na VM)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduled_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_path TEXT,
        thumbnail_youtube TEXT,
        thumbnail_tiktok TEXT,
        title_youtube TEXT,
        title_shorts TEXT,
        tiktok_caption TEXT,
        instagram_caption TEXT,
        post_youtube INTEGER DEFAULT 0,
        post_shorts INTEGER DEFAULT 0,
        post_tiktok INTEGER DEFAULT 0,
        post_instagram INTEGER DEFAULT 0,
        tiktok_privacy TEXT,
        scheduled_time TEXT, -- Formato YYYY-MM-DD HH:MM:SS
        status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

def log_post(video_path, youtube_title, tiktok_title, instagram_caption,
             youtube_status='skipped', tiktok_status='skipped', instagram_status='skipped'):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO post_logs (
        video_path, youtube_title, tiktok_title, instagram_caption, 
        youtube_status, tiktok_status, instagram_status
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (video_path, youtube_title, tiktok_title, instagram_caption, 
          youtube_status, tiktok_status, instagram_status))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return post_id

def update_post_status(post_id, platform, status, url=None, error=None):
    """
    Atualiza o status de postagem para uma plataforma específica (youtube, tiktok, instagram).
    """
    if platform not in ['youtube', 'tiktok', 'instagram']:
        raise ValueError("Plataforma inválida para atualização de status.")
        
    conn = get_connection()
    cursor = conn.cursor()
    
    status_field = f"{platform}_status"
    url_field = f"{platform}_url"
    
    if url:
        cursor.execute(f"""
        UPDATE post_logs 
        SET {status_field} = ?, {url_field} = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (status, url, error, post_id))
    else:
        cursor.execute(f"""
        UPDATE post_logs 
        SET {status_field} = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (status, error, post_id))
        
    conn.commit()
    conn.close()

def add_to_instagram_queue(video_drive_path, caption, cover_drive_path, scheduled_time):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO instagram_queue (
        video_drive_path, caption, cover_drive_path, scheduled_time
    ) VALUES (?, ?, ?, ?)
    """, (video_drive_path, caption, cover_drive_path, scheduled_time))
    queue_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return queue_id

def get_pending_instagram_jobs():
    conn = get_connection()
    cursor = conn.cursor()
    # Pega itens pendentes cuja data agendada já passou em relação ao horário atual
    cursor.execute("""
    SELECT id, video_drive_path, caption, cover_drive_path, scheduled_time
    FROM instagram_queue
    WHERE status = 'pending' AND datetime(scheduled_time) <= datetime('now', 'localtime')
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_queue_status(queue_id, status, error=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE instagram_queue
    SET status = ?, error_message = ?
    WHERE id = ?
    """, (status, error, queue_id))
    conn.commit()
    conn.close()

def add_scheduled_post(video_path, thumbnail_youtube, thumbnail_tiktok,
                       title_youtube, title_shorts, tiktok_caption, instagram_caption,
                       post_youtube, post_shorts, post_tiktok, post_instagram,
                       tiktok_privacy, scheduled_time):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO scheduled_posts (
        video_path, thumbnail_youtube, thumbnail_tiktok,
        title_youtube, title_shorts, tiktok_caption, instagram_caption,
        post_youtube, post_shorts, post_tiktok, post_instagram,
        tiktok_privacy, scheduled_time
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (video_path, thumbnail_youtube, thumbnail_tiktok,
          title_youtube, title_shorts, tiktok_caption, instagram_caption,
          int(post_youtube), int(post_shorts), int(post_tiktok), int(post_instagram),
          tiktok_privacy, scheduled_time))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return post_id

def get_pending_scheduled_posts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, video_path, thumbnail_youtube, thumbnail_tiktok,
           title_youtube, title_shorts, tiktok_caption, instagram_caption,
           post_youtube, post_shorts, post_tiktok, post_instagram,
           tiktok_privacy, scheduled_time
    FROM scheduled_posts
    WHERE status = 'pending' AND datetime(scheduled_time) <= datetime('now', 'localtime')
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_scheduled_post_status(post_id, status, error=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE scheduled_posts
    SET status = ?, error_message = ?
    WHERE id = ?
    """, (status, error, post_id))
    conn.commit()
    conn.close()

def get_all_pending_scheduled():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, scheduled_time, title_youtube, title_shorts, tiktok_caption,
           post_youtube, post_shorts, post_tiktok, post_instagram, status
    FROM scheduled_posts
    WHERE status = 'pending' OR status = 'failed'
    ORDER BY scheduled_time ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_scheduled_post(post_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT video_path, thumbnail_youtube, thumbnail_tiktok
    FROM scheduled_posts
    WHERE id = ?
    """, (post_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
        conn.commit()
    conn.close()
    return row

# Inicializar o banco de dados ao importar
init_db()
