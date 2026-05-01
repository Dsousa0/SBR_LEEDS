# Guia de Setup — Passo a Passo

Este guia leva você do zero até o sistema rodando localmente. Siga na ordem.

## Parte 1 — Pré-requisitos no Windows

### 1.1 — Instalar o Docker Desktop

1. Baixe em https://www.docker.com/products/docker-desktop/
2. Execute o instalador (mantenha a opção "Use WSL 2" marcada)
3. Reinicie o Windows quando solicitado
4. Após reiniciar, abra o Docker Desktop e aguarde inicializar

### 1.2 — Configurar Recursos do Docker

No Docker Desktop, abra **Settings (engrenagem) → Resources → Advanced**:

| Recurso | Valor mínimo | Recomendado |
|---------|--------------|-------------|
| Memory | 6 GB | 8 GB |
| CPUs | 4 | 6 |
| Disk image size | 100 GB | 150 GB |

Clique em **Apply & restart**.

### 1.3 — Instalar o Git

Baixe em https://git-scm.com/download/win e instale com as opções padrão.

Verifique no PowerShell:
```powershell
git --version
```

### 1.4 — Instalar o VS Code

Baixe em https://code.visualstudio.com/ e instale.

### 1.5 — Validar instalação

Abra o PowerShell e rode:
```powershell
docker --version
docker compose version
git --version
```

Se todos retornam versões, está pronto.

## Parte 2 — Criar Repositório no GitHub

### 2.1 — Criar conta (se ainda não tem)

Acesse https://github.com e crie uma conta.

### 2.2 — Criar o repositório

1. Clique em **New repository** (botão verde no topo direito)
2. **Repository name:** `prospec-leads`
3. **Description:** `Ferramenta de prospecção de leads via base CNPJ da Receita Federal`
4. **Visibility:** Private (recomendado para projeto pessoal) ou Public
5. **Não marque nada** em "Add a README", "Add .gitignore" ou "Choose a license" — vamos enviar nosso próprio
6. Clique **Create repository**

### 2.3 — Configurar SSH (recomendado)

Para evitar digitar senha toda vez:

```powershell
# Gerar chave SSH (se não tiver)
ssh-keygen -t ed25519 -C "[email protected]"

# Copiar a chave pública
Get-Content ~/.ssh/id_ed25519.pub | clip
```

Vá em https://github.com/settings/keys → **New SSH key** → cole a chave → **Add SSH key**

## Parte 3 — Configurar o Projeto Local

### 3.1 — Extrair o ZIP

Extraia o arquivo `prospec-leads.zip` em `C:\dev\prospec-leads` (ou outro local de sua preferência, em SSD).

### 3.2 — Abrir no VS Code

```powershell
cd C:\dev\prospec-leads
code .
```

O VS Code vai sugerir instalar extensões recomendadas (Python, Docker, Claude Code, etc.). Aceite todas.

### 3.3 — Criar arquivo .env

No terminal integrado do VS Code (`Ctrl+'`):
```powershell
Copy-Item .env.example .env
```

Abra o `.env` e altere os valores das senhas:
```
POSTGRES_PASSWORD=defina_uma_senha_aqui
PGADMIN_PASSWORD=defina_outra_senha_aqui
```

### 3.4 — Inicializar Git e enviar para o GitHub

```powershell
# Inicializar repositório local
git init
git branch -M main

# Adicionar o remote (use a URL SSH do seu repositório)
git remote add origin [email protected]:SEU_USUARIO/prospec-leads.git

# Configurar usuário (se ainda não fez globalmente)
git config user.name "Seu Nome"
git config user.email "[email protected]"

# Primeiro commit
git add .
git status   # confira que .env NÃO aparece (correto, está no .gitignore)
git commit -m "feat: setup inicial do projeto (Etapa 1)"

# Enviar para o GitHub
git push -u origin main
```

Verifique no navegador que os arquivos apareceram no GitHub.

## Parte 4 — Subir o Ambiente Docker

### 4.1 — Build e start

No terminal do VS Code:
```powershell
docker compose up -d --build
```

A primeira vez baixa as imagens do Postgres, Python e pgAdmin (~500MB), demora alguns minutos.

### 4.2 — Conferir status

```powershell
docker compose ps
```

Você deve ver os 3 containers com status `running` ou `healthy`:
- `prospec_postgres`
- `prospec_app`
- `prospec_pgadmin`

### 4.3 — Testar

Abra no navegador:

| URL | O que esperar |
|-----|---------------|
| http://localhost:8000 | JSON com `"status": "running"` |
| http://localhost:8000/health | JSON com `"database": "connected"` |
| http://localhost:8000/docs | Swagger UI da API |
| http://localhost:5050 | Tela de login do pgAdmin |

### 4.4 — Configurar pgAdmin (uma única vez)

1. Acesse http://localhost:5050
2. Login com `PGADMIN_EMAIL` e `PGADMIN_PASSWORD` do `.env`
3. Clique direito em **Servers → Register → Server**
4. Aba **General:** Name = `Prospec Local`
5. Aba **Connection:**
   - Host name/address: `postgres` ⚠️ (nome do container, não `localhost`)
   - Port: `5432`
   - Maintenance database: `prospec_db`
   - Username: `prospec`
   - Password: o valor de `POSTGRES_PASSWORD` do `.env`
   - ☑ Save password
6. Clique **Save**

Você deve ver o banco `prospec_db` na árvore lateral. Ainda não tem tabelas — isso vem na Etapa 2.

## Parte 5 — Validar Conclusão da Etapa 1

✅ Docker Desktop rodando
✅ 3 containers rodando (`docker compose ps`)
✅ http://localhost:8000/health retorna `database: connected`
✅ pgAdmin conectado ao Postgres
✅ Repositório no GitHub com primeiro push

**Se todos os itens acima estão OK, a Etapa 1 está concluída! 🎉**

## Parte 6 — Próximo Passo: Etapa 2

Para iniciar a Etapa 2 (importação da base da Receita), use o Claude Code dentro do VS Code:

1. Abra o painel do Claude Code (atalho da extensão)
2. Digite uma instrução como:
   > "Vamos iniciar a Etapa 2 do projeto. Leia o CLAUDE.md e me mostre o plano detalhado de implementação dos scripts de ETL."

O Claude Code vai ler o `CLAUDE.md`, entender o contexto e te guiar pela implementação.

## Comandos Úteis (para guardar)

```powershell
# Subir tudo
docker compose up -d

# Subir e reconstruir após mudanças no Dockerfile
docker compose up -d --build

# Parar (preserva dados)
docker compose down

# Parar e APAGAR todos os dados (cuidado!)
docker compose down -v

# Ver logs em tempo real
docker compose logs -f

# Ver logs só do app
docker compose logs -f app

# Acessar shell do app
docker compose exec app bash

# Acessar psql do banco
docker compose exec postgres psql -U prospec -d prospec_db

# Ver uso de recursos
docker stats
```

## Resolução de Problemas Comuns

### "docker: command not found"
Docker Desktop não está rodando ou não foi instalado. Abra o Docker Desktop.

### "port is already allocated"
Algum outro programa está usando a porta 8000, 5432 ou 5050. Pare esse programa ou mude a porta no `docker-compose.yml`.

### "/health retorna database: disconnected"
O Postgres ainda está iniciando. Aguarde 30 segundos e tente de novo. Se persistir, veja logs:
```powershell
docker compose logs postgres
```

### pgAdmin não conecta
Confira que está usando `postgres` como host (nome do container), não `localhost`. Confira que a senha bate com o `.env`.

### "WSL 2 installation is incomplete"
Execute no PowerShell como administrador:
```powershell
wsl --update
wsl --set-default-version 2
```
