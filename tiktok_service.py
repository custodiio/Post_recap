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

def upload_video_to_tiktok(video_path, title, privacy_level="Public", schedule_time=None, schedule_day=None, progress_callback=None):
    """
    Realiza o envio de um vídeo para o TikTok (Direct Post) usando a API Oficial v2 (upload em chunks).
    O vídeo é postado diretamente no perfil do criador.
    """
    import os
    import requests
    
    # 1. Obter token de acesso
    access_token = get_valid_tiktok_token()
    if not access_token:
        raise Exception("[ERRO] Token de acesso do TikTok não encontrado ou inválido.")
        
    # 2. Mapear privacidade
    privacy_map = {
        "public": "PUBLIC_TO_EVERYONE",
        "friends": "MUTUAL_FOLLOW_FRIENDS",
        "private": "SELF_ONLY"
    }
    selected_privacy = privacy_map.get(privacy_level.lower(), "PUBLIC_TO_EVERYONE")
    
    # 3. Calcular tamanho e quantidade de chunks
    video_size = os.path.getsize(video_path)
    MAX_SINGLE_CHUNK = 64 * 1024 * 1024  # 64MB
    
    if video_size <= MAX_SINGLE_CHUNK:
        chunk_size = video_size
        total_chunk_count = 1
    else:
        chunk_size = 50 * 1024 * 1024  # chunks de 50MB
        total_chunk_count = video_size // chunk_size
        if total_chunk_count < 2:
            chunk_size = video_size // 2
            total_chunk_count = 2
            
    print(f"[TIKTOK] Iniciando postagem oficial. Vídeo: {video_size} bytes, Privacidade: {selected_privacy}", flush=True)
    print(f"[TIKTOK] Chunks: {total_chunk_count}, tamanho de cada chunk: {chunk_size} bytes", flush=True)
    
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    body = {
        "post_info": {
            "title": title,
            "privacy_level": selected_privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count
        }
    }
    
    # 4. Inicializar Postagem (com tratamento de renovação automática para 401)
    response = requests.post(init_url, headers=headers, json=body)
    
    if response.status_code == 401:
        print("[TIKTOK] Token expirado (401). Renovando e tentando novamente...", flush=True)
        refresh_tiktok_token()
        access_token = get_valid_tiktok_token()
        headers["Authorization"] = f"Bearer {access_token}"
        response = requests.post(init_url, headers=headers, json=body)
        
    if response.status_code != 200:
        raise Exception(f"[ERRO] Falha HTTP ao inicializar post no TikTok ({response.status_code}): {response.text}")
        
    res_data = response.json()
    error_info = res_data.get("error", {})
    if error_info.get("code") != "ok":
        # Tenta renovar o token se houver qualquer erro relacionado a token inválido no JSON
        if "token" in error_info.get("message", "").lower():
            print("[TIKTOK] Erro de token detectado no JSON. Renovando e tentando novamente...", flush=True)
            refresh_tiktok_token()
            access_token = get_valid_tiktok_token()
            headers["Authorization"] = f"Bearer {access_token}"
            response = requests.post(init_url, headers=headers, json=body)
            res_data = response.json()
            error_info = res_data.get("error", {})
            if error_info.get("code") != "ok":
                raise Exception(f"[ERRO] Erro na API do TikTok após renovação: {error_info}")
        else:
            raise Exception(f"[ERRO] Erro na API do TikTok: {error_info}")
            
    upload_url = res_data["data"]["upload_url"]
    publish_id = res_data["data"]["publish_id"]
    
    # 5. Fazer upload dos chunks usando PUT sequenciais
    print(f"[TIKTOK] Upload iniciado. ID de Publicação: {publish_id}", flush=True)
    
    with open(video_path, "rb") as f:
        for chunk_index in range(total_chunk_count):
            start_byte = chunk_index * chunk_size
            remaining = video_size - start_byte
            
            # O último chunk leva todos os bytes restantes
            if chunk_index == total_chunk_count - 1:
                this_chunk_size = remaining
            else:
                this_chunk_size = chunk_size
                
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
                raise Exception(f"[ERRO] Falha no upload do chunk {chunk_index + 1} ({put_response.status_code}): {put_response.text}")
                
    print(f"[TIKTOK] Upload concluído com sucesso! ID de Publicação: {publish_id}", flush=True)
    return publish_id

