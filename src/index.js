import { createClient } from '@supabase/supabase-js';
import { Resend } from 'resend';

// ─── Clientes ────────────────────────────────────────────────────────────────
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

const resend = new Resend(process.env.RESEND_API_KEY);

// ─── Configuração ────────────────────────────────────────────────────────────
const ALERT_DAYS = [45, 30, 15];

// ─── Utilitários ─────────────────────────────────────────────────────────────
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

// ─── Buscar contratos no Supabase ─────────────────────────────────────────────
async function getExpiringContracts() {
  const today = new Date();
  const results = [];

  for (const days of ALERT_DAYS) {
    const targetDate = new Date(today);
    targetDate.setDate(today.getDate() + days);
    const dateStr = targetDate.toISOString().split('T')[0];

    const { data, error } = await supabase
      .from('processes')
      .select(`
        process_number,
        object,
        vigencia_date,
        total_concedente_value,
        licitado_value,
        municipalities (
          name
        )
      `)
      .eq('vigencia_date', dateStr);

    if (error) {
      console.error(`Erro ao buscar contratos com ${days} dias:`, error.message);
      continue;
    }

    if (data && data.length > 0) {
      results.push({ days, contracts: data });
    }
  }

  return results;
}

// ─── Montar HTML do e-mail ────────────────────────────────────────────────────
function buildEmailHtml(expiringGroups) {
  const alertColors = { 15: '#c0392b', 30: '#e67e22', 45: '#2980b9' };
  const alertEmojis = { 15: '🔴', 30: '🟠', 45: '🔵' };

  const sections = expiringGroups.map(({ days, contracts }) => {
    const color = alertColors[days];
    const emoji = alertEmojis[days];

    const rows = contracts.map(c => `
      <tr>
        <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px">
          ${c.process_number ?? 'N/A'}
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px">
          ${c.municipalities?.name ?? 'N/A'}
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px">
          ${c.object ?? 'N/A'}
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap">
          ${formatCurrency(c.total_concedente_value)}
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap">
          ${formatCurrency(c.licitado_value)}
        </td>
        <td style="padding:12px 10px;border-bottom:1px solid #eee;font-size:13px;white-space:nowrap">
          ${formatDate(c.vigencia_date)}
        </td>
      </tr>
    `).join('');

    return `
      <div style="margin-bottom:30px">
        <h3 style="color:${color};margin-bottom:12px">
          ${emoji} Contratos que vencem em ${days} dias (${contracts.length} contrato${contracts.length > 1 ? 's' : ''})
        </h3>
        <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08)">
          <thead>
            <tr style="background:#f8f9fa">
              <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">Nº PROCESSO</th>
              <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">MUNICÍPIO</th>
              <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">OBJETO</th>
              <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VALOR CONCEDENTE</th>
              <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VALOR LICITADO</th>
              <th style="padding:12px 10px;text-align:left;font-size:12px;color:#555;border-bottom:2px solid #dee2e6">VENCIMENTO</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }).join('');

  const total = expiringGroups.reduce((acc, g) => acc + g.contracts.length, 0);

  return `
    <div style="font-family:Arial,sans-serif;max-width:960px;margin:auto;padding:20px;background:#f5f5f5">
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

// ─── Montar mensagens do WhatsApp ─────────────────────────────────────────────
function buildWhatsAppMessages(expiringGroups) {
  const messages = [];

  for (const { days, contracts } of expiringGroups) {
    for (const c of contracts) {
      const municipality = c.municipalities?.name ?? 'N/A';
      const msg =
        `⚠️ *ALERTA DE VENCIMENTO*\n\n` +
        `📁 *Processo:* ${c.process_number ?? 'N/A'}\n` +
        `🏙️ *Município:* ${municipality}\n` +
        `📄 *Objeto:* ${c.object ?? 'N/A'}\n` +
        `💰 *Valor Concedente:* ${formatCurrency(c.total_concedente_value)}\n` +
        `🏷️ *Valor Licitado:* ${formatCurrency(c.licitado_value)}\n` +
        `📅 *Vencimento:* ${formatDate(c.vigencia_date)}\n` +
        `⏳ *Dias restantes:* ${days} dias`;
      messages.push(msg);
    }
  }

  return messages;
}

// ─── Enviar e-mail ────────────────────────────────────────────────────────────
async function sendEmail(expiringGroups) {
  const total = expiringGroups.reduce((acc, g) => acc + g.contracts.length, 0);

  const { error } = await resend.emails.send({
    from: 'onboarding@resend.dev', // ← troque pelo seu domínio após verificar no Resend
    to: process.env.NOTIFY_EMAIL,
    subject: `📋 ${total} contrato(s) próximo(s) ao vencimento — ${new Date().toLocaleDateString('pt-BR')}`,
    html: buildEmailHtml(expiringGroups),
  });

  if (error) {
    console.error('Erro ao enviar e-mail:', error);
  } else {
    console.log(`✅ E-mail enviado com sucesso — ${total} contrato(s)`);
  }
}

// ─── Enviar WhatsApp ──────────────────────────────────────────────────────────
async function sendWhatsApp(expiringGroups) {
  const messages = buildWhatsAppMessages(expiringGroups);
  console.log(`📱 Enviando ${messages.length} mensagem(ns) no WhatsApp...`);

  for (const [i, msg] of messages.entries()) {
    const encoded = encodeURIComponent(msg);
    const url = `https://api.callmebot.com/whatsapp.php?phone=${process.env.WHATSAPP_PHONE}&text=${encoded}&apikey=${process.env.CALLMEBOT_API_KEY}`;

    try {
      const res = await fetch(url);
      console.log(`✅ WhatsApp ${i + 1}/${messages.length} enviado — status ${res.status}`);
    } catch (err) {
      console.error(`❌ Erro ao enviar WhatsApp ${i + 1}:`, err.message);
    }

    if (i < messages.length - 1) {
      await new Promise(r => setTimeout(r, 5000));
    }
  }
}

// ─── Função principal ─────────────────────────────────────────────────────────
async function main() {
  console.log(`\n🔍 Verificando contratos — ${new Date().toLocaleDateString('pt-BR')}\n`);

  const expiringGroups = await getExpiringContracts();

  if (!expiringGroups.length) {
    console.log('✅ Nenhum contrato a vencer em 15, 30 ou 45 dias hoje.');
    return;
  }

  const total = expiringGroups.reduce((acc, g) => acc + g.contracts.length, 0);
  console.log(`⚠️  Encontrado(s) ${total} contrato(s) a vencer.\n`);

  await sendEmail(expiringGroups);
  await sendWhatsApp(expiringGroups);

  console.log('\n🎉 Processo finalizado com sucesso!');
}

main().catch(err => {
  console.error('❌ Erro fatal:', err);
  process.exit(1);
});
