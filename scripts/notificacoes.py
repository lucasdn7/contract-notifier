"""
notificacoes.py
Módulo compartilhado — funções de envio para todos os canais.
Importado por todos os scripts de automação.
"""

import os
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


# ──────────────────────────────────────────────
# CONFIGURAÇÕES (lidas das variáveis de ambiente / GitHub Secrets)
# ──────────────────────────────────────────────

GMAIL_USER       = os.environ.get("GMAIL_USER", "")
GMAIL_PASS       = os.environ.get("GMAIL_PASS", "")
EMAILS_DESTINO   = [e.strip() for e in os.environ.get("EMAILS_DESTINO", "").split(",") if e.strip()]

EVOLUTION_URL      = os.environ.get("EVOLUTION_URL", "").rstrip("/")
EVOLUTION_KEY      = os.environ.get("EVOLUTION_KEY", "")
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE", "")
WHATSAPP_NUMEROS   = [n.strip() for n in os.environ.get("WHATSAPP_NUMEROS", "").split(",") if n.strip()]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHATS = [c.strip() for c in os.environ.get("TELEGRAM_CHATS", "").split(",") if c.strip()]

NTFY_TOPICO = os.environ.get("NTFY_TOPICO", "")
SISTEMA_URL = os.environ.get("SISTEMA_URL", "").rstrip("/")


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


# ──────────────────────────────────────────────
# ENVIO — E-MAIL (Gmail SMTP)
# ──────────────────────────────────────────────

def enviar_email(assunto: str, html: str):
    """
    Envia e-mail HTML para todos os destinatários configurados.
    Usa Gmail SMTP com senha de app (16 caracteres).
    """
    if not GMAIL_USER or not GMAIL_PASS or not EMAILS_DESTINO:
        print("[EMAIL] ⚠️  Configuração de e-mail incompleta — pulando.")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = f"Sistema de Vigências <{GMAIL_USER}>"
        msg["To"]      = ", ".join(EMAILS_DESTINO)

        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
            servidor.login(GMAIL_USER, GMAIL_PASS)
            servidor.sendmail(GMAIL_USER, EMAILS_DESTINO, msg.as_bytes())

        print(f"[EMAIL] ✅ Enviado para {len(EMAILS_DESTINO)} destinatário(s).")
    except Exception as e:
        print(f"[EMAIL] ❌ Erro: {e}")


# ──────────────────────────────────────────────
# ENVIO — WHATSAPP (Evolution API)
# ──────────────────────────────────────────────

def enviar_whatsapp(mensagem: str):
    """
    Envia mensagem de texto para todos os números configurados.
    Usa a Evolution API (self-hosted, gratuita).
    """
    if not EVOLUTION_URL or not EVOLUTION_KEY or not EVOLUTION_INSTANCE or not WHATSAPP_NUMEROS:
        print("[WHATSAPP] ⚠️  Configuração incompleta — pulando.")
        return

    url = f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_KEY
    }

    sucesso = 0
    for numero in WHATSAPP_NUMEROS:
        try:
            resp = requests.post(url, json={"number": numero, "text": mensagem}, headers=headers, timeout=15)
            if resp.status_code in (200, 201):
                sucesso += 1
            else:
                print(f"[WHATSAPP] ⚠️  Número {numero}: status {resp.status_code} — {resp.text[:100]}")
        except Exception as e:
            print(f"[WHATSAPP] ❌ Erro no número {numero}: {e}")

    if sucesso:
        print(f"[WHATSAPP] ✅ Enviado para {sucesso}/{len(WHATSAPP_NUMEROS)} número(s).")


# ──────────────────────────────────────────────
# ENVIO — TELEGRAM
# ──────────────────────────────────────────────

def enviar_telegram(mensagem: str):
    """
    Envia mensagem HTML para todos os chats/grupos configurados.
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
    Prioridades: 5=urgente, 4=alta, 3=normal, 2=baixa
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
