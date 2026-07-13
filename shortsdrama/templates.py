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
    Retorna os metadados formatados para postagem selecionando um template aleatório
    dentre as predefinições salvas no banco de dados SQLite.
    """
    import db  # Importação atrasada para evitar importação circular
    
    # 1. Carrega os templates de descrição do YouTube do banco
    yt_desc_raw = db.get_setting("yt_desc_template", "")
    if yt_desc_raw and yt_desc_raw.strip():
        # Divide pelo separador '---'
        yt_templates = [t.strip() for t in yt_desc_raw.split("---") if t.strip()]
    else:
        yt_templates = DEFAULT_YT_DESC_TEMPLATES
        
    # 2. Carrega os templates do TikTok do banco
    tt_desc_raw = db.get_setting("tt_desc_template", "")
    if tt_desc_raw and tt_desc_raw.strip():
        tt_templates = [t.strip() for t in tt_desc_raw.split("---") if t.strip()]
    else:
        tt_templates = DEFAULT_TT_DESC_TEMPLATES
        
    # 3. Carrega as tags do banco
    tags_raw = db.get_setting("default_tags", "")
    if tags_raw and tags_raw.strip():
        # Divide por quebra de linha ou vírgula
        if "---" in tags_raw:
             tags_groups = [g.strip() for g in tags_raw.split("---") if g.strip()]
             chosen_tags_str = random.choice(tags_groups)
        else:
             chosen_tags_str = tags_raw
        tags_list = [tag.strip() for tag in chosen_tags_str.split(",") if tag.strip()]
    else:
        chosen_tags_str = random.choice(DEFAULT_TAGS_TEMPLATES)
        tags_list = [tag.strip() for tag in chosen_tags_str.split(",") if tag.strip()]

    # 4. Escolhe os templates de forma aleatória para intercalação
    chosen_yt_desc_template = random.choice(yt_templates)
    chosen_tt_desc_template = random.choice(tt_templates)
    
    part_str = f"Parte {part_number}"
    
    # 5. Formata os títulos
    yt_title_pattern = db.get_setting("yt_title_template", DEFAULT_YT_TITLE_TEMPLATE)
    yt_title = yt_title_pattern.format(title=title, part_str="Completo")
    if len(yt_title) > 95:
         yt_title = yt_title[:92] + "..."
         
    tt_title = f"{title} - {part_str}"
    if len(tt_title) > 95:
         tt_title = tt_title[:92] + "..."
         
    # 6. Formata descrições
    yt_desc = chosen_yt_desc_template.format(title=title, part_str="Completo")
    tt_desc = chosen_tt_desc_template.format(title=title, part_str=part_str)
    
    logger.info(f"[TEMPLATES] Metadados gerados por intercalação aleatória de templates.")
    
    return {
        "title": tt_title,
        "youtube_title": yt_title,
        "youtube_desc": yt_desc,
        "tiktok_desc": tt_desc,
        "tags": tags_list
    }
