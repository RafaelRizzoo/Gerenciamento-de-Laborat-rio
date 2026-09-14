"""Configuracao central da aplicacao (lida do arquivo .env)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Carrega o .env sem depender de biblioteca externa (fallback simples).
try:  # pragma: no cover
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:  # pragma: no cover
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for linha in env_file.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


def _bool(nome: str, padrão: bool = False) -> bool:
    return os.getenv(nome, "1" if padrão else "0").strip().lower() in ("1", "true", "yes", "sim")


# ----------------------------------------------------------------- Banco
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").strip().lower()
SQLITE_PATH = os.getenv("SQLITE_PATH", "gestao_quimicos.db")

MSSQL_HOST = os.getenv("MSSQL_HOST", "localhost")
MSSQL_PORT = os.getenv("MSSQL_PORT", "1433")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "GestaoQuimicos")
MSSQL_USER = os.getenv("MSSQL_USER", "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "")
MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 17 for SQL Server")
MSSQL_TRUSTED = _bool("MSSQL_TRUSTED", False)


def database_url() -> str:
    """Monta a URL de conexao. Trocar de SQLite para SQL Server e' so mudar o .env."""
    if DB_ENGINE == "mssql":
        from urllib.parse import quote_plus

        driver = quote_plus(MSSQL_DRIVER)
        if MSSQL_TRUSTED:
            return (
                f"mssql+pyodbc://@{MSSQL_HOST}:{MSSQL_PORT}/{MSSQL_DATABASE}"
                f"?driver={driver}&trusted_connection=yes"
            )
        senha = quote_plus(MSSQL_PASSWORD)
        return (
            f"mssql+pyodbc://{MSSQL_USER}:{senha}@{MSSQL_HOST}:{MSSQL_PORT}/"
            f"{MSSQL_DATABASE}?driver={driver}"
        )
    caminho = Path(SQLITE_PATH)
    if not caminho.is_absolute():
        caminho = BASE_DIR / caminho
    return f"sqlite:///{caminho}"


# ------------------------------------------------------------- Segurança
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-trocar")

# ------------------------------------------------------------------ SMTP
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_TLS = _bool("SMTP_TLS", True)
SMTP_FROM = os.getenv("SMTP_FROM", "gestao.quimicos@tenaris.com")
SMTP_ATIVO = bool(SMTP_HOST)

# ---------------------------------------------------------------- Upload
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20") or 20)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# --------------------------------------------------------- Lembretes
# Cobrança automática das solicitações paradas: o main.py verifica ao
# subir e a cada 12 horas. Desligue com LEMBRETES_ATIVOS=0 se preferir
# usar o Agendador de Tarefas do Windows chamando lembretes.py.
LEMBRETES_ATIVOS = _bool("LEMBRETES_ATIVOS", True)
LEMBRETE_DIAS = int(os.getenv("LEMBRETE_DIAS", "7") or 7)

APP_NOME = "Gestão de Produtos Químicos"
APP_EMPRESA = "Tenaris"
