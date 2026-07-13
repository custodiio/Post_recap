import re
import random
import logging

logger = logging.getLogger(__name__)

# Fallbacks padrão caso as configurações no banco estejam vazias
DEFAULT_YT_TITLE_TEMPLATE = "{title} - Completo"
DEFAULT_YT_DESC_TEMPLATES = [
    "Prepare o coração! Assista a este trecho de {title} ({part_str}).\n\nDeixe seu like e se inscreva no canal para não perder as próximas partes desse drama incrível!\n\n#dramas #shorts #recap #kdrama #cdrama #drama",
    "Você não vai acreditar no que aconteceu nessa cena! Confira: {title} ({part_str}).\n\nInscreva-se no canal para apoiar e acompanhar os melhores momentos!\n\n#doramas #romance #series #shorts",
    "Mais um momento marcante de {title} ({part_str})🍿 O que você achou dessa atitude? Deixe seu comentário e apoie o canal se inscrevendo!\n\n#filmes #shorts #resumo #cortes"
]
DEFAULT_TT_DESC_TEMPLATES = [
    "😭 Impossível não se emocionar com essa cena! {title} ({part_str}) 🎬🍿 #dramas #shorts #doramas #series #recap #foryou",
    "Olha o que aconteceu aqui! 😱 {title} ({part_str}) O que você faria nessa situação? #series #recap #cortes #drama #fyp",
    "Essa cena me pegou de surpresa! Eles são muito fofos juntos 😍🍿 {title} ({part_str}) #casal #romance #doramas #foryou"
]
DEFAULT_TAGS_TEMPLATES = [
    "dramas, shorts, doramas, recap, novela, cdrama, kdrama",
    "filmes, series, resumo, cortes, cinema, fyp, entretenimento",
    "romance, comedia, doramas, dramas, casal, fofocas, shorts"
]

def clean_tags_and_title(raw_title: str) -> str:
    """Limpa o título removendo marcações extras, emojis e espaços duplos."""
    if not raw_title:
        return ""
    # Remove emojis
    text = raw_title.encode('ascii', 'ignore').decode('ascii')
    # Remove colchetes/parênteses poluentes
    text = re.sub(r'[\[\](){}\-_]+', ' ', text)
    # Limpa múltiplos espaços
    return " ".join(text.split()).strip()

def format_post_meta(title: str, part_number: int) -> dict:
    """
    Retorna os metadados formatados para postagem rotacionando (intercalando) 
    sequencialmente pelos modelos de postagem cadastrados na tabela 'templates'.
    """
    import db  # Importação atrasada para evitar importação circular
    
    # 1. Carrega todos os modelos da base
    db_templates = db.get_all_templates()
    
    if db_templates:
        # Pega o ID do último modelo usado para intercalar
        last_id_str = db.get_setting("last_used_template_id", "")
        
        # Encontra o próximo índice da sequência
        chosen_index = 0
        if last_id_str:
            try:
                last_id = int(last_id_str)
                for idx, t in enumerate(db_templates):
                    if t["id"] == last_id:
                        chosen_index = (idx + 1) % len(db_templates)
                        break
            except ValueError:
                pass
                
        model = db_templates[chosen_index]
        
        # Grava o modelo escolhido como último usado
        db.update_setting("last_used_template_id", str(model["id"]))
        
        yt_title_pattern = model.get("youtube_title", "{title} - Completo")
        chosen_yt_desc_template = model.get("youtube_desc", "")
        chosen_tt_desc_template = model.get("tiktok_desc", "")
        tags_raw = model.get("tags", "")
        tags_list = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]
    else:
        # Fallback para as constantes estáticas com rotação baseada em um contador na settings
        fallback_counter = int(db.get_setting("fallback_template_counter", "0"))
        db.update_setting("fallback_template_counter", str(fallback_counter + 1))
        
        yt_title_pattern = DEFAULT_YT_TITLE_TEMPLATE
        chosen_yt_desc_template = DEFAULT_YT_DESC_TEMPLATES[fallback_counter % len(DEFAULT_YT_DESC_TEMPLATES)]
        chosen_tt_desc_template = DEFAULT_TT_DESC_TEMPLATES[fallback_counter % len(DEFAULT_TT_DESC_TEMPLATES)]
        chosen_tags_str = DEFAULT_TAGS_TEMPLATES[fallback_counter % len(DEFAULT_TAGS_TEMPLATES)]
        tags_list = [tag.strip() for tag in chosen_tags_str.split(",") if tag.strip()]
    
    part_str = f"Parte {part_number}"
    
    # 2. Formata os títulos de forma dinâmica
    yt_title = yt_title_pattern.format(title=title, part_str="Completo")
    if len(yt_title) > 95:
         yt_title = yt_title[:92] + "..."
         
    tt_title = f"{title} - {part_str}"
    if len(tt_title) > 95:
         tt_title = tt_title[:92] + "..."
         
    # 3. Formata descrições
    yt_desc = chosen_yt_desc_template.format(title=title, part_str="Completo")
    tt_desc = chosen_tt_desc_template.format(title=title, part_str=part_str)
    
    logger.info(f"[TEMPLATES] Metadados gerados por rotação sequencial de templates (ID: {model['id'] if db_templates else 'fallback'}).")
    
    return {
        "title": tt_title,
        "youtube_title": yt_title,
        "youtube_desc": yt_desc,
        "tiktok_desc": tt_desc,
        "tags": tags_list
    }
