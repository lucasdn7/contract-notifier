"""
alerta_periodo_critico.py
Fluxo 4 — Executa todo dia às 8h (GitHub Actions cron).
Busca processos que vencem exatamente daqui 15 dias e notifica.
Dispara apenas UMA VEZ, no dia exato da entrada no período crítico.
 
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
import requests
from datetime import datetime, timedelta
 
sys.path.insert(0, os.path.dirname(__file__))
from notificacoes_v2 import (
    fmt_moeda, fmt_data, link_processo,
    notificar_todos, resolver_municipios, SISTEMA_URL
)
 
SUPABASE_URL   = os.environ["SUPABASE_URL"]
SUPABASE_KEY   = os.environ["SUPABASE_KEY"]
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "processos")
 
 
def buscar_criticos():
    """Busca processos com vigencia_date = hoje + 15 dias (data exata)."""
    data_alvo = (datetime.now().date() + timedelta(days=15)).isoformat()
 
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    params = {
        "select": "id,process_number,municipality_id,object,total_concedente_value,licitado_value,vigencia_date",
        "vigencia_date": f"eq.{data_alvo}"
    }
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
 
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
 
    processos = resp.json()
    # Resolve nomes dos municípios em lote
    return resolver_municipios(processos)
 
 
def notificar_processo(p):
    dias  = 15
    venc  = fmt_data(p.get("vigencia_date"))
    conc  = fmt_moeda(p.get("total_concedente_value"))
    lic   = fmt_moeda(p.get("licitado_value"))
    lnk   = link_processo(p.get("id") or p.get("process_number", ""))
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
 
    # municipio_nome já foi resolvido por resolver_municipios()
    municipio_nome = p.get("municipio_nome", str(p.get("municipality_id", "")))
 
    # ─── WHATSAPP ──────────────────────────────
    wpp = (
        f"🚨 *ALERTA — PERÍODO CRÍTICO DE 15 DIAS*\n\n"
        f"O processo abaixo entra hoje no período de alerta máximo!\n\n"
        f"📌 *Processo:* {p['process_number']}\n"
        f"🏙️ *Município:* {municipio_nome}\n"
        f"📄 *Objeto:* {p['object']}\n"
        f"💰 *Valor concedente:* {conc}\n"
        f"💰 *Valor licitado:* {lic}\n"
        f"📅 *Vencimento:* {venc}\n"
        f"⏱️ *Dias restantes:* {dias} dias\n\n"
        f"⚠️ Providências: aditivo, renovação ou encerramento.\n"
        f"🔗 {lnk}"
    )
 
    # ─── TELEGRAM ─────────────────────────────
    tg = (
        f"🚨 <b>ALERTA — PERÍODO CRÍTICO DE 15 DIAS</b>\n\n"
        f"O processo abaixo entra hoje no período de alerta máximo!\n\n"
        f"📌 <b>Processo:</b> {p['process_number']}\n"
        f"🏙️ <b>Município:</b> {municipio_nome}\n"
        f"📄 <b>Objeto:</b> {p['object']}\n"
        f"💰 <b>Valor concedente:</b> {conc}\n"
        f"💰 <b>Valor licitado:</b> {lic}\n"
        f"📅 <b>Vencimento:</b> {venc}\n"
        f"⏱️ <b>Dias restantes:</b> {dias} dias\n\n"
        f"⚠️ Providências: aditivo, renovação ou encerramento.\n"
        f"🔗 <a href=\"{lnk}\">Acessar processo</a>"
    )
 
    # ─── E-MAIL HTML ──────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="font-family:Arial,sans-serif;max-width:600px;
  margin:0 auto;background:#f4f6fa;padding:24px;">
  <div style="background:white;border-radius:12px;overflow:hidden;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <div style="background:#b91c1c;color:white;padding:24px 28px;">
      <h1 style="margin:0;font-size:20px;">🚨 Alerta — Período Crítico de 15 Dias</h1>
      <p style="margin:6px 0 0;opacity:0.8;font-size:13px;">Gerado em {agora}</p>
    </div>
    <div style="padding:28px;">
      <div style="background:#fee2e2;border-left:4px solid #b91c1c;padding:14px 18px;
                  border-radius:0 8px 8px 0;margin-bottom:24px;font-size:14px;color:#7f1d1d;">
        O processo abaixo <b>vence em exatamente {dias} dias</b>.
        Tome as providências necessárias imediatamente.
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr><td style="padding:10px 0;color:#6b7280;width:160px;">Nº do Processo</td>
            <td style="padding:10px 0;font-weight:700;">{p['process_number']}</td></tr>
        <tr style="background:#f8fafc;"><td style="padding:10px 8px;color:#6b7280;">Município</td>
            <td style="padding:10px 8px;">{municipio_nome}</td></tr>
        <tr><td style="padding:10px 0;color:#6b7280;">Objeto</td>
            <td style="padding:10px 0;">{p['object']}</td></tr>
        <tr style="background:#f8fafc;"><td style="padding:10px 8px;color:#6b7280;">Valor Concedente</td>
            <td style="padding:10px 8px;">{conc}</td></tr>
        <tr><td style="padding:10px 0;color:#6b7280;">Valor Licitado</td>
            <td style="padding:10px 0;">{lic}</td></tr>
        <tr style="background:#fee2e2;"><td style="padding:10px 8px;color:#6b7280;">Vencimento</td>
            <td style="padding:10px 8px;font-weight:700;color:#b91c1c;font-size:16px;">
              {venc} ({dias} dias)</td></tr>
      </table>
      <div style="margin-top:20px;text-align:center;">
        <a href="{lnk}" style="background:#b91c1c;color:white;padding:12px 28px;
           border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">
          🔗 Acessar Processo
        </a>
      </div>
    </div>
  </div>
</body></html>"""
 
    notificar_todos(
        assunto_email   = f"🚨 URGENTE — Proc. {p['process_number']} | {municipio_nome} — Vence em {dias} dias ({venc})",
        html_email      = html,
        texto_whatsapp  = wpp,
        texto_telegram  = tg,
        ntfy_titulo     = f"URGENTE: Proc. {p['process_number']} vence em {dias} dias",
        ntfy_mensagem   = f"{municipio_nome} | {p['object']} | Vencimento: {venc}",
        ntfy_prioridade = 5,
        ntfy_link       = lnk
    )
 
 
def main():
    print("🔍 Verificando processos que entram hoje no período crítico...")
    processos = buscar_criticos()
 
    if not processos:
        print("✅ Nenhum processo entra no período crítico hoje. Nada a notificar.")
        return
 
    print(f"⚠️  {len(processos)} processo(s) entra(m) hoje no período de 15 dias!")
    for p in processos:
        municipio_nome = p.get("municipio_nome", p.get("municipality_id", ""))
        print(f"   → {p.get('process_number')} | {municipio_nome}")
        notificar_processo(p)
 
 
if __name__ == "__main__":
    main()
