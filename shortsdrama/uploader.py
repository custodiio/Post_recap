import os
import sys
import logging
import asyncio
import uuid
import httpx
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Insere a pasta pai no path para importar os serviços originais de postagem
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Configura o filtro de e-mail temporariamente no ambiente antes de carregar
os.environ["TIKTOK_USER_EMAIL"] = "allessandrocustodio.alves@gmail.com"
os.environ["YOUTUBE_USER_EMAIL"] = "allessandrocustodio.alves@gmail.com"

try:
    import tiktok_service
    import youtube_uploader
except ImportError as e:
    logger.error(f"[UPLOADER] Erro ao importar serviços de postagem da raiz: {e}")

async def upload_to_tiktok(
    video_path: str,
    title: str,
    privacy_level: str = "SELF_ONLY", # SELF_ONLY, PUBLIC_TO_EVERYONE
    progress_callback = None
) -> Tuple[bool, str]:
    """
    Realiza o upload de um vídeo para o TikTok usando as credenciais do e-mail allessandrocustodio.alves@gmail.com.
    """
    logger.info(f"[UPLOADER] Iniciando upload para TikTok: {video_path}")
    
    # Garante a injeção do e-mail correto antes do load
    os.environ["TIKTOK_USER_EMAIL"] = "allessandrocustodio.alves@gmail.com"
    
    try:
        # Chama a função oficial do tiktok_service
        # Mapeia os progressos para o callback (escala de 0 a 100)
        def internal_progress(percent):
            if progress_callback:
                # O uploader do tiktok envia percentuais discretos
                asyncio.run_coroutine_threadsafe(
                    progress_callback(f"📤 Enviando TikTok: {percent}%..."),
                    asyncio.get_event_loop()
                )

        # Roda o upload síncrono em thread pool para não bloquear o loop de eventos
        def run_upload():
            # Mapeamento do nível de privacidade
            p_level = "SELF_ONLY"
            if privacy_level.lower() in ["public", "public_to_everyone"]:
                p_level = "PUBLIC_TO_EVERYONE"
                
            return tiktok_service.upload_video_to_tiktok(
                video_path=video_path,
                title=title,
                privacy_level=p_level,
                progress_callback=internal_progress
            )
            
        publish_id = await asyncio.to_thread(run_upload)
        
        if publish_id:
            logger.info(f"[UPLOADER] Postagem no TikTok concluída! ID: {publish_id}")
            return True, publish_id
        return False, "Nenhum ID de publicação retornado pelo TikTok."
        
    except Exception as e:
        logger.error(f"[UPLOADER] Falha ao postar no TikTok: {e}")
        return False, str(e)

async def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    privacy_status: str = "private", # private, public, unlisted
    thumbnail_path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Realiza o upload de um vídeo para o YouTube usando as credenciais do e-mail allessandrocustodio.alves@gmail.com.
    """
    logger.info(f"[UPLOADER] Iniciando upload para YouTube: {video_path} | Privacidade: {privacy_status} | Capa: {thumbnail_path}")
    
    # Garante a injeção do e-mail correto antes do load
    os.environ["YOUTUBE_USER_EMAIL"] = "allessandrocustodio.alves@gmail.com"
    
    try:
        # A função original de upload_video_to_youtube do youtube_uploader é síncrona
        def run_upload():
            video_id, video_url = youtube_uploader.upload_video_to_youtube(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy_status.lower(),
                thumbnail_path=thumbnail_path
            )
            return video_id
            
        video_id = await asyncio.to_thread(run_upload)
        
        if video_id:
            logger.info(f"[UPLOADER] Postagem no YouTube concluída! ID: {video_id}")
            return True, video_id
        return False, "Nenhum ID de vídeo retornado pelo YouTube."
        
    except Exception as e:
        logger.error(f"[UPLOADER] Falha ao postar no YouTube: {e}")
        return False, str(e)

async def upload_to_dailymotion(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    privacy_status: str = "private", # private, public
    progress_callback = None
) -> Tuple[bool, str]:
    """
    Realiza o upload de um vídeo para o Dailymotion usando credenciais OAuth2 do .env.
    """
    logger.info(f"[UPLOADER] Iniciando upload para Dailymotion: {video_path}")
    
    # 1. Carrega as credenciais das variáveis de ambiente
    client_id = os.getenv("DAILYMOTION_CLIENT_ID")
    client_secret = os.getenv("DAILYMOTION_CLIENT_SECRET")
    username = os.getenv("DAILYMOTION_USERNAME")
    password = os.getenv("DAILYMOTION_PASSWORD")
    
    if not all([client_id, client_secret, username, password]):
        logger.error("[UPLOADER] Credenciais do Dailymotion ausentes no .env")
        return False, "Credenciais do Dailymotion ausentes no arquivo .env"
        
    try:
        # FASE 1: Obter Token
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.dailymotion.com/oauth/token", data={
                "grant_type": "password",
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password,
                "scope": "manage_videos",
            })
            r.raise_for_status()
            token = r.json().get("access_token")
            if not token:
                return False, "Falha ao obter token de acesso do Dailymotion."
                
            # FASE 2: Handshake da URL de upload
            r = await client.get(
                "https://api.dailymotion.com/file/upload",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            upload_url = r.json().get("upload_url")
            if not upload_url:
                return False, "Falha ao obter URL de upload temporária do Dailymotion."
                
            # FASE 3: Envio do arquivo streamado (chunks de 1MB)
            file_size = os.path.getsize(video_path)
            boundary = "----DailymotionAgentBoundary" + str(uuid.uuid4())[:8]
            header_boundary = f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"video.mp4\"\r\nContent-Type: video/mp4\r\n\r\n"
            footer_boundary = f"\r\n--{boundary}--\r\n"
            total_len = len(header_boundary) + file_size + len(footer_boundary)
            
            async def file_generator():
                sent = 0
                with open(video_path, "rb") as f_obj:
                    while True:
                        chunk = await asyncio.to_thread(f_obj.read, 1 * 1024 * 1024)
                        if not chunk:
                            break
                        sent += len(chunk)
                        if progress_callback:
                            try:
                                pct = int(sent / file_size * 100)
                                if asyncio.iscoroutinefunction(progress_callback):
                                    await progress_callback(f"📤 Enviando Dailymotion: {pct}%...")
                                else:
                                    progress_callback(f"📤 Enviando Dailymotion: {pct}%...")
                            except:
                                pass
                        yield chunk
                        
            async def multipart_generator():
                yield header_boundary.encode()
                async for chunk in file_generator():
                    yield chunk
                yield footer_boundary.encode()
                
            timeout = httpx.Timeout(None, connect=30.0, read=60.0, write=None)
            async with httpx.AsyncClient(timeout=timeout, http1=True) as upload_client:
                r = await upload_client.post(
                    upload_url,
                    content=multipart_generator(),
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Content-Length": str(total_len),
                    }
                )
                r.raise_for_status()
                video_url = r.json().get("url") or r.json().get("upload_url")
                if not video_url:
                    return False, "Sem URL de vídeo após upload."
                    
            # FASE 4: Publicação final
            tags_str = ",".join(tags) if isinstance(tags, list) else tags
            is_private = "true" if privacy_status.lower() == "private" else "false"
            
            payload = {
                "url": video_url,
                "title": title,
                "description": description,
                "tags": tags_str,
                "channel": "school", # Canal padrão obrigatório no Dailymotion
                "published": "true",
                "private": is_private
            }
            
            r = await client.post(
                "https://api.dailymotion.com/me/videos",
                headers={"Authorization": f"Bearer {token}"},
                data=payload
            )
            r.raise_for_status()
            video_id = r.json().get("id")
            if not video_id:
                return False, "Nenhum ID retornado na publicação do Dailymotion."
                
            logger.info(f"[UPLOADER] Upload concluído no Dailymotion! ID: {video_id}")
            return True, video_id
            
    except Exception as e:
        logger.error(f"[UPLOADER] Falha ao postar no Dailymotion: {e}")
        return False, str(e)
