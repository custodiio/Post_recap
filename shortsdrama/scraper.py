import os
import re
import asyncio
import logging
from typing import Optional, Tuple
from telethon import TelegramClient
from telethon import functions, types
from telethon.tl.types import Message, MessageMediaDocument, InputDocumentFileLocation
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Configurações do scraper do Telegram
API_ID = int(os.getenv("TELEGRAM_API_ID", "25657270"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "f2d5b9d5c89471989432ef1c2ee22993")
SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "shortsdrama_agent")

# Configurações de Download Paralelo Otimizado (Estilo DailymotionAgent)
FAST_DOWNLOAD_CONNECTIONS = 25
FAST_CHUNK_SIZE = 512 * 1024 # 512 KB

async def get_telegram_client() -> TelegramClient:
    """Retorna um cliente Telethon autenticado."""
    # Garante que a sessão fique salva na pasta correta na VPS ou local
    if os.path.exists('/home/ubuntu/apps'):
        session_path = f"/home/ubuntu/apps/database/{SESSION_NAME}"
    else:
        session_path = SESSION_NAME
        
    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.start()
    return client

async def download_telegram_video(
    client: TelegramClient,
    chat_id: str,
    message_id: int,
    output_path: str,
    progress_callback = None
) -> Tuple[bool, str]:
    """
    Baixa um arquivo de vídeo do Telegram de forma paralela (25 conexões assíncronas)
    para velocidade máxima absoluta e resiliência a timeouts.
    """
    logger.info(f"[SCRAPER] Buscando mensagem {message_id} no chat {chat_id} para download paralelo")
    
    try:
        # Resolve o chat ID se for numérico
        if isinstance(chat_id, str) and (chat_id.startswith('-100') or chat_id.isdigit()):
            chat = int(chat_id)
        else:
            chat = chat_id
            
        message = await client.get_messages(chat, ids=message_id)
        if not message or not message.media or not isinstance(message.media, MessageMediaDocument):
            return False, "Mensagem não contém um arquivo de vídeo válido."

        doc = message.media.document
        total_size = doc.size
        logger.info(f"[SCRAPER] Iniciando Download Paralelo: {total_size / (1024*1024):.2f} MB")

        # Pre-aloca o arquivo no disco
        with open(output_path, "wb") as f:
            f.truncate(total_size)

        # Prepara escrita concorrente compatível com Windows e Linux
        HAS_PWRITE = hasattr(os, "pwrite")
        fd = None
        file_obj = None
        file_lock = asyncio.Lock()

        if HAS_PWRITE:
            fd = os.open(output_path, os.O_WRONLY)
        else:
            file_obj = open(output_path, "r+b")

        try:
            semaphore = asyncio.Semaphore(FAST_DOWNLOAD_CONNECTIONS)
            downloaded = 0
            last_reported_pct = -1
            
            # Prepara a localização do arquivo para o MTProto
            file_location = InputDocumentFileLocation(
                id=doc.id,
                access_hash=doc.access_hash,
                file_reference=doc.file_reference,
                thumb_size=''
            )

            async def download_chunk(offset: int):
                async with semaphore:
                    for retry in range(3):
                        try:
                            result = await client(functions.upload.GetFileRequest(
                                location=file_location,
                                offset=offset,
                                limit=FAST_CHUNK_SIZE
                            ))
                            
                            if isinstance(result, types.upload.File):
                                if HAS_PWRITE:
                                    os.pwrite(fd, result.bytes, offset)
                                else:
                                    async with file_lock:
                                        file_obj.seek(offset)
                                        file_obj.write(result.bytes)
                                
                                nonlocal downloaded
                                downloaded += len(result.bytes)
                                
                                # Envia progresso de 10% em 10%
                                if progress_callback:
                                    pct = int(downloaded / total_size * 100)
                                    nonlocal last_reported_pct
                                    if pct // 10 > last_reported_pct // 10 or pct == 100:
                                        last_reported_pct = pct
                                        try:
                                            await progress_callback(f"📥 Baixando vídeo: {pct}% concluído...")
                                        except:
                                            pass
                                return
                        except Exception as e:
                            # Tratamento de Flood Wait dinâmico
                            wait_seconds = getattr(e, "seconds", None)
                            if not wait_seconds and ("wait" in str(e).lower() or "flood" in str(e).lower()):
                                wait_seconds = 5
                            
                            if wait_seconds:
                                logger.warning(f"[SCRAPER] Telegram Wait (Tentativa {retry+1}/3): {e}. Aguardando {wait_seconds}s...")
                                await asyncio.sleep(wait_seconds)
                            else:
                                if retry == 2:
                                    raise e
                                await asyncio.sleep(1)

            # Dispara todas as tarefas em paralelo
            offsets = range(0, total_size, FAST_CHUNK_SIZE)
            tasks = [download_chunk(offset) for offset in offsets]
            await asyncio.gather(*tasks)

        finally:
            if fd is not None:
                os.close(fd)
            if file_obj is not None:
                file_obj.close()

        # Verificação final de integridade
        actual_size = os.path.getsize(output_path)
        if actual_size != total_size:
            if os.path.exists(output_path):
                os.remove(output_path)
            return False, f"Download incompleto! Esperado {total_size}B, recebido {actual_size}B."

        logger.info(f"[SCRAPER] Download paralelo concluído com sucesso: {output_path}")
        return True, output_path

    except Exception as e:
        logger.error(f"[SCRAPER] Erro crítico no download paralelo: {e}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        return False, str(e)

async def extract_post_meta_from_telegram(
    client: TelegramClient,
    chat_id: str,
    video_message_id: int,
    lookup_window: int = 10,
    threshold: int = 80
) -> Tuple[str, str]:
    """
    Busca nas mensagens anteriores ao vídeo para extrair o título e sinopse/capa.
    Baseado no fuzzy match de títulos do DailymotionAgent.
    """
    try:
        if isinstance(chat_id, str) and (chat_id.startswith('-100') or chat_id.isdigit()):
            chat = int(chat_id)
        else:
            chat = chat_id
            
        video_msg = await client.get_messages(chat, ids=video_message_id)
        video_caption = video_msg.message or ""
        
        # Pega a primeira linha da legenda como título base
        title_base = ""
        if video_caption:
            title_base = video_caption.strip().split("\n")[0]
            # Remove marcações e colchetes
            title_base = re.sub(r'[\[\](){}\-_]+', ' ', title_base).strip()
            
        logger.info(f"[SCRAPER] Buscando metadados para o título base: '{title_base}'")
        
        messages_above = []
        async for msg in client.iter_messages(chat, limit=lookup_window, max_id=video_message_id):
            messages_above.append(msg)
            
        # Procura por texto e imagens de capa nas mensagens anteriores
        best_title = title_base or "Drama Sem Título"
        best_desc = video_caption
        cover_msg = None
        
        for msg in messages_above:
            if not msg.message:
                continue
                
            # Verifica similaridade para ver se refere-se ao mesmo drama
            msg_first_line = msg.message.strip().split("\n")[0]
            msg_clean = re.sub(r'[\[\](){}\-_]+', ' ', msg_first_line).strip()
            
            score = fuzz.partial_ratio(title_base.lower(), msg_clean.lower()) if title_base else 0
            if score >= threshold or (not title_base and len(msg.message) > 50):
                logger.info(f"[SCRAPER] Post de texto correspondente encontrado na msg_id={msg.id} (Score: {score}%)")
                best_title = msg_clean
                best_desc = msg.message
                break
                
        # Procura por mensagens com fotos de capa
        for msg in messages_above:
            if msg.photo:
                logger.info(f"[SCRAPER] Possível capa encontrada na msg_id={msg.id}")
                cover_msg = msg
                break
                
        return best_title, best_desc
        
    except Exception as e:
        logger.error(f"[SCRAPER] Erro ao extrair metadados do Telegram: {e}")
        return "Drama Sem Título", ""

async def download_telegram_cover(
    client: TelegramClient,
    chat_id: str,
    video_message_id: int,
    output_path: str,
    lookup_window: int = 10
) -> bool:
    """
    Busca nas mensagens anteriores ao vídeo por uma foto (capa).
    Se encontrada, baixa e salva no output_path. Retorna True se tiver sucesso.
    """
    try:
        if isinstance(chat_id, str) and (chat_id.startswith('-100') or chat_id.isdigit()):
            chat = int(chat_id)
        else:
            chat = chat_id

        messages_above = []
        async for msg in client.iter_messages(chat, limit=lookup_window, max_id=video_message_id):
            messages_above.append(msg)

        # Procura por fotos
        for msg in messages_above:
            if msg.photo:
                logger.info(f"[SCRAPER] Capa encontrada na msg_id={msg.id}. Fazendo download...")
                path = await client.download_media(msg.photo, file=output_path)
                if path:
                    logger.info(f"[SCRAPER] Download da capa concluído: {path}")
                    return True
        return False
    except Exception as e:
        logger.error(f"[SCRAPER] Erro ao buscar/baixar capa: {e}")
        return False

async def scrape_douyin_video(url: str, output_path: str) -> Tuple[bool, str]:
    """
    Placeholder robusto para scraper do Douyin.
    Baixa o vídeo de Douyin usando yt-dlp ou similar.
    """
    logger.info(f"[SCRAPER] Iniciando scrape do Douyin para URL: {url}")
    try:
        import yt_dlp
        
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'mp4/best',
            'quiet': True,
            'no_warnings': True
        }
        
        # Roda em thread pool para evitar travar o loop assíncrono
        def run_ytdl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
        await asyncio.to_thread(run_ytdl)
        
        if os.path.exists(output_path):
            logger.info(f"[SCRAPER] Vídeo do Douyin baixado: {output_path}")
            return True, output_path
        return False, "Falha ao salvar vídeo do Douyin."
        
    except Exception as e:
        logger.error(f"[SCRAPER] Erro no scraper do Douyin: {e}")
        return False, str(e)
