import os
import sys
import json
import threading
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Configura o stdout/stderr para flushing imediato no console do terminal
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import NetworkError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Módulos locais
import db
from drive_manager import drive_manager
import youtube_uploader
import tiktok_uploader
import instagram_uploader

load_dotenv()

# Estados da conversação
SELECT_PLATFORMS, SELECT_YOUTUBE_TITLE, INPUT_YOUTUBE_TITLE_MANUAL, SELECT_INSTAGRAM_SCHEDULING, INPUT_INSTAGRAM_TIME, CONFIRM_POST = range(6)

# Lista de usuários aprovados (suporta IDs e Usernames)
APPROVED_USERS = [u.strip() for u in (os.getenv("AUTHORIZED_TELEGRAM_USERS", "") + "," + os.getenv("APPROVED_USERS", "")).split(",") if u.strip()]

def user_is_approved(update: Update) -> bool:
    """Verifica se o usuário que enviou a mensagem está autorizado por username ou ID."""
    user = update.effective_user
    if not user:
        return False
    # Se não houver lista no .env, permite por padrão
    if not APPROVED_USERS:
        return True
    return (user.username in APPROVED_USERS) or (str(user.id) in APPROVED_USERS)

# Worker de fila para agendamentos do Instagram (roda em segundo plano)
def run_queue_worker():
    print("Iniciando Worker de fila em segundo plano...")
    while True:
        try:
            # Executa a função síncrona de processamento da fila
            instagram_uploader.process_instagram_queue()
        except Exception as e:
            print(f"[ERRO] Erro na execução do Worker da fila: {e}")
        time.sleep(60)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o bot e apresenta o menu principal."""
    if not user_is_approved(update):
        await update.message.reply_text("Desculpe, você não está autorizado a usar este bot.")
        return ConversationHandler.END
        
    # Inicializa o dicionário de contexto da postagem
    context.user_data["post_data"] = {
        "platforms": {"youtube": False, "tiktok": False, "instagram": False},
        "youtube_title": "",
        "instagram_scheduled_time": None,  # None se for postar agora
        "guia": None,
        "files": None
    }
    
    keyboard = [
        [InlineKeyboardButton("Postar Novo Vídeo", callback_data="menu_postar")],
        [InlineKeyboardButton("Ver Fila do Instagram", callback_data="menu_fila")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Olá! Bem-vindo ao Post Recap Bot.\nSelecione uma opção no menu abaixo:",
        reply_markup=reply_markup
    )
    return SELECT_PLATFORMS

async def show_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Retorna ao menu principal via callback query."""
    query = update.callback_query
    await query.answer()
    
    context.user_data["post_data"] = {
        "platforms": {"youtube": False, "tiktok": False, "instagram": False},
        "youtube_title": "",
        "instagram_scheduled_time": None,
        "guia": None,
        "files": None
    }
    
    keyboard = [
        [InlineKeyboardButton("Postar Novo Vídeo", callback_data="menu_postar")],
        [InlineKeyboardButton("Ver Fila do Instagram", callback_data="menu_fila")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Selecione uma opção no menu abaixo:",
        reply_markup=reply_markup
    )
    return SELECT_PLATFORMS

async def menu_fila(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mostra os agendamentos pendentes na fila."""
    query = update.callback_query
    await query.answer()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, scheduled_time, status, video_drive_path 
        FROM instagram_queue 
        ORDER BY scheduled_time ASC 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        text = "📭 A fila do Instagram está vazia no momento."
    else:
        text = "📅 Próximos agendamentos do Instagram (limite 10):\n\n"
        for r in rows:
            status_emoji = "⏳" if r[2] == "pending" else ("✅" if r[2] == "completed" else "❌")
            filename = r[3].split("/")[-1]
            text += f"{status_emoji} ID: {r[0]} | {r[1]} | {filename} ({r[2]})\n"
            
    keyboard = [[InlineKeyboardButton("Voltar", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)
    return SELECT_PLATFORMS

async def menu_postar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Busca o JSON guia_postagem do Drive e apresenta as opções de plataforma."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("🔍 Conectando ao Google Drive e buscando informações do post...")
    
    try:
        # Busca o ID da pasta e o arquivo guia_postagem.json
        folder_id = os.getenv("DRIVE_FOLDER_ID")
        if not folder_id:
            folder_id = drive_manager.find_id_by_path("KAGGLE/PIPELINE/FINAL")
            
        if not folder_id:
            folder_id = drive_manager.find_id_by_path("PIPELINE/FINAL")
            
        if not folder_id:
            await query.edit_message_text(
                "❌ Erro: Não foi possível localizar a pasta do pipeline final no Drive.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data="back_to_menu")]])
            )
            return SELECT_PLATFORMS

        # Lista arquivos na pasta
        files = drive_manager.list_files_in_folder(folder_id)
        guia_id = None
        for f in files:
            if f["name"] == "guia_postagem.json":
                guia_id = f["id"]
                break
                
        if not guia_id:
            # Guia ausente - define dados padrão genéricos para postagem sem guia
            guia_data = {
                "titulo_principal": f"Video_Recap_{datetime.now().strftime('%Y-%m-%d_%H%M')}",
                "titulos_alternativos": [],
                "descricao": "Vídeo enviado via Post Recap Bot.",
                "hashtags_youtube": ["#anime", "#recap"],
                "tags_youtube": "recap, anime",
                "tiktok_titulo": f"Video_Recap_{datetime.now().strftime('%Y-%m-%d_%H%M')}",
                "tiktok_sinopse": "Recap enviado via Bot.",
                "tiktok_hashtags": ["#anime", "#recap", "#viral"],
                "tiktok_descricao": "Vídeo enviado via Post Recap Bot."
            }
            warning_prefix = "⚠️ *guia_postagem.json não encontrado no Drive. Usando dados genéricos.*\n\n"
        else:
            # Baixa temporariamente o guia_postagem.json para ler os dados
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            local_guia_path = os.path.join(temp_dir, "guia_postagem.json")
            
            drive_manager.download_file_by_id(guia_id, local_guia_path)
            
            with open(local_guia_path, "r", encoding="utf-8") as file:
                guia_data = json.load(file)
            warning_prefix = ""
            
        # Salva os dados no contexto
        context.user_data["post_data"]["guia"] = guia_data
        context.user_data["post_data"]["folder_id"] = folder_id
        
        # Mostra o resumo do vídeo e as opções
        title = guia_data.get("titulo_principal", "Sem Título")
        desc = guia_data.get("tiktok_sinopse", "Sem Sinopse")
        
        message_text = (
            f"🎬 **Vídeo Detectado!**\n"
            f"**Título:** {title}\n"
            f"**Sinopse:** {desc}\n\n"
            f"Selecione as redes sociais para envio:"
        )
        
        reply_markup = get_platforms_keyboard(context.user_data["post_data"]["platforms"])
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
        return SELECT_PLATFORMS
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Erro ao ler informações do Drive: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data="back_to_menu")]])
        )
        return SELECT_PLATFORMS

def get_platforms_keyboard(platforms):
    """Gera o teclado de seleção de plataformas."""
    yt_check = "✅" if platforms["youtube"] else "⬜"
    tt_check = "✅" if platforms["tiktok"] else "⬜"
    ig_check = "✅" if platforms["instagram"] else "⬜"
    
    keyboard = [
        [InlineKeyboardButton(f"{yt_check} YouTube", callback_data="toggle_youtube")],
        [InlineKeyboardButton(f"{tt_check} TikTok", callback_data="toggle_tiktok")],
        [InlineKeyboardButton(f"{ig_check} Instagram", callback_data="toggle_instagram")],
        [
            InlineKeyboardButton("Cancelar", callback_data="back_to_menu"),
            InlineKeyboardButton("Confirmar Redes", callback_data="confirm_platforms")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def toggle_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Alterna a seleção de uma rede social."""
    query = update.callback_query
    await query.answer()
    
    platform = query.data.split("_")[1]
    platforms = context.user_data["post_data"]["platforms"]
    platforms[platform] = not platforms[platform]
    
    reply_markup = get_platforms_keyboard(platforms)
    await query.edit_message_reply_markup(reply_markup=reply_markup)
    return SELECT_PLATFORMS

async def confirm_platforms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma a seleção e define o próximo passo do fluxo."""
    query = update.callback_query
    await query.answer()
    
    platforms = context.user_data["post_data"]["platforms"]
    
    # Valida se pelo menos uma plataforma foi escolhida
    if not any(platforms.values()):
        await query.answer("Por favor, selecione pelo menos uma rede social!", show_alert=True)
        return SELECT_PLATFORMS
        
    # Se YouTube foi selecionado, pergunta o título
    if platforms["youtube"]:
        guia = context.user_data["post_data"]["guia"]
        titulo_p = guia.get("titulo_principal", "Sem Título")
        alt_titles = guia.get("titulos_alternativos", [])
        
        text = (
            f"📌 **Opções de Título para o YouTube:**\n\n"
            f"**Principal:** {titulo_p}\n\n"
            f"Selecione qual deseja utilizar:"
        )
        
        keyboard = [
            [InlineKeyboardButton("Título Principal", callback_data="yt_title_principal")]
        ]
        
        for idx, alt in enumerate(alt_titles):
            keyboard.append([InlineKeyboardButton(f"Alt {idx+1}: {alt[:30]}...", callback_data=f"yt_title_alt_{idx}")])
            
        keyboard.append([InlineKeyboardButton("✍️ Digitar Título Manualmente", callback_data="yt_title_manual")])
        keyboard.append([InlineKeyboardButton("Voltar", callback_data="menu_postar")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        return SELECT_YOUTUBE_TITLE
        
    # Se não tem YouTube, mas tem Instagram, decide agendamento
    elif platforms["instagram"]:
        return await ask_instagram_scheduling(query, context)
        
    # Senão, vai direto para a confirmação final
    else:
        return await show_final_confirmation(query, context)

async def handle_youtube_title_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do título do YouTube a partir dos botões."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    guia = context.user_data["post_data"]["guia"]
    
    if data == "yt_title_principal":
        context.user_data["post_data"]["youtube_title"] = guia.get("titulo_principal")
    elif data.startswith("yt_title_alt_"):
        idx = int(data.split("_")[-1])
        context.user_data["post_data"]["youtube_title"] = guia.get("titulos_alternativos", [])[idx]
    elif data == "yt_title_manual":
        await query.edit_message_text("Por favor, digite o título desejado para o YouTube:")
        return INPUT_YOUTUBE_TITLE_MANUAL
        
    # Após definir o título do YouTube, verifica se precisa definir agendamento do Instagram
    if context.user_data["post_data"]["platforms"]["instagram"]:
        return await ask_instagram_scheduling(query, context)
    else:
        return await show_final_confirmation(query, context)

async def handle_youtube_title_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o título do YouTube digitado manualmente pelo usuário."""
    if not user_is_approved(update):
        return ConversationHandler.END
        
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Título inválido. Por favor, envie um texto válido:")
        return INPUT_YOUTUBE_TITLE_MANUAL
        
    context.user_data["post_data"]["youtube_title"] = title
    
    # Após definir o título do YouTube, verifica se precisa definir agendamento do Instagram
    if context.user_data["post_data"]["platforms"]["instagram"]:
        # Como veio por mensagem de texto (não callback), enviamos uma nova mensagem
        keyboard = [
            [InlineKeyboardButton("Postar Agora", callback_data="ig_now")],
            [InlineKeyboardButton("Agendar Postagem", callback_data="ig_schedule")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🕐 **Agendamento do Instagram**\nComo deseja enviar o Reels para o Instagram?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return SELECT_INSTAGRAM_SCHEDULING
    else:
        # Mostra confirmação
        await show_final_confirmation_message(update.message, context)
        return CONFIRM_POST

async def ask_instagram_scheduling(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pergunta sobre o agendamento do Instagram."""
    keyboard = [
        [InlineKeyboardButton("Postar Agora", callback_data="ig_now")],
        [InlineKeyboardButton("Agendar Postagem", callback_data="ig_schedule")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🕐 **Agendamento do Instagram**\nComo deseja enviar o Reels para o Instagram?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return SELECT_INSTAGRAM_SCHEDULING

async def handle_instagram_scheduling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha de agendar ou postar agora no Instagram."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "ig_now":
        context.user_data["post_data"]["instagram_scheduled_time"] = None
        return await show_final_confirmation(query, context)
    elif data == "ig_schedule":
        await query.edit_message_text(
            "Por favor, digite a data e hora do agendamento.\n"
            "Use o formato: `AAAA-MM-DD HH:MM`\n"
            "Exemplo: `2026-05-24 18:00`",
            parse_mode="Markdown"
        )
        return INPUT_INSTAGRAM_TIME

async def handle_instagram_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data e hora do agendamento digitada pelo usuário."""
    if not user_is_approved(update):
        return ConversationHandler.END
        
    raw_time = update.message.text.strip()
    try:
        # Valida o formato inserido
        dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M")
        context.user_data["post_data"]["instagram_scheduled_time"] = dt.strftime("%Y-%m-%d %H:%M:00")
        
        await show_final_confirmation_message(update.message, context)
        return CONFIRM_POST
    except ValueError:
        await update.message.reply_text(
            "❌ Formato inválido! Por favor, utilize o formato correto:\n"
            "`AAAA-MM-DD HH:MM` (ex: `2026-05-24 18:00`)",
            parse_mode="Markdown"
        )
        return INPUT_INSTAGRAM_TIME

async def show_final_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gera e exibe a mensagem de confirmação final de postagem."""
    post_data = context.user_data["post_data"]
    platforms = post_data["platforms"]
    
    redes = []
    if platforms["youtube"]:
        redes.append(f"• YouTube (Título: {post_data['youtube_title']})")
    if platforms["tiktok"]:
        redes.append("• TikTok (Privado)")
    if platforms["instagram"]:
        sched = post_data["instagram_scheduled_time"]
        sched_text = f"Agendado para {sched}" if sched else "Postar Agora"
        redes.append(f"• Instagram Reels ({sched_text})")
        
    redes_str = "\n".join(redes)
    
    text = (
        "📝 **Resumo da Postagem:**\n\n"
        f"As mídias serão baixadas do Google Drive e enviadas para:\n"
        f"{redes_str}\n\n"
        "Confirma o envio?"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("Cancelar", callback_data="back_to_menu"),
            InlineKeyboardButton("Confirmar e Enviar", callback_data="execute_upload")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    return CONFIRM_POST

async def show_final_confirmation_message(msg_object, context: ContextTypes.DEFAULT_TYPE):
    """Versão auxiliar para enviar a confirmação quando o fluxo vem de entrada de texto."""
    post_data = context.user_data["post_data"]
    platforms = post_data["platforms"]
    
    redes = []
    if platforms["youtube"]:
        redes.append(f"• YouTube (Título: {post_data['youtube_title']})")
    if platforms["tiktok"]:
        redes.append("• TikTok (Privado)")
    if platforms["instagram"]:
        sched = post_data["instagram_scheduled_time"]
        sched_text = f"Agendado para {sched}" if sched else "Postar Agora"
        redes.append(f"• Instagram Reels ({sched_text})")
        
    redes_str = "\n".join(redes)
    
    text = (
        "📝 **Resumo da Postagem:**\n\n"
        f"As mídias serão baixadas do Google Drive e enviadas para:\n"
        f"{redes_str}\n\n"
        "Confirma o envio?"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("Cancelar", callback_data="back_to_menu"),
            InlineKeyboardButton("Confirmar e Enviar", callback_data="execute_upload")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg_object.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def execute_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Executa o download dos arquivos do Google Drive e posta nas redes selecionadas."""
    query = update.callback_query
    await query.answer()
    
    post_data = context.user_data["post_data"]
    platforms = post_data["platforms"]
    guia = post_data["guia"]
    
    status_msg = await query.edit_message_text("📥 Iniciando download dos arquivos do Google Drive...")
    
    # Executa a postagem em segundo plano para não travar a UI do Telegram
    asyncio.create_task(run_upload_pipeline(status_msg, platforms, post_data, guia))
    
    return ConversationHandler.END

async def run_upload_pipeline(status_msg, platforms, post_data, guia):
    """Pipeline de download e upload assíncrono com barra de progresso no Telegram."""
    temp_paths = {}
    db_post_id = None
    loop = asyncio.get_running_loop()
    
    # Helper assíncrono para atualizar o status sem derrubar o pipeline caso a rede oscile
    async def safe_edit_status(text, parse_mode=None, disable_web_page_preview=None):
        try:
            await status_msg.edit_text(text, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
        except Exception as edit_err:
            print(f"[TELEGRAM WARNING] Falha ao atualizar mensagem no Telegram: {edit_err}", flush=True)
    
    # Função auxiliar para gerar callback de progresso no Telegram com throttling temporal (10s)
    def make_telegram_progress_callback(msg, prefix):
        state = {
            "last_percent": -1,
            "last_update_time": 0.0
        }
        def progress_callback(percent):
            now = time.time()
            time_diff = now - state["last_update_time"]
            percent_diff = percent - state["last_percent"]
            
            # Atualiza no início (0%), no fim (100%) ou se mudou mais que 5% e passou 10 segundos
            if percent == 0 or percent == 100 or (percent_diff >= 5 and time_diff >= 10):
                state["last_percent"] = percent
                state["last_update_time"] = now
                print(f"[PIPELINE LOG] {prefix} {percent}%", flush=True)
                
                async def edit_msg():
                    try:
                        await msg.edit_text(f"{prefix} {percent}%")
                    except Exception as telegram_err:
                        print(f"[TELEGRAM ERR] Erro ao editar mensagem de progresso: {telegram_err}", flush=True)
                
                asyncio.run_coroutine_threadsafe(edit_msg(), loop)
        return progress_callback

    try:
        print("[PIPELINE LOG] Iniciando pipeline de envio...", flush=True)
        # 1. Registrar no Banco de Dados
        yt_title = post_data.get("youtube_title", "")
        tt_title = guia.get("titulo_principal", "")
        
        # Constrói o texto formatado para TikTok e Instagram
        def get_formatted_caption(g):
            if g.get("tiktok_guia"):
                return g["tiktok_guia"]
            
            hook = g.get("tiktok_titulo") or g.get("titulo_principal") or "Você teria coragem de assistir até o final? 😳"
            titulo_anime = g.get("tiktok_titulo_anime") or g.get("titulo_anime") or "Release That Witch"
            sinopse = g.get("tiktok_sinopse") or g.get("sinopse") or "Um resumo incrível desse anime!"
            
            # Pega as 5 hashtags virais
            tags_list = g.get("instagram_hashtags") or g.get("tiktok_hashtags") or ["#anime", "#recap", "#viral", "#desenho", "#otaku"]
            if isinstance(tags_list, list):
                tags_str = " ".join(tags_list[:5])
            else:
                tags_str = " ".join([t for t in tags_list.split() if t.startswith("#")][:5])
                
            return f"{hook}\n\nTitulo: {titulo_anime}\n\nSinopse: {sinopse}\n\n{tags_str}"

        caption_texto = get_formatted_caption(guia)
        ig_caption = caption_texto
        
        print(f"[PIPELINE LOG] Registrando post no banco de dados. YouTube={platforms['youtube']}, TikTok={platforms['tiktok']}, Instagram={platforms['instagram']}...", flush=True)
        db_post_id = db.log_post(
            video_path="KAGGLE/PIPELINE/FINAL/video_final.mp4",
            youtube_title=yt_title if platforms["youtube"] else "",
            tiktok_title=tt_title if platforms["tiktok"] else "",
            instagram_caption=ig_caption if platforms["instagram"] else "",
            youtube_status="pending" if platforms["youtube"] else "skipped",
            tiktok_status="pending" if platforms["tiktok"] else "skipped",
            instagram_status="pending" if platforms["instagram"] else "skipped"
        )
        
        # 2. Baixar arquivos do Drive
        temp_paths = {}
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
        os.makedirs(local_dir, exist_ok=True)
        
        folder_id = post_data.get("folder_id")
        
        print(f"[PIPELINE LOG] Buscando arquivos no Google Drive na pasta ID={folder_id}...", flush=True)
        await safe_edit_status("🔍 Buscando arquivos na pasta do Google Drive...")
        drive_files = await loop.run_in_executor(None, drive_manager.list_files_in_folder, folder_id)
        
        files_to_download = {
            "video_final.mp4": "Vídeo Final (.mp4)",
            "thumbnail_youtube.png": "Thumbnail YouTube (.png)",
            "thumbnail_tiktok.png": "Thumbnail TikTok (.png)"
        }
        
        found_files = {}
        for df in drive_files:
            if df["name"] in files_to_download:
                found_files[df["name"]] = df["id"]
                
        for filename, display_name in files_to_download.items():
            # Só baixa a capa específica se a rede social correspondente foi selecionada
            if filename == "thumbnail_youtube.png" and not platforms["youtube"]:
                continue
            if filename == "thumbnail_tiktok.png" and not platforms["tiktok"] and not platforms["instagram"]:
                continue
                
            local_path = os.path.join(local_dir, filename)
            file_id = found_files.get(filename)
            
            if file_id:
                print(f"[PIPELINE LOG] Baixando '{display_name}' via ID={file_id}...", flush=True)
                progress_cb = make_telegram_progress_callback(status_msg, f"📥 Baixando {display_name}:")
                await safe_edit_status(f"📥 Baixando {display_name}: 0%")
                await loop.run_in_executor(None, drive_manager.download_file_by_id, file_id, local_path, progress_cb)
                temp_paths[filename] = local_path
                print(f"[PIPELINE LOG] Download de '{display_name}' concluído com sucesso!", flush=True)
            else:
                # Tenta baixar pelo caminho alternativo
                try:
                    alt_path = f"KAGGLE/PIPELINE/FINAL/{filename}"
                    print(f"[PIPELINE LOG] Arquivo não listado por ID. Buscando '{display_name}' via caminho alternativo '{alt_path}'...", flush=True)
                    progress_cb = make_telegram_progress_callback(status_msg, f"📥 Buscando {display_name}:")
                    await safe_edit_status(f"📥 Buscando {display_name} via caminho alternativo...")
                    await loop.run_in_executor(None, drive_manager.download_file_by_path, alt_path, local_path, progress_cb)
                    temp_paths[filename] = local_path
                    print(f"[PIPELINE LOG] Download alternativo de '{display_name}' concluído com sucesso!", flush=True)
                except Exception as e:
                    print(f"[PIPELINE LOG] Não foi possível baixar {filename} pelo caminho: {e}", flush=True)
                    
        video_path = temp_paths.get("video_final.mp4")
        yt_thumb = temp_paths.get("thumbnail_youtube.png")
        tt_thumb = temp_paths.get("thumbnail_tiktok.png")
        
        if not video_path or not os.path.exists(video_path):
            raise Exception("Vídeo final (video_final.mp4) não pôde ser baixado do Drive.")
            
        results_text = "🚀 <b>Resultados do Envio:</b>\n\n"
        
        # 3. Upload para o YouTube
        if platforms["youtube"]:
            print(f"[PIPELINE LOG] Iniciando upload para o YouTube com o título: '{yt_title}'...", flush=True)
            progress_cb = make_telegram_progress_callback(status_msg, "📤 Enviando para o YouTube:")
            await safe_edit_status("📤 Enviando para o YouTube: 0%")
            try:
                # Constrói a descrição do YouTube com timestamps e hashtags
                desc_yt = guia.get("descricao", "")
                tags_yt = [t.strip() for t in guia.get("tags_youtube", "").split(",") if t.strip()]
                
                vid_id, vid_url = await loop.run_in_executor(
                    None,
                    youtube_uploader.upload_video_to_youtube,
                    video_path,
                    yt_title,
                    desc_yt,
                    tags_yt,
                    "24", # Categoria Entretenimento
                    "private", # Posta como privado/rascunho
                    yt_thumb,
                    progress_cb
                )
                db.update_post_status(db_post_id, "youtube", "completed", url=vid_url)
                results_text += f"✅ <b>YouTube:</b> Enviado com sucesso!\n🔗 <a href=\"{vid_url}\">Link do Vídeo</a>\n\n"
                print(f"[PIPELINE LOG] YouTube enviado com sucesso! URL: {vid_url}", flush=True)
            except Exception as e:
                db.update_post_status(db_post_id, "youtube", "failed", error=str(e))
                results_text += f"❌ <b>YouTube:</b> Falhou! Erro: {e}\n\n"
                print(f"[PIPELINE LOG] YouTube falhou! Erro: {e}", flush=True)
                
        # 4. Upload para o TikTok
        if platforms["tiktok"]:
            print(f"[PIPELINE LOG] Iniciando upload para o TikTok...", flush=True)
            progress_cb = make_telegram_progress_callback(status_msg, "📤 Enviando para o TikTok:")
            await safe_edit_status("📤 Enviando para o TikTok: 0%")
            try:
                # Constrói a legenda do TikTok
                tt_desc = caption_texto
                
                pub_id = await loop.run_in_executor(
                    None,
                    tiktok_uploader.upload_video_to_tiktok,
                    video_path,
                    tt_desc,
                    "PRIVATE",
                    progress_cb
                )
                db.update_post_status(db_post_id, "tiktok", "completed", url=f"publish_id:{pub_id}")
                results_text += f"✅ <b>TikTok:</b> Enviado com sucesso (Privado)!\n\n"
                print(f"[PIPELINE LOG] TikTok enviado com sucesso! ID de Publicação: {pub_id}", flush=True)
            except Exception as e:
                db.update_post_status(db_post_id, "tiktok", "failed", error=str(e))
                results_text += f"❌ <b>TikTok:</b> Falhou! Erro: {e}\n\n"
                print(f"[PIPELINE LOG] TikTok falhou! Erro: {e}", flush=True)
                
        # 5. Upload para o Instagram
        if platforms["instagram"]:
            sched_time = post_data["instagram_scheduled_time"]
            if sched_time:
                # Salva na fila
                print(f"[PIPELINE LOG] Enfileirando Reels para o Instagram agendado para: {sched_time}...", flush=True)
                db.add_to_instagram_queue(
                    video_drive_path="KAGGLE/PIPELINE/FINAL/video_final.mp4",
                    caption=ig_caption,
                    cover_drive_path="KAGGLE/PIPELINE/FINAL/thumbnail_tiktok.png" if tt_thumb else None,
                    scheduled_time=sched_time
                )
                db.update_post_status(db_post_id, "instagram", "scheduled")
                results_text += f"📅 <b>Instagram:</b> Agendado com sucesso para <code>{sched_time}</code>!\n\n"
                print(f"[PIPELINE LOG] Reels agendado no banco com sucesso!", flush=True)
            else:
                print(f"[PIPELINE LOG] Iniciando upload imediato para o Instagram Reels...", flush=True)
                await safe_edit_status("📤 Enviando Reels para o Instagram (isso pode levar alguns minutos)...")
                try:
                    media_id, media_url = await loop.run_in_executor(
                        None,
                        instagram_uploader.upload_reel_to_instagram,
                        video_path,
                        ig_caption,
                        tt_thumb
                    )
                    db.update_post_status(db_post_id, "instagram", "completed", url=media_url)
                    results_text += f"✅ <b>Instagram:</b> Publicado Reels com sucesso!\n🔗 <a href=\"{media_url}\">Link do Reels</a>\n\n"
                    print(f"[PIPELINE LOG] Instagram Reels publicado com sucesso! URL: {media_url}", flush=True)
                except Exception as e:
                    db.update_post_status(db_post_id, "instagram", "failed", error=str(e))
                    results_text += f"❌ <b>Instagram:</b> Falhou! Erro: {e}\n\n"
                    print(f"[PIPELINE LOG] Instagram Reels falhou! Erro: {e}", flush=True)
                    
        # Conclusão
        print("[PIPELINE LOG] Pipeline finalizado. Enviando resultado final para o usuário...", flush=True)
        await safe_edit_status(results_text, parse_mode="HTML", disable_web_page_preview=True)
        
    except Exception as e:
        error_msg = f"❌ Ocorreu um erro geral no pipeline: {e}"
        print(f"[PIPELINE LOG] Erro geral: {e}", flush=True)
        await safe_edit_status(error_msg)
        if db_post_id:
            try:
                db.update_post_status(db_post_id, "youtube", "failed", error=error_msg)
            except: pass
            
    finally:
        # Limpa todos os arquivos baixados localmente
        print("[PIPELINE LOG] Limpando arquivos temporários...", flush=True)
        for name, path in temp_paths.items():
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[PIPELINE LOG] Removido: {path}", flush=True)
                except Exception as ex:
                    print(f"[PIPELINE LOG] Erro ao remover {path}: {ex}", flush=True)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela a operação atual e limpa dados do contexto."""
    if update.message:
        await update.message.reply_text("Operação cancelada.")
    elif update.callback_query:
        await update.callback_query.answer("Operação cancelada.")
        await update.callback_query.edit_message_text("Operação cancelada.")
    return ConversationHandler.END

def main():
    # Define o event loop na thread principal para evitar RuntimeError no Python 3.12+
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[ERRO] TELEGRAM_BOT_TOKEN ausente no .env. Configure para rodar o bot.")
        return
        
    # Inicializa o bot
    app = ApplicationBuilder().token(token).build()
    
    # Handler de conversação
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(menu_postar, pattern="^menu_postar$"),
            CallbackQueryHandler(menu_fila, pattern="^menu_fila$"),
            CallbackQueryHandler(show_main_menu_callback, pattern="^back_to_menu$"),
        ],
        states={
            SELECT_PLATFORMS: [
                CallbackQueryHandler(menu_postar, pattern="^menu_postar$"),
                CallbackQueryHandler(menu_fila, pattern="^menu_fila$"),
                CallbackQueryHandler(toggle_platform, pattern="^toggle_"),
                CallbackQueryHandler(confirm_platforms, pattern="^confirm_platforms$"),
                CallbackQueryHandler(show_main_menu_callback, pattern="^back_to_menu$"),
            ],
            SELECT_YOUTUBE_TITLE: [
                CallbackQueryHandler(handle_youtube_title_selection, pattern="^yt_title_"),
                CallbackQueryHandler(menu_postar, pattern="^menu_postar$"),
            ],
            INPUT_YOUTUBE_TITLE_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_title_manual)
            ],
            SELECT_INSTAGRAM_SCHEDULING: [
                CallbackQueryHandler(handle_instagram_scheduling, pattern="^ig_")
            ],
            INPUT_INSTAGRAM_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram_time)
            ],
            CONFIRM_POST: [
                CallbackQueryHandler(execute_upload, pattern="^execute_upload$"),
                CallbackQueryHandler(show_main_menu_callback, pattern="^back_to_menu$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$")
        ]
    )
    
    app.add_handler(conv_handler)
    
    # Inicia o worker de fila em segundo plano em uma thread separada
    worker_thread = threading.Thread(target=run_queue_worker, daemon=True)
    worker_thread.start()
    
    while True:
        try:
            print("Bot do Telegram em execução...", flush=True)
            app.run_polling()
            break
        except NetworkError as e:
            print(f"[REDE] Erro de conexão com o Telegram: {e}. Tentando novamente em 5 segundos...", flush=True)
            time.sleep(5)
        except Exception as e:
            print(f"[ERRO] Erro inesperado ao rodar o bot: {e}. Reiniciando em 5 segundos...", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
