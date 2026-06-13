import os
from dotenv import load_dotenv

load_dotenv()

from tiktok_service import upload_video_to_tiktok

# Use um vídeo MP4 de teste (curto, <30s, formato 9:16)
VIDEO_TEST = r"C:\Users\alecu\Downloads\pt1_renderizado2.mp4"
ACCOUNT = os.getenv("TIKTOK_ACCOUNT_NAME", "default_account")

# TESTE 1: Upload privado, sem agendamento
result = upload_video_to_tiktok(
    video_path=VIDEO_TEST,
    title="precisamos testar se esta publicando tudo certinho 🤖 #teste",
    privacy_level="Private",
    schedule_time=None
)

print("Resultado do upload:", result)
