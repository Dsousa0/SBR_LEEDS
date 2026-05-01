# Claude Code — Contexto do Projeto

> **Atenção, Claude:** Antes de qualquer ação neste projeto, leia obrigatoriamente:
>
> 1. [`docs/CLAUDE.md`](docs/CLAUDE.md) — histórico completo de decisões, estado atual e próximas etapas
> 2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — decisões técnicas e fluxo de dados
> 3. [`docs/ETAPAS.md`](docs/ETAPAS.md) — detalhamento de cada etapa do roadmap
> 4. [`README.md`](README.md) — instruções de uso e setup

## Resumo Rápido

**Projeto:** Ferramenta pessoal de prospecção de leads usando a base pública de CNPJ da Receita Federal.

**Estado atual:** Etapa 1 — Setup do ambiente local com Docker.

**Próxima etapa:** Etapa 2 — Importação da base completa do CNPJ no PostgreSQL.

## Princípios Inegociáveis

- ❌ **Não usar APIs pagas** — toda a fonte de dados deve ser gratuita
- ❌ **Não simplificar para SQLite** — o volume da base exige PostgreSQL
- ❌ **Não commitar `.env`** — apenas `.env.example`
- ❌ **Não apagar `data/`** sem confirmação explícita do usuário
- ✅ **Sempre português brasileiro** em mensagens, comentários e UI
- ✅ **Sempre testar localmente** antes de propor PR
- ✅ **Manter compatibilidade com VPS futura** — nada que rode só local

## Stack Confirmada

- Python 3.11 + FastAPI
- PostgreSQL 16
- HTMX + Jinja2 + TailwindCSS (Etapa 4 em diante)
- Docker + Docker Compose
- Leaflet + OpenStreetMap (Etapa 4)
- Caddy (apenas Etapa 6 — produção)

## Como Começar Trabalhando Aqui

1. Leia `docs/CLAUDE.md` por completo
2. Confirme com o usuário em qual etapa estamos
3. Para mudanças estruturais (stack, arquitetura), pergunte antes
4. Para implementação dentro de uma etapa já definida, pode prosseguir
