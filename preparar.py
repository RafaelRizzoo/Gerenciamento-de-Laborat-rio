"""Prepara o banco antes de subir a aplicação.

Roda sempre na mesma ordem e é seguro repetir:

1. cria/atualiza as tabelas e converte dados de versões anteriores;
2. se o banco estiver vazio, carrega os dados de exemplo (seed).

Usado pelo `iniciar.bat` (instalação sem Docker) e pelo
`docker-entrypoint.sh` (instalação com Docker).
"""

from sqlalchemy import func, select


def main() -> int:
    try:
        import migrar_fluxo

        migrar_fluxo.executar()
    except Exception as exc:  # pragma: no cover
        print(f"  (migração pulada: {exc})")

    from database import db_session
    from models import Usuario

    with db_session() as s:
        total = s.scalar(select(func.count(Usuario.id))) or 0

    if total == 0:
        print("Banco vazio: carregando os dados de exemplo.")
        import seed

        seed.executar()
    else:
        print(f"Banco já tem {total} usuário(s) - dados de exemplo não recarregados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
