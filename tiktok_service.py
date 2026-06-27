import os
import sys
from dotenv import load_dotenv

load_dotenv()

def upload_video_to_tiktok(video_path, title, privacy_level="Public", schedule_time=None, schedule_day=None, progress_callback=None):
    """
    Realiza o envio de um vídeo para o TikTok usando o uploader do Maki (requests baseados em cookies de sessão).
    """
    # 1. Adicionar o diretório do maki ao path
    MAKI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maki_tiktok")
    if MAKI_DIR not in sys.path:
        sys.path.append(MAKI_DIR)

    from tiktok_uploader.Config import Config
    from tiktok_uploader import upload_video

    # 2. Configurar caminhos absolutos para evitar dependência do diretório atual de execução
    cfg = Config.get()
    cfg._options["COOKIES_DIR"] = os.path.join(MAKI_DIR, "CookiesDir")
    cfg._options["VIDEOS_DIR"] = os.path.join(MAKI_DIR, "VideosDirPath")

    # 3. Obter nome da conta a partir do .env
    session_user = os.getenv("TIKTOK_ACCOUNT_NAME", "default_account")

    # 4. Mapear privacidade
    privacy_lower = privacy_level.lower() if privacy_level else "public"
    if privacy_lower == "private":
        visibility_type = 1
    elif privacy_lower == "friends":
        visibility_type = 2
    else:
        visibility_type = 0

    print(f"[TIKTOK-MAKI] Iniciando postagem com uploader do Maki. Conta: {session_user}, Privacidade: {privacy_level} ({visibility_type})", flush=True)

    # 5. Executar o upload usando a biblioteca do Maki
    success = upload_video(
        session_user=session_user,
        video=video_path,
        title=title,
        schedule_time=0,  # Bypassa agendamento do tiktok no post imediato
        visibility_type=visibility_type
    )

    if success is False:
        raise Exception("[ERRO] Falha no upload para o TikTok usando o uploader do Maki. Verifique os logs e se os cookies da conta estão válidos.")

    print("[TIKTOK-MAKI] Upload concluído com sucesso via Maki!", flush=True)
    return "Maki_Upload_Success"
