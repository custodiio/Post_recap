import json
import os
import sqlite3
import requests

def test():
    db_path = "/home/ubuntu/apps/database/users.db"
    access_token = None
    
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT access_token FROM tiktok_connections ORDER BY connected_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            access_token = row[0]
            print("Loaded access_token from users.db")
        conn.close()
        
    if not access_token:
        print("No access token found!")
        return
        
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    video_size = 171302532
    real_failed_title = "ELA TEM UM FERRÃO MISTERIOSO... E QUEM TOCAR NELE TEM QUE SE CASAR! | Desconhecido EP 1"
    
    # Casos de teste
    tests = [
        ("A: chunk_size=64MiB, count=2", 64 * 1024 * 1024, 2),
        ("B: chunk_size=50MiB, count=3", 50 * 1024 * 1024, 3),
        ("C: chunk_size=64MB, count=2", 64 * 1000 * 1000, 2),
        ("D: chunk_size=50MB, count=3", 50 * 1000 * 1000, 3),
        ("E: chunk_size=60MiB, count=2", 60 * 1024 * 1024, 2),
    ]
    
    for name, chunk_size, count in tests:
        payload = {
            "post_info": {
                "title": real_failed_title,
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": True,
                "disable_stitch": True,
                "disable_comment": False
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": count
            }
        }
        print(f"Testando {name}...")
        res = requests.post(init_url, headers=headers, json=payload)
        print(f"Status: {res.status_code}")
        print(f"Body: {res.text}\n")

if __name__ == "__main__":
    test()
