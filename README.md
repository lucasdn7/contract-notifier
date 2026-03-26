# contract-notifier

## Disparo manual do relatório (para botão do site)

Foi adicionado suporte ao evento `repository_dispatch` com action `relatorio_manual` no workflow `01_relatorio_semanal.yml`.

Exemplo de chamada (backend do seu site):

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <GITHUB_TOKEN_COM_REPO>" \
  https://api.github.com/repos/<OWNER>/<REPO>/dispatches \
  -d '{"event_type":"relatorio_manual","client_payload":{"source":"botao_site"}}'
```
