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


# ---------------------------------------------------------------------
# Migração leve de colunas
# ---------------------------------------------------------------------
# `create_all` cria tabelas novas, mas não adiciona colunas em tabelas que
# já existem. Como o banco de desenvolvimento (e depois o de produção) já
# tem dados, comparamos o modelo com o banco e emitimos os ALTER TABLE que
# faltam. Só adiciona coluna - nunca remove nem altera tipo.


def _tipo_sql(coluna, dialeto: str) -> str:
    return coluna.type.compile(dialect=engine.dialect)


# Colunas renomeadas: (tabela, coluna_nova, coluna_antiga). Depois de criar a
# coluna nova, o valor da antiga e' copiado uma unica vez. A coluna antiga fica
# no banco (nao removemos nada automaticamente), apenas deixa de ser usada.
_RENOMEADAS = [
    ("produtos", "tipo_produto", "tipo_oleo"),
]


def _copiar_renomeadas(inspetor) -> None:
    from sqlalchemy import text

    for tabela, nova, antiga in _RENOMEADAS:
        colunas = {c["name"] for c in inspetor.get_columns(tabela)}
        if nova not in colunas or antiga not in colunas:
            continue
        with engine.begin() as conexao:
            copiadas = conexao.execute(
                text(
                    f"UPDATE {tabela} SET {nova} = {antiga} "
                    f"WHERE {nova} IS NULL AND {antiga} IS NOT NULL"
                )
            ).rowcount
        if copiadas:
            print(f"  {tabela}.{antiga} -> {nova}: {copiadas} registro(s) copiados.")


def _migrar_colunas() -> None:
    from sqlalchemy import inspect, text

    inspetor = inspect(engine)
    tabelas_no_banco = set(inspetor.get_table_names())
    dialeto = engine.dialect.name
    palavra = "ADD COLUMN" if dialeto == "sqlite" else "ADD"

    novas: list[str] = []
    for tabela in Base.metadata.sorted_tables:
        if tabela.name not in tabelas_no_banco:
            continue  # tabela nova: o create_all ja cuidou
        existentes = {c["name"] for c in inspetor.get_columns(tabela.name)}
        for coluna in tabela.columns:
            if coluna.name in existentes:
                continue
            if not coluna.nullable and coluna.default is None:
                # Nao da para adicionar coluna obrigatoria sem default numa
                # tabela que ja tem linhas; avisa em vez de quebrar.
                print(
                    f"  ! coluna {tabela.name}.{coluna.name} e' obrigatoria e "
                    f"precisa ser criada manualmente."
                )
                continue
            ddl = (
                f"ALTER TABLE {tabela.name} {palavra} "
                f"{coluna.name} {_tipo_sql(coluna, dialeto)}"
            )
            with engine.begin() as conexao:
                conexao.execute(text(ddl))
            novas.append(f"{tabela.name}.{coluna.name}")

    if novas:
        print(f"  Banco atualizado - colunas adicionadas: {', '.join(novas)}")
    _copiar_renomeadas(inspect(engine))


def criar_tabelas() -> None:
    """Cria as tabelas que ainda não existem e completa as colunas que faltam."""
    Base.metadata.create_all(engine)
    try:
        _migrar_colunas()
    except Exception as exc:  # pragma: no cover
        print(f"  ! Nao foi possivel migrar colunas automaticamente: {exc}")


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
