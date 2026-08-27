"""Conexao com o banco de dados e helpers de sessao."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from models import Base

_url = config.database_url()
_kwargs = {"echo": False, "future": True}
if _url.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}
else:
    _kwargs["pool_pre_ping"] = True
    _kwargs["fast_executemany"] = True

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def criar_tabelas() -> None:
    """Cria as tabelas que ainda não existem."""
    Base.metadata.create_all(engine)


@contextmanager
def db_session():
    """Sessao transacional: commit no sucesso, rollback no erro."""
    sessao = SessionLocal()
    try:
        yield sessao
        sessao.commit()
    except Exception:
        sessao.rollback()
        raise
    finally:
        sessao.close()


def descricao_conexao() -> str:
    if config.DB_ENGINE == "mssql":
        return f"SQL Server - {config.MSSQL_HOST}/{config.MSSQL_DATABASE}"
    return f"SQLite - {config.SQLITE_PATH}"
