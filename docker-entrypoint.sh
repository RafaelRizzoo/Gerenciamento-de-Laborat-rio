#!/bin/sh
# =====================================================================
#  Preparação do banco antes de subir a aplicação.
#  Tudo aqui é seguro de repetir: roda a cada start do contêiner.
# =====================================================================
set -e

echo "== Gestão de Produtos Químicos - preparando o banco =="

# Cria/atualiza as tabelas, converte dados de versões anteriores e, se o
# banco estiver vazio, carrega os dados de exemplo. O mesmo script é usado
# pelo iniciar.bat (instalação sem Docker).
python preparar.py

echo "== Iniciando a aplicação em http://localhost:5001 =="
exec "$@"
