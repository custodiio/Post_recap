import os
import sys
import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Adiciona diretórios ao path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import db
import uploader
import ffmpeg_handler
import scraper
import templates

# Configurações do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ShortsDrama Manager API", version="1.0.0")

# Habilita CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servindo arquivos estáticos para o painel frontend
frontend_path = os.path.join(current_dir, "frontend")
os.makedirs(frontend_path, exist_ok=True)

# Banco de dados de sessões em memória (expiração de 1 hora)
ACTIVE_SESSIONS = {}

def create_session(username: str) -> str:
    session_id = str(uuid.uuid4())
    expiry = datetime.now() + timedelta(hours=1)
    ACTIVE_SESSIONS[session_id] = {
        "username": username,
        "expiry": expiry
    }
    return session_id

def verify_session(session_id: str) -> bool:
    if not session_id or session_id not in ACTIVE_SESSIONS:
        return False
    session = ACTIVE_SESSIONS[session_id]
    if datetime.now() > session["expiry"]:
        # Expirada
        ACTIVE_SESSIONS.pop(session_id, None)
        return False
    # Estende a expiração a cada interação
    session["expiry"] = datetime.now() + timedelta(hours=1)
    return True

# Schemas Pydantic
class LoginRequest(BaseModel):
    email: str

class SettingsUpdate(BaseModel):
    tiktok_auto_post: str
    youtube_auto_post: str
    posts_per_day: str
    scheduled_hours: str
    youtube_default_privacy: str
    tiktok_default_privacy: str = "SELF_ONLY"

class TemplateRequest(BaseModel):
    name: str
    youtube_title: str
    youtube_desc: str
    tiktok_desc: str
    tags: str

class PostPartRequest(BaseModel):
    platform: str = "tt"   # tt, yt, both, all
    privacy: str = "SELF_ONLY"  # SELF_ONLY, PUBLIC_TO_EVERYONE, private, public

# Endpoints de Autenticação
@app.post("/dramas/api/auth/login")
async def login(req: LoginRequest):
    # Aceita os mesmos e-mails aprovados do painel principal
    allowed_emails = ["alecust123@gmail.com", "allessandrocustodio.alves@gmail.com"]
    if req.email.lower() not in allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso não autorizado. E-mail não cadastrado na lista de administradores."
        )
    session_id = create_session(req.email.lower())
    response = JSONResponse(content={"status": "success", "session_id": session_id})
    # Define cookie de sessão seguro
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        max_age=3600,
        samesite="lax"
    )
    return response

@app.post("/dramas/api/auth/logout")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        ACTIVE_SESSIONS.pop(session_id, None)
    response = JSONResponse(content={"status": "success"})
    response.delete_cookie("session_id")
    return response

# Dependency de Autenticação
def get_current_user(request: Request):
    # Permite passar via header para desenvolvimento ou cookies
    session_id = request.headers.get("Authorization") or request.cookies.get("session_id")
    if session_id and session_id.startswith("Bearer "):
        session_id = session_id.split(" ")[1]
        
    if not verify_session(session_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada. Faça login novamente."
        )
    return ACTIVE_SESSIONS[session_id]["username"]

# Endpoints do Dashboard
@app.get("/dramas/api/dramas")
async def list_dramas(user: str = Depends(get_current_user)):
    dramas = db.get_all_dramas()
    # Adiciona as partes de cada drama no retorno
    for d in dramas:
        d["parts"] = db.get_parts_for_drama(d["id"])
    return dramas

@app.get("/dramas/api/dramas/{drama_id}")
async def get_drama_details(drama_id: int, user: str = Depends(get_current_user)):
    drama = db.get_drama(drama_id)
    if not drama:
        raise HTTPException(status_code=404, detail="Drama não encontrado.")
    parts = db.get_parts_for_drama(drama_id)
    return {"drama": drama, "parts": parts}

@app.delete("/dramas/api/dramas/{drama_id}")
async def delete_drama_endpoint(drama_id: int, user: str = Depends(get_current_user)):
    db.delete_drama(drama_id)
    return {"status": "success", "message": "Drama excluído com sucesso."}

@app.get("/dramas/api/settings")
async def get_settings(user: str = Depends(get_current_user)):
    return {
        "tiktok_auto_post": db.get_setting("tiktok_auto_post", "0"),
        "youtube_auto_post": db.get_setting("youtube_auto_post", "0"),
        "posts_per_day": db.get_setting("posts_per_day", "2"),
        "scheduled_hours": db.get_setting("scheduled_hours", "12:00,18:00"),
        "youtube_default_privacy": db.get_setting("youtube_default_privacy", "private"),
        "tiktok_default_privacy": db.get_setting("tiktok_default_privacy", "SELF_ONLY")
    }

@app.post("/dramas/api/settings")
async def update_settings_endpoint(settings: SettingsUpdate, user: str = Depends(get_current_user)):
    db.update_setting("tiktok_auto_post", settings.tiktok_auto_post)
    db.update_setting("youtube_auto_post", settings.youtube_auto_post)
    db.update_setting("posts_per_day", settings.posts_per_day)
    db.update_setting("scheduled_hours", settings.scheduled_hours)
    db.update_setting("youtube_default_privacy", settings.youtube_default_privacy)
    db.update_setting("tiktok_default_privacy", settings.tiktok_default_privacy)
    return {"status": "success", "message": "Configurações atualizadas."}

@app.get("/dramas/api/templates")
async def get_templates(user: str = Depends(get_current_user)):
    return db.get_all_templates()

@app.post("/dramas/api/templates")
async def create_template(req: TemplateRequest, user: str = Depends(get_current_user)):
    t_id = db.save_template(req.name, req.youtube_title, req.youtube_desc, req.tiktok_desc, req.tags)
    return {"status": "success", "id": t_id}

@app.put("/dramas/api/templates/{template_id}")
async def update_template_endpoint(template_id: int, req: TemplateRequest, user: str = Depends(get_current_user)):
    db.update_template(template_id, req.name, req.youtube_title, req.youtube_desc, req.tiktok_desc, req.tags)
    return {"status": "success"}

@app.delete("/dramas/api/templates/{template_id}")
async def delete_template_endpoint(template_id: int, user: str = Depends(get_current_user)):
    db.delete_template(template_id)
    return {"status": "success"}

@app.post("/dramas/api/parts/{part_id}/post")
async def post_part_endpoint(part_id: int, req: PostPartRequest = PostPartRequest(), user: str = Depends(get_current_user)):
    """Dispara a postagem imediata de uma parte específica em background."""
    asyncio.create_task(run_manual_part_posting(part_id, req.platform, req.privacy))
    return {"status": "success", "message": "Pipeline de postagem iniciado em background."}

async def run_manual_part_posting(part_id: int, platform: str = "tt", privacy: str = "SELF_ONLY"):
    """Executa o download, corte e envio da parte na VPS."""
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
        logger.error(f"[API] Falha ao iniciar postagem da parte {part_id}: registro não encontrado.")
        return
        
    part = dict(row)
    msg_id = part['telegram_message_id']
    source_chat = part['telegram_chat_id']
    title = part['drama_title']
    part_num = part['part_number']
    
    logger.info(f"[API] Postagem manual disparada pelo painel para: {title} (Parte {part_num})")
    
    db.update_part(part_id, {'status': 'processing', 'error_message': None})
    
    tmp_orig = os.path.join(current_dir, "temp", f"orig_api_{msg_id}_p{part_num}.mp4")
    tmp_cut = os.path.join(current_dir, "temp", f"cut_api_{msg_id}_p{part_num}.mp4")
    os.makedirs(os.path.dirname(tmp_orig), exist_ok=True)
    
    # Ponto de início com 30s de recap
    start_time = max(0.0, part['start_time'] - 30.0)
    duration = part['duration'] + 30.0 if part['start_time'] > 30.0 else part['duration']
    
    client = None
    try:
        client = await scraper.get_telegram_client()
        
        # Download
        success, path = await scraper.download_telegram_video(
            client=client,
            chat_id=source_chat,
            message_id=msg_id,
            output_path=tmp_orig
        )
        
        if not success:
            db.update_part(part_id, {'status': 'failed', 'error_message': f"Erro no download: {path}"})
            return
            
        # Corte
        cut_ok, cut_path = await ffmpeg_handler.cut_video_part(
            src_path=tmp_orig,
            dst_path=tmp_cut,
            start_sec=start_time,
            duration_sec=duration
        )
        
        if not cut_ok:
            db.update_part(part_id, {'status': 'failed', 'error_message': f"Erro no FFmpeg: {cut_path}"})
            return
            
        meta = templates.format_post_meta(title, part_num)
        
        # Upload para as plataformas escolhidas pelo usuário no painel
        tt_ok, tt_id = False, "Pulado"
        yt_ok, yt_id = False, "Pulado"
        
        if platform in ["tt", "both", "all"]:
            # TikTok: mapeia privacidade legível para constante da API
            tt_privacy_map = {
                "public": "PUBLIC_TO_EVERYONE",
                "private": "SELF_ONLY",
            }
            tt_privacy = tt_privacy_map.get(privacy, privacy)  # aceita constante direta também
            tt_ok, tt_id = await uploader.upload_to_tiktok(
                video_path=tmp_cut,
                title=meta["tiktok_desc"],
                privacy_level=tt_privacy
            )
        
        if platform in ["yt", "both", "all"]:
            yt_privacy = "public" if privacy in ["public", "PUBLIC_TO_EVERYONE"] else "private"
            yt_ok, yt_id = await uploader.upload_to_youtube(
                video_path=tmp_cut,
                title=meta["youtube_title"],
                description=meta["youtube_desc"],
                tags=meta["tags"],
                privacy_status=yt_privacy
            )
        
        any_success = tt_ok or yt_ok
        if any_success:
            db.update_part(part_id, {
                'status': 'posted',
                'tiktok_publish_id': tt_id if tt_ok else None,
                'youtube_video_id': yt_id if yt_ok else None,
                'posted_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            logger.info(f"[API] Parte {part_num} do drama '{title}' postada com sucesso. Platform={platform}")
        else:
            db.update_part(part_id, {'status': 'failed', 'error_message': f"Upload falhou. TikTok={tt_id} | YT={yt_id}"})
            
    except Exception as e:
        logger.error(f"[API] Falha no pipeline da parte {part_id}: {e}", exc_info=True)
        db.update_part(part_id, {'status': 'failed', 'error_message': str(e)})
    finally:
        # Limpeza total imediata após postagem para economizar espaço
        if os.path.exists(tmp_orig): os.remove(tmp_orig)
        if os.path.exists(tmp_cut): os.remove(tmp_cut)
        if client: await client.disconnect()

# Motor de Tarefas de Fundo (Background Scheduler) para Postagens Automáticas
async def auto_post_scheduler_loop():
    """Loop recorrente que acorda a cada 5 minutos para processar posts automáticos no horário agendado."""
    logger.info("[SCHEDULER] Fila de postagens automáticas iniciada.")
    db.init_db()
    
    while True:
        try:
            # Verifica se algum auto poster está ativado
            tt_auto = db.get_setting("tiktok_auto_post", "0") == "1"
            yt_auto = db.get_setting("youtube_auto_post", "0") == "1"
            
            if tt_auto or yt_auto:
                now = datetime.now()
                scheduled_hours_str = db.get_setting("scheduled_hours", "12:00,18:00")
                scheduled_hours = [h.strip() for h in scheduled_hours_str.split(",") if h.strip()]
                
                # Compara hora e minutos atuais para ver se estamos no momento de postar
                current_time_str = now.strftime("%H:%M")
                
                for target_hour in scheduled_hours:
                    # Permite variação dinâmica de minutos (comparação flexível na janela do scheduler)
                    # ex: se a hora alvo é 12:00, o scheduler vai disparar entre 12:00 e 12:05
                    t_dt = datetime.strptime(target_hour, "%H:%M")
                    diff = abs((now.hour * 60 + now.minute) - (t_dt.hour * 60 + t_dt.minute))
                    
                    if diff <= 3: # Janela de 3 minutos para disparar
                        # Evita disparar múltiplas vezes na mesma janela
                        last_run = db.get_setting("last_cron_run", "")
                        today_key = f"{now.strftime('%Y-%m-%d')}_{target_hour}"
                        
                        if last_run != today_key:
                            db.update_setting("last_cron_run", today_key)
                            logger.info(f"[SCHEDULER] Horário de disparo atingido: {target_hour}. Buscando posts...")
                            
                            # Busca a próxima parte pendente da fila
                            pending_parts = db.get_pending_parts()
                            if pending_parts:
                                next_part = pending_parts[0]
                                logger.info(f"[SCHEDULER] Disparando envio automático da parte: {next_part['drama_title']} - Parte {next_part['part_number']}")
                                asyncio.create_task(run_manual_part_posting(next_part['id']))
                            else:
                                logger.warning("[SCHEDULER] Horário de postagem atingido, mas a fila de partes pendentes está vazia!")
                            break
                            
        except Exception as e:
            logger.error(f"[SCHEDULER] Erro no loop de postagem automática: {e}")
            
        await asyncio.sleep(300) # Dorme por 5 minutos

@app.on_event("startup")
async def startup_event():
    # Inicializa banco de dados
    db.init_db()
    # Inicia o loop de postagens automáticas em background
    asyncio.create_task(auto_post_scheduler_loop())

# Montando pasta frontend para servir arquivos estáticos
# Se o index.html não existir na pasta, criamos um template básico inicial
if os.path.exists(frontend_path):
    app.mount("/dramas/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/dramas", response_class=HTMLResponse)
async def get_dashboard_page(request: Request, token: Optional[str] = None):
    # Fluxo de login automático via Token do Telegram
    if token:
        email = db.consume_login_token(token)
        if email:
            session_id = create_session(email)
            response = RedirectResponse(url="/dramas", status_code=303)
            response.set_cookie(
                key="session_id",
                value=session_id,
                httponly=True,
                max_age=3600,
                samesite="lax"
            )
            # Retorna redirect limpo
            return response
        else:
            # HTML de erro amigável caso o token falhe
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Link Expirado</title>
                <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600&display=swap" rel="stylesheet">
                <style>
                    body { background: #0a0a0c; color: #e2e2e8; font-family: 'Outfit', sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
                    .card { background: #131317; border: 1px solid #212128; padding: 40px; border-radius: 20px; text-align: center; max-width: 400px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
                    h2 { color: #d11270; margin-bottom: 10px; }
                    p { color: #8e8e9c; font-size: 0.95rem; line-height: 1.5; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h2>⚠️ Link de Acesso Expirado</h2>
                    <p>Este link de login de uso único expirou (limite de 10 minutos) ou já foi utilizado. Por favor, envie o comando /login no bot do Telegram para gerar um novo link.</p>
                </div>
            </body>
            </html>
            """, status_code=400)

    # Fluxo normal: serve a página do dashboard index.html
    index_file = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard Frontend em Construção...</h1>")
