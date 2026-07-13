import os
import sys
import json
import asyncio
import logging
import random
import subprocess
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Detecta caminhos do FFmpeg/FFprobe na VPS ou local
FFMPEG_PATH = '/usr/bin/ffmpeg' if os.path.exists('/usr/bin/ffmpeg') else 'ffmpeg'
FFPROBE_PATH = '/usr/bin/ffprobe' if os.path.exists('/usr/bin/ffprobe') else 'ffprobe'

async def probe_file(filepath: str) -> dict:
    """Executa ffprobe e retorna metadados do arquivo."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    cmd = [
        FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe falhou: {stderr.decode()}")

    return json.loads(stdout.decode())

async def get_video_duration(filepath: str) -> float:
    """Retorna a duração total do vídeo em segundos."""
    try:
        data = await probe_file(filepath)
        return float(data.get("format", {}).get("duration", 0))
    except Exception as e:
        logger.error(f"[FFMPEG] Erro ao obter duração: {e}")
        return 0.0

async def cut_video_part(
    src_path: str,
    dst_path: str,
    start_sec: float,
    duration_sec: float
) -> Tuple[bool, str]:
    """
    Corta um segmento específico do vídeo.
    Para garantir precisão e evitar congelamentos ou tela preta no TikTok/YouTube Shorts,
    utiliza re-encodamento ultrafast para o vídeo e cópia direta para o áudio.
    """
    if not os.path.exists(src_path):
        return False, "Arquivo de origem não existe."

    # Comando do FFmpeg otimizado para velocidade e compatibilidade
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss", f"{start_sec:.3f}",
        "-i", src_path,
        "-t", f"{duration_sec:.3f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        dst_path
    ]

    logger.info(f"[FFMPEG] Cortando segmento: ss={start_sec:.2f}s, t={duration_sec:.2f}s")
    logger.debug(f"[FFMPEG] Comando: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode()[-500:]
        logger.error(f"[FFMPEG] Erro no corte: {err_msg}")
        return False, f"FFmpeg falhou: {err_msg}"

    logger.info(f"[FFMPEG] Segmento gerado com sucesso: {dst_path}")
    return True, dst_path

def calculate_parts(total_duration: float) -> list:
    """
    Calcula as partes de um filme/vídeo.
    Cada parte terá uma duração aleatória entre 6 e 8 minutos (360 a 480 segundos).
    A partir da Parte 2, há uma sobreposição (recapitulação) de 30 segundos.
    Retorna uma lista de dicionários contendo os intervalos de tempo.
    """
    parts = []
    current_start = 0.0
    part_number = 1
    recap_sec = 30.0

    while current_start < total_duration:
        # Define duração aleatória entre 6 e 8 minutos
        dur = float(random.randint(360, 480))
        
        # Ajusta se for a última parte para não passar da duração total
        if current_start + dur >= total_duration:
            dur = total_duration - current_start
            # Evita criar partes minúsculas de menos de 1 minuto no final
            if dur < 60.0 and parts:
                # Soma o restante na parte anterior se existir
                parts[-1]['end_time'] = total_duration
                parts[-1]['duration'] = parts[-1]['end_time'] - parts[-1]['start_time']
                break

        end_time = current_start + dur
        parts.append({
            'part_number': part_number,
            'start_time': current_start,
            'end_time': end_time,
            'duration': dur
        })
        
        # Próxima parte inicia 'recap_sec' antes do fim da atual
        current_start = end_time - recap_sec
        part_number += 1

    return parts

async def extract_thumbnail(video_path: str, output_image_path: str, time_sec: float = 10.0) -> bool:
    """Extrai uma imagem de preview do vídeo no segundo especificado."""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss", f"{time_sec:.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_image_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception as e:
        logger.error(f"[FFMPEG] Erro ao extrair thumbnail: {e}")
        return False
