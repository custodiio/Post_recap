import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")

def load_tiktok_token():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"[ERRO] Arquivo token.json não encontrado em: {TOKEN_FILE}")
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tiktok_token(token_data):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=4, ensure_ascii=False)

def refresh_tiktok_token():
    """
    Renova o access_token do TikTok usando o refresh_token.
    """
    print("Renovando token do TikTok...")
    token_data = load_tiktok_token()
    refresh_token = token_data.get("refresh_token")
    
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
    
    if not client_key or not client_secret:
        raise ValueError("[ERRO] TIKTOK_CLIENT_KEY ou TIKTOK_CLIENT_SECRET ausentes no .env")
        
    url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }
    data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    response = requests.post(url, headers=headers, data=data)
    
    if response.status_code == 200:
        res_json = response.json()
        # Se contiver erro na resposta JSON
        if "error" in res_json and res_json["error"] != "ok":
            raise Exception(f"[ERRO] Erro ao renovar token no JSON: {res_json}")
            
        # Atualiza o token
        token_data.update(res_json)
        save_tiktok_token(token_data)
        print("[OK] Token do TikTok renovado com sucesso!")
        return token_data
    else:
        raise Exception(f"[ERRO] Falha HTTP ao renovar token ({response.status_code}): {response.text}")

def get_valid_tiktok_token():
    """
    Retorna o token de acesso ativo ou tenta renová-lo.
    """
    token_data = load_tiktok_token()
    # Como não sabemos o timestamp exato de expiração, sempre tentamos usar.
    # Mas se houver erro de autorização durante a postagem, podemos chamar refresh_tiktok_token e tentar de novo.
    return token_data.get("access_token")

class ProgressFile:
    def __init__(self, filename, callback):
        self.file = open(filename, 'rb')
        self.size = os.path.getsize(filename)
        self.callback = callback
        self.read_so_far = 0
        self.last_percent = -1

    def read(self, size=-1):
        data = self.file.read(size)
        if data:
            self.read_so_far += len(data)
            percent = int((self.read_so_far / self.size) * 100)
            if percent != self.last_percent:
                print(f"[TIKTOK] Progresso de upload: {percent}%", flush=True)
                if self.callback:
                    try:
                        self.callback(percent)
                    except:
                        pass
                self.last_percent = percent
        return data

    def close(self):
        self.file.close()

def upload_video_to_tiktok(video_path, title, privacy_level="PRIVATE", progress_callback=None):
    """
    Realiza o envio de um vídeo para o TikTok (Direct Post) usando upload em chunks.
    O vídeo é enviado como privado por padrão (PRIVATE).
    Retorna o publish_id gerado pelo TikTok.
    """
    access_token = get_valid_tiktok_token()
    video_size = os.path.getsize(video_path)
    
    # Configurações de chunks para o TikTok (conforme documentação oficial)
    # 1. Cada chunk deve ter entre 5MB e 64MB (exceto o último, que pode ter até 128MB)
    # 2. O total_chunk_count deve ser igual a video_size // chunk_size (divisão inteira arredondada para baixo)
    MAX_SINGLE_CHUNK = 64 * 1000 * 1000  # 64MB
    
    if video_size <= MAX_SINGLE_CHUNK:
        actual_chunk_size = video_size
        total_chunk_count = 1
    else:
        TARGET_CHUNK_SIZE = 50 * 1000 * 1000  # 50MB
        total_chunk_count = video_size // TARGET_CHUNK_SIZE
        if total_chunk_count < 2:
            total_chunk_count = 2
            actual_chunk_size = video_size // 2
        else:
            actual_chunk_size = TARGET_CHUNK_SIZE
            
    print(f"[TIKTOK] Vídeo: {video_size} bytes, Chunk: {actual_chunk_size} bytes, Total chunks: {total_chunk_count}", flush=True)
    
    init_url = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    body = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": actual_chunk_size,
            "total_chunk_count": total_chunk_count
        }
    }
    
    # 1. Inicializar
    response = requests.post(init_url, headers=headers, json=body)
    
    # Se der erro 401 ou token inválido, renova e tenta de novo
    if response.status_code == 401:
        print("Token expirado (401). Tentando renovar...", flush=True)
        refresh_tiktok_token()
        access_token = get_valid_tiktok_token()
        headers["Authorization"] = f"Bearer {access_token}"
        response = requests.post(init_url, headers=headers, json=body)
        
    if response.status_code != 200:
        raise Exception(f"[ERRO] Inicialização do post no TikTok falhou ({response.status_code}): {response.text}")
        
    res_data = response.json()
    error_info = res_data.get("error", {})
    if error_info.get("code") != "ok":
        # Se for erro de escopo ou outro, tenta renovar antes de desistir
        if "spam" in error_info.get("message", "").lower() or "token" in error_info.get("message", "").lower():
            print("Tentando renovar token após erro de API...", flush=True)
            refresh_tiktok_token()
            access_token = get_valid_tiktok_token()
            headers["Authorization"] = f"Bearer {access_token}"
            response = requests.post(init_url, headers=headers, json=body)
            res_data = response.json()
            error_info = res_data.get("error", {})
            if error_info.get("code") != "ok":
                raise Exception(f"[ERRO] Erro na API do TikTok: {error_info}")
        else:
            raise Exception(f"[ERRO] Erro na API do TikTok: {error_info}")
            
    upload_url = res_data["data"]["upload_url"]
    publish_id = res_data["data"]["publish_id"]
    
    # 2. Upload dos chunks
    print(f"[TIKTOK] Fazendo upload do vídeo em {total_chunk_count} chunk(s)...", flush=True)
    
    with open(video_path, "rb") as f:
        for chunk_index in range(total_chunk_count):
            start_byte = chunk_index * actual_chunk_size
            remaining = video_size - start_byte
            
            # O último chunk leva todos os bytes restantes (que podem exceder actual_chunk_size)
            if chunk_index == total_chunk_count - 1:
                this_chunk_size = remaining
            else:
                this_chunk_size = actual_chunk_size
                
            end_byte = start_byte + this_chunk_size - 1
            
            chunk_data = f.read(this_chunk_size)
            
            put_headers = {
                "Content-Range": f"bytes {start_byte}-{end_byte}/{video_size}",
                "Content-Type": "video/mp4",
                "Content-Length": str(this_chunk_size)
            }
            
            percent = int(((chunk_index + 1) / total_chunk_count) * 100)
            print(f"[TIKTOK] Enviando chunk {chunk_index + 1}/{total_chunk_count} (bytes {start_byte}-{end_byte}) - {percent}%", flush=True)
            
            if progress_callback:
                try:
                    progress_callback(percent)
                except:
                    pass
            
            put_response = requests.put(upload_url, headers=put_headers, data=chunk_data)
            
            if put_response.status_code not in [200, 201, 204, 206]:
                raise Exception(f"[ERRO] Falha no upload do chunk {chunk_index + 1} para o TikTok ({put_response.status_code}): {put_response.text}")
        
    print(f"[OK] Vídeo enviado com sucesso para o TikTok! ID de Publicação: {publish_id}", flush=True)
    return publish_id

