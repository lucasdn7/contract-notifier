import { createClient } from '@supabase/supabase-js';
import { Resend } from 'resend';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

const resend = new Resend(process.env.RESEND_API_KEY);

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

function getDaysUntil(dateStr) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(dateStr + 'T00:00:00');
  return Math.ceil((target - today) / (1000 * 60 * 60 * 24));
}

async function getExpiringContracts() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const limit = new Date(today);
  limit.setDate(today.getDate() + 45);

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
    .gte('vigencia_date', todayStr)
    .lte('vigencia_date', limitStr)
    .order('vigencia_date', { ascending: true });

  if (error) {
    console.error('Erro ao buscar contratos:', error.message);
    return { urgent: [], warning: [], notice: [] };
  }

  const urgent = [], warning = [], notice = [];

  for (const contract of data ?? []) {
    const days = getDaysUntil(contract.vigencia_date);
    if (days <= 15) urgent.push({ ...contract, daysLeft: days });
    else if (days <= 30) warning.push({ ...contract, daysLeft: days });
    else notice.push({ ...contract, daysLeft: days });
  }

  return { urgent, warning, notice };
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
    </tr>
  `).join('');

  return `
    <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08)">
      <thead>
        <tr style="background:#f8f9fa">
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">Nº PROCESSO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">MUNICÍPIO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">OBJETO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VALOR CONCEDENTE</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VALOR LICITADO</th>
          <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VENCIMENTO</th>
          <th style="padding:12px 10px;text-align:center;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">DIAS RESTANTES</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function buildEmailHtml({ urgent, warning, notice }) {
  const total = urgent.length + warning.length + notice.length;

  const sections = [
    { list: urgent, color: '#c0392b', bg: '#fdf0ef', emoji: '🔴', label: 'URGENTE — Vencem em até 15 dias' },
    { list: warning, color: '#e67e22', bg: '#fef9f0', emoji: '🟠', label: 'ATENÇÃO — Vencem entre 16 e 30 dias' },
    { list: notice, color: '#2980b9', bg: '#f0f7fd', emoji: '🔵', label: 'AVISO — Vencem entre 31 e 45 dias' },
  ]
    .filter(s => s.list.length > 0)
    .map(({ list, color, bg, emoji, label }) => `
      <div style="margin-bottom:35px;background:${bg};border-left:5px solid ${color};border-radius:6px;padding:20px">
        <h3 style="color:${color};margin:0 0 15px 0">
          ${emoji} ${label} (${list.length} contrato${list.length > 1 ? 's' : ''})
        </h3>
        ${buildTable(list)}
      </div>
    `).join('');

  return `
    <div style="font-family:Arial,sans-serif;max-width:980px;margin:auto;padding:20px;background:#f5f5f5">
      <div style="background:#fff;border-radius:10px;padding:30px;box-shadow:0 2px 8px rgba(0,0,0,0.1)">
        <h2 style="color:#2c3e50;margin-top:0;border-bottom:3px solid #3498db;padding-bottom:15px">
          📋 Alertas de Vencimento de Contratos
        </h2>
        <p style="color:#666;margin-bottom:25px">
          Foram encontrados <strong>${total} contrato(s)</strong> próximos ao vencimento em ${new Date().toLocaleDateString('pt-BR')}.
        </p>
        ${sections}
        <p style="color:#aaa;font-size:11px;margin-top:30px;border-top:1px solid #eee;padding-top:15px">
          Enviado automaticamente pelo sistema de monitoramento de contratos.
        </p>
      </div>
    </div>
  `;
}

// Uma única mensagem resumida por grupo
function buildWhatsAppSummary({ urgent, warning, notice }) {
  const lines = [];
  lines.push(`📋 *ALERTA DE CONTRATOS — ${new Date().toLocaleDateString('pt-BR')}*\n`);

  if (urgent.length > 0) {
    lines.push(`🔴 *URGENTE — até 15 dias (${urgent.length})*`);
    for (const c of urgent) {
      lines.push(`• ${c.process_number ?? 'N/A'} | ${c.municipalities?.name ?? 'N/A'} | ${formatDate(c.vigencia_date)} (${c.daysLeft}d)`);
    }
    lines.push('');
  }

  if (warning.length > 0) {
    lines.push(`🟠 *ATENÇÃO — 16 a 30 dias (${warning.length})*`);
    for (const c of warning) {
      lines.push(`• ${c.process_number ?? 'N/A'} | ${c.municipalities?.name ?? 'N/A'} | ${formatDate(c.vigencia_date)} (${c.daysLeft}d)`);
    }
    lines.push('');
  }

  if (notice.length > 0) {
    lines.push(`🔵 *AVISO — 31 a 45 dias (${notice.length})*`);
    for (const c of notice) {
      lines.push(`• ${c.process_number ?? 'N/A'} | ${c.municipalities?.name ?? 'N/A'} | ${formatDate(c.vigencia_date)} (${c.daysLeft}d)`);
    }
  }

  return lines.join('\n');
}

async function sendEmail(groups) {
  const total = groups.urgent.length + groups.warning.length + groups.notice.length;

  const { error } = await resend.emails.send({
    from: 'onboarding@resend.dev',
    to: process.env.NOTIFY_EMAIL,
    subject: `📋 ${total} contrato(s) próximo(s) ao vencimento — ${new Date().toLocaleDateString('pt-BR')}`,
    html: buildEmailHtml(groups),
  });

  if (error) console.error('Erro ao enviar e-mail:', error);
  else console.log(`✅ E-mail enviado — ${total} contrato(s)`);
}

async function sendWhatsApp(groups) {
  const msg = buildWhatsAppSummary(groups);
  const encoded = encodeURIComponent(msg);
  const url = `https://api.callmebot.com/whatsapp.php?phone=${process.env.WHATSAPP_PHONE}&text=${encoded}&apikey=${process.env.CALLMEBOT_API_KEY}`;

  try {
    const res = await fetch(url);
    console.log(`✅ WhatsApp enviado — status ${res.status}`);
  } catch (err) {
    console.error('❌ Erro ao enviar WhatsApp:', err.message);
  }
}

async function main() {
  console.log(`\n🔍 Verificando contratos — ${new Date().toLocaleDateString('pt-BR')}\n`);

  const groups = await getExpiringContracts();
  const total = groups.urgent.length + groups.warning.length + groups.notice.length;

  if (total === 0) {
    console.log('✅ Nenhum contrato a vencer nos próximos 45 dias.');
    return;
  }

  console.log(`⚠️  ${groups.urgent.length} urgente(s) | ${groups.warning.length} atenção | ${groups.notice.length} aviso(s)\n`);

  await sendEmail(groups);
  await sendWhatsApp(groups);

  console.log('\n🎉 Processo finalizado!');
}

main().catch(err => {
  console.error('❌ Erro fatal:', err);
  process.exit(1);
});
