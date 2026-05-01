# ETL — Importação da Base da Receita Federal

Scripts Python que processam e importam os dados públicos do CNPJ disponibilizados
mensalmente pela Receita Federal.

## Arquivos

| Script | Descrição |
|--------|-----------|
| `schema.sql` | DDL de todas as tabelas da base CNPJ |
| `importer.py` | Importa os ZIPs via COPY FROM STDIN (psycopg2) |
| `update_monthly.py` | Detecta ZIPs novos e re-importa quando necessário |
| `validators.py` | Queries de sanidade e performance após a importação |

## Pré-requisitos

- Etapa 1 concluída (containers rodando: `docker compose ps`)
- ~10 GB de espaço livre (base filtrada por segmento)

## Fluxo de uso

### 1. Baixar os arquivos manualmente

Acesse o portal e baixe os ZIPs do mês mais recente:

- **Portal:** https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj
- Salve todos os ZIPs em `./downloads/YYYY-MM/` (ex: `./downloads/2026-04/`)

### 2. Importar os dados

**Recomendado — importar só um segmento (muito mais rápido):**

```powershell
# Farmácias e drogarias (segmento padrão do projeto)
docker compose --profile etl run --rm etl python importer.py --segmento farmacia

# CNAEs customizados
docker compose --profile etl run --rm etl python importer.py --cnaes 4771701,4771702,4771703
```

**Importação completa (Brasil inteiro — 3 a 8 horas):**

```powershell
docker compose --profile etl run --rm etl python importer.py
```

A importação:
- Aplica o `schema.sql` automaticamente (idempotente)
- Com `--segmento`: importa referências → estabelecimento (filtrado) → empresa (filtrado)
- Sem `--segmento`: importa tudo na ordem padrão
- Filtra apenas situação cadastral `02` (ativa) por padrão
- Cria os índices ao final
- Registra a importação na tabela `importacao`

**Segmentos pré-definidos:**

| Segmento | Descrição | CNAEs |
|----------|-----------|-------|
| `farmacia` | Farmácias e drogarias | 4771701, 4771702, 4771703 |
| `restaurante` | Restaurantes e lanchonetes | 5611201, 5611203-05 |
| `oficina` | Oficinas mecânicas | 4520001-05 |
| `supermercado` | Supermercados e mercados | 4711301, 4711302 |
| `padaria` | Padarias e confeitarias | 1091102, 4721102 |
| `salao` | Salões de beleza e barbearias | 9602501, 9602502 |
| `clinica` | Clínicas médicas | 8630501-03 |

### 3. Validar

```powershell
docker compose --profile etl run --rm etl python validators.py
```

Verifica contagens por tabela, distribuição por situação, e faz uma busca de teste.

### 4. Atualização mensal

Baixe os novos ZIPs para `./downloads/YYYY-MM/` e rode:

```powershell
# Verifica se o mês em disco é mais novo que o banco e re-importa se necessário
docker compose --profile etl run --rm etl python update_monthly.py --segmento farmacia
```

Para apenas verificar sem importar:
```powershell
docker compose --profile etl run --rm etl python update_monthly.py --segmento farmacia --apenas-verificar
```

## Flags úteis

### importer.py
| Flag | Descrição |
|------|-----------|
| `--segmento farmacia` | Importa só farmácias (recomendado) |
| `--cnaes 4771701,...` | CNAEs customizados separados por vírgula |
| `--tudo` | Inclui estabelecimentos inativos |
| `--incluir-socios` | Inclui sócios (omitidos por padrão no modo filtrado) |
| `--tabela estabelecimento` | Re-importa apenas uma tabela |
| `--truncar` | Trunca as tabelas antes de importar |
| `--pular-indices` | Não cria índices ao final |
| `--downloads-dir /downloads/2026-04` | Pasta específica |

### update_monthly.py
| Flag | Descrição |
|------|-----------|
| `--segmento farmacia` | Segmento a importar |
| `--force` | Re-importa mesmo se o mês já estiver no banco |
| `--apenas-verificar` | Mostra o que seria importado sem executar |

## Fontes de dados

- **Portal:** https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj
- **Layout (PDF):** https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf

## Notas técnicas

- **Encoding:** arquivos da Receita são LATIN1 — convertidos para UTF-8 durante o import
- **Separador:** `;` com aspas `"` como quote character
- **Datas:** armazenadas como `VARCHAR(8)` no formato `YYYYMMDD`. Use `TO_DATE(campo, 'YYYYMMDD')` nas queries
- **Capital social:** usa `,` como separador decimal nos arquivos originais — convertido para `.` antes do COPY
- **COPY FROM STDIN:** 10–100x mais rápido que INSERT em massa
