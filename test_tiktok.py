import os
from dotenv import load_dotenv

load_dotenv()

from tiktok_service import upload_video_to_tiktok

# Usar o vídeo leve existente em maki_tiktok/VideosDirPath
VIDEO_TEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maki_tiktok", "VideosDirPath", "pre-processed.mp4")
ACCOUNT = os.getenv("TIKTOK_ACCOUNT_NAME", "default_account")

# TESTE 1: Upload privado, sem agendamento
result = upload_video_to_tiktok(
    video_path=VIDEO_TEST,
    title="precisamos testar se esta publicando tudo certinho 🤖 #teste",
    privacy_level="Private",
    schedule_time=None
)

print("Resultado do upload:", result)
