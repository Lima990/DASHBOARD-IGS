CREATE TABLE IF NOT EXISTS estudos_igs (
    id BIGSERIAL PRIMARY KEY,
    origem_id TEXT,
    nome_produto TEXT NOT NULL,
    territorio_identidade TEXT,
    municipios_abrangidos TEXT,
    tipo_produto TEXT,
    modalidade_ig TEXT,
    singularidade TEXT,
    tradicao_historica TEXT,
    vinculo_territorial TEXT,
    viabilidade_economica TEXT,
    atores_chave TEXT,
    geometria_espacial TEXT,
    fonte_dados TEXT,
    titulo_trabalho TEXT,
    link TEXT,
    ano INTEGER,
    referencia_abnt TEXT,
    status_diagnostico TEXT,
    string_busca TEXT,
    fonte_busca TEXT,
    estudo_key TEXT,
    chave_agrupamento TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_estudos_nome_produto
    ON estudos_igs (nome_produto);
CREATE INDEX IF NOT EXISTS idx_estudos_chave_agrupamento
    ON estudos_igs (chave_agrupamento);
CREATE INDEX IF NOT EXISTS idx_estudos_estudo_key
    ON estudos_igs (estudo_key);

CREATE TABLE IF NOT EXISTS igs_concedidas (
    id BIGSERIAL PRIMARY KEY,
    nome_produto TEXT NOT NULL,
    territorio_identidade TEXT,
    municipios_abrangidos TEXT,
    tipo_produto TEXT,
    modalidade_ig TEXT,
    status_diagnostico TEXT,
    geometria_espacial TEXT,
    ano INTEGER,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_igs_concedidas_nome_produto
    ON igs_concedidas (nome_produto);

CREATE TABLE IF NOT EXISTS carga_dados (
    id BIGSERIAL PRIMARY KEY,
    arquivo_origem TEXT NOT NULL,
    carregado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    linhas_estudos INTEGER NOT NULL,
    linhas_igs_concedidas INTEGER NOT NULL
);
