"""Modelo de dados do Sistema de Gestão de Produtos Químicos.

Escrito em SQLAlchemy 2.0 com tipos compatíveis tanto com SQLite
(desenvolvimento) quanto com SQL Server (produção).
"""

import calendar
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- Datas
def somar_meses(d: date, meses: int) -> date:
    """Soma meses a uma data respeitando o último dia do mês de destino."""
    total = d.month - 1 + meses
    ano = d.year + total // 12
    mes = total % 12 + 1
    dia = min(d.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


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
    "PENDENTE": "Pendente",
    "EM_ANALISE": "Em análise",
    "AGUARDANDO_CORRECAO": "Aguardando correção",
    "APROVADO": "Aprovado",
    "REPROVADO": "Reprovado",
    "DESCONTINUADO": "Descontinuado",
}

# Uma solicitação está "aberta" enquanto não foi aprovada nem reprovada.
#   PENDENTE            - criada, nenhuma etapa decidida ainda
#   EM_ANALISE          - ao menos uma etapa já registrou parecer
#   AGUARDANDO_CORRECAO - devolvida ao solicitante; retoma na etapa que pediu
STATUS_ABERTOS = ("PENDENTE", "EM_ANALISE", "AGUARDANDO_CORRECAO")

# Motivos de reprovação sugeridos no formulário (o parecer segue obrigatório).
MOTIVOS_REPROVACAO = [
    "FDS desatualizada",
    "Informações incompletas",
    "Produto não aprovado para uso",
    "Pendências regulatórias",
    "Documentação insuficiente",
    "Outro motivo (descrever no parecer)",
]

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

# ---------------------------------------------------------------------
# Módulo de consulta de FDS
# ---------------------------------------------------------------------

# Unidades / instalações onde um produto pode ser autorizado.
FABRICAS = [
    "Pinda Tubos",
    "MC SCON2",
    "MC TCHB",
    "COSE",
    "RDO",
]

# Tipo de produto: categoria principal usada no cadastro e no filtro de FDS.
TIPOS_PRODUTO = [
    "Lubrificante",
    "Hidráulico",
    "Emulsão",
    "Limpeza",
    "Solvente",
    "Outros",
]

# Área da planta responsável pela utilização do produto.
AREAS_SOLICITANTES = [
    "Produção",
    "Manutenção",
    "Laboratório",
    "Engenharia",
    "Qualidade",
    "HSE",
]

# Classes de risco (um produto pode acumular várias).
CLASSES_RISCO = [
    "Inflamável",
    "Corrosivo",
    "Tóxico",
    "Perigoso ao Meio Ambiente",
    "Comburente",
    "Irritante",
    "Nocivo",
    "Gás sob pressão",
]

# Órgãos que exercem controle legal sobre produtos químicos.
ORGAOS_CONTROLADORES = {
    "POLICIA_FEDERAL": "Polícia Federal",
    "POLICIA_CIVIL": "Polícia Civil",
    "EXERCITO": "Exército Brasileiro",
}

# Validade da FDS: contada a partir da data de revisão do documento.
FDS_VALIDADE_ANOS = 5
FDS_ALERTA_MESES = 6

SITUACOES_FDS = {
    "VIGENTE": "Vigente",
    "PROXIMA": "Próxima do vencimento",
    "VENCIDA": "Vencida",
    "SEM_FDS": "Sem FDS anexada",
}


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
    nome_tecnico: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    fabricante: Mapped[str] = mapped_column(Unicode(180), nullable=False)
    fornecedor: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    categoria: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    tipo_produto: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    numero_cas: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    composicao: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    estado_fisico: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)

    # Uso na planta
    setor_solicitante: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    area_solicitante: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    prazo_utilizacao: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    aplicacao: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    processo: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    consumo_estimado: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    unidade: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    local_armazenamento: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)

    # Segurança / meio ambiente
    classificacao_ghs: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    onu_numero: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    epi_recomendado: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    restricoes_uso: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
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
    # O que o aprovador pediu para corrigir (limpo quando o solicitante reenvia).
    pendencia: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)

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
    fabricas: Mapped[list["ProdutoFabrica"]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="ProdutoFabrica.fabrica",
        lazy="selectin",
    )
    controles: Mapped[list["ControleOrgao"]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="ControleOrgao.orgao",
        lazy="selectin",
    )
    riscos: Mapped[list["ProdutoRisco"]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="ProdutoRisco.classe",
        lazy="selectin",
    )

    @property
    def status_label(self) -> str:
        return STATUS.get(self.status, self.status)

    @property
    def etapa_label(self) -> str | None:
        return dict(FLUXO_APROVACAO).get(self.etapa_atual) if self.etapa_atual else None

    @property
    def aberta(self) -> bool:
        return self.status in STATUS_ABERTOS

    @property
    def aguardando_correcao(self) -> bool:
        return self.status == "AGUARDANDO_CORRECAO"

    @property
    def dias_em_aberto(self) -> int | None:
        if not self.aberta or not self.criado_em:
            return None
        return (datetime.now() - self.criado_em).days

    # ------------------------------------------------------------ Fábricas
    @property
    def fabricas_nomes(self) -> list[str]:
        return [f.fabrica for f in self.fabricas]

    @property
    def riscos_nomes(self) -> list[str]:
        return [r.classe for r in self.riscos]

    # ------------------------------------------------- Controle regulatório
    @property
    def controlado(self) -> bool:
        """Derivado: é controlado quando há ao menos um órgão vinculado."""
        return bool(self.controles)

    @property
    def orgaos_nomes(self) -> list[str]:
        return [c.orgao_label for c in self.controles]

    @property
    def licenca_vencida(self) -> bool:
        return any(c.vencida for c in self.controles)

    # ------------------------------------------------------------- FDS
    @property
    def fds_versoes(self) -> list["Documento"]:
        """Todas as FDS do produto, da mais recente para a mais antiga."""
        docs = [d for d in self.documentos if d.tipo == "FDS"]
        return sorted(
            docs,
            key=lambda d: (d.versao or 0, d.enviado_em or datetime.min),
            reverse=True,
        )

    @property
    def fds(self) -> "Documento | None":
        """A FDS vigente: a versão mais recente anexada."""
        versoes = self.fds_versoes
        return versoes[0] if versoes else None

    @property
    def fds_vencimento(self) -> date | None:
        doc = self.fds
        return doc.vencimento if doc else None

    @property
    def fds_dias_restantes(self) -> int | None:
        venc = self.fds_vencimento
        return (venc - date.today()).days if venc else None

    @property
    def fds_situacao(self) -> str:
        """VIGENTE | PROXIMA | VENCIDA | SEM_FDS"""
        venc = self.fds_vencimento
        if venc is None:
            return "SEM_FDS"
        hoje = date.today()
        if venc < hoje:
            return "VENCIDA"
        if venc <= somar_meses(hoje, FDS_ALERTA_MESES):
            return "PROXIMA"
        return "VIGENTE"

    @property
    def fds_situacao_label(self) -> str:
        return SITUACOES_FDS.get(self.fds_situacao, self.fds_situacao)

    @property
    def progresso(self) -> tuple[int, int]:
        """(etapas decididas, total de etapas)."""
        total = len(self.aprovacoes) or len(FLUXO_APROVACAO)
        feitas = sum(1 for a in self.aprovacoes if a.decisao != "PENDENTE")
        return feitas, total


class ProdutoFabrica(Base):
    """Unidade / instalação em que o produto está autorizado.

    Um produto pode estar liberado em várias fábricas ao mesmo tempo.
    """

    __tablename__ = "produto_fabricas"
    __table_args__ = (
        UniqueConstraint("produto_id", "fabrica", name="uq_produto_fabrica"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    fabrica: Mapped[str] = mapped_column(Unicode(60), nullable=False)

    produto: Mapped["Produto"] = relationship(back_populates="fabricas")


class ProdutoRisco(Base):
    """Classe de risco do produto (inflamável, corrosivo, tóxico...).

    É lista porque a FDS normalmente traz mais de uma para o mesmo produto.
    """

    __tablename__ = "produto_riscos"
    __table_args__ = (
        UniqueConstraint("produto_id", "classe", name="uq_produto_risco"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    classe: Mapped[str] = mapped_column(Unicode(60), nullable=False)

    produto: Mapped["Produto"] = relationship(back_populates="riscos")


class ControleOrgao(Base):
    """Vínculo do produto com um órgão que exerce controle legal sobre ele.

    O mesmo produto pode responder a mais de um órgão (por exemplo, Polícia
    Federal e Exército), cada um com a sua própria licença e validade.
    """

    __tablename__ = "controles_orgao"
    __table_args__ = (
        UniqueConstraint("produto_id", "orgao", name="uq_produto_orgao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    orgao: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    numero_licenca: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    validade_licenca: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacao: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)

    produto: Mapped["Produto"] = relationship(back_populates="controles")

    @property
    def orgao_label(self) -> str:
        return ORGAOS_CONTROLADORES.get(self.orgao, self.orgao)

    @property
    def vencida(self) -> bool:
        return bool(self.validade_licenca and self.validade_licenca < date.today())

    @property
    def dias_restantes(self) -> int | None:
        if not self.validade_licenca:
            return None
        return (self.validade_licenca - date.today()).days


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
    data_revisao: Mapped[date | None] = mapped_column(Date, nullable=True)
    enviado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    enviado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    produto: Mapped["Produto"] = relationship(back_populates="documentos")

    @property
    def tipo_label(self) -> str:
        return TIPOS_DOCUMENTO.get(self.tipo, self.tipo)

    @property
    def data_base(self) -> date:
        """Data que conta para a validade: a revisão informada ou, na falta
        dela, a data em que o arquivo foi anexado."""
        if self.data_revisao:
            return self.data_revisao
        return self.enviado_em.date() if self.enviado_em else date.today()

    @property
    def vencimento(self) -> date:
        return somar_meses(self.data_base, FDS_VALIDADE_ANOS * 12)

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
    status_anterior: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    status_novo: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def status_anterior_label(self) -> str | None:
        return STATUS.get(self.status_anterior, self.status_anterior)

    @property
    def status_novo_label(self) -> str | None:
        return STATUS.get(self.status_novo, self.status_novo)

    @property
    def e_observacao(self) -> bool:
        return self.acao == "OBSERVACAO"

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
