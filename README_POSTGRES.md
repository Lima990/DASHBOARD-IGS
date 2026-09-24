# Migração para PostgreSQL

## 1. Criar o banco

Crie um banco PostgreSQL local ou hospedado. Para desenvolvimento, use uma URL neste formato:

```text
postgresql+psycopg://usuario:senha@localhost:5432/igs_bahia
```

## 2. Instalar as dependências

```powershell
py -m pip install -r requirements.txt
```

## 3. Fazer a carga inicial do Excel

O Excel é usado somente nesta etapa para migrar os dados. O dashboard não lê mais o arquivo.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:senha@localhost:5432/igs_bahia"
py importar_excel_postgres.py base_de_dados_IGs.xlsx
```

O script cria as tabelas `estudos_igs`, `igs_concedidas` e `carga_dados`. A carga é idempotente: limpa as duas tabelas operacionais e recarrega a versão atual da planilha.

## 4. Executar o dashboard

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:senha@localhost:5432/igs_bahia"
streamlit run app_mapa_bahia.py
```

No Streamlit Community Cloud, configure `DATABASE_URL` em **Settings > Secrets**:

```toml
DATABASE_URL = "postgresql+psycopg://usuario:senha@host:5432/igs_bahia?sslmode=require"
```

## Atualizações futuras

Quando a base mudar, execute novamente o importador com o Excel atualizado. O histórico da carga fica registrado em `carga_dados`.

Para produção, o próximo passo recomendado é substituir a carga destrutiva por uma rotina de `upsert` usando uma chave estável de origem e executar a migração por CI/CD ou tarefa agendada.
