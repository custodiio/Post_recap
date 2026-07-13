import os
import sys
import logging
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
    privacy_status: str = "private" # private, public, unlisted
) -> Tuple[bool, str]:
    """
    Realiza o upload de um vídeo para o YouTube usando as credenciais do e-mail allessandrocustodio.alves@gmail.com.
    """
    logger.info(f"[UPLOADER] Iniciando upload para YouTube: {video_path} | Privacidade: {privacy_status}")
    
    # Garante a injeção do e-mail correto antes do load
    os.environ["YOUTUBE_USER_EMAIL"] = "allessandrocustodio.alves@gmail.com"
    
    try:
        # A função original de upload_video do youtube_uploader é síncrona
        def run_upload():
            youtube = youtube_uploader.get_youtube_service()
            # Mapeia tags para string separada por vírgulas ou lista
            video_id = youtube_uploader.upload_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy_status.lower()
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
