# Arquitetura

## Visão Geral

```
┌──────────────────────────────────────────────────────────┐
│                    Navegador (cliente)                    │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP
                           ▼
┌──────────────────────────────────────────────────────────┐
│                                                           │
│  Container: app (FastAPI + Jinja2 + HTMX)                │
│                                                           │
│  ┌─────────────────┐  ┌──────────────────────────────┐   │
│  │   Routes API    │  │   Routes Frontend (HTML)     │   │
│  │  /api/buscar    │  │   /                          │   │
│  │  /api/cnaes     │  │   /resultados (HTMX partial) │   │
│  │  /api/exportar  │  │                              │   │
│  └────────┬────────┘  └──────────────┬───────────────┘   │
│           └──────────────┬───────────┘                    │
│                          ▼                                │
│            ┌───────────────────────┐                     │
│            │  SQLAlchemy + asyncpg  │                     │
│            └───────────┬────────────┘                     │
└────────────────────────┼─────────────────────────────────┘
                         │ TCP 5432
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Container: postgres                                       │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Tabelas (base CNPJ Receita Federal):                │ │
│  │    empresa, estabelecimento, socio, simples,         │ │
│  │    cnae, municipio, pais, natureza_juridica,         │ │
│  │    qualificacao_socio, motivo                        │ │
│  └─────────────────────────────────────────────────────┘ │
│  Volume persistido: ./data/postgres                       │
└──────────────────────────────────────────────────────────┘
                         ▲
                         │
┌──────────────────────────────────────────────────────────┐
│  Container: pgadmin (apenas em dev/local)                 │
│  http://localhost:5050                                    │
└──────────────────────────────────────────────────────────┘
```

## Por Que PostgreSQL e Não SQLite?

A base completa do CNPJ tem cerca de **22 milhões de estabelecimentos ativos** e **55 milhões de registros de empresas**. SQLite começa a ter problemas significativos de performance com volumes acima de 10 milhões de registros, especialmente em queries com múltiplos filtros e JOINs entre tabelas grandes.

PostgreSQL é projetado para esse volume, oferece índices avançados (GIN para busca textual, B-tree para igualdade), tem `COPY FROM` que é 10-100x mais rápido que INSERT em massa, e permite tunning fino de memória/cache (configurado no `docker-compose.yml`).

## Por Que HTMX e Não React/Next.js?

Para uso pessoal e MVP, HTMX entrega 95% da experiência de uma SPA com 5% da complexidade. Sem build step, sem npm, sem hidratação, sem estado do cliente para gerenciar. O servidor retorna HTML, HTMX troca pedaços da página. Resultado: deploy mais simples (apenas um container Python), debug trivial (você inspeciona HTML, não bundle JS), e código menos suscetível a bugs.

Se no futuro o projeto crescer e precisar de uma UI mais sofisticada (drag & drop, gráficos interativos, multi-step wizard), migrar para React é viável — a API REST do FastAPI já estará pronta.

## Por Que Docker Compose e Não Kubernetes?

Para um único usuário rodando localmente e uma VPS pequena, Kubernetes é overkill absoluto. Docker Compose resolve orquestração, networking entre containers, volumes persistidos e variáveis de ambiente com um arquivo YAML simples. Sobe e desce com um comando. Suficiente para dezenas de usuários simultâneos.

## Fluxo de Dados — Da Receita ao Lead

1. **Download mensal:** A Receita publica novos arquivos sempre no mesmo dia do mês (varia, mas geralmente entre dia 10 e 20). Um cron job no container roda `etl/update_monthly.py` no dia 25 de cada mês.

2. **Processamento:** Os arquivos vêm em formato CSV com encoding ISO-8859-1, separador `;`, e campos numéricos com vírgula como decimal. O ETL converte tudo para UTF-8 e o formato esperado pelo Postgres.

3. **Carga via COPY:** Em vez de gerar milhões de INSERTs, o script usa `COPY FROM STDIN` que é dezenas de vezes mais rápido. A importação completa do Brasil leva 3-8h em hardware mediano.

4. **Indexação:** Após a carga, cria índices em `(uf, municipio)`, `cnae_fiscal_principal`, `situacao_cadastral`. Isso é o que permite a query "todas as farmácias de Floriano-PI" responder em milissegundos.

5. **Consulta do usuário:** Usuário seleciona PI + Floriano + atalho "farmácias" no frontend. Backend monta query SQL com os filtros, executa contra o Postgres, retorna resultados paginados.

## Tabelas Principais — Layout Oficial Resumido

### `estabelecimento` (a tabela mais importante para nós)
Cada linha é um estabelecimento (matriz ou filial) com endereço, telefone, e-mail, CNAE.

Campos relevantes para busca:
- `cnpj_basico` (8 dígitos, FK para empresa)
- `cnpj_ordem` (4 dígitos, identifica filial)
- `cnpj_dv` (2 dígitos verificadores)
- `identificador_matriz_filial` (1=matriz, 2=filial)
- `nome_fantasia`
- `situacao_cadastral` (01=Nula, 02=Ativa, 03=Suspensa, 04=Inapta, 08=Baixada)
- `cnae_fiscal_principal` (7 dígitos)
- `cnae_fiscal_secundaria` (string com CNAEs separados por vírgula)
- `tipo_logradouro`, `logradouro`, `numero`, `complemento`, `bairro`, `cep`
- `uf`, `municipio` (código IBGE numérico)
- `ddd_1`, `telefone_1`, `ddd_2`, `telefone_2`, `correio_eletronico`

### `empresa`
Dados da matriz (razão social, capital social, porte).

Campos relevantes:
- `cnpj_basico` (PK)
- `razao_social`
- `natureza_juridica` (FK)
- `qualificacao_responsavel`
- `capital_social`
- `porte` (00=Não informado, 01=Micro, 03=Pequena, 05=Demais)

### `cnae`
Tabela de domínio com código + descrição do CNAE (~1.300 entradas).

### `municipio`
Tabela de domínio com código IBGE + nome do município.

## Performance Esperada

Com índices corretos e PostgreSQL bem configurado:

- Listar municípios de uma UF: **< 50ms**
- Autocomplete de CNAE: **< 100ms**
- Buscar farmácias de uma cidade: **< 500ms** (geralmente retorna dezenas a centenas de registros)
- Buscar todas as empresas de uma capital: **1-3s** (pode retornar milhares)

A importação inicial é a única operação cara. Depois, tudo é rápido.

## Backup e Recuperação

O volume `./data/postgres` é a única fonte de verdade. Estratégias:

- **Backup manual:** `docker compose exec postgres pg_dump -U prospec prospec_db | gzip > backup_$(date +%Y%m%d).sql.gz`
- **Restauração:** `gunzip < backup.sql.gz | docker compose exec -T postgres psql -U prospec -d prospec_db`
- **Em produção:** considerar pg_dump diário automatizado + envio para storage externo

Como a base é reconstruível a partir do download mensal da Receita, a perda de dados não é catastrófica — apenas demanda 3-8h de reimportação.

## Considerações de Segurança

- **Local (dev):** porta 5432 do Postgres exposta no host. Não é problema em rede doméstica, mas se você expor a máquina à internet, fechar essa porta no firewall.
- **Produção (VPS):** o `docker-compose.prod.yml` NÃO deve expor porta 5432. Apenas o serviço `app` se conecta ao Postgres pela rede interna do Docker.
- **Senhas:** sempre via `.env`, nunca hardcoded. Em produção, usar senhas longas e únicas.
- **HTTPS:** obrigatório em produção. Caddy faz isso automaticamente via Let's Encrypt.
