# Segurança

**Idioma:** [English](SECURITY.md) · **Português (Brasil)**

**Modelo operacional. Revise e complete os dados de contato e o processo antes
de oferecer suporte comercial.**

## Reportar uma vulnerabilidade

Use o recurso **Report a vulnerability** / GitHub Security Advisories do
repositório em que o Argus estiver publicado. Se esse recurso estiver
desabilitado, abra um issue privado ao mantenedor do repositório e não inclua
detalhes exploráveis em um issue público. Não há endereço de e-mail ou prazo de
resposta oficial definido neste projeto.

Inclua a versão ou commit afetado, sistema operacional, passos mínimos para
reproduzir, impacto observado e uma mitigação possível. Remova tokens, chaves,
dados pessoais e conteúdo privado de logs e capturas. Não teste contra serviços
ou contas de terceiros sem autorização.

## Configuração segura

- Em produção, defina `JWT_SECRET`, `ARGUS_ENCRYPTION_KEY`, `DATABASE_URL`,
  `REDIS_URL` e `CORS_ORIGINS` próprios. A API não sobe em produção com
  segredos de menos de 32 caracteres ou iguais entre si, banco que não seja
  PostgreSQL, `CORS_ORIGINS` ausente ou sem `https://`, ou sem Redis acessível
  (`api/config.py`, `api/rate_limit.py`).
- Atrás de um proxy, defina `CLIENT_IP_HEADER` ou `TRUSTED_PROXY_HOPS` para que
  os limites de taxa vejam o IP real; o `X-Forwarded-For` sozinho é escrito
  pelo cliente.
- Não publique `.env`, arquivos de credenciais OAuth, bancos, dumps ou dados
  locais. Restrinja acesso ao banco e aos logs do provedor.
- Atualize dependências e revise permissões de microfone, tela, câmera, sistema
  de arquivos e integrações externas.
- A política atual de expiração de dados e suas limitações estão em
  `PRIVACY.md`; ela não apaga contas, memória ou segredos persistidos.

## Resposta

Os mantenedores devem confirmar recebimento pelo canal privado, reproduzir o
problema, avaliar impacto, preparar correção e coordenar divulgação com quem
reportou. Este repositório ainda não define SLA, equipe de resposta ou processo
de crédito; preencha esses itens antes de prometer suporte.

---

**Idioma:** [English](SECURITY.md) · **Português (Brasil)**
