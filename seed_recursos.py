"""Popula SOMENTE a biblioteca de Recursos e Documentos.

Diferente do seed.py, este script não apaga nada: ele apenas cria as tabelas
novas (se ainda não existirem) e insere os itens de exemplo da biblioteca,
preservando os produtos, usuários e aprovações já cadastrados.

Uso:
    python seed_recursos.py            # só insere se a biblioteca estiver vazia
    python seed_recursos.py --forcar   # insere mesmo que já existam itens
"""

import sys

from sqlalchemy import func, select

from database import criar_tabelas, db_session
from models import Recurso, Usuario
from seed import popular_biblioteca


def executar(forcar: bool = False) -> None:
    criar_tabelas()
    with db_session() as s:
        existentes = s.scalar(select(func.count(Recurso.id))) or 0
        if existentes and not forcar:
            print(
                f"A biblioteca já tem {existentes} item(ns). "
                "Nada foi alterado. Use --forcar para inserir os exemplos assim mesmo."
            )
            return

        usuarios = {}
        for usuario in s.scalars(select(Usuario).where(Usuario.ativo.is_(True))):
            usuarios.setdefault(usuario.papel, usuario)
        if not usuarios:
            print("Nenhum usuário cadastrado. Rode antes: python seed.py")
            return

        # Se algum papel não existir na base, usa o primeiro usuário encontrado.
        reserva = next(iter(usuarios.values()))
        for papel in ("SAUDE", "SEGURANCA", "MEIO_AMBIENTE", "QUIMICO_RESPONSAVEL"):
            usuarios.setdefault(papel, reserva)

        popular_biblioteca(s, usuarios)
        print("Pronto. Abra http://127.0.0.1:5001/recursos para conferir.")


if __name__ == "__main__":
    executar("--forcar" in sys.argv)
