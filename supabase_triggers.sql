-- ================================================================
-- SUPABASE — Triggers SQL que chamam a API do GitHub Actions
-- Cole no SQL Editor do Supabase (Database → SQL Editor)
-- ================================================================
-- 
-- ANTES DE COLAR: substitua os valores abaixo:
--   SEU_USUARIO_GITHUB  → lucasdn7
--   SEU_REPOSITORIO     → contract-notifier
--   SEU_TOKEN_GITHUB    → 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
--   processes           → processes (já está correto)
-- ================================================================


-- ─────────────────────────────────────────────────────────────
-- EXTENSÃO pg_net (necessária para HTTP requests)
-- ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pg_net;


-- ─────────────────────────────────────────────────────────────
-- FUNÇÃO AUXILIAR: chama a API do GitHub Actions
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION chamar_github_actions(event_type TEXT, payload JSONB)
RETURNS void AS $$
BEGIN
  PERFORM net.http_post(
    url     := 'https://api.github.com/repos/SEU_USUARIO_GITHUB/SEU_REPOSITORIO/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer SEU_TOKEN_GITHUB',
      'Accept',        'application/vnd.github+json',
      'Content-Type',  'application/json',
      'X-GitHub-Api-Version', '2022-11-28'
    ),
    body    := jsonb_build_object(
      'event_type',     event_type,
      'client_payload', payload
    )::text
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ─────────────────────────────────────────────────────────────
-- TRIGGER 1: Novo processo inserido COM data de vigência
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_fn_novo_processo()
RETURNS trigger AS $$
BEGIN
  -- Só notifica se o novo registro tem data_vigencia preenchida
  IF NEW.data_vigencia IS NOT NULL THEN
    PERFORM chamar_github_actions(
      'novo_processo',
      jsonb_build_object('record', row_to_json(NEW)::jsonb)
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_novo_processo ON processes;
CREATE TRIGGER trg_novo_processo
  AFTER INSERT ON processes
  FOR EACH ROW
  EXECUTE FUNCTION trigger_fn_novo_processo();


-- ─────────────────────────────────────────────────────────────
-- TRIGGER 2: Data de vigência foi alterada em um UPDATE
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_fn_vigencia_editada()
RETURNS trigger AS $$
BEGIN
  -- Só notifica se a coluna data_vigencia realmente mudou
  IF OLD.data_vigencia IS DISTINCT FROM NEW.data_vigencia THEN
    PERFORM chamar_github_actions(
      'vigencia_editada',
      jsonb_build_object(
        'record',     row_to_json(NEW)::jsonb,
        'old_record', row_to_json(OLD)::jsonb
      )
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_vigencia_editada ON processes;
CREATE TRIGGER trg_vigencia_editada
  AFTER UPDATE ON processes
  FOR EACH ROW
  EXECUTE FUNCTION trigger_fn_vigencia_editada();


-- ─────────────────────────────────────────────────────────────
-- VERIFICAÇÃO: listar triggers ativos na tabela
-- ─────────────────────────────────────────────────────────────
SELECT trigger_name, event_manipulation, action_timing
FROM information_schema.triggers
WHERE event_object_table = 'processes';
