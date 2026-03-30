import { createClient } from '@supabase/supabase-js';
import { Resend } from 'resend';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

const resend = new Resend(process.env.RESEND_API_KEY);

function getEmailRecipients() {
  const raw = process.env.NOTIFY_EMAIL || process.env.EMAILS_DESTINO || '';
  return raw.split(',').map((item) => item.trim()).filter(Boolean);
}

function getWhatsAppRecipients() {
  const raw = process.env.CALLMEBOT_NUMEROS || '';
  const recipients = raw
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const [phone, apiKey] = entry.split(':').map((item) => item?.trim());
      if (!phone || !apiKey) return null;
      return { phone, apiKey };
    })
    .filter(Boolean);

  if (recipients.length > 0) return recipients;

  if (process.env.WHATSAPP_PHONE && process.env.CALLMEBOT_API_KEY) {
    return [{ phone: process.env.WHATSAPP_PHONE, apiKey: process.env.CALLMEBOT_API_KEY }];
  }

  return [];
}

function getTelegramChatIds() {
  const fromList = (process.env.TELEGRAM_CHATS || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

  if (fromList.length > 0) return fromList;

  if (process.env.TELEGRAM_CHAT_ID?.trim()) {
    return [process.env.TELEGRAM_CHAT_ID.trim()];
  }

  return [];
}

function formatCurrency(value) {
  if (value === null || value === undefined) return 'N/A';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

function formatDate(dateStr) {
  if (!dateStr) return 'N/A';
  const [year, month, day] = dateStr.split('-');
  return `${day}/${month}/${year}`;
}

function escapeHtml(value) {
  return String(value ?? 'N/A')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function splitMessage(text, maxLen = 900) {
  if (!text) return [];
  if (text.length <= maxLen) return [text];

  const lines = text.split('\n');
  const chunks = [];
  let current = '';

  for (const line of lines) {
    const candidate = current ? `${current}\n${line}` : line;
    if (candidate.length <= maxLen) {
      current = candidate;
      continue;
    }

    if (current) chunks.push(current);

    if (line.length <= maxLen) {
      current = line;
      continue;
    }

    let start = 0;
    while (start < line.length) {
      chunks.push(line.slice(start, start + maxLen));
      start += maxLen;
    }
    current = '';
  }

  if (current) chunks.push(current);
  return chunks;
}

function getDaysUntil(dateStr) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(dateStr + 'T00:00:00');
  return Math.ceil((target - today) / (1000 * 60 * 60 * 24));
}

function buildGoogleCalendarLink(contract) {
  if (!contract?.vigencia_date) return '';

  const start = contract.vigencia_date.replaceAll('-', '');
  const endDate = new Date(`${contract.vigencia_date}T00:00:00`);
  endDate.setDate(endDate.getDate() + 1);
  const end = endDate.toISOString().slice(0, 10).replaceAll('-', '');

  const title = `Vencimento do processo ${contract.process_number ?? 'N/A'}`;
  const details = [
    `Processo: ${contract.process_number ?? 'N/A'}`,
    `Município: ${contract.municipalities?.name ?? 'N/A'}`,
    `Objeto: ${contract.object ?? 'N/A'}`,
    `Valor concedente: ${formatCurrency(contract.total_concedente_value)}`,
    `Valor licitado: ${formatCurrency(contract.licitado_value)}`,
    `Vigência: ${formatDate(contract.vigencia_date)}`,
  ].join('\n');

  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: title,
    dates: `${start}/${end}`,
    details,
  });

  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

async function getExpiringContracts() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const pastLimit = new Date(today);
  pastLimit.setDate(today.getDate() - 30);
  const limit = new Date(today);
  limit.setDate(today.getDate() + 45);

  const pastLimitStr = pastLimit.toISOString().split('T')[0];
  const todayStr = today.toISOString().split('T')[0];
  const limitStr = limit.toISOString().split('T')[0];

  const { data, error } = await supabase
    .from('processes')
    .select(`
      process_number,
      object,
      vigencia_date,
      total_concedente_value,
      licitado_value,
      municipalities ( name )
    `)
    .gte('vigencia_date', pastLimitStr)
    .lte('vigencia_date', limitStr)
    .order('vigencia_date', { ascending: true });

  if (error) {
    console.error('Erro ao buscar contratos:', error.message);
    return { expired: [], urgent: [], warning: [], notice: [] };
  }

  const expired = [], urgent = [], warning = [], notice = [];

  for (const contract of data ?? []) {
    const days = getDaysUntil(contract.vigencia_date);
    if (days < 0) expired.push({ ...contract, daysLeft: days });
    else if (days <= 15) urgent.push({ ...contract, daysLeft: days });
    else if (days <= 30) warning.push({ ...contract, daysLeft: days });
    else notice.push({ ...contract, daysLeft: days });
  }

  return { expired, urgent, warning, notice };
}

function buildTable(contracts) {
  const rows = contracts.map(c => `
    <tr>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px">${c.process_number ?? 'N/A'}</td>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px">${c.municipalities?.name ?? 'N/A'}</td>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px">${c.object ?? 'N/A'}</td>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap">${formatCurrency(c.total_concedente_value)}</td>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap">${formatCurrency(c.licitado_value)}</td>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap;font-weight:bold">${formatDate(c.vigencia_date)}</td>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;text-align:center;font-weight:bold">${c.daysLeft} dias</td>
      <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;text-align:center">
        <a href="${buildGoogleCalendarLink(c)}" style="color:#2563eb;text-decoration:none;font-weight:600">Adicionar</a>
      </td>
    </tr>
  `).join('');

  return `
    <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden">
      <thead>
        <tr style="background:#f8f9fa">
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">Nº PROCESSO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">MUNICÍPIO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">OBJETO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VALOR CONCEDENTE</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VALOR LICITADO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VENCIMENTO</th>
          <th style="padding:12px 10px;text-align:center;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">DIAS RESTANTES</th>
          <th style="padding:12px 10px;text-align:center;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">GOOGLE CALENDAR</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function buildEmailHtml({ expired, urgent, warning, notice }) {
  const total = expired.length + urgent.length + warning.length + notice.length;

  const sections = [
    { list: expired, color: '#7f1d1d', bg: '#fef2f2', emoji: '⚫', label: 'VENCIDOS — Já passaram da vigência' },
    { list: urgent, color: '#c0392b', bg: '#fdf0ef', emoji: '🔴', label: 'URGENTE — Vencem em até 15 dias' },
    { list: warning, color: '#e67e22', bg: '#fef9f0', emoji: '🟠', label: 'ATENÇÃO — Vencem entre 16 e 30 dias' },
    { list: notice, color: '#2980b9', bg: '#f0f7fd', emoji: '🔵', label: 'AVISO — Vencem entre 31 e 45 dias' },
  ].map(({ list, color, bg, emoji, label }) => `
    <div style="margin-bottom:35px;background:${bg};border-left:5px solid ${color};border-radius:6px;padding:20px">
      <h3 style="color:${color};margin:0 0 15px 0">${emoji} ${label} (${list.length} contrato${list.length > 1 ? 's' : ''})</h3>
      ${list.length > 0
        ? buildTable(list)
        : '<p style="margin:0;color:#64748b;font-size:13px;">Nenhum contrato nesta faixa no momento.</p>'}
    </div>
  `).join('');

  const emptyState = total === 0
    ? `
      <div style="margin-bottom:25px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:18px;color:#334155">
        ✅ Nenhum contrato vencido ou próximo do vencimento no período monitorado (últimos 30 dias + próximos 45 dias).
      </div>
    `
    : '';

  return `
    <div style="font-family:Arial,sans-serif;max-width:980px;margin:auto;padding:20px;background:#f5f5f5">
      <div style="background:#fff;border-radius:10px;padding:30px;box-shadow:0 2px 8px rgba(0,0,0,0.1)">
        <h2 style="color:#2c3e50;margin-top:0;border-bottom:3px solid #3498db;padding-bottom:15px">
          📋 Alertas Semanais de Vencimento de Contratos
        </h2>
        <p style="color:#666;margin-bottom:25px">
          Foram encontrados <strong>${total} contrato(s)</strong> vencidos e/ou próximos ao vencimento em ${new Date().toLocaleDateString('pt-BR')}.
        </p>
        ${emptyState}
        ${sections}
        <p style="color:#aaa;font-size:11px;margin-top:30px;border-top:1px solid #eee;padding-top:15px">
          Enviado automaticamente toda segunda-feira às 10h.
        </p>
      </div>
    </div>
  `;
}

function buildWhatsAppSummary({ expired, urgent, warning, notice }) {
  const lines = [];
  const total = expired.length + urgent.length + warning.length + notice.length;

  lines.push(`📋 *ALERTA DE VENCIMENTOS*`);
  lines.push(`📅 ${new Date().toLocaleDateString('pt-BR')}`);
  lines.push(`📦 Total monitorado: *${total} contrato(s)*\n`);

  if (total === 0) {
    lines.push(`✅ Nenhum contrato vencido ou próximo do vencimento no período monitorado.`);
    return lines.join('\n');
  }

  if (expired.length > 0) {
    lines.push(`⚫ *VENCIDOS* (${expired.length})`);
    for (const c of expired) {
      lines.push(`• Proc. ${c.process_number ?? 'N/A'} · ${c.municipalities?.name ?? 'N/A'}`);
      lines.push(`  ⛔ Vencido há ${Math.abs(c.daysLeft)} dia(s) (${formatDate(c.vigencia_date)})`);
    }
    lines.push('');
  }

  if (urgent.length > 0) {
    lines.push(`🔴 *URGENTE* · até 15 dias (${urgent.length})`);
    for (const c of urgent) {
      lines.push(`• Proc. ${c.process_number ?? 'N/A'} · ${c.municipalities?.name ?? 'N/A'}`);
      lines.push(`  ⏳ Vence em ${c.daysLeft} dia(s) (${formatDate(c.vigencia_date)})`);
      lines.push(`  📅 Agenda: ${buildGoogleCalendarLink(c)}`);
    }
    lines.push('');
  }

  if (warning.length > 0) {
    lines.push(`🟠 *ATENÇÃO* · 16 a 30 dias (${warning.length})`);
    for (const c of warning) {
      lines.push(`• Proc. ${c.process_number ?? 'N/A'} · ${c.municipalities?.name ?? 'N/A'}`);
      lines.push(`  ⏳ Vence em ${c.daysLeft} dia(s) (${formatDate(c.vigencia_date)})`);
      lines.push(`  📅 Agenda: ${buildGoogleCalendarLink(c)}`);
    }
    lines.push('');
  }

  if (notice.length > 0) {
    lines.push(`🔵 *AVISO* · 31 a 45 dias (${notice.length})`);
    for (const c of notice) {
      lines.push(`• Proc. ${c.process_number ?? 'N/A'} · ${c.municipalities?.name ?? 'N/A'}`);
      lines.push(`  ⏳ Vence em ${c.daysLeft} dia(s) (${formatDate(c.vigencia_date)})`);
      lines.push(`  📅 Agenda: ${buildGoogleCalendarLink(c)}`);
    }
  }

  return lines.join('\n');
}

function buildTelegramSummary({ expired, urgent, warning, notice }) {
  const lines = [];
  const total = expired.length + urgent.length + warning.length + notice.length;

  lines.push(`<b>📋 ALERTA DE VENCIMENTOS</b>`);
  lines.push(`📅 ${new Date().toLocaleDateString('pt-BR')}`);
  lines.push(`📦 Total monitorado: <b>${total} contrato(s)</b>\n`);

  if (total === 0) {
    lines.push(`✅ Nenhum contrato vencido ou próximo do vencimento no período monitorado.`);
    return lines.join('\n');
  }

  if (expired.length > 0) {
    lines.push(`<b>⚫ VENCIDOS (${expired.length})</b>`);
    for (const c of expired) {
      lines.push(`• <b>${escapeHtml(c.process_number)}</b>`);
      lines.push(`  🏙 ${escapeHtml(c.municipalities?.name)}`);
      lines.push(`  📄 ${escapeHtml(c.object)}`);
      lines.push(`  💰 ${escapeHtml(formatCurrency(c.total_concedente_value))}`);
      lines.push(`  ⛔ Vencido há ${Math.abs(c.daysLeft)} dia(s) · ${formatDate(c.vigencia_date)}`);
    }
    lines.push('');
  }

  if (urgent.length > 0) {
    lines.push(`<b>🔴 URGENTE — até 15 dias (${urgent.length})</b>`);
    for (const c of urgent) {
      lines.push(`• <b>${escapeHtml(c.process_number)}</b>`);
      lines.push(`  🏙 ${escapeHtml(c.municipalities?.name)}`);
      lines.push(`  📄 ${escapeHtml(c.object)}`);
      lines.push(`  💰 ${escapeHtml(formatCurrency(c.total_concedente_value))}`);
      lines.push(`  ⏳ ${c.daysLeft} dia(s) · ${formatDate(c.vigencia_date)}`);
      lines.push(`  🔗 <a href="${buildGoogleCalendarLink(c)}">Google Calendar</a>`);
    }
    lines.push('');
  }

  if (warning.length > 0) {
    lines.push(`<b>🟠 ATENÇÃO — 16 a 30 dias (${warning.length})</b>`);
    for (const c of warning) {
      lines.push(`• <b>${escapeHtml(c.process_number)}</b>`);
      lines.push(`  🏙 ${escapeHtml(c.municipalities?.name)}`);
      lines.push(`  📄 ${escapeHtml(c.object)}`);
      lines.push(`  💰 ${escapeHtml(formatCurrency(c.total_concedente_value))}`);
      lines.push(`  ⏳ ${c.daysLeft} dia(s) · ${formatDate(c.vigencia_date)}`);
      lines.push(`  🔗 <a href="${buildGoogleCalendarLink(c)}">Google Calendar</a>`);
    }
    lines.push('');
  }

  if (notice.length > 0) {
    lines.push(`<b>🔵 AVISO — 31 a 45 dias (${notice.length})</b>`);
    for (const c of notice) {
      lines.push(`• <b>${escapeHtml(c.process_number)}</b>`);
      lines.push(`  🏙 ${escapeHtml(c.municipalities?.name)}`);
      lines.push(`  📄 ${escapeHtml(c.object)}`);
      lines.push(`  💰 ${escapeHtml(formatCurrency(c.total_concedente_value))}`);
      lines.push(`  ⏳ ${c.daysLeft} dia(s) · ${formatDate(c.vigencia_date)}`);
      lines.push(`  🔗 <a href="${buildGoogleCalendarLink(c)}">Google Calendar</a>`);
    }
  }

  return lines.join('\n');
}

async function sendEmail(groups) {
  const total = groups.expired.length + groups.urgent.length + groups.warning.length + groups.notice.length;
  const recipients = getEmailRecipients();
  if (recipients.length === 0) {
    console.warn('⚠️ E-mail não enviado: configure NOTIFY_EMAIL ou EMAILS_DESTINO.');
    return;
  }

  const { error } = await resend.emails.send({
    from: 'onboarding@resend.dev',
    to: recipients,
    subject: `📋 Alerta Semanal — ${total} contrato(s) vencidos e/ou próximos do vencimento — ${new Date().toLocaleDateString('pt-BR')}`,
    html: buildEmailHtml(groups),
  });
  if (error) console.error('Erro ao enviar e-mail:', error);
  else console.log(`✅ E-mail enviado — ${total} contrato(s)`);
}

async function sendWhatsApp(groups) {
  const msg = buildWhatsAppSummary(groups);
  const recipients = getWhatsAppRecipients();
  if (recipients.length === 0) {
    console.warn('⚠️ WhatsApp não enviado: configure CALLMEBOT_NUMEROS ou WHATSAPP_PHONE + CALLMEBOT_API_KEY.');
    return;
  }
  let success = 0;
  const parts = splitMessage(msg, 850);

  for (const recipient of recipients) {
    let recipientSuccess = true;
    for (const [index, part] of parts.entries()) {
      const finalPart = parts.length > 1 ? `[${index + 1}/${parts.length}]\n${part}` : part;
      const encoded = encodeURIComponent(finalPart);
      const url = `https://api.callmebot.com/whatsapp.php?phone=${recipient.phone}&text=${encoded}&apikey=${recipient.apiKey}`;
      try {
        const res = await fetch(url);
        const body = await res.text();
        if (!(res.ok && body.toLowerCase().includes('queued'))) {
          recipientSuccess = false;
          console.error(`⚠️ Falha WhatsApp (${recipient.phone}) parte ${index + 1}/${parts.length} — status ${res.status} — ${body}`);
          break;
        }
      } catch (err) {
        recipientSuccess = false;
        console.error(`❌ Erro WhatsApp (${recipient.phone}) parte ${index + 1}/${parts.length}:`, err.message);
        break;
      }
    }
    if (recipientSuccess) success += 1;
  }

  console.log(`✅ WhatsApp enviado para ${success}/${recipients.length} número(s).`);
}

async function sendTelegram(groups) {
  const msg = buildTelegramSummary(groups);
  const token = process.env.TELEGRAM_BOT_TOKEN || process.env.TELEGRAM_TOKEN;
  const chatIds = getTelegramChatIds();

  if (!token || chatIds.length === 0) {
    console.warn('⚠️ Telegram não enviado: configure TELEGRAM_BOT_TOKEN/TELEGRAM_TOKEN e TELEGRAM_CHAT_ID/TELEGRAM_CHATS.');
    return;
  }

  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  const parts = splitMessage(msg, 3900);
  let success = 0;

  for (const chatId of chatIds) {
    let chatOk = true;
    for (const [index, part] of parts.entries()) {
      const finalPart = parts.length > 1 ? `<b>Parte ${index + 1}/${parts.length}</b>\n${part}` : part;
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: chatId,
            text: finalPart,
            parse_mode: 'HTML',
            disable_web_page_preview: true,
          }),
        });
        const data = await res.json();
        if (!data.ok) {
          chatOk = false;
          console.error(`❌ Erro Telegram chat ${chatId} parte ${index + 1}/${parts.length}:`, JSON.stringify(data));
          break;
        }
      } catch (err) {
        chatOk = false;
        console.error(`❌ Erro Telegram chat ${chatId} parte ${index + 1}/${parts.length}:`, err.message);
        break;
      }
    }

    if (chatOk) success += 1;
  }

  console.log(`✅ Telegram enviado para ${success}/${chatIds.length} chat(s).`);
}

async function main() {
  console.log(`\n🔍 Verificando contratos — ${new Date().toLocaleDateString('pt-BR')}\n`);

  const groups = await getExpiringContracts();
  const total = groups.expired.length + groups.urgent.length + groups.warning.length + groups.notice.length;

  if (total === 0) {
    console.log('ℹ️ Nenhum contrato vencido ou a vencer entre os últimos 30 e próximos 45 dias. Enviando notificação mesmo assim.\n');
  } else {
    console.log(`⚠️  ${groups.expired.length} vencido(s) | ${groups.urgent.length} urgente(s) | ${groups.warning.length} atenção | ${groups.notice.length} aviso(s)\n`);
  }

  await sendEmail(groups);
  await sendWhatsApp(groups);
  await sendTelegram(groups);

  console.log('\n🎉 Processo finalizado!');
}

main().catch(err => {
  console.error('❌ Erro fatal:', err);
  process.exit(1);
});
