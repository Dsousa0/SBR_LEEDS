# SBR Leads

Ferramenta interna de prospecção de leads B2B usando a base pública de CNPJs da Receita Federal, com integração ao Pedido Mobile para cruzar prospectos com a carteira atual de clientes.

## Funcionalidades

- **Busca filtrada** por estado, município, porte e status de cliente (com scroll automático para os resultados)
- **Listagem paginada** com razão social, endereço, telefone, e-mail, porte e capital social
- **Modal de detalhes** — clique em qualquer linha para ver todas as informações do estabelecimento
- **Mapa interativo** (Leaflet) com clustering de marcadores, tooltip no hover e alternância entre OSM e satélite ESRI
- **Geocodificação** por endereço completo via Photon + fallback por CEP via AwesomeAPI, com validação de cidade para evitar marcadores errados
- **Exportação** em CSV e XLSX
- **Integração Pedido Mobile** — sincroniza clientes e datas de última compra; leads já clientes aparecem com badge laranja e dias sem comprar
- **Autenticação** — JWT via cookie HTTPOnly, dois papéis (admin / usuário), troca obrigatória de senha no primeiro acesso
- **Painel de administração** — criação, ativação/desativação e reset de senha de usuários

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11 + FastAPI 0.115 |
| Banco | PostgreSQL 16 |
| Frontend | HTMX 1.9 + Jinja2 + TailwindCSS CDN |
| Mapa | Leaflet 1.9 + Leaflet.markercluster |
| Autenticação | python-jose + passlib/bcrypt |
| Exportação | openpyxl |
| Container | Docker + Docker Compose |
| Proxy (produção) | Caddy |
| Fonte de dados | [CNPJ Aberto — Receita Federal](https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj) |

## Pré-requisitos

- **Docker Desktop** rodando ([download](https://www.docker.com/products/docker-desktop/))
- **Git**
- Mínimo **80 GB de espaço livre** (base completa do CNPJ)
- Mínimo **8 GB de RAM** (16 GB recomendado)
- **SSD** recomendado para a importação

### Configuração do Docker Desktop (Windows)

**Settings → Resources → Advanced:**

- Memory: 6 GB (mínimo) — 8 GB recomendado
- CPUs: 4+
- Disk image size: 100 GB+

## Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/Dsousa0/SBR_LEADS.git
cd SBR_LEADS

# 2. Crie o .env
cp .env.example .env
# Edite o .env e preencha as senhas e credenciais

# 3. Suba os containers
docker compose up -d --build

# 4. Verifique
docker compose ps
```

Acesse **http://localhost:8000** e faça login com:

- **E-mail:** `admin@sbr.local`
- **Senha:** `admin123`

> O admin padrão é criado automaticamente na primeira inicialização. Troque a senha em `/admin/usuarios` imediatamente.

## Variáveis de Ambiente

Copie `.env.example` para `.env` e preencha:

| Variável | Descrição |
|---|---|
| `APP_ENV` | `development` ou `production` |
| `SECRET_KEY` | Chave JWT — gere com `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_USER` | Usuário do banco |
| `POSTGRES_PASSWORD` | Senha do banco |
| `POSTGRES_DB` | Nome do banco |
| `PGADMIN_EMAIL` | Login do pgAdmin |
| `PGADMIN_PASSWORD` | Senha do pgAdmin |
| `PEDIDO_MOBILE_BASE_URL` | URL base da API do Pedido Mobile |
| `PEDIDO_MOBILE_USER` | Usuário da API do Pedido Mobile |
| `PEDIDO_MOBILE_PASSWORD` | Senha da API do Pedido Mobile |

## Importando a Base da Receita Federal

Com os containers rodando, execute na ordem:

```bash
# 1. Baixar os arquivos (~5 GB, 30–60 min)
docker compose --profile etl run --rm etl python download.py

# 2. Importar para o PostgreSQL (~3–8h, recomendado deixar à noite)
docker compose --profile etl run --rm etl python importer.py

# 3. Validar
docker compose --profile etl run --rm etl python validators.py
```

Consulte [`etl/README.md`](etl/README.md) para opções detalhadas.

## Integração Pedido Mobile

A sincronização busca dois endpoints da API:

- `/clienteintegracao/versao` — carteira de clientes (versionamento incremental)
- `/pedidointegracao/versao` — pedidos para calcular a data da última compra

Clique em **Sincronizar** no card do painel inicial. A sincronização é incremental — apenas registros alterados desde o último sync são processados.

## Comandos Úteis

```bash
# Logs em tempo real
docker compose logs -f app

# Parar (preserva dados)
docker compose down

# Parar e apagar volumes (cuidado!)
docker compose down -v

# Reconstruir após mudanças no Dockerfile
docker compose up -d --build

# Shell do container
docker compose exec app bash

# psql direto
docker compose exec postgres psql -U prospec -d prospec_db
```

## Estrutura do Projeto

```
SBR_LEADS/
├── docker-compose.yml          # Ambiente local
├── docker-compose.prod.yml     # Ambiente de produção (Caddy)
├── Caddyfile                   # Configuração do proxy reverso
├── .env.example                # Template de variáveis (commitado)
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # Startup, bootstrap do banco, exception handlers
│   ├── auth.py                 # JWT, require_login, require_admin
│   ├── config.py               # Settings via pydantic-settings
│   ├── database.py             # Engine e sessão SQLAlchemy
│   ├── schemas.py              # Modelos Pydantic
│   ├── service.py              # Queries, build_where, buscar, buscar_para_mapa
│   ├── pedido_mobile.py        # Sync com API externa (clientes + pedidos)
│   ├── routers/
│   │   ├── frontend.py         # Rotas HTML (HTMX)
│   │   ├── api.py              # Rotas REST (CSV/XLSX)
│   │   ├── admin.py            # Gestão de usuários
│   │   └── auth_router.py      # Login, logout, troca de senha
│   └── templates/
│       ├── base.html
│       ├── index.html          # Página principal com filtros sticky
│       ├── login.html
│       ├── trocar_senha.html
│       ├── admin/
│       └── partials/
│           ├── resultados.html # Tabela + mapa + modal + geocodificação
│           ├── pedido_mobile_card.html
│           ├── municipios_options.html
│           └── cnaes_options.html
├── etl/
│   ├── schema.sql              # DDL completo das tabelas CNPJ
│   ├── download.py             # Baixa ZIPs da Receita Federal
│   ├── importer.py             # Importa via COPY FROM STDIN
│   ├── update_monthly.py       # Atualização mensal
│   ├── validators.py           # Validação pós-importação
│   └── sync_pedido_mobile.py   # Sync avulso do Pedido Mobile
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ETAPAS.md
│   └── CLAUDE.md
└── data/                       # Volumes persistidos (não commitado)
```

## Endpoints Principais

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Página principal |
| `POST` | `/buscar` | Busca com filtros (HTMX) |
| `POST` | `/exportar.csv` | Exporta resultados em CSV |
| `POST` | `/exportar.xlsx` | Exporta resultados em XLSX |
| `POST` | `/sync-clientes` | Sincroniza Pedido Mobile (HTMX) |
| `GET` | `/admin/usuarios` | Gestão de usuários (admin) |
| `GET` | `/health` | Health check do banco |
| `GET` | `/login` | Tela de login |
| `GET` | `/logout` | Encerrar sessão |

## Licença

Uso interno. Os dados utilizados são públicos, fornecidos pela Receita Federal do Brasil via [Dados Abertos](https://dados.gov.br).
