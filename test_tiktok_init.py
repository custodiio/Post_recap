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
        token_path = "/home/ubuntu/apps/Post_recap/token.json"
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                token_data = json.load(f)
                access_token = token_data.get("access_token")
                print("Loaded access_token from token.json")
                
    if not access_token:
        print("No access token found anywhere!")
        return
        
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    # 1. Testar payload com chaves básicas
    payload = {
        "post_info": {
            "title": "Teste de post",
            "privacy_level": "SELF_ONLY",
            "disable_duet": True,
            "disable_stitch": True,
            "disable_comment": False
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": 1000000,
            "chunk_size": 1000000,
            "total_chunk_count": 1
        }
    }
    print("Testando payload básico...")
    res = requests.post(init_url, headers=headers, json=payload)
    print(f"Status: {res.status_code}")
    print(f"Body: {res.text}\n")
    
    # 2. Testar payload apenas com title e privacy_level
    payload2 = {
        "post_info": {
            "title": "Teste de post",
            "privacy_level": "SELF_ONLY"
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": 1000000,
            "chunk_size": 1000000,
            "total_chunk_count": 1
        }
    }
    print("Testando payload minimalista (apenas title e privacy_level)...")
    res2 = requests.post(init_url, headers=headers, json=payload2)
    print(f"Status: {res2.status_code}")
    print(f"Body: {res2.text}\n")

if __name__ == "__main__":
    test()
