import os
import logging
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

def create_16_9_cover(original_path: str, output_path: str) -> bool:
    """
    Gera uma miniatura 16:9 (1280x720) com base em uma imagem de capa original.
    - Imagem do meio: em destaque no centro (100% brilho), mantendo a proporção (altura 720px).
    - Lateral Esquerda: cópia da imagem original com opacidade/brilho reduzida a 40%, alinhada à esquerda.
    - Lateral Direita: cópia da imagem original com opacidade/brilho reduzida a 40%, alinhada à direita.
    Isso evita que as laterais fiquem excessivamente esticadas ou distorcidas.
    """
    if not os.path.exists(original_path):
        logger.error(f"[COVER] Imagem original não encontrada: {original_path}")
        return False

    try:
        # 1. Abre a imagem original
        orig_img = Image.open(original_path)
        
        # Converte para RGBA se necessário
        if orig_img.mode != "RGBA":
            orig_img = orig_img.convert("RGBA")
            
        canvas_width = 1280
        canvas_height = 720
        
        # 2. Cria o Canvas com fundo preto sólido
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 255))
        
        # 3. Redimensiona a imagem original proporcionalmente para a altura de 720px
        orig_w, orig_h = orig_img.size
        mid_h = canvas_height
        mid_w = int(orig_w * (mid_h / orig_h))
        
        # Garante que a largura não seja zero
        mid_w = max(1, mid_w)
        
        resized_img = orig_img.resize((mid_w, mid_h), Image.Resampling.LANCZOS)
        
        # 4. Cria a versão escurecida (40% de brilho) para as laterais
        enhancer = ImageEnhance.Brightness(resized_img)
        dark_img = enhancer.enhance(0.40) # 0.4 = 40% brilho/opacidade
        
        # 5. Cola as laterais escurecidas no Canvas
        # Lateral esquerda alinhada em x=0
        canvas.paste(dark_img, (0, 0), mask=dark_img)
        # Lateral direita alinhada em x=1280 - largura da imagem
        canvas.paste(dark_img, (canvas_width - mid_w, 0), mask=dark_img)
        
        # 6. Cola a imagem principal com 100% de brilho no centro
        center_x = (canvas_width - mid_w) // 2
        canvas.paste(resized_img, (center_x, 0), mask=resized_img)
        
        # 7. Salva a imagem final convertendo para RGB (JPEG)
        final_img = canvas.convert("RGB")
        final_img.save(output_path, "JPEG", quality=90)
        
        logger.info(f"[COVER] Capa 16:9 de 3 painéis gerada com sucesso e salva em: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"[COVER] Falha ao processar capa de 3 painéis: {e}", exc_info=True)
        return False
