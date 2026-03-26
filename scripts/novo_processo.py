"""
novo_processo.py
Fluxo 2 — Disparado via repository_dispatch quando o Supabase
detecta um INSERT na tabela de processos (trigger SQL → GitHub API).
 
Mapeamento de colunas (Supabase):
  id                    → id
  process_number        → número do processo
  municipality_id       → FK para tabela municipalities (id, name)
  object                → objeto do processo
  total_concedente_value → valor concedente
  licitado_value        → valor licitado
  vigencia_date         → data de vigência
"""
 
import os
import sys
import json
from datetime import datetime
 
sys.path.insert(0, os.path.dirname(__file__))
from notificacoes import (
    fmt_moeda, fmt_data, dias_restantes, link_processo, link_google_calendar,
    notificar_todos, buscar_nome_municipio, SISTEMA_URL
)
 
 
def main():
    # O payload enviado pelo Supabase chega como variável de ambiente
    payload_raw = os.environ.get("EVENT_PAYLOAD", "{}")
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        print(f"❌ Payload inválido: {payload_raw[:200]}")
        sys.exit(1)
 
    # O Supabase envia o registro em payload.record
    p = payload.get("record") or payload
    print(f"📥 Payload recebido: Proc. {p.get('process_number')} | municipality_id: {p.get('municipality_id')}")
 
    # Se não tem data de vigência, não notifica
    if not p.get("vigencia_date"):
        print("ℹ️  Processo sem data de vigência — nenhuma notificação enviada.")
        return
 
    # Resolve o nome do município via FK
    municipio_nome = buscar_nome_municipio(p.get("municipality_id"))
 
    dias  = dias_restantes(p["vigencia_date"])
    venc  = fmt_data(p["vigencia_date"])
    conc  = fmt_moeda(p.get("total_concedente_value"))
    lic   = fmt_moeda(p.get("licitado_value"))
    lnk   = link_processo(p.get("id") or p.get("process_number", ""))
    lnk_calendar = link_google_calendar(
        titulo=f"Vigência processo {p.get('process_number', '')}",
        data_iso=p.get("vigencia_date"),
        descricao=(
            f"Processo: {p.get('process_number', '')}\n"
            f"Município: {municipio_nome}\n"
            f"Objeto: {p.get('object', '')}\n"
            f"Link: {lnk}"
        ),
        local=municipio_nome
    )
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
 
    # ─── WHATSAPP ──────────────────────────────────────────
    wpp = (
        f"✅ *NOVO PROCESSO CADASTRADO*\n\n"
        f"📌 *Processo:* {p['process_number']}\n"
        f"🏙️ *Município:* {municipio_nome}\n"
        f"📄 *Objeto:* {p['object']}\n"
        f"💰 *Valor concedente:* {conc}\n"
        f"💰 *Valor licitado:* {lic}\n"
        f"📅 *Vigência até:* {venc} _({dias} dias restantes)_\n"
        f"🔗 {lnk}\n"
        f"🗓️ Google Calendar: {lnk_calendar}\n\n"
        f"_Cadastrado em {agora}_"
    )
 
    # ─── TELEGRAM ──────────────────────────────────────────
    tg = (
        f"✅ <b>NOVO PROCESSO CADASTRADO</b>\n\n"
        f"📌 <b>Processo:</b> {p['process_number']}\n"
        f"🏙️ <b>Município:</b> {municipio_nome}\n"
        f"📄 <b>Objeto:</b> {p['object']}\n"
        f"💰 <b>Valor concedente:</b> {conc}\n"
        f"💰 <b>Valor licitado:</b> {lic}\n"
        f"📅 <b>Vigência até:</b> {venc} <i>({dias} dias restantes)</i>\n"
        f"🔗 <a href=\"{lnk}\">Acessar processo</a>\n"
        f"🗓️ <a href=\"{lnk_calendar}\">Adicionar no Google Calendar</a>\n\n"
        f"<i>Cadastrado em {agora}</i>"
    )
 
    # ─── E-MAIL HTML ───────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="font-family:Arial,sans-serif;max-width:600px;
  margin:0 auto;background:#f4f6fa;padding:24px;">
  <div style="background:white;border-radius:12px;overflow:hidden;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <div style="background:#166534;color:white;padding:24px 28px;">
      <h1 style="margin:0;font-size:20px;">✅ Novo Processo Cadastrado</h1>
      <p style="margin:6px 0 0;opacity:0.8;font-size:13px;">Cadastrado em {agora}</p>
    </div>
    <div style="padding:28px;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr><td style="padding:10px 0;color:#6b7280;width:160px;">Nº do Processo</td>
            <td style="padding:10px 0;font-weight:700;">{p.get('process_number','')}</td></tr>
        <tr style="background:#f8fafc;"><td style="padding:10px 8px;color:#6b7280;">Município</td>
            <td style="padding:10px 8px;">{municipio_nome}</td></tr>
        <tr><td style="padding:10px 0;color:#6b7280;">Objeto</td>
            <td style="padding:10px 0;">{p.get('object','')}</td></tr>
        <tr style="background:#f8fafc;"><td style="padding:10px 8px;color:#6b7280;">Valor Concedente</td>
            <td style="padding:10px 8px;">{conc}</td></tr>
        <tr><td style="padding:10px 0;color:#6b7280;">Valor Licitado</td>
            <td style="padding:10px 0;">{lic}</td></tr>
        <tr style="background:#dcfce7;"><td style="padding:10px 8px;color:#6b7280;">Vigência até</td>
            <td style="padding:10px 8px;font-weight:700;color:#166534;font-size:15px;">
              {venc} ({dias} dias)</td></tr>
      </table>
      <div style="margin-top:20px;text-align:center;">
        <a href="{lnk}" style="background:#4361ee;color:white;padding:12px 28px;
           border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">
          🔗 Acessar Processo
        </a>
      </div>
      <div style="margin-top:12px;text-align:center;">
        <a href="{lnk_calendar}" style="background:#166534;color:white;padding:12px 28px;
           border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;display:inline-block;">
          🗓️ Adicionar no Google Calendar
        </a>
      </div>
    </div>
  </div>
</body></html>"""
 
    notificar_todos(
        assunto_email   = f"✅ Novo Processo — {p.get('process_number')} | {municipio_nome} | Vigência: {venc}",
        html_email      = html,
        texto_whatsapp  = wpp,
        texto_telegram  = tg,
        ntfy_titulo     = f"Novo processo: {p.get('process_number')}",
        ntfy_mensagem   = f"{municipio_nome} | Vigência: {venc} ({dias} dias)",
        ntfy_prioridade = 4,
        ntfy_link       = lnk
    )
 
 
if __name__ == "__main__":
    main()
