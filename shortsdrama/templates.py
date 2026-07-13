import re

# Modelos pré-definidos de descrição para as postagens
DESCRIPTION_TEMPLATES = {
    "drama_emocionante": {
        "name": "🎬 Drama Emocionante",
        "youtube_desc": (
            "Prepare o coração! Assista a este trecho emocionante de {title} ({part_str}).\n\n"
            "Deixe seu like e se inscreva no canal para não perder as próximas partes desse drama incrível!\n\n"
            "#dramas #shorts #recap #kdrama #cdrama #drama"
        ),
        "tiktok_desc": "😭 Impossível não se emocionar com essa cena! {title} ({part_str}) 🎬🍿 #dramas #shorts #doramas #series #recap #foryou",
        "tags": ["dramas", "shorts", "doramas", "recap", "novela", "cdrama", "kdrama"]
    },
    "comedia_romantica": {
        "name": "❤️ Romance e Comédia",
        "youtube_desc": (
            "A química perfeita! Acompanhe as trapalhadas românticas de {title} ({part_str}).\n\n"
            "Diga nos comentários o que você achou dessa cena! Inscreva-se para apoiar o canal.\n\n"
            "#romance #comedia #doramas #dramas #shorts"
        ),
        "tiktok_desc": "Eles dois são muito fofos juntos! 😍🍿 {title} ({part_str}) #doramas #romance #comedia #dramas #series #casal #fyp",
        "tags": ["romance", "comedia", "doramas", "dramas", "casal", "shorts"]
    },
    "suspense_acao": {
        "name": "⚡ Suspense e Ação",
        "youtube_desc": (
            "Tensão máxima! O que vai acontecer a seguir em {title} ({part_str})?\n\n"
            "Inscreva-se no canal e ative o sininho para acompanhar o desfecho desse mistério!\n\n"
            "#suspense #acao #shorts #dramas #series"
        ),
        "tiktok_desc": "O clima esquentou aqui! 😱💥 {title} ({part_str}) O que acham que vai acontecer? #dramas #suspense #acao #series #recap #foryou",
        "tags": ["suspense", "acao", "dramas", "series", "recap", "filmes"]
    },
    "recap_geral": {
        "name": "🍿 Recap Geral de Filmes",
        "youtube_desc": (
            "Resumo e melhores momentos do filme/série: {title} ({part_str}).\n\n"
            "Inscreva-se para ver mais cortes rápidos dos seus filmes e séries favoritos!\n\n"
            "#filmes #resumo #recap #shorts #cinema"
        ),
        "tiktok_desc": "Corte imperdível desse filmaço! 🎬🍿 {title} ({part_str}) #filmes #series #recap #resumo #cinema #foryou",
        "tags": ["filmes", "resumo", "recap", "cortes", "cinema", "shorts"]
    }
}

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

def format_post_meta(title: str, part_number: int, template_key: str = "drama_emocionante") -> dict:
    """
    Retorna os metadados formatados para postagem baseados no template selecionado.
    """
    template = DESCRIPTION_TEMPLATES.get(template_key, DESCRIPTION_TEMPLATES["drama_emocionante"])
    part_str = f"Parte {part_number}"
    
    # Formata título para YouTube (limite clássico de 100 caracteres)
    formatted_title = f"{title} - {part_str}"
    if len(formatted_title) > 95:
         formatted_title = formatted_title[:92] + "..."
         
    # Formata descrições
    yt_desc = template["youtube_desc"].format(title=title, part_str=part_str)
    tt_desc = template["tiktok_desc"].format(title=title, part_str=part_str)
    
    return {
        "title": formatted_title,
        "youtube_desc": yt_desc,
        "tiktok_desc": tt_desc,
        "tags": template["tags"]
    }
