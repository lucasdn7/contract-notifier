"""
vigencia_editada.py
Fluxo 3 — Disparado via repository_dispatch quando o Supabase
detecta UPDATE na data_vigencia de um processo.
Compara data antiga vs nova e notifica com a diferença.
"""

import os
import sys
import json
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(__file__))
from notificacoes import (
    fmt_moeda, fmt_data, dias_restantes, link_processo,
    notificar_todos, SISTEMA_URL
)


def main():
    payload_raw = os.environ.get("EVENT_PAYLOAD", "{}")
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        print(f"❌ Payload inválido: {payload_raw[:200]}")
        sys.exit(1)

    novo   = payload.get("record")    or payload
    antigo = payload.get("old_record") or {}

    data_nova   = novo.get("data_vigencia")
    data_antiga = antigo.get("data_vigencia")

    print(f"📥 Proc. {novo.get('numero_processo')} | Antiga: {data_antiga} → Nova: {data_nova}")

    # Se a data não mudou, ignora
    if not data_nova or str(data_nova)[:10] == str(data_antiga or "")[:10]:
        print("ℹ️  Data de vigência não alterada — nenhuma notificação enviada.")
        return

    dias  = dias_restantes(data_nova)
    venc_novo  = fmt_data(data_nova)
    venc_antigo = fmt_data(data_antiga) if data_antiga else "Não informada"
    conc  = fmt_moeda(novo.get("valor_concedente"))
    lic   = fmt_moeda(novo.get("valor_licitado"))
    lnk   = link_processo(novo.get("id") or novo.get("numero_processo", ""))
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

    # Calcula diferença entre datas
    diff_dias  = None
    diff_texto_wpp = ""
    diff_texto_tg  = ""
    cor_diff   = "#92400e"
    bg_diff    = "#fef9c3"

    if data_antiga:
        try:
            d_ant = datetime.strptime(str(data_antiga)[:10], "%Y-%m-%d").date()
            d_nov = datetime.strptime(str(data_nova)[:10],   "%Y-%m-%d").date()
            diff_dias = (d_nov - d_ant).days
            if diff_dias > 0:
                diff_texto_wpp = f"⬆️ Vigência *ampliada* em {diff_dias} dias."
                diff_texto_tg  = f"⬆️ Vigência <b>ampliada</b> em {diff_dias} dias."
                cor_diff, bg_diff = "#166534", "#dcfce7"
            elif diff_dias < 0:
                diff_texto_wpp = f"⬇️ Vigência *reduzida* em {abs(diff_dias)} dias. Atenção!"
                diff_texto_tg  = f"⬇️ Vigência <b>reduzida</b> em {abs(diff_dias)} dias. Atenção!"
                cor_diff, bg_diff = "#b91c1c", "#fee2e2"
        except ValueError:
            pass

    # ─── WHATSAPP ──────────────────────────────────────────
    linhas_wpp = [
        "✏️ *VIGÊNCIA ALTERADA*", "",
        f"📌 *Processo:* {novo.get('numero_processo')}",
        f"🏙️ *Município:* {novo.get('municipio')}",
        f"📄 *Objeto:* {novo.get('objeto')}",
        f"💰 *Valor concedente:* {conc}",
        f"💰 *Valor licitado:* {lic}", "",
        f"🗓️ *Data anterior:* {venc_antigo}",
        f"🗓️ *Nova data:* {venc_novo} _({dias} dias restantes)_",
    ]
    if diff_texto_wpp:
        linhas_wpp.append(diff_texto_wpp)
    linhas_wpp += [f"🔗 {lnk}", "", f"_Alterado em {agora}_"]
    wpp = "\n".join(linhas_wpp)

    # ─── TELEGRAM ──────────────────────────────────────────
    linhas_tg = [
        "✏️ <b>VIGÊNCIA ALTERADA</b>", "",
        f"📌 <b>Processo:</b> {novo.get('numero_processo')}",
        f"🏙️ <b>Município:</b> {novo.get('municipio')}",
        f"📄 <b>Objeto:</b> {novo.get('objeto')}",
        f"💰 <b>Valor concedente:</b> {conc}",
        f"💰 <b>Valor licitado:</b> {lic}", "",
        f"🗓️ <b>Data anterior:</b> {venc_antigo}",
        f"🗓️ <b>Nova data:</b> {venc_novo} <i>({dias} dias restantes)</i>",
    ]
    if diff_texto_tg:
        linhas_tg.append(diff_texto_tg)
    linhas_tg += [f"🔗 <a href=\"{lnk}\">Acessar processo</a>", "", f"<i>Alterado em {agora}</i>"]
    tg = "\n".join(linhas_tg)

    # ─── E-MAIL HTML ───────────────────────────────────────
    diff_html = ""
    if diff_dias is not None:
        seta = f"⬆️ Ampliada em {diff_dias} dias" if diff_dias > 0 else f"⬇️ Reduzida em {abs(diff_dias)} dias"
        diff_html = f'<div style="margin-top:8px;font-weight:700;color:{cor_diff};">{seta}</div>'

    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><body style="font-family:Arial,sans-serif;max-width:600px;
  margin:0 auto;background:#f4f6fa;padding:24px;">
  <div style="background:white;border-radius:12px;overflow:hidden;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <div style="background:#92400e;color:white;padding:24px 28px;">
      <h1 style="margin:0;font-size:20px;">✏️ Vigência Alterada</h1>
      <p style="margin:6px 0 0;opacity:0.8;font-size:13px;">Alterado em {agora}</p>
    </div>
    <div style="padding:28px;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr><td style="padding:10px 0;color:#6b7280;width:160px;">Nº do Processo</td>
            <td style="padding:10px 0;font-weight:700;">{novo.get('numero_processo','')}</td></tr>
        <tr style="background:#f8fafc;"><td style="padding:10px 8px;color:#6b7280;">Município</td>
            <td style="padding:10px 8px;">{novo.get('municipio','')}</td></tr>
        <tr><td style="padding:10px 0;color:#6b7280;">Objeto</td>
            <td style="padding:10px 0;">{novo.get('objeto','')}</td></tr>
        <tr style="background:#f8fafc;"><td style="padding:10px 8px;color:#6b7280;">Valor Concedente</td>
            <td style="padding:10px 8px;">{conc}</td></tr>
        <tr><td style="padding:10px 0;color:#6b7280;">Valor Licitado</td>
            <td style="padding:10px 0;">{lic}</td></tr>
      </table>
      <div style="margin:20px 0;padding:16px;background:{bg_diff};border-radius:8px;
                  border-left:4px solid {cor_diff};">
        <div style="font-size:12px;color:{cor_diff};font-weight:700;
                    text-transform:uppercase;margin-bottom:8px;">Alteração de vigência</div>
        <div style="font-size:14px;color:#374151;">
          <span style="color:#6b7280;">Anterior:</span>
          <b>{venc_antigo}</b>
        </div>
        <div style="font-size:14px;color:#374151;margin-top:6px;">
          <span style="color:#6b7280;">Nova data:</span>
          <b style="color:{cor_diff};">{venc_novo}</b>
          <span style="color:#6b7280;">({dias} dias restantes)</span>
        </div>
        {diff_html}
      </div>
      <div style="text-align:center;">
        <a href="{lnk}" style="background:#4361ee;color:white;padding:12px 28px;
           border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">
          🔗 Acessar Processo
        </a>
      </div>
    </div>
  </div>
</body></html>"""

    ntfy_prioridade = 5 if (diff_dias is not None and diff_dias < 0) else 4
    ntfy_msg = f"{novo.get('numero_processo')} | {venc_antigo} → {venc_novo} ({dias} dias)"

    notificar_todos(
        assunto_email   = f"✏️ Vigência alterada — Proc. {novo.get('numero_processo')} | Nova data: {venc_novo}",
        html_email      = html,
        texto_whatsapp  = wpp,
        texto_telegram  = tg,
        ntfy_titulo     = f"Vigência alterada: {novo.get('numero_processo')}",
        ntfy_mensagem   = ntfy_msg,
        ntfy_prioridade = ntfy_prioridade,
        ntfy_link       = lnk
    )


if __name__ == "__main__":
    main()
