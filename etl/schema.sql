-- =============================================================
-- Schema da base CNPJ da Receita Federal
-- Baseado no layout oficial:
--   https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf
--
-- NOTAS:
--   Datas: VARCHAR(8) no formato YYYYMMDD (ex: 20230101).
--          '00000000' = não preenchida. Use TO_DATE(campo, 'YYYYMMDD') ao consultar.
--   Capital social: NUMERIC após conversão de ',' para '.' feita pelo importer.
--   Sem FKs nem NOT NULL: qualidade dos dados da Receita não garante integridade.
-- =============================================================

BEGIN;

-- -------------------------------------------------------
-- Tabelas de referência (pequenas — importar primeiro)
-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS pais (
    codigo  VARCHAR(3)  PRIMARY KEY,
    descricao VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS municipio (
    codigo    VARCHAR(4)  PRIMARY KEY,
    descricao VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS natureza_juridica (
    codigo    VARCHAR(4)  PRIMARY KEY,
    descricao VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS qualificacao_socio (
    codigo    VARCHAR(2)  PRIMARY KEY,
    descricao VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS motivo (
    codigo    VARCHAR(2)  PRIMARY KEY,
    descricao VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS cnae (
    codigo    VARCHAR(7)  PRIMARY KEY,
    descricao VARCHAR(200)
);

-- -------------------------------------------------------
-- Controle de importações
-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS importacao (
    id              SERIAL PRIMARY KEY,
    mes_referencia  VARCHAR(7),
    iniciada_em     TIMESTAMP DEFAULT NOW(),
    concluida_em    TIMESTAMP,
    status          VARCHAR(20) DEFAULT 'em_andamento',
    apenas_ativos   BOOLEAN DEFAULT TRUE,
    observacoes     TEXT
);

-- -------------------------------------------------------
-- Tabelas principais
-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS empresa (
    cnpj_basico                 VARCHAR(8)  PRIMARY KEY,
    razao_social                VARCHAR(200),
    natureza_juridica           VARCHAR(4),
    qualificacao_responsavel    VARCHAR(2),
    capital_social              NUMERIC(20,2),
    porte                       VARCHAR(2),  -- 00=N/Inf, 01=MEI, 03=ME, 05=EPP, 99=Demais
    ente_federativo_responsavel VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS estabelecimento (
    cnpj_basico                 VARCHAR(8),
    cnpj_ordem                  VARCHAR(4),
    cnpj_dv                     VARCHAR(2),
    identificador_matriz_filial VARCHAR(1),  -- 1=Matriz, 2=Filial
    nome_fantasia               VARCHAR(200),
    situacao_cadastral          VARCHAR(2),  -- 01=Nula, 02=Ativa, 03=Suspensa, 04=Inapta, 08=Baixada
    data_situacao_cadastral     VARCHAR(8),
    motivo_situacao_cadastral   VARCHAR(2),
    nome_cidade_exterior        VARCHAR(55),
    pais                        VARCHAR(3),
    data_inicio_atividade       VARCHAR(8),
    cnae_fiscal_principal       VARCHAR(7),
    cnae_fiscal_secundaria      TEXT,
    tipo_logradouro             VARCHAR(20),
    logradouro                  VARCHAR(60),
    numero                      VARCHAR(6),
    complemento                 VARCHAR(156),
    bairro                      VARCHAR(50),
    cep                         VARCHAR(8),
    uf                          VARCHAR(2),
    municipio                   VARCHAR(4),
    ddd_1                       VARCHAR(4),
    telefone_1                  VARCHAR(8),
    ddd_2                       VARCHAR(4),
    telefone_2                  VARCHAR(8),
    ddd_fax                     VARCHAR(4),
    fax                         VARCHAR(8),
    correio_eletronico          VARCHAR(115),
    situacao_especial           VARCHAR(29),
    data_situacao_especial      VARCHAR(8),
    PRIMARY KEY (cnpj_basico, cnpj_ordem, cnpj_dv)
);

CREATE TABLE IF NOT EXISTS socio (
    cnpj_basico                         VARCHAR(8),
    identificador_socio                 VARCHAR(1),  -- 1=PJ, 2=PF, 3=Estrangeiro
    nome_socio                          VARCHAR(200),
    cnpj_cpf_socio                      VARCHAR(14),
    qualificacao_socio                  VARCHAR(2),
    data_entrada_sociedade              VARCHAR(8),
    pais                                VARCHAR(3),
    representante_legal                 VARCHAR(11),
    nome_representante                  VARCHAR(60),
    qualificacao_representante_legal    VARCHAR(2),
    faixa_etaria                        VARCHAR(1)
);

CREATE TABLE IF NOT EXISTS simples (
    cnpj_basico         VARCHAR(8) PRIMARY KEY,
    opcao_simples       VARCHAR(1),
    data_opcao_simples  VARCHAR(8),
    data_exclusao_simples VARCHAR(8),
    opcao_mei           VARCHAR(1),
    data_opcao_mei      VARCHAR(8),
    data_exclusao_mei   VARCHAR(8)
);

-- -------------------------------------------------------
-- Integração Pedido Mobile (clientes ativos dos vendedores)
-- -------------------------------------------------------

CREATE TABLE IF NOT EXISTS cliente_pedido_mobile (
    documento     VARCHAR(14) PRIMARY KEY,  -- CNPJ ou CPF, somente dígitos
    tipo_documento VARCHAR(4),
    razao_social  VARCHAR(200),
    nome_fantasia VARCHAR(200),
    vendedor      VARCHAR(100),
    inativo       BOOLEAN DEFAULT FALSE,
    municipio     VARCHAR(100),
    uf            VARCHAR(2),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pedido_mobile_sync (
    id              SERIAL PRIMARY KEY,
    iniciada_em     TIMESTAMP DEFAULT NOW(),
    concluida_em    TIMESTAMP,
    ultima_versao   BIGINT NOT NULL DEFAULT 0,
    total_clientes  INTEGER,
    novos           INTEGER,
    atualizados     INTEGER,
    paginas         INTEGER,
    erro            TEXT
);

COMMIT;

-- =============================================================
-- Índices — executar APÓS a importação completa.
-- Criar antes torna a importação 3-5x mais lenta.
-- O importer.py os cria automaticamente ao final.
--
-- Para criar manualmente:
--   docker compose exec postgres psql -U prospec -d prospec_db -f /etl/schema.sql
-- =============================================================

-- CREATE INDEX IF NOT EXISTS idx_estab_uf_municipio   ON estabelecimento(uf, municipio);
-- CREATE INDEX IF NOT EXISTS idx_estab_cnae_principal ON estabelecimento(cnae_fiscal_principal);
-- CREATE INDEX IF NOT EXISTS idx_estab_situacao       ON estabelecimento(situacao_cadastral);
-- CREATE INDEX IF NOT EXISTS idx_estab_cnpj_basico    ON estabelecimento(cnpj_basico);
-- CREATE INDEX IF NOT EXISTS idx_empresa_cnpj_basico  ON empresa(cnpj_basico);
-- CREATE INDEX IF NOT EXISTS idx_cnae_gin             ON cnae USING gin(to_tsvector('portuguese', descricao));
