# ETL — Importação da Base da Receita Federal

> ⏳ **Esta pasta é referente à Etapa 2 do projeto e ainda não está implementada.**

## Visão Geral

Scripts Python que automatizam o download, processamento e importação dos dados públicos do CNPJ disponibilizados mensalmente pela Receita Federal.

## Arquivos Planejados

- `download.py` — baixa os arquivos zipados mais recentes
- `schema.sql` — DDL com todas as tabelas oficiais do CNPJ
- `importer.py` — importa via `COPY FROM STDIN` (rápido)
- `update_monthly.py` — atualização incremental mensal
- `validators.py` — queries de sanidade após a importação

## Fontes de Dados

- **Página oficial:** https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj
- **URL dos arquivos:** https://arquivos.receitafederal.gov.br/CNPJ/dados_abertos_cnpj/
- **Layout dos arquivos (PDF):** https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf

## Referência de Implementação

Repositório usado como referência (não copiar, apenas estudar a abordagem):
https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ

## Para Iniciar a Implementação

Use o Claude Code com o contexto do `CLAUDE.md` na raiz do projeto:

> "Vamos iniciar a Etapa 2. Leia o CLAUDE.md e o ETAPAS.md, depois implemente os scripts da pasta etl/ seguindo o roadmap."
