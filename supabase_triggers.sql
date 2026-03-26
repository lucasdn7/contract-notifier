-- ================================================================
-- SUPABASE — Triggers SQL que chamam a API do GitHub Actions
-- Cole no SQL Editor do Supabase (Database → SQL Editor)
-- ================================================================
-- 
-- ANTES DE COLAR: substitua os valores abaixo:
--   SEU_USUARIO_GITHUB  → seu usuário ou organização no GitHub
--   SEU_REPOSITORIO     → nome do repositório que criou
--   SEU_TOKEN_GITHUB    → Personal Access Token com permissão "repo"
--   processos           → nome real da sua tabela
--
-- Como gerar o Personal Access Token (PAT):
--   1. GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic)
--   2. Clique "Generate new token"
--   3. Marque o escopo: "repo" (Full control of private repositories)
--   4. Copie o token gerado (começa com ghp_...)
-- ================================================================


-- ─────────────────────────────────────────────────────────────
-- EXTENSÃO pg_net (necessária para HTTP requests)
-- Ative em: Supabase → Database → Extensions → pg_net
-- ─────────────────────────────────────────────────────────────
-- Se não estiver ativa, rode:
-- CREATE EXTENSION IF NOT EXISTS pg_net;


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

DROP TRIGGER IF EXISTS trg_novo_processo ON processos;
CREATE TRIGGER trg_novo_processo
  AFTER INSERT ON processos
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

DROP TRIGGER IF EXISTS trg_vigencia_editada ON processos;
CREATE TRIGGER trg_vigencia_editada
  AFTER UPDATE ON processos
  FOR EACH ROW
  EXECUTE FUNCTION trigger_fn_vigencia_editada();


-- ─────────────────────────────────────────────────────────────
-- VERIFICAÇÃO: listar triggers ativos na tabela
-- ─────────────────────────────────────────────────────────────
SELECT trigger_name, event_manipulation, action_timing
FROM information_schema.triggers
WHERE event_object_table = 'processos';
