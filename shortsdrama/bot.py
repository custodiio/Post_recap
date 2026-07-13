import os
import re
import sys
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode

# Adiciona pastas necessárias ao path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import db
import scraper
import ffmpeg_handler
import uploader
import templates
import cover_processor

# Configura logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações do Bot vindas do ambiente
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", "7321866230"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8651236601:AAGeOV_1rMNv9Fpoleh2WSiYrjpJ8gTXdmI")

# Estado de sessão temporária
_session = {}

def admin_only(func):
    """Filtra requisições de chat que não sejam do administrador."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != ADMIN_CHAT_ID:
            logger.warning(f"[BOT] Acesso não autorizado do chat_id: {chat_id}")
            return
        return await func(update, context)
    return wrapper

@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Mostra painel de controle no Telegram."""
    await _show_panel(update, context)

async def _show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    """Renderiza a interface do painel de controle do Telegram."""
    db.init_db() # Garante o banco iniciado
    
    tt_auto = db.get_setting('tiktok_auto_post', '0') == '1'
    yt_auto = db.get_setting('youtube_auto_post', '0') == '1'
    posts_day = db.get_setting('posts_per_day', '2')
    hours = db.get_setting('scheduled_hours', '12:00,18:00')
    
    status_tt = "🟢 LIGADO" if tt_auto else "🔴 DESLIGADO"
    status_yt = "🟢 LIGADO" if yt_auto else "🔴 DESLIGADO"
    
    text = (
        "🎭 *SHORTS DRAMAS - PAINEL DE CONTROLE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 *Auto-Poster TikTok:* {status_tt}\n"
        f"🤖 *Auto-Poster YouTube:* {status_yt}\n"
        f"📅 *Volume:* {posts_day} posts/dia em ({hours})\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📥 *Postagem Manual:* Envie um link do Telegram privado de um vídeo (ex: `https://t.me/c/1234/567`)\n"
        "ou envie um link de Douyin."
    )
    
    # Teclado interativo
    keyboard = [
        [
            InlineKeyboardButton(f"TikTok: {'Pausar' if tt_auto else 'Iniciar'}", callback_data="toggle_auto_tt"),
            InlineKeyboardButton(f"YouTube: {'Pausar' if yt_auto else 'Iniciar'}", callback_data="toggle_auto_yt")
        ],
        [
            InlineKeyboardButton("📚 Ver Partes Pendentes", callback_data="view_pending"),
            InlineKeyboardButton("🔑 Acessar Painel Web", callback_data="generate_login_link")
        ],
        [
            InlineKeyboardButton("🔄 Atualizar Painel", callback_data="refresh_lobby")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg:
            await msg.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

@admin_only
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia callbacks inline do teclado."""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "refresh_lobby":
        await _show_panel(update, context, edit=True)
        
    elif data == "generate_login_link":
        import uuid
        token = str(uuid.uuid4())
        db.create_login_token("allessandrocustodio.alves@gmail.com", token)
        login_url = f"https://animesrecaps.me/dramas?token={token}"
        await query.message.reply_text(
            f"🔑 *Link de Acesso Único (Válido por 10 minutos):*\n\n"
            f"🔗 [Clique aqui para entrar no Painel]({login_url})\n\n"
            f"_Após entrar, a sua sessão no navegador durará 1 hora._",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
    elif data == "toggle_auto_tt":
        current = db.get_setting('tiktok_auto_post', '0')
        new_val = '1' if current == '0' else '0'
        db.update_setting('tiktok_auto_post', new_val)
        await _show_panel(update, context, edit=True)
        
    elif data == "toggle_auto_yt":
        current = db.get_setting('youtube_auto_post', '0')
        new_val = '1' if current == '0' else '0'
        db.update_setting('youtube_auto_post', new_val)
        await _show_panel(update, context, edit=True)
        
    elif data == "view_pending":
        await _show_pending_parts(update, context, edit=True)
        
    elif data.startswith("post_part_"):
        part_id = int(data.split("_")[2])
        context.application.create_task(_process_pending_part(query.message.chat_id, part_id, context))
        await query.edit_message_text("🚀 Iniciando fatiamento e upload da parte selecionada...")
        
    elif data.startswith("set_dest_"):
        # Processo de postagem manual - define plataforma e privacidade
        parts = data.split("_")
        chat_id = parts[2]
        msg_id = int(parts[3])
        platform_choice = parts[4] # yt, tt, dm, both, all
        priv_choice = parts[5] # public, private
        
        context.application.create_task(
            _process_manual_post(update.effective_chat.id, chat_id, msg_id, platform_choice, priv_choice, context)
        )
        dest_label = {
            "yt": "YouTube",
            "tt": "TikTok",
            "dm": "Dailymotion",
            "both": "YouTube + TikTok",
            "all": "YouTube + TikTok + Dailymotion"
        }.get(platform_choice, "Desconhecido")
        await query.edit_message_text(f"⏳ Processando vídeo no *{dest_label}* com privacidade: *{priv_choice.upper()}*...", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercepta links do Telegram ou Douyin enviados pelo admin."""
    text = update.message.text or ""
    
    # 1. Tenta identificar link de mensagem privada do Telegram
    # Formato: https://t.me/c/123456789/456 ou t.me/c/123456789/456
    tg_match = re.search(r't\.me\/c\/(\d+|-\d+)\/(\d+)', text)
    if tg_match:
        chat_id = f"-100{tg_match.group(1)}"
        msg_id = int(tg_match.group(2))
        
        # Pergunta o destino e a privacidade antes de fazer o upload
        keyboard = [
            [
                InlineKeyboardButton("📺 YouTube (Público)", callback_data=f"set_dest_{chat_id}_{msg_id}_yt_public"),
                InlineKeyboardButton("📺 YouTube (Privado)", callback_data=f"set_dest_{chat_id}_{msg_id}_yt_private")
            ],
            [
                InlineKeyboardButton("🎵 TikTok (Público)", callback_data=f"set_dest_{chat_id}_{msg_id}_tt_public"),
                InlineKeyboardButton("🎵 TikTok (Privado)", callback_data=f"set_dest_{chat_id}_{msg_id}_tt_private")
            ],
            [
                InlineKeyboardButton("Ⓜ️ Dailymotion (Público)", callback_data=f"set_dest_{chat_id}_{msg_id}_dm_public"),
                InlineKeyboardButton("Ⓜ️ Dailymotion (Privado)", callback_data=f"set_dest_{chat_id}_{msg_id}_dm_private")
            ],
            [
                InlineKeyboardButton("🔄 Ambos YT+TT (Público)", callback_data=f"set_dest_{chat_id}_{msg_id}_both_public"),
                InlineKeyboardButton("🔄 Ambos YT+TT (Privado)", callback_data=f"set_dest_{chat_id}_{msg_id}_both_private")
            ],
            [
                InlineKeyboardButton("🌟 Todas Redes (Público)", callback_data=f"set_dest_{chat_id}_{msg_id}_all_public"),
                InlineKeyboardButton("🌟 Todas Redes (Privado)", callback_data=f"set_dest_{chat_id}_{msg_id}_all_private")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Selecione o destino e a privacidade para esta postagem:",
            reply_markup=reply_markup
        )
        return
        
    # 2. Tenta identificar link do Douyin
    if "douyin.com" in text:
        await update.message.reply_text("📥 Link do Douyin detectado! Função de autopost Douyin pendente de refinação.")
        return
        
    await update.message.reply_text("❌ Link não reconhecido. Envie um link válido de vídeo de canal privado do Telegram ou Douyin.")

async def _process_manual_post(chat_id: int, source_chat: str, msg_id: int, platform: str, privacy: str, context: ContextTypes.DEFAULT_TYPE):
    """Pipeline que baixa, corta a Parte 1 de 6-8 minutos e posta nas redes selecionadas."""
    status_msg = await context.bot.send_message(chat_id, "⏳ Inicializando cliente Telegram MTProto...")
    
    tmp_orig = os.path.join(current_dir, "temp", f"orig_{msg_id}.mp4")
    tmp_cut = os.path.join(current_dir, "temp", f"cut_{msg_id}.mp4")
    tmp_orig_cover = os.path.join(current_dir, "temp", f"cover_orig_{msg_id}.jpg")
    tmp_final_cover = os.path.join(current_dir, "temp", f"cover_final_{msg_id}.jpg")
    os.makedirs(os.path.dirname(tmp_orig), exist_ok=True)
    
    client = None
    try:
        client = await scraper.get_telegram_client()
        
        # Fase 1: Baixar o vídeo
        async def progress(text):
            try:
                await status_msg.edit_text(text)
            except Exception:
                pass
            
        success, path = await scraper.download_telegram_video(
            client=client,
            chat_id=source_chat,
            message_id=msg_id,
            output_path=tmp_orig,
            progress_callback=progress
        )
        
        if not success:
            await status_msg.edit_text(f"❌ Erro ao baixar vídeo: {path}")
            return
            
        # Fase 2: Scrape da Sinopse / Título e Capa
        await status_msg.edit_text("🔍 Varrendo metadados e capa do post no canal...")
        title, caption = await scraper.extract_post_meta_from_telegram(client, source_chat, msg_id)
        
        # Faz download da capa (foto anterior ao vídeo no Telegram)
        has_cover = await scraper.download_telegram_cover(client, source_chat, msg_id, tmp_orig_cover)
        cover_ready = False
        if has_cover:
            await status_msg.edit_text("🎨 Editando capa 16:9 (3 painéis)...")
            cover_ready = cover_processor.create_16_9_cover(tmp_orig_cover, tmp_final_cover)
        
        # Fase 3: Fatiamento em 6-8 minutos
        total_duration = await ffmpeg_handler.get_video_duration(tmp_orig)
        parts_plan = ffmpeg_handler.calculate_parts(total_duration)
        
        if not parts_plan:
            await status_msg.edit_text("❌ Falha ao calcular fatiamento do vídeo.")
            return
            
        p1 = parts_plan[0]
        await status_msg.edit_text(f"✂️ Fatiando Parte 1 ({p1['duration']/60:.1f} minutos)...")
        cut_ok, cut_path = await ffmpeg_handler.cut_video_part(
            src_path=tmp_orig,
            dst_path=tmp_cut,
            start_sec=p1['start_time'],
            duration_sec=p1['duration']
        )
        
        if not cut_ok:
            await status_msg.edit_text(f"❌ Erro ao cortar vídeo: {cut_path}")
            return
            
        # Salva o drama no banco
        covers_dir = os.path.join(current_dir, "covers")
        os.makedirs(covers_dir, exist_ok=True)
        drama_id = db.save_drama(
            title=title,
            msg_id=msg_id,
            chat_id=source_chat,
            duration=int(total_duration),
            file_size=os.path.getsize(tmp_orig),
            caption=caption,
            file_name=os.path.basename(tmp_orig)
        )

        # Persiste a capa final no disco de forma permanente
        permanent_cover = os.path.join(covers_dir, f"drama_{drama_id}.jpg")
        if cover_ready and os.path.exists(tmp_final_cover):
            import shutil
            shutil.copy2(tmp_final_cover, permanent_cover)
            db.update_drama_cover(drama_id, permanent_cover)
        else:
            # Tenta extrair thumbnail do vídeo como fallback
            thumb_ok = await ffmpeg_handler.extract_thumbnail(tmp_orig, permanent_cover, time_sec=10.0)
            if thumb_ok:
                db.update_drama_cover(drama_id, permanent_cover)
        
        # Salva APENAS a Parte 1 — as demais partes são postadas manualmente pelo painel web.
        # Não pré-criamos as partes 2+ para evitar que o scheduler automático as poste
        # como sequência de outro drama.
        part1_id = db.save_part(drama_id, 1, p1['start_time'], p1['end_time'], p1['duration'], status='processing')
            
        # Gera metadados de postagem formatados pelo template
        meta = templates.format_post_meta(title, 1)
        
        # Fase 4: Postagem no YouTube (Vídeo Completo com Capa)
        yt_ok, yt_id = False, "Pulado"
        if platform in ["yt", "both", "all"]:
            await status_msg.edit_text("📤 Enviando Vídeo Completo para o YouTube...")
            yt_ok, yt_id = await uploader.upload_to_youtube(
                video_path=tmp_orig,
                title=meta["youtube_title"],
                description=meta["youtube_desc"],
                tags=meta["tags"],
                privacy_status=privacy,
                thumbnail_path=tmp_final_cover if cover_ready else None
            )
        
        # Fase 5: Postagem no TikTok (Parte 1 Fatiada)
        tt_ok, tt_id = False, "Pulado"
        if platform in ["tt", "both", "all"]:
            await status_msg.edit_text("📤 Enviando Parte 1 para o TikTok...")
            tt_privacy = db.get_setting("tiktok_default_privacy", "SELF_ONLY")
            tt_ok, tt_id = await uploader.upload_to_tiktok(
                video_path=tmp_cut,
                title=meta["tiktok_desc"],
                privacy_level=tt_privacy
            )

        # Fase 6: Postagem no Dailymotion (Vídeo Completo)
        dm_ok, dm_id = False, "Pulado"
        if platform in ["dm", "all"]:
            await status_msg.edit_text("📤 Enviando Vídeo Completo para o Dailymotion...")
            async def dm_progress(status_text):
                try:
                    await status_msg.edit_text(status_text)
                except:
                    pass
            dm_ok, dm_id = await uploader.upload_to_dailymotion(
                video_path=tmp_orig,
                title=meta["youtube_title"],
                description=meta["youtube_desc"],
                tags=meta["tags"],
                privacy_status=privacy,
                progress_callback=dm_progress
            )
        
        # Atualiza o status da Parte 1 no banco após os uploads
        any_success = tt_ok or yt_ok or dm_ok
        if any_success:
            db.update_part(part1_id, {
                'status': 'posted',
                'tiktok_publish_id': tt_id if tt_ok else None,
                'youtube_video_id': yt_id if yt_ok else None,
                'posted_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        else:
            db.update_part(part1_id, {'status': 'failed', 'error_message': 'Todos os uploads falharam.'})
        
        # Finalização e Limpeza
        num_total_parts = len(parts_plan)
        result_text = (
            f"✅ *PROCESSO CONCLUÍDO!*\n\n"
            f"🎬 *Drama:* {title}\n"
            f"📂 *Total de partes disponíveis:* {num_total_parts} "
            f"(poste as próximas pelo Painel Web)\n\n"
        )
        if platform in ["yt", "both", "all"]:
            if yt_ok: result_text += f"📺 YouTube (Completo): Enviado (ID: `{yt_id}`)\n"
            else: result_text += f"❌ YouTube Falhou: {yt_id}\n"
        
        if platform in ["tt", "both", "all"]:
            if tt_ok: result_text += f"🎵 TikTok (Parte 1): Enviado (ID: `{tt_id}`)\n"
            else: result_text += f"❌ TikTok Falhou: {tt_id}\n"

        if platform in ["dm", "all"]:
            if dm_ok: result_text += f"Ⓜ️ Dailymotion (Completo): Enviado (ID: `{dm_id}`)\n"
            else: result_text += f"❌ Dailymotion Falhou: {dm_id}\n"
        
        await status_msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"[BOT] Erro ao processar postagem manual: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Erro crítico no pipeline: {e}")
        
    finally:
        # Garante a remoção dos arquivos temporários do disco
        if os.path.exists(tmp_orig): os.remove(tmp_orig)
        if os.path.exists(tmp_cut): os.remove(tmp_cut)
        if os.path.exists(tmp_orig_cover):
            try: os.remove(tmp_orig_cover)
            except: pass
        # NÃO remove tmp_final_cover — foi copiado para covers/ (ou ignorado se já lá está)
        if os.path.exists(tmp_final_cover):
            try: os.remove(tmp_final_cover)
            except: pass
        if client: await client.disconnect()

async def _show_pending_parts(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    """Mostra lista de partes pendentes e gera teclado para postagem."""
    parts = db.get_pending_parts()
    
    if not parts:
        text = "📭 Nenhuma parte 2 ou subsequente pendente na fila."
        keyboard = [[InlineKeyboardButton("🔙 Voltar", callback_data="refresh_lobby")]]
    else:
        text = f"📚 *PARTES PENDENTES NA FILA ({len(parts)}):*\n\n"
        keyboard = []
        for p in parts[:8]: # Limita visualização rápida
            text += f"🎬 *{p['drama_title']}* [Parte {p['part_number']}]\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"Postar Parte {p['part_number']}: {p['drama_title'][:20]}...",
                    callback_data=f"post_part_{p['id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="refresh_lobby")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        msg = update.message or (update.callback_query.message if update.callback_query else None)
        if msg:
            await msg.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

async def _process_pending_part(chat_id: int, part_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Recorta e envia a parte selecionada aplicando recapitulação de 30 segundos."""
    status_msg = await context.bot.send_message(chat_id, "⏳ Inicializando faturamento de parte...")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT dp.*, d.title as drama_title, d.telegram_message_id, d.telegram_chat_id 
        FROM drama_parts dp
        JOIN dramas d ON dp.drama_id = d.id
        WHERE dp.id = ?
    ''', (part_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await status_msg.edit_text("❌ Parte não encontrada no banco.")
        return
        
    part = dict(row)
    msg_id = part['telegram_message_id']
    source_chat = part['telegram_chat_id']
    title = part['drama_title']
    part_num = part['part_number']
    
    # Ponto de início recalculado aplicando 30 segundos de recapitulação
    start_time = max(0.0, part['start_time'] - 30.0)
    # Aumenta a duração para incluir os 30 segundos extras
    duration = part['duration'] + 30.0 if part['start_time'] > 30.0 else part['duration']
    
    tmp_orig = os.path.join(current_dir, "temp", f"orig_{msg_id}_p{part_num}.mp4")
    tmp_cut = os.path.join(current_dir, "temp", f"cut_{msg_id}_p{part_num}.mp4")
    
    client = None
    try:
        client = await scraper.get_telegram_client()
        
        async def progress(text):
            await status_msg.edit_text(text)
            
        # Baixa original de novo sob demanda
        await progress("📥 Baixando vídeo original do Telegram...")
        success, path = await scraper.download_telegram_video(
            client=client,
            chat_id=source_chat,
            message_id=msg_id,
            output_path=tmp_orig,
            progress_callback=progress
        )
        
        if not success:
            await status_msg.edit_text(f"❌ Erro ao baixar vídeo: {path}")
            return
            
        await progress(f"✂️ Cortando Parte {part_num} com 30s de recap...")
        cut_ok, cut_path = await ffmpeg_handler.cut_video_part(
            src_path=tmp_orig,
            dst_path=tmp_cut,
            start_sec=start_time,
            duration_sec=duration
        )
        
        if not cut_ok:
            await status_msg.edit_text(f"❌ Erro ao fatiar vídeo: {cut_path}")
            return
            
        meta = templates.format_post_meta(title, part_num)
        
        # Postagem no TikTok (apenas TikTok para as partes subsequentes)
        await progress(f"📤 Enviando Parte {part_num} para o TikTok...")
        tt_privacy = db.get_setting("tiktok_default_privacy", "SELF_ONLY")
        tt_ok, tt_id = await uploader.upload_to_tiktok(
            video_path=tmp_cut,
            title=meta["tiktok_desc"],
            privacy_level=tt_privacy
        )
        
        if tt_ok:
            db.update_part(part_id, {
                'status': 'posted',
                'tiktok_publish_id': tt_id,
                'posted_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            await status_msg.edit_text(f"✅ *Parte {part_num} publicada com sucesso!*\n🎵 TikTok ID: `{tt_id}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await status_msg.edit_text("❌ Falha na postagem no TikTok.")
            
    except Exception as e:
        logger.error(f"[BOT] Erro ao postar Parte {part_num}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Erro no pipeline: {e}")
    finally:
        if os.path.exists(tmp_orig): os.remove(tmp_orig)
        if os.path.exists(tmp_cut): os.remove(tmp_cut)
        if client: await client.disconnect()

@admin_only
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gera um link de login válido por 10 minutos."""
    import uuid
    token = str(uuid.uuid4())
    db.create_login_token("allessandrocustodio.alves@gmail.com", token)
    login_url = f"https://animesrecaps.me/dramas?token={token}"
    await update.message.reply_text(
        f"🔑 *Link de Acesso Único (Válido por 10 minutos):*\n\n"
        f"🔗 [Clique aqui para entrar no Painel]({login_url})\n\n"
        f"_Após entrar, a sua sessão no navegador durará 1 hora._",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

def main():
    """Inicialização do Bot."""
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_handler))
    
    logger.info("[SHORTSDRAMA] Bot iniciado e aguardando conexões...")
    app.run_polling()

if __name__ == '__main__':
    main()
