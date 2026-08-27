"""Modelo de dados do Sistema de Gestão de Produtos Químicos.

Escrito em SQLAlchemy 2.0 com tipos compatíveis tanto com SQLite
(desenvolvimento) quanto com SQL Server (produção).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Unicode,
    UnicodeText,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# =====================================================================
# Domínios (listas fixas usadas pelo sistema)
# =====================================================================

PAPEIS = {
    "SOLICITANTE": "Solicitante",
    "MEIO_AMBIENTE": "Meio Ambiente",
    "SAUDE_SEGURANCA": "Saúde e Segurança",
    "QUIMICO_RESPONSAVEL": "Químico Responsável",
    "APROVADOR_FINAL": "Aprovador Final",
    "ADMIN": "Administrador",
}

# Ordem oficial do fluxo de aprovacao
FLUXO_APROVACAO = [
    ("MEIO_AMBIENTE", "Meio Ambiente"),
    ("SAUDE_SEGURANCA", "Saúde e Segurança"),
    ("QUIMICO_RESPONSAVEL", "Químico Responsável"),
    ("APROVADOR_FINAL", "Aprovador Final"),
]

STATUS = {
    "RASCUNHO": "Rascunho",
    "EM_ANALISE": "Em análise",
    "APROVADO": "Aprovado",
    "REPROVADO": "Reprovado",
    "DESCONTINUADO": "Descontinuado",
}

CATEGORIAS = [
    "Ácido",
    "Base / Álcali",
    "Solvente",
    "Tinta / Revestimento",
    "Óleo / Lubrificante",
    "Gás",
    "Detergente / Limpeza",
    "Reagente de laboratório",
    "Aditivo de processo",
    "Outros",
]

TIPOS_DOCUMENTO = {
    "FDS": "FDS - Ficha de Dados de Segurança",
    "FICHA_EMERGENCIA": "Ficha de Emergência",
    "LAUDO": "Laudo / Análise",
    "CERTIFICADO": "Certificado / Licença",
    "OUTRO": "Outro documento",
}

# Documentos obrigatórios para submeter uma solicitacao
DOCUMENTOS_OBRIGATORIOS = ["FDS"]

ESTADOS_FISICOS = ["Sólido", "Líquido", "Gás", "Pasta / Gel", "Aerossol"]


# =====================================================================
# Tabelas
# =====================================================================


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    email: Mapped[str] = mapped_column(Unicode(180), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    papel: Mapped[str] = mapped_column(Unicode(40), nullable=False, default="SOLICITANTE")
    setor: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def papel_label(self) -> str:
        return PAPEIS.get(self.papel, self.papel)

    @property
    def iniciais(self) -> str:
        partes = [p for p in self.nome.split() if p]
        if not partes:
            return "?"
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[-1][0]).upper()


class Produto(Base):
    """Uma solicitacao de cadastro de produto químico (e o produto em si)."""

    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo_interno: Mapped[str] = mapped_column(Unicode(40), nullable=False, unique=True)

    # Identificação
    nome_comercial: Mapped[str] = mapped_column(Unicode(180), nullable=False)
    fabricante: Mapped[str] = mapped_column(Unicode(180), nullable=False)
    fornecedor: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    categoria: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    numero_cas: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    composicao: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    estado_fisico: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)

    # Uso na planta
    setor_solicitante: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    aplicacao: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    consumo_estimado: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    unidade: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    local_armazenamento: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)

    # Segurança / meio ambiente
    classificacao_ghs: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    onu_numero: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    epi_recomendado: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)

    # Controle
    status: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="EM_ANALISE")
    etapa_atual: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_encerramento: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)

    solicitante: Mapped["Usuario"] = relationship(lazy="joined")
    aprovacoes: Mapped[list["Aprovacao"]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="Aprovacao.ordem",
        lazy="selectin",
    )
    documentos: Mapped[list["Documento"]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="Documento.id",
        lazy="selectin",
    )

    @property
    def status_label(self) -> str:
        return STATUS.get(self.status, self.status)

    @property
    def etapa_label(self) -> str | None:
        return dict(FLUXO_APROVACAO).get(self.etapa_atual) if self.etapa_atual else None

    @property
    def fds(self) -> "Documento | None":
        for doc in self.documentos:
            if doc.tipo == "FDS":
                return doc
        return None

    @property
    def progresso(self) -> tuple[int, int]:
        """(etapas decididas, total de etapas)."""
        total = len(self.aprovacoes) or len(FLUXO_APROVACAO)
        feitas = sum(1 for a in self.aprovacoes if a.decisao != "PENDENTE")
        return feitas, total


class Aprovacao(Base):
    """Uma etapa do fluxo de aprovacao de um produto."""

    __tablename__ = "aprovacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    etapa: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    decisao: Mapped[str] = mapped_column(Unicode(20), nullable=False, default="PENDENTE")
    parecer: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    aprovador_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    produto: Mapped["Produto"] = relationship(back_populates="aprovacoes")
    aprovador: Mapped["Usuario | None"] = relationship(lazy="joined")

    @property
    def etapa_label(self) -> str:
        return dict(FLUXO_APROVACAO).get(self.etapa, self.etapa)


class Documento(Base):
    """Arquivo anexado ao produto. O conteudo fica no próprio banco."""

    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="OUTRO")
    nome_arquivo: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    tamanho: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enviado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    enviado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    produto: Mapped["Produto"] = relationship(back_populates="documentos")

    @property
    def tipo_label(self) -> str:
        return TIPOS_DOCUMENTO.get(self.tipo, self.tipo)

    @property
    def tamanho_legivel(self) -> str:
        tam = float(self.tamanho or 0)
        for unidade in ("B", "KB", "MB", "GB"):
            if tam < 1024 or unidade == "GB":
                return f"{tam:.0f} {unidade}" if unidade == "B" else f"{tam:.1f} {unidade}"
            tam /= 1024
        return f"{tam:.1f} GB"


class LogAuditoria(Base):
    """Rastreabilidade: toda alteracao relevante gera um registro aqui."""

    __tablename__ = "log_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int | None] = mapped_column(ForeignKey("produtos.id"), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    acao: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    detalhe: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    usuario: Mapped["Usuario | None"] = relationship(lazy="joined")
    produto: Mapped["Produto | None"] = relationship(lazy="joined")


class Notificacao(Base):
    """Caixa de saída de e-mails: registro de tudo que o sistema notificou."""

    __tablename__ = "notificacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int | None] = mapped_column(ForeignKey("produtos.id"), nullable=True)
    destinatario: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    assunto: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    corpo: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    enviado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    erro: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    produto: Mapped["Produto | None"] = relationship(lazy="joined")
