#!/bin/sh
# =====================================================================
#  Preparação do banco antes de subir a aplicação.
#  Tudo aqui é seguro de repetir: roda a cada start do contêiner.
# =====================================================================
set -e

echo "== Gestão de Produtos Químicos - preparando o banco =="

# 1) cria/atualiza as tabelas e converte dados de versões anteriores
python migrar_fluxo.py || echo "  (migração pulada)"

# 2) na primeira execução (banco vazio), carrega os dados de exemplo
python - <<'PY'
from sqlalchemy import func, select

from database import db_session
from models import Usuario

with db_session() as s:
    total = s.scalar(select(func.count(Usuario.id))) or 0

if total == 0:
    print("Banco vazio: carregando dados de exemplo (seed).")
    import seed
    seed.executar()
else:
    print(f"Banco já tem {total} usuário(s) - seed não foi executado.")
PY

echo "== Iniciando a aplicação em http://localhost:5001 =="
exec "$@"
