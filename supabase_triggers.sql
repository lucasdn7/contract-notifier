-- ================================================================
-- SUPABASE — Triggers SQL que chamam a API do GitHub Actions
-- ================================================================
-- Substitua antes de rodar:
--   SEU_USUARIO_GITHUB  → lucasdn7
--   SEU_REPOSITORIO     → contract-notifier
--   SEU_TOKEN_GITHUB    → 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
-- ================================================================

CREATE EXTENSION IF NOT EXISTS pg_net;

-- Função auxiliar para chamar o GitHub Actions
CREATE OR REPLACE FUNCTION chamar_github_actions(event_type TEXT, payload JSONB)
RETURNS void AS $$
DECLARE
  v_request_id bigint;
BEGIN
  SELECT net.http_post(
    url    := 'https://api.github.com/repos/lucasdn7/contract-notifier/dispatches',
    body   := jsonb_build_object(
                'event_type',     event_type,
                'client_payload', payload
              ),
    params := '{}'::jsonb,
    headers:= jsonb_build_object(
                'Authorization', 'Bearer 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',
                'Accept',        'application/vnd.github+json',
                'Content-Type',  'application/json',
                'X-GitHub-Api-Version', '2022-11-28'
              ),
    timeout_milliseconds := 5000
  )
  INTO v_request_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger 1: novo processo com vigência
CREATE OR REPLACE FUNCTION trigger_fn_novo_processo()
RETURNS trigger AS $$
BEGIN
  IF NEW.vigencia_date IS NOT NULL THEN
    PERFORM chamar_github_actions(
      'novo_processo',
      row_to_json(NEW)::jsonb
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

-- Trigger 2: vigência alterada em UPDATE
CREATE OR REPLACE FUNCTION trigger_fn_vigencia_editada()
RETURNS trigger AS $$
BEGIN
  IF OLD.vigencia_date IS DISTINCT FROM NEW.vigencia_date THEN
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

-- Verificar triggers
SELECT trigger_name, event_manipulation, action_timing
FROM information_schema.triggers
WHERE event_object_table = 'processes';
