"""Popula SOMENTE os kits ambientais de exemplo.

Como o seed_recursos.py, este script não apaga nada: cria as tabelas que
faltarem e insere os kits, itens e pontos de coleta de exemplo,
preservando produtos, usuários, aprovações e a biblioteca.

Uso:
    python seed_kits.py            # só insere se não houver nenhum kit
    python seed_kits.py --forcar   # insere mesmo que já existam kits
"""

import sys

from sqlalchemy import func, select

from database import criar_tabelas, db_session
from models import KitAmbiental, Usuario
from seed import popular_kits


def executar(forcar: bool = False) -> None:
    criar_tabelas()
    with db_session() as s:
        existentes = s.scalar(select(func.count(KitAmbiental.id))) or 0
        if existentes and not forcar:
            print(
                f"Já existem {existentes} kit(s) cadastrados. Nada foi alterado. "
                "Use --forcar para inserir os exemplos assim mesmo."
            )
            return

        usuarios = {}
        for usuario in s.scalars(select(Usuario).where(Usuario.ativo.is_(True))):
            usuarios.setdefault(usuario.papel, usuario)
        if not usuarios:
            print("Nenhum usuário cadastrado. Rode antes: python seed.py")
            return

        popular_kits(s, usuarios)
        print("Pronto. Abra http://127.0.0.1:5001/kit-ambiental para conferir.")


if __name__ == "__main__":
    executar("--forcar" in sys.argv)
