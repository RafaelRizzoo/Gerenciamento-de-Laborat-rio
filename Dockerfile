# =====================================================================
#  Gestão de Produtos Químicos - Tenaris
#  Imagem da aplicação (FastHTML + SQLAlchemy)
# =====================================================================
FROM python:3.12-slim

# Fuso e saída sem buffer (os prints aparecem na hora no `docker logs`)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Sao_Paulo \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---------------------------------------------------------------------
# Dependências
# ---------------------------------------------------------------------
# Por padrão o banco é SQLite e nada além do Python é necessário.
# Para usar SQL Server, construa com:  --build-arg SQLSERVER=1
ARG SQLSERVER=0

COPY requirements.txt .
RUN set -eux; \
    # o pyodbc só é instalado quando o SQL Server é pedido (precisa compilar)
    grep -v -i '^pyodbc' requirements.txt > /tmp/req-base.txt; \
    pip install --no-cache-dir -r /tmp/req-base.txt; \
    if [ "$SQLSERVER" = "1" ]; then \
        apt-get update; \
        apt-get install -y --no-install-recommends gcc g++ unixodbc-dev curl gnupg; \
        pip install --no-cache-dir pyodbc; \
        apt-get purge -y gcc g++; \
        apt-get autoremove -y; \
        rm -rf /var/lib/apt/lists/*; \
    fi

# ---------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------
COPY . .

# O banco SQLite e a chave de sessão ficam fora do código, num volume,
# para sobreviverem a atualizações da imagem.
ENV SQLITE_PATH=/dados/gestao_quimicos.db
RUN mkdir -p /dados

EXPOSE 5001

# Conferência simples de saúde do contêiner
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:5001/login').read()" || exit 1

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["python", "main.py"]
