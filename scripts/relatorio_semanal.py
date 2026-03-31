"""
relatorio_semanal.py
Fluxo 1 — Executa toda segunda às 10h (via GitHub Actions cron).
Busca contratos que vencem em até 45 dias e envia relatório categorizado.
 
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
    fmt_moeda, fmt_data, dias_restantes, link_processo, link_google_calendar,
    notificar_todos, resolver_municipios, SISTEMA_URL
)
 
SUPABASE_URL   = os.environ["SUPABASE_URL"]
SUPABASE_KEY   = os.environ["SUPABASE_KEY"]
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "processos")
 
 
# ──────────────────────────────────────────────
# 1. BUSCA NO SUPABASE
# ──────────────────────────────────────────────
 
def buscar_processos():
    hoje   = datetime.now().date()
    limite = hoje + timedelta(days=45)
 
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    params = {
        "select": "id,process_number,municipality_id,object,total_concedente_value,licitado_value,vigencia_date",
        "vigencia_date": f"gte.{hoje.isoformat()}",
        "order": "vigencia_date.asc"
    }
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
 
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
 
    processos = resp.json()
    # Filtra apenas os próximos 45 dias
    processos = [
        p for p in processos
        if p.get("vigencia_date") and
        str(p["vigencia_date"])[:10] <= limite.isoformat()
    ]
 
    # Resolve nomes dos municípios em lote (uma única chamada ao Supabase)
    return resolver_municipios(processos)
 
 
# ──────────────────────────────────────────────
# 2. CLASSIFICAÇÃO
# ──────────────────────────────────────────────
 
def classificar(processos):
    urgentes, atencao, avisos = [], [], []
 
    for p in processos:
        d = dias_restantes(p.get("vigencia_date"))
        if d is None:
            continue
        p["dias"]         = d
        p["venc_fmt"]     = fmt_data(p.get("vigencia_date"))
        p["val_conc_fmt"] = fmt_moeda(p.get("total_concedente_value"))
        p["val_lic_fmt"]  = fmt_moeda(p.get("licitado_value"))
        p["link"]         = link_processo(p.get("id") or p.get("process_number", ""))
        p["calendar_link"] = link_google_calendar(
            titulo=f"Vigência processo {p.get('process_number', '')}",
            data_iso=p.get("vigencia_date"),
            descricao=(
                f"Processo: {p.get('process_number', '')}\n"
                f"Município: {p.get('municipio_nome', '')}\n"
                f"Objeto: {p.get('object', '')}\n"
                f"Link: {p['link']}"
            ),
            local=p.get("municipio_nome", "")
        )
        # municipio_nome já foi resolvido por resolver_municipios()
 
        if d <= 15:
            urgentes.append(p)
        elif d <= 30:
            atencao.append(p)
        elif d <= 45:
            avisos.append(p)
 
    return urgentes, atencao, avisos
 
 
# ──────────────────────────────────────────────
# 3. MONTAGEM DAS MENSAGENS
# ──────────────────────────────────────────────
 
def montar_whatsapp(urgentes, atencao, avisos):
    data_hoje = datetime.now().strftime("%A, %d/%m/%Y").capitalize()
    linhas = [f"📋 *RELATÓRIO SEMANAL DE VIGÊNCIAS*\n_{data_hoje}_"]

    def encurtar_url(url: str) -> str:
        """Encurta URL para deixar a mensagem do WhatsApp mais legível."""
        if not url:
            return ""
        try:
            resp = requests.get(
                "https://tinyurl.com/api-create.php",
                params={"url": url},
                timeout=8
            )
            resp.raise_for_status()
            curta = resp.text.strip()
            if curta.startswith("http"):
                return curta
        except Exception as e:
            print(f"[WHATSAPP] ⚠️  Falha ao encurtar URL: {e}")
        return url
 
    def secao(emoji, titulo, lista):
        if not lista:
            return ""
        items = []
        for p in lista:
            objeto = str(p.get("object") or "Não informado").strip()
            calendar_link_curto = encurtar_url(p.get("calendar_link", ""))
            items.append(
                f"📌 *Proc. {p['process_number']}* | {p['municipio_nome']}\n"
                f"   📄 Objeto: {objeto}\n"
                f"   💰 Concedente: {p['val_conc_fmt']} | Licitado: {p['val_lic_fmt']}\n"
                f"   📅 Vencimento: {p['venc_fmt']} _({p['dias']} dias)_\n"
                f"   🔗 {p['link']}\n"
                f"   🗓️ Calendar: {calendar_link_curto}"
            )
        return f"{emoji} *{titulo}*\n\n" + "\n\n".join(items)
 
    secoes = [
        secao("🔴", "URGENTE — Vencem em até 15 dias", urgentes),
        secao("🟡", "ATENÇÃO — Vencem entre 16 e 30 dias", atencao),
        secao("🔵", "AVISO — Vencem entre 31 e 45 dias", avisos),
    ]
    linhas += [s for s in secoes if s]
    return "\n\n━━━━━━━━━━━━━━━━━━\n\n".join(linhas)
 
 
def montar_telegram(urgentes, atencao, avisos):
    data_hoje = datetime.now().strftime("%A, %d/%m/%Y").capitalize()
    linhas = [f"📋 <b>RELATÓRIO SEMANAL DE VIGÊNCIAS</b>\n<i>{data_hoje}</i>"]
 
    def secao(emoji, titulo, lista):
        if not lista:
            return ""
        items = []
        for p in lista:
            items.append(
                f"📌 <b>Proc. {p['process_number']}</b> | {p['municipio_nome']}\n"
                f"   📄 {p['object']}\n"
                f"   💰 Concedente: {p['val_conc_fmt']} | Licitado: {p['val_lic_fmt']}\n"
                f"   📅 Vencimento: {p['venc_fmt']} <i>({p['dias']} dias)</i>\n"
                f"   🔗 <a href=\"{p['link']}\">Acessar processo</a>\n"
                f"   🗓️ <a href=\"{p['calendar_link']}\">Google Calendar</a>"
            )
        return f"{emoji} <b>{titulo}</b>\n\n" + "\n\n".join(items)
 
    secoes = [
        secao("🔴", "URGENTE — Vencem em até 15 dias", urgentes),
        secao("🟡", "ATENÇÃO — Vencem entre 16 e 30 dias", atencao),
        secao("🔵", "AVISO — Vencem entre 31 e 45 dias", avisos),
    ]
    linhas += [s for s in secoes if s]
    return "\n\n─────────────────\n\n".join(linhas)
 
 
def montar_html_email(urgentes, atencao, avisos):
    data_hoje = datetime.now().strftime("%A, %d de %B de %Y").capitalize()
 
    def tabela(lista, cor_header, cor_texto, titulo):
        if not lista:
            return ""
        linhas_html = ""
        for p in lista:
            linhas_html += f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;">{p['process_number']}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;">{p['municipio_nome']}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;line-height:1.45;">{p['object']}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;">{p['val_conc_fmt']}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;">{p['val_lic_fmt']}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;">{p['venc_fmt']}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;font-weight:700;color:{cor_texto};">{p['dias']} dias</td>
              <td style="padding:10px 12px;border-bottom:1px solid #f0f0f0;text-align:center;">
                <a href="{p['calendar_link']}" style="display:inline-block;background:#166534;color:#ffffff;font-weight:700;
                   padding:8px 12px;border-radius:6px;text-decoration:none;font-size:12px;white-space:nowrap;">Adicionar no Calendar</a>
              </td>
            </tr>"""
 
        return f"""
        <div style="margin-bottom:28px;">
          <div style="background:{cor_header};color:{cor_texto};padding:12px 20px;
                      border-radius:8px 8px 0 0;font-weight:700;font-size:15px;">{titulo}</div>
          <table style="width:100%;border-collapse:collapse;font-size:13px;
                        border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">
            <thead>
              <tr style="background:#f8fafc;">
                <th style="padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;
                           color:#6b7280;font-size:11px;text-transform:uppercase;">Nº Processo</th>
                <th style="padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;
                           color:#6b7280;font-size:11px;text-transform:uppercase;">Município</th>
                <th style="padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;
                           color:#6b7280;font-size:11px;text-transform:uppercase;">Objeto</th>
                <th style="padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;
                           color:#6b7280;font-size:11px;text-transform:uppercase;">Val. Concedente</th>
                <th style="padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;
                           color:#6b7280;font-size:11px;text-transform:uppercase;">Val. Licitado</th>
                <th style="padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;
                           color:#6b7280;font-size:11px;text-transform:uppercase;">Vencimento</th>
                <th style="padding:9px 12px;text-align:left;border-bottom:2px solid #e5e7eb;
                           color:#6b7280;font-size:11px;text-transform:uppercase;">Restam</th>
                <th style="padding:9px 12px;text-align:center;border-bottom:2px solid #e5e7eb;
                           color:#166534;font-size:11px;text-transform:uppercase;">Google Calendar</th>
              </tr>
            </thead>
            <tbody>{linhas_html}</tbody>
          </table>
        </div>"""
 
    gerado_em = datetime.now().strftime("%d/%m/%Y às %H:%M")
 
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="font-family:Arial,sans-serif;max-width:960px;
  margin:0 auto;background:#f4f6fa;padding:24px;">
  <div style="background:white;border-radius:12px;overflow:hidden;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <div style="background:#1a1a2e;color:white;padding:24px 28px;">
      <h1 style="margin:0;font-size:22px;">📋 Relatório Semanal de Vigências</h1>
      <p style="margin:6px 0 0;opacity:0.7;font-size:13px;">{data_hoje}</p>
    </div>
    <div style="padding:28px;">
      {tabela(urgentes, '#fee2e2', '#b91c1c', '🔴 URGENTE — Vencem em até 15 dias')}
      {tabela(atencao,  '#fef9c3', '#92400e', '🟡 ATENÇÃO — Vencem entre 16 e 30 dias')}
      {tabela(avisos,   '#dbeafe', '#1e40af', '🔵 AVISO — Vencem entre 31 e 45 dias')}
      <p style="color:#9ca3af;font-size:12px;text-align:center;margin-top:20px;">
        Gerado automaticamente via GitHub Actions • {gerado_em}
      </p>
    </div>
  </div>
</body></html>"""
 
 
# ──────────────────────────────────────────────
# 4. EXECUÇÃO PRINCIPAL
# ──────────────────────────────────────────────
 
def main():
    origem = os.environ.get("NOTIFICACAO_ORIGEM", "semanal").strip().lower()
    print("🔍 Buscando processos no Supabase...")
    processos = buscar_processos()
    print(f"   {len(processos)} processo(s) com vencimento nos próximos 45 dias.")
 
    urgentes, atencao, avisos = classificar(processos)
    total = len(urgentes) + len(atencao) + len(avisos)
 
    if total == 0:
        print("✅ Nenhum processo vence nos próximos 45 dias. Nenhuma notificação enviada.")
        return
 
    print(f"   🔴 {len(urgentes)} URGENTE(s) · 🟡 {len(atencao)} ATENÇÃO · 🔵 {len(avisos)} AVISO(s)")
 
    prefixo = "📋 Relatório de Vigências" if origem == "semanal" else "📋 Relatório sob demanda de Vigências"
    assunto = (
        f"{prefixo} — "
        f"{len(urgentes)} URGENTE(s), {len(atencao)} ATENÇÃO, {len(avisos)} AVISO(s)"
    )
 
    ntfy_partes = []
    if urgentes: ntfy_partes.append(f"🔴 {len(urgentes)} URGENTE(s)")
    if atencao:  ntfy_partes.append(f"🟡 {len(atencao)} ATENÇÃO")
    if avisos:   ntfy_partes.append(f"🔵 {len(avisos)} AVISO(s)")
    ntfy_prioridade = 5 if urgentes else 4 if atencao else 3
 
    notificar_todos(
        assunto_email    = assunto,
        html_email       = montar_html_email(urgentes, atencao, avisos),
        texto_whatsapp   = montar_whatsapp(urgentes, atencao, avisos),
        texto_telegram   = montar_telegram(urgentes, atencao, avisos),
        ntfy_titulo      = "Relatório Semanal de Vigências" if origem == "semanal" else "Relatório sob demanda de Vigências",
        ntfy_mensagem    = " · ".join(ntfy_partes),
        ntfy_prioridade  = ntfy_prioridade,
        ntfy_link        = SISTEMA_URL
    )
 
 
if __name__ == "__main__":
    main()
