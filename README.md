# Prospec Leads

Ferramenta pessoal de prospecção de leads usando a base pública de CNPJs da Receita Federal.

Permite filtrar empresas por **estado, cidade e CNAE** (segmento de atuação), retornando uma lista de potenciais clientes com nome, endereço, telefone, e-mail e demais dados cadastrais — tudo a partir de dados públicos oficiais, sem custos de API.

## Status do Projeto

🟡 **Etapa 2 — Importação da base da Receita Federal** (pronta para executar)

### Roadmap

- [x] **Etapa 1** — Setup do ambiente local (Docker + PostgreSQL + FastAPI base)
- [x] **Etapa 2** — Scripts ETL implementados (download + import + validação)
- [ ] **Etapa 3** — Backend completo (endpoints de busca, filtros, exportação)
- [ ] **Etapa 4** — Frontend (HTMX + Jinja2 + TailwindCSS + Leaflet)
- [ ] **Etapa 5** — Refinamento local e testes
- [ ] **Etapa 6** — Deploy em VPS Hostinger (produção)

## Stack

- **Backend:** Python 3.11 + FastAPI
- **Banco:** PostgreSQL 16
- **Frontend:** HTMX + Jinja2 + TailwindCSS + Leaflet (a partir da Etapa 4)
- **Container:** Docker + Docker Compose
- **Fonte de dados:** [Dados Abertos CNPJ - Receita Federal](https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj)

## Pré-requisitos

- **Docker Desktop** instalado e rodando ([download](https://www.docker.com/products/docker-desktop/))
- **Git** instalado
- **VS Code** com a extensão **Dev Containers** (recomendado)
- Mínimo **80GB de espaço livre em disco** (base completa do CNPJ)
- Mínimo **8GB de RAM** (16GB recomendado)
- **SSD** fortemente recomendado para a importação

### Configuração do Docker Desktop (Windows)

Antes de subir o projeto, ajuste em **Docker Desktop → Settings → Resources → Advanced**:

- **Memory:** 6GB (mínimo) — 8GB recomendado
- **CPUs:** 4 (mínimo)
- **Disk image size:** 100GB

## Como Rodar Localmente

```powershell
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/prospec-leads.git
cd prospec-leads

# 2. Crie o arquivo .env a partir do template
Copy-Item .env.example .env
# Abra o .env e ajuste as senhas (campos POSTGRES_PASSWORD e PGADMIN_PASSWORD)

# 3. Suba os containers (primeira vez baixa imagens, demora alguns minutos)
docker compose up -d --build

# 4. Verifique que tudo subiu
docker compose ps
```

Acesse:

- **API:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health
- **pgAdmin:** http://localhost:5050

### Comandos Úteis

```powershell
# Ver logs em tempo real
docker compose logs -f

# Ver logs de um serviço específico
docker compose logs -f app
docker compose logs -f postgres

# Parar tudo (preserva os dados)
docker compose down

# Parar e APAGAR dados (cuidado!)
docker compose down -v

# Reconstruir após mudanças no Dockerfile
docker compose up -d --build

# Acessar shell do container app
docker compose exec app bash

# Acessar psql diretamente
docker compose exec postgres psql -U prospec -d prospec_db
```

### Conectando o pgAdmin ao Postgres

1. Acesse http://localhost:5050 e faça login com as credenciais do `.env`
2. Clique direito em **Servers → Register → Server**
3. **General → Name:** `Prospec Local`
4. **Connection:**
   - **Host:** `postgres` (nome do container, NÃO `localhost`)
   - **Port:** `5432`
   - **Database:** `prospec_db`
   - **Username:** `prospec`
   - **Password:** valor do `.env`

## Estrutura do Projeto

```
prospec-leads/
├── docker-compose.yml      # Orquestração dos containers (+ serviço etl)
├── .env.example            # Template de variáveis (commitado)
├── .env                    # Variáveis reais (NÃO commitado)
├── .gitignore
├── README.md
├── SETUP.md                # Guia passo a passo para setup inicial
├── app/                    # Backend FastAPI
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── etl/                    # Scripts de importação da Receita Federal (Etapa 2)
│   ├── schema.sql          # DDL de todas as tabelas CNPJ
│   ├── download.py         # Baixa os ZIPs mais recentes
│   ├── importer.py         # Importa via COPY FROM STDIN
│   ├── update_monthly.py   # Atualização mensal automatizada
│   └── validators.py       # Queries de validação pós-importação
├── docs/                   # Documentação técnica
│   ├── ARCHITECTURE.md
│   ├── ETAPAS.md
│   └── CLAUDE.md           # Guia do projeto para o Claude Code
└── data/                   # Volumes persistidos (NÃO commitado)
    ├── postgres/
    └── pgadmin/
```

## Etapa 2 — Importar a Base da Receita Federal

Com os containers rodando, execute na ordem:

```powershell
# 1. Baixar os arquivos (~5 GB, pode levar 30-60 min dependendo da internet)
docker compose --profile etl run --rm etl python download.py

# 2. Importar para o PostgreSQL (~3-8h, recomendado deixar rodando à noite)
docker compose --profile etl run --rm etl python importer.py

# 3. Validar a importação
docker compose --profile etl run --rm etl python validators.py
```

Consulte [`etl/README.md`](etl/README.md) para todas as opções disponíveis.

## Documentação Adicional

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Decisões técnicas e arquitetura
- [`docs/ETAPAS.md`](docs/ETAPAS.md) — Detalhamento de cada etapa do roadmap
- [`docs/CLAUDE.md`](docs/CLAUDE.md) — Contexto e instruções para o Claude Code

## Validação da Etapa 1

A Etapa 1 está concluída quando:

- [x] `docker compose ps` mostra os 3 containers rodando
- [x] `http://localhost:8000/` retorna o JSON de status
- [x] `http://localhost:8000/health` retorna `"database": "connected"`
- [x] `http://localhost:5050` carrega o pgAdmin
- [x] pgAdmin consegue conectar ao Postgres usando o host `postgres`

## Licença

Uso pessoal. Os dados utilizados são públicos, fornecidos pela Receita Federal do Brasil.
