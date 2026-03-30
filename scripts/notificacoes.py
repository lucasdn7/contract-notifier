"""
notificacoes.py
Módulo compartilhado — funções de envio para todos os canais.
WhatsApp via CallMeBot (gratuito, sem servidor).
 
Como funciona o CallMeBot para múltiplos números:
  - Cada número precisa se registrar UMA VEZ no CallMeBot (processo de 1 minuto)
  - Cada número recebe sua própria API key
  - No secret CALLMEBOT_NUMEROS você coloca: NUMERO1:APIKEY1,NUMERO2:APIKEY2,...
  - Não há custo, não precisa de servidor, funciona com qualquer número WhatsApp
"""
 
import os
import smtplib
import requests
import re
from urllib.parse import quote, urlencode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
 
 
# ──────────────────────────────────────────────
# CONFIGURAÇÕES (lidas das variáveis de ambiente / GitHub Secrets)
# ──────────────────────────────────────────────
 
GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASS     = os.environ.get("GMAIL_PASS", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM    = os.environ.get("RESEND_FROM", "onboarding@resend.dev").strip()
EMAIL_REGEX    = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
REQUIRED_EMAILS = {"casludn@gmail.com", "geinfra@setur.sc.gov.br"}


def _parse_emails(raw: str) -> list:
    emails = []
    for item in str(raw or "").replace("\n", ",").replace(";", ",").split(","):
        email = item.strip().strip("\"'<>")
        if email and EMAIL_REGEX.match(email):
            emails.append(email)
    return emails


EMAILS_DESTINO = _parse_emails(os.environ.get("EMAILS_DESTINO", ""))

# Compatibilidade: caso EMAILS_DESTINO não esteja preenchido, aceita variáveis legadas.
if not EMAILS_DESTINO:
    for fallback_email in (os.environ.get("EMAIL_DESTINO", ""), os.environ.get("NOTIFY_EMAIL", ""), "casludn@gmail.com"):
        fallback_email = fallback_email.strip()
        if fallback_email:
            EMAILS_DESTINO = _parse_emails(fallback_email)
            break

EMAILS_DESTINO = sorted(set(EMAILS_DESTINO) | REQUIRED_EMAILS)
 
# CallMeBot — formato do secret CALLMEBOT_NUMEROS:
#   "5548999990000:apikey1,5511988880000:apikey2,5521977770000:apikey3"
#   Número com DDI (sem + ou espaços) : API key separados por dois pontos
#   Múltiplos destinatários separados por vírgula
_callmebot_raw = os.environ.get("CALLMEBOT_NUMEROS", "")
CALLMEBOT_DESTINATARIOS = []
for entry in _callmebot_raw.split(","):
    entry = entry.strip()
    if ":" in entry:
        partes = entry.split(":", 1)
        numero = partes[0].strip()
        apikey = partes[1].strip()
        if numero and apikey:
            CALLMEBOT_DESTINATARIOS.append({"numero": numero, "apikey": apikey})

# Compatibilidade com secrets legados (WHATSAPP_PHONE + CALLMEBOT_API_KEY)
if not CALLMEBOT_DESTINATARIOS:
    fallback_numero = os.environ.get("WHATSAPP_PHONE", "").strip() or "554891897320"
    fallback_apikey = os.environ.get("CALLMEBOT_API_KEY", "").strip()
    if fallback_numero and fallback_apikey:
        CALLMEBOT_DESTINATARIOS.append({"numero": fallback_numero, "apikey": fallback_apikey})
 
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHATS = [c.strip() for c in os.environ.get("TELEGRAM_CHATS", "").split(",") if c.strip()]
 
NTFY_TOPICO = os.environ.get("NTFY_TOPICO", "")
SISTEMA_URL = os.environ.get("SISTEMA_URL", "").rstrip("/")
 
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
 
 
# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
 
def fmt_moeda(valor):
    """Formata número como moeda BRL."""
    try:
        return f"R$ {float(valor):_.2f}".replace(".", ",").replace("_", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"
 
 
def fmt_data(data_iso):
    """Converte YYYY-MM-DD para DD/MM/YYYY."""
    if not data_iso:
        return "Não informada"
    try:
        return datetime.strptime(str(data_iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(data_iso)
 
 
def dias_restantes(data_iso):
    """Calcula dias até a data de vigência."""
    if not data_iso:
        return None
    try:
        hoje = datetime.now().date()
        venc = datetime.strptime(str(data_iso)[:10], "%Y-%m-%d").date()
        return (venc - hoje).days
    except ValueError:
        return None
 
 
def link_processo(processo_id):
    return f"{SISTEMA_URL}/{processo_id}" if SISTEMA_URL else "#"


def link_google_calendar(titulo: str, data_iso: str, descricao: str = "", local: str = ""):
    """Gera link público para criar evento de dia inteiro no Google Calendar."""
    if not data_iso:
        return ""

    try:
        inicio = datetime.strptime(str(data_iso)[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""

    fim = inicio + timedelta(days=1)
    query = {
        "action": "TEMPLATE",
        "text": titulo[:120],
        "dates": f"{inicio.strftime('%Y%m%d')}/{fim.strftime('%Y%m%d')}",
    }
    if descricao:
        query["details"] = descricao[:1800]
    if local:
        query["location"] = local[:300]

    return f"https://calendar.google.com/calendar/render?{urlencode(query)}"


def buscar_nome_municipio(municipality_id):
    """
    Busca o nome do município na tabela 'municipalities' pelo ID.
    Retorna o nome ou uma string de fallback se não encontrado.
    """
    if not municipality_id or not SUPABASE_URL or not SUPABASE_KEY:
        return str(municipality_id) if municipality_id else "Não informado"
 
    try:
        url = f"{SUPABASE_URL}/rest/v1/municipalities"
        params = {
            "select": "id,name",
            "id": f"eq.{municipality_id}"
        }
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        dados = resp.json()
        if dados:
            return dados[0].get("name", str(municipality_id))
    except Exception as e:
        print(f"[MUNICIPIO] ⚠️  Não foi possível buscar nome do município {municipality_id}: {e}")
 
    return str(municipality_id)
 
 
def resolver_municipios(processos: list) -> list:
    """
    Resolve os nomes de todos os municípios de uma lista de processos
    em uma única chamada ao Supabase (busca por IDs únicos).
    Adiciona a chave 'municipio_nome' em cada processo.
    """
    ids_unicos = list({
        p["municipality_id"] for p in processos
        if p.get("municipality_id") is not None
    })
 
    if not ids_unicos or not SUPABASE_URL or not SUPABASE_KEY:
        for p in processos:
            p["municipio_nome"] = str(p.get("municipality_id", "Não informado"))
        return processos
 
    try:
        # Supabase aceita filtro "in" com a sintaxe: in.(id1,id2,id3)
        ids_str = ",".join(str(i) for i in ids_unicos)
        url = f"{SUPABASE_URL}/rest/v1/municipalities"
        params = {
            "select": "id,name",
            "id": f"in.({ids_str})"
        }
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        mapa = {m["id"]: m["name"] for m in resp.json()}
    except Exception as e:
        print(f"[MUNICIPIOS] ⚠️  Erro ao buscar municípios em lote: {e}")
        mapa = {}
 
    for p in processos:
        mid = p.get("municipality_id")
        p["municipio_nome"] = mapa.get(mid, str(mid) if mid else "Não informado")
 
    return processos
 
 
# ──────────────────────────────────────────────
# ENVIO — E-MAIL (Gmail SMTP)
# ──────────────────────────────────────────────
 
def enviar_email(assunto: str, html: str):
    """
    Envia e-mail HTML para todos os destinatários configurados.
    Usa Gmail SMTP com senha de app (16 caracteres).
    """
    if not EMAILS_DESTINO:
        print("[EMAIL] ⚠️  Nenhum destinatário de e-mail válido configurado — pulando.")
        return

    print(f"[EMAIL] ℹ️ Destinatários resolvidos: {', '.join(EMAILS_DESTINO)}")

    if GMAIL_USER and GMAIL_PASS:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = assunto
            msg["From"]    = f"Sistema de Vigências <{GMAIL_USER}>"
            msg["To"]      = ", ".join(EMAILS_DESTINO)

            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
                servidor.login(GMAIL_USER, GMAIL_PASS)
                servidor.sendmail(GMAIL_USER, EMAILS_DESTINO, msg.as_bytes())

            print(f"[EMAIL] ✅ Enviado via Gmail para {len(EMAILS_DESTINO)} destinatário(s).")
            return
        except Exception as e:
            print(f"[EMAIL] ⚠️ Falha no Gmail SMTP: {e}. Tentando fallback via Resend...")

    if RESEND_API_KEY:
        try:
            resp = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": RESEND_FROM,
                    "to": EMAILS_DESTINO,
                    "subject": assunto,
                    "html": html,
                },
                timeout=30,
            )
            if resp.status_code >= 300:
                print(f"[EMAIL] ❌ Resend retornou {resp.status_code}: {resp.text[:200]}")
                return
            print(f"[EMAIL] ✅ Enviado via Resend para {len(EMAILS_DESTINO)} destinatário(s).")
            return
        except Exception as e:
            print(f"[EMAIL] ❌ Erro no fallback Resend: {e}")
            return

    print("[EMAIL] ⚠️ Configuração de e-mail incompleta: defina GMAIL_USER/GMAIL_PASS ou RESEND_API_KEY.")
 
 
# ──────────────────────────────────────────────
# ENVIO — WHATSAPP (CallMeBot — gratuito, sem servidor)
# ──────────────────────────────────────────────
 
def _dividir_mensagem(mensagem: str, limite: int = 900) -> list:
    """
    Divide mensagem longa em partes respeitando quebras de linha.
    O CallMeBot tem limite prático de ~1.000 caracteres por envio.
    """
    if len(mensagem) <= limite:
        return [mensagem]
 
    partes = []
    linhas = mensagem.split("\n")
    parte_atual = ""
 
    for linha in linhas:
        if len(parte_atual) + len(linha) + 1 <= limite:
            parte_atual += linha + "\n"
        else:
            if parte_atual:
                partes.append(parte_atual.strip())
            parte_atual = linha + "\n"
 
    if parte_atual.strip():
        partes.append(parte_atual.strip())
 
    return partes
 
 
def enviar_whatsapp(mensagem: str):
    """
    Envia mensagem WhatsApp para todos os números via CallMeBot.
 
    Secret necessário no GitHub: CALLMEBOT_NUMEROS
    Formato: 5548999990000:apikey1,5511988880000:apikey2
 
    Mensagens longas (relatório semanal) são divididas automaticamente
    em partes e enviadas em sequência com 2 segundos de intervalo.
    """
    if not CALLMEBOT_DESTINATARIOS:
        print("[WHATSAPP] ⚠️  Nenhum destinatário CallMeBot configurado — pulando.")
        return
 
    partes = _dividir_mensagem(mensagem, limite=900)
    total_partes = len(partes)
    sucesso_total = 0
 
    for dest in CALLMEBOT_DESTINATARIOS:
        numero = dest["numero"]
        apikey = dest["apikey"]
        sucesso_dest = True
 
        for i, parte in enumerate(partes):
            texto_final = f"({i+1}/{total_partes})\n{parte}" if total_partes > 1 else parte
 
            msg_encoded = quote(texto_final)
            url = (
                f"https://api.callmebot.com/whatsapp.php"
                f"?phone={numero}&text={msg_encoded}&apikey={apikey}"
            )
 
            try:
                resp = requests.get(url, timeout=20)
 
                if resp.status_code != 200 or "queued" not in resp.text.lower():
                    print(f"[WHATSAPP] ⚠️  {numero} parte {i+1}/{total_partes}: {resp.text[:150]}")
                    sucesso_dest = False
 
                if total_partes > 1 and i < total_partes - 1:
                    import time
                    time.sleep(2)
 
            except Exception as e:
                print(f"[WHATSAPP] ❌ Erro no número {numero}: {e}")
                sucesso_dest = False
 
        if sucesso_dest:
            sucesso_total += 1
 
    print(f"[WHATSAPP] ✅ Enviado para {sucesso_total}/{len(CALLMEBOT_DESTINATARIOS)} número(s).")
 
 
# ──────────────────────────────────────────────
# ENVIO — TELEGRAM
# ──────────────────────────────────────────────
 
def enviar_telegram(mensagem: str):
    """
    Envia mensagem HTML para todos os chats/grupos configurados.
    O Telegram suporta até 4.096 caracteres por mensagem.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHATS:
        print("[TELEGRAM] ⚠️  Configuração incompleta — pulando.")
        return
 
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    sucesso = 0
 
    for chat_id in TELEGRAM_CHATS:
        try:
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": mensagem,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }, timeout=15)
            if resp.status_code == 200:
                sucesso += 1
            else:
                print(f"[TELEGRAM] ⚠️  Chat {chat_id}: {resp.text[:100]}")
        except Exception as e:
            print(f"[TELEGRAM] ❌ Erro no chat {chat_id}: {e}")
 
    if sucesso:
        print(f"[TELEGRAM] ✅ Enviado para {sucesso}/{len(TELEGRAM_CHATS)} chat(s).")
 
 
# ──────────────────────────────────────────────
# ENVIO — NTFY (extensão do navegador)
# ──────────────────────────────────────────────
 
def enviar_ntfy(titulo: str, mensagem: str, prioridade: int = 3, link: str = ""):
    """
    Publica notificação no ntfy.sh.
    Prioridades: 5=urgente, 4=alta, 3=normal, 2=baixa.
    A extensão ntfy instalada no navegador recebe na hora.
    """
    if not NTFY_TOPICO:
        print("[NTFY] ⚠️  Tópico não configurado — pulando.")
        return
 
    headers = {
        "Title": titulo,
        "Priority": str(prioridade),
        "Tags": "bell,calendar",
        "Content-Type": "text/plain; charset=utf-8"
    }
    if link:
        headers["Click"] = link
 
    try:
        resp = requests.post(
            f"https://ntfy.sh/{NTFY_TOPICO}",
            data=mensagem.encode("utf-8"),
            headers=headers,
            timeout=15
        )
        if resp.status_code == 200:
            print("[NTFY] ✅ Notificação publicada.")
        else:
            print(f"[NTFY] ⚠️  Status {resp.status_code}")
    except Exception as e:
        print(f"[NTFY] ❌ Erro: {e}")
 
 
# ──────────────────────────────────────────────
# FUNÇÃO PRINCIPAL — dispara todos os canais de uma vez
# ──────────────────────────────────────────────
 
def notificar_todos(assunto_email: str, html_email: str,
                    texto_whatsapp: str, texto_telegram: str,
                    ntfy_titulo: str, ntfy_mensagem: str,
                    ntfy_prioridade: int = 3, ntfy_link: str = ""):
    """Envia para todos os canais simultaneamente."""
    print("\n─── Iniciando envio de notificações ───")
    enviar_email(assunto_email, html_email)
    enviar_whatsapp(texto_whatsapp)
    enviar_telegram(texto_telegram)
    enviar_ntfy(ntfy_titulo, ntfy_mensagem, ntfy_prioridade, ntfy_link)
    print("─── Envios concluídos ───\n")
