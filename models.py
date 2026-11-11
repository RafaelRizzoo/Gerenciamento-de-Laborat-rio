"""Modelo de dados do Sistema de Gestão de Produtos Químicos.

Escrito em SQLAlchemy 2.0 com tipos compatíveis tanto com SQLite
(desenvolvimento) quanto com SQL Server (produção).
"""

import calendar
import unicodedata
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
    "SAUDE": "Saúde",
    "SEGURANCA": "Segurança",
    "QUIMICO_RESPONSAVEL": "Químico Responsável",
    "APROVADOR_FINAL": "Aprovador Final",
    "ADMIN": "Administrador",
}

# ---------------------------------------------------------------------
# Fluxo de aprovação
# ---------------------------------------------------------------------
# NÃO existe ordem entre as áreas: Meio Ambiente, Saúde, Segurança e
# Químico Responsável recebem a solicitação ao mesmo tempo e analisam na
# ordem que quiserem. O Aprovador Final é o único passo fixo: só é
# acionado quando as quatro áreas tiverem concluído.

AREAS_APROVACAO = [
    ("MEIO_AMBIENTE", "Meio Ambiente"),
    ("SAUDE", "Saúde"),
    ("SEGURANCA", "Segurança"),
    ("QUIMICO_RESPONSAVEL", "Químico Responsável"),
]

ETAPA_FINAL = "APROVADOR_FINAL"

# Lista completa (áreas + etapa final). Serve para rótulos e consultas.
FLUXO_APROVACAO = AREAS_APROVACAO + [(ETAPA_FINAL, "Aprovador Final")]

# Papéis que participam de alguma etapa de aprovação.
PAPEIS_APROVADORES = [chave for chave, _ in FLUXO_APROVACAO]

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

ESTADOS_FISICOS = ["Sólido", "Líquido", "Gás"]

# Respostas objetivas: no formulário aparecem como lista suspensa, para
# ninguém digitar "sim", "SIM", "s" ou "afirmativo".
SIM_NAO = {"SIM": "Sim", "NAO": "Não"}

# Por quanto tempo o produto será usado na planta.
PRAZOS_UTILIZACAO = [
    "Uso Único",
    "Até 6 Meses",
    "Até 1 Ano",
    "Até 2 Anos",
    "Acima de 2 Anos",
    "Uso Contínuo",
]

# Unidade da quantidade prevista de consumo.
UNIDADES_CONSUMO = [
    "L/mês", "mL/mês", "kg/mês", "g/mês", "t/mês",
    "L/ano", "kg/ano", "un/mês", "un/ano",
]

# ---------------------------------------------------------------------
# Módulo de consulta de FDS
# ---------------------------------------------------------------------

# Unidades físicas da Tenaris onde um produto pode ser autorizado.
#
# Antes esta lista se chamava FABRICAS e misturava unidade com área: "COSE"
# e "MC SCON2" são áreas, não unidades. A conversão dos cadastros antigos
# está em migrar_fluxo.py.
#
# As colunas do banco continuam se chamando `fabrica` - renomear coluna em
# SQLite dá trabalho e não muda nada para quem usa. O que a pessoa lê na
# tela é "Unidade".
UNIDADES = [
    "Pinda",
    "MC",
    "RDO",
]

# Tipo de produto: categoria principal usada no cadastro e no filtro de FDS.
TIPOS_PRODUTO = [
    "Óleo Lubrificante",
    "Óleo Hidráulico",
    "Emulsão",
    "Limpeza",
    "Solvente",
    "Outros",
]

# Área da planta responsável pela utilização do produto, dentro de cada
# unidade. "Qualidade" e "SUCH" existem em mais de uma unidade, por isso a
# área sozinha não identifica o lugar: o par unidade + área é que vale.
AREAS_POR_UNIDADE: dict[str, list[str]] = {
    "Pinda": [
        "Fábrica 4",
        "Manutenção F4",
        "Rev 6 - Externo",
        "Rev 10 - Interno",
        "Rev Concreto",
        "Rev 4",
        "Rev PPS",
        "Manutenção Rev",
        "MAOG - SCON",
        "MAOG - RCON",
        "MAOG - F1 - ERW",
        "MAOG - F6",
        "COSE",
        "COSE 4º Processo",
        "Manutenção MAOG",
        "SUCH",
        "Manutenção - Almoxarifado",
        "Manutenção - Oficina",
        "Manutenção - Oficina de veículos",
        "Manutenção - ETE",
        "Qualidade",
        "Restaurante e Limpeza",
    ],
    "MC": [
        "SCON 2",
        "Qualidade",
        "TCHB",
        "SUCH",
    ],
    "RDO": [
        "Rio das Ostras",
    ],
}

# Lista achatada, sem repetição, para validar e para filtrar.
AREAS_SOLICITANTES = list(
    dict.fromkeys(a for areas in AREAS_POR_UNIDADE.values() for a in areas)
)


def areas_da_unidade(unidade: str | None) -> list[str]:
    """Áreas válidas de uma unidade. Unidade desconhecida devolve lista vazia."""
    return list(AREAS_POR_UNIDADE.get(unidade or "", []))


def par_valido(unidade: str | None, area: str | None) -> bool:
    """A área pertence mesmo a essa unidade?"""
    return bool(area) and area in AREAS_POR_UNIDADE.get(unidade or "", [])


# ---------------------------------------------------------------------
# Técnico de Segurança responsável por cada área
# ---------------------------------------------------------------------
# A solicitação vai para UM técnico de Segurança, definido pelo par
# unidade + área. Os outros técnicos não a veem. Áreas sem responsável
# fixo (hoje só Rio das Ostras) deixam o solicitante escolher na lista.
#
# Esta tabela é o único lugar onde a regra mora: para trocar um técnico de
# área, basta alterar o nome aqui.

TECNICOS_SEGURANCA = [
    "Paulo Rocha",
    "Paulo Oliveira",
    "Manoel Messias",
    "Rafael Luz",
    "Claudio Santos",
    "Cesar Ranna",
    "Maicon Lima",
    "Antonio Santos",
    "Priscila Jele",
]

TECNICO_POR_AREA: dict[tuple[str, str], str | None] = {
    ("Pinda", "Fábrica 4"): "Rafael Luz",
    ("Pinda", "Manutenção F4"): "Rafael Luz",
    ("Pinda", "Rev 6 - Externo"): "Claudio Santos",
    ("Pinda", "Rev 10 - Interno"): "Claudio Santos",
    ("Pinda", "Rev Concreto"): "Claudio Santos",
    ("Pinda", "Rev 4"): "Claudio Santos",
    ("Pinda", "Rev PPS"): "Claudio Santos",
    ("Pinda", "Manutenção Rev"): "Claudio Santos",
    ("Pinda", "MAOG - SCON"): "Manoel Messias",
    ("Pinda", "MAOG - RCON"): "Manoel Messias",
    ("Pinda", "MAOG - F1 - ERW"): "Manoel Messias",
    ("Pinda", "MAOG - F6"): "Manoel Messias",
    ("Pinda", "COSE"): "Cesar Ranna",
    ("Pinda", "COSE 4º Processo"): "Cesar Ranna",
    ("Pinda", "Manutenção MAOG"): "Paulo Rocha",
    ("Pinda", "SUCH"): "Cesar Ranna",
    ("Pinda", "Manutenção - Almoxarifado"): "Paulo Oliveira",
    ("Pinda", "Manutenção - Oficina"): "Paulo Rocha",
    ("Pinda", "Manutenção - Oficina de veículos"): "Paulo Rocha",
    ("Pinda", "Manutenção - ETE"): "Paulo Rocha",
    ("Pinda", "Qualidade"): "Paulo Oliveira",
    ("Pinda", "Restaurante e Limpeza"): "Paulo Oliveira",
    ("MC", "SCON 2"): "Priscila Jele",
    ("MC", "Qualidade"): "Priscila Jele",
    ("MC", "TCHB"): "Priscila Jele",
    ("MC", "SUCH"): "Priscila Jele",
    # Sem responsável fixo: o solicitante escolhe na lista de técnicos.
    ("RDO", "Rio das Ostras"): None,
}


def tecnico_da_area(unidade: str | None, area: str | None) -> str | None:
    """Nome do técnico de Segurança da área, ou None se a escolha é manual."""
    return TECNICO_POR_AREA.get((unidade or "", area or ""))


def unidade_da_area(unidades: list[str], area: str | None) -> str | None:
    """Primeira das unidades em que a área existe (para dados antigos)."""
    return next((u for u in unidades if par_valido(u, area)), None)


# E-mails corporativos reais dos técnicos de Segurança.
EMAIL_TECNICO = {
    "Paulo Rocha": "phrocha@tenaris.com",
    "Paulo Oliveira": "poliveira@tenaris.com",
    "Manoel Messias": "mmsilva@tenaris.com",
    "Rafael Luz": "rcluz@tenaris.com",
    "Claudio Santos": "cfbcfs@tenaris.com",
    "Cesar Ranna": "ceranna@tenaris.com",
    "Maicon Lima": "mdlima@tenaris.com",
    "Antonio Santos": "amdossantos@tenaris.com",
    "Priscila Jele": "pdjele@tenaris.com",
}


def email_do_tecnico(nome: str) -> str:
    """E-mail corporativo do técnico (se não estiver na lista, nome.sobrenome)."""
    if nome in EMAIL_TECNICO:
        return EMAIL_TECNICO[nome]
    return email_provisorio_tecnico(nome)


def email_provisorio_tecnico(nome: str) -> str:
    """Padrão nome.sobrenome@tenaris.com (sem acento), usado antes dos e-mails reais."""
    import unicodedata

    texto = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return ".".join(texto.lower().split()) + "@tenaris.com"

# Classes de risco (um produto pode acumular várias).
# Como o produto é aplicado na planta. Padronizado para dar para filtrar
# depois ("me mostre tudo o que é aplicado por pulverização").
FORMAS_APLICACAO = [
    "Aplicação Manual (Pano, Pincel ou Rolo)",
    "Pulverização / Spray",
    "Imersão",
    "Dosagem Automática",
    "Circulação em Sistema Fechado",
    "Mistura ou Diluição em Tanque",
    "Aplicação por Terceiros",
    "Transferência entre Recipientes",
    "Limpeza e Higienização",
    "Outros",
]

# EPIs que o aprovador de Segurança marca no parecer, conforme a seção 8 da
# FDS. Para incluir ou tirar um item, basta editar esta lista.
EPIS = [
    "Óculos de segurança",
    "Protetor facial",
    "Luva de segurança química",
    "Luva de raspa / vaqueta",
    "Respirador semifacial com filtro químico",
    "Respirador facial inteiro",
    "Máscara PFF2",
    "Avental de PVC",
    "Avental de raspa",
    "Macacão / vestimenta de proteção",
    "Bota de segurança impermeável",
    "Protetor auricular",
    "Creme de proteção para as mãos",
]

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

# O filtro da tela não oferece "Sem FDS anexada": anexar a FDS é o passo 1 do
# cadastro, então nenhuma solicitação nova chega sem ela. O estado continua
# existindo para rotular registros antigos.
# Na tela de FDS os três estados usam os mesmos nomes dos cartões do topo
# (Produtos Aprovados / Pendentes / Reprovados), no filtro e na bolinha.
SITUACOES_FDS_TELA = {
    "VIGENTE": "Produtos Aprovados",
    "PROXIMA": "Produtos Pendentes",
    "VENCIDA": "Produtos Reprovados",
    "SEM_FDS": "Sem FDS anexada",
}

SITUACOES_FDS_FILTRO = {
    chave: rotulo for chave, rotulo in SITUACOES_FDS_TELA.items() if chave != "SEM_FDS"
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
    # Quem entra com senha provisória é obrigado a trocar no primeiro acesso.
    precisa_trocar_senha: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=False
    )
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
    # Por que a planta precisa deste produto (pergunta pedida pela Tenaris).
    forma_aplicacao: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    necessidade_uso: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    motivo_desenvolvimento: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    # Exposição dos colaboradores - usado por Saúde e Segurança na análise.
    funcionarios_expostos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funcoes_expostas: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    # Quem pediu, quando a solicitação vem de empresa terceira. O gestor é
    # a pessoa da Tenaris que responde pelo contrato dessa empresa.
    solicitante_terceiro: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    terceiro_nome: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    terceiro_empresa: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    gestor_contrato: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    gestor_email: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    processo: Mapped[str | None] = mapped_column(Unicode(180), nullable=True)
    consumo_estimado: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    unidade: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    # Onde o produto será usado (unidade da planta) e quem, na Segurança, é
    # responsável por essa área. `seguranca_primeiro` (nome histórico) marca
    # as solicitações com técnico definido na abertura. Não cria ordem: todas
    # as áreas analisam ao mesmo tempo, só o Aprovador Final espera.
    unidade_solicitante: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    tecnico_seguranca_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    seguranca_primeiro: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=False
    )
    local_armazenamento: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)

    # Segurança / meio ambiente
    classificacao_ghs: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    inflamavel: Mapped[str | None] = mapped_column(Unicode(10), nullable=True)
    cancerigeno: Mapped[str | None] = mapped_column(Unicode(10), nullable=True)
    ponto_fulgor: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
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
    # Última vez que o sistema cobrou os aprovadores pendentes por e-mail.
    ultimo_lembrete_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    solicitante: Mapped["Usuario"] = relationship(
        lazy="joined", foreign_keys="Produto.solicitante_id"
    )
    tecnico_seguranca: Mapped["Usuario | None"] = relationship(
        lazy="joined", foreign_keys="Produto.tecnico_seguranca_id"
    )
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
    epis: Mapped[list["ProdutoEPI"]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="ProdutoEPI.id",
        lazy="selectin",
    )
    cas: Mapped[list["ProdutoCAS"]] = relationship(
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="ProdutoCAS.id",
        lazy="selectin",
    )

    @property
    def cas_numeros(self) -> list[str]:
        """Todos os números CAS do produto, na ordem em que foram informados.

        A FDS costuma trazer um CAS por substância da composição, então um
        produto tem vários. O campo antigo `numero_cas`, de um valor só,
        continua gravado e serve de reserva para cadastros que ainda não
        passaram pela conversão.
        """
        lista = [c.numero for c in self.cas if c.numero]
        if not lista and self.numero_cas:
            return [self.numero_cas]
        return lista

    @property
    def cas_label(self) -> str:
        return ", ".join(self.cas_numeros) or ""

    @property
    def status_label(self) -> str:
        return STATUS.get(self.status, self.status)

    @property
    def inflamavel_label(self) -> str | None:
        return SIM_NAO.get(self.inflamavel) if self.inflamavel else None

    @property
    def cancerigeno_label(self) -> str | None:
        return SIM_NAO.get(self.cancerigeno) if self.cancerigeno else None

    @property
    def expostos_label(self) -> str | None:
        if self.funcionarios_expostos is None:
            return None
        return f"{self.funcionarios_expostos} colaborador(es)"

    @property
    def etapa_label(self) -> str | None:
        """Texto curto de quem a solicitação está esperando."""
        if not self.aberta:
            return None
        pendentes = self.areas_pendentes
        if not pendentes:
            return None
        if pendentes == [ETAPA_FINAL]:
            return "Aprovador Final"
        nomes = [dict(FLUXO_APROVACAO).get(e, e) for e in pendentes if e != ETAPA_FINAL]
        if len(nomes) == 1:
            return nomes[0]
        return f"{len(nomes)} áreas"

    @property
    def areas_pendentes(self) -> list[str]:
        """Etapas que ainda não registraram parecer."""
        return [a.etapa for a in self.aprovacoes if a.decisao == "PENDENTE"]

    @property
    def areas_pendentes_labels(self) -> list[str]:
        return [dict(FLUXO_APROVACAO).get(e, e) for e in self.areas_pendentes]

    @property
    def aguardando_labels(self) -> list[str]:
        """Quem a solicitação espera agora, com o nome do técnico na Segurança."""
        rotulos = dict(FLUXO_APROVACAO)
        saida = []
        for etapa in self.areas_pendentes:
            if not self.aguarda(etapa):
                continue
            rotulo = rotulos.get(etapa, etapa)
            if etapa == "SEGURANCA" and self.tecnico_seguranca:
                rotulo = f"{rotulo} ({self.tecnico_seguranca.nome})"
            saida.append(rotulo)
        return saida

    @property
    def areas_concluidas(self) -> bool:
        """Todas as áreas (menos o Aprovador Final) já decidiram?"""
        return not [e for e in self.areas_pendentes if e != ETAPA_FINAL]

    def aguarda(self, area: str) -> bool:
        """A solicitação depende do parecer desta área AGORA?

        As quatro áreas analisam em paralelo, cada uma independe das outras.
        O Aprovador Final só entra quando todas tiverem concluído.
        """
        if self.status not in STATUS_ABERTOS:
            return False
        pendentes = self.areas_pendentes
        if area == ETAPA_FINAL:
            return ETAPA_FINAL in pendentes and self.areas_concluidas
        if area not in pendentes:
            return False
        return True

    def aguarda_usuario(self, area: str, usuario_id: int | None) -> bool:
        """Como `aguarda`, mas a etapa de Segurança só vale para o técnico
        escolhido para esta solicitação (quando há um)."""
        if not self.aguarda(area):
            return False
        if (
            area == "SEGURANCA"
            and self.tecnico_seguranca_id
            and self.tecnico_seguranca_id != usuario_id
        ):
            return False
        return True

    @property
    def unidade_da_solicitacao(self) -> str | None:
        """Unidade em que o produto será usado (cadastros antigos: a primeira
        unidade em que a área existe)."""
        if self.unidade_solicitante:
            return self.unidade_solicitante
        return unidade_da_area(self.fabricas_nomes, self.area_solicitante)

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

    @property
    def epis_nomes(self) -> list[str]:
        """EPIs que a área de Segurança marcou como obrigatórios."""
        return [e.epi for e in self.epis]

    @property
    def terceiro_label(self) -> str | None:
        """Solicitante terceiro em uma linha, para a ficha e os e-mails."""
        partes = [p for p in (self.terceiro_nome, self.terceiro_empresa) if p]
        return " - ".join(partes) or self.solicitante_terceiro or None

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


class ProdutoEPI(Base):
    """EPI que a área de Segurança marcou como obrigatório para o produto.

    Diferente de `epi_recomendado`, que é o texto copiado da FDS: aqui é a
    decisão do técnico de Segurança, tomada ao dar o parecer.
    """

    __tablename__ = "produto_epis"
    __table_args__ = (
        UniqueConstraint("produto_id", "epi", name="uq_produto_epi"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    epi: Mapped[str] = mapped_column(Unicode(80), nullable=False)

    produto: Mapped["Produto"] = relationship(back_populates="epis")


class ProdutoCAS(Base):
    """Um número CAS da composição do produto.

    A FDS traz um CAS por substância (seção 3), então um produto tem vários.
    Antes existia um campo único `numero_cas` no produto, que continua lá
    para não perder o que já estava cadastrado.
    """

    __tablename__ = "produto_cas"
    __table_args__ = (
        UniqueConstraint("produto_id", "numero", name="uq_produto_cas"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    numero: Mapped[str] = mapped_column(Unicode(40), nullable=False)

    produto: Mapped["Produto"] = relationship(back_populates="cas")


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


class AreaAprovador(Base):
    """Quem aprova por cada área.

    Substitui a regra antiga de "um papel = um aprovador": a área pode ter
    várias pessoas e a lista é mantida pela tela de Aprovações, sem mexer
    no código. Basta UMA delas registrar o parecer para a área concluir.
    """

    __tablename__ = "area_aprovadores"
    __table_args__ = (UniqueConstraint("area", "usuario_id", name="uq_area_usuario"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    usuario: Mapped["Usuario"] = relationship(lazy="joined")

    @property
    def area_label(self) -> str:
        return dict(FLUXO_APROVACAO).get(self.area, self.area)


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


# =====================================================================
# Módulo Recursos e Documentos (biblioteca digital)
# =====================================================================

# Seções da biblioteca. A ordem aqui é a ordem exibida na tela.
SECOES_RECURSO = {
    "ETIQUETAS": "Etiquetas e identificação",
    "PROCEDIMENTOS": "Procedimentos e políticas",
    "FORMULARIOS": "Formulários e modelos",
    "NORMAS": "Normas e legislações",
    "TREINAMENTOS": "Materiais de treinamento",
    "LINKS": "Links úteis",
}

DESCRICAO_SECAO = {
    "ETIQUETAS": "Modelos padronizados de etiquetas GHS, armazenamento, "
                 "recipientes, resíduos perigosos e produtos controlados.",
    "PROCEDIMENTOS": "Procedimentos de manuseio, políticas de HSE e "
                     "instruções de trabalho da planta.",
    "FORMULARIOS": "Formulários e planilhas em branco para preenchimento "
                   "(requisições, checklists, inspeções).",
    "NORMAS": "Normas internas, legislação ambiental, requisitos de saúde, "
              "segurança, armazenamento e transporte.",
    "TREINAMENTOS": "Apresentações, guias rápidos, manuais do sistema, "
                    "vídeos e cartilhas de boas práticas.",
    "LINKS": "Atalhos para SharePoint HSE, Power BI, sistemas corporativos "
             "e sites de órgãos reguladores.",
}

ICONE_SECAO = {
    "ETIQUETAS": "▤",
    "PROCEDIMENTOS": "▣",
    "FORMULARIOS": "▦",
    "NORMAS": "§",
    "TREINAMENTOS": "▷",
    "LINKS": "↗",
}

TIPOS_MIDIA = {
    "ARQUIVO": "Arquivo para download",
    "LINK": "Link externo",
}

# Agrupamento das extensões usado no filtro "tipo de arquivo".
GRUPOS_ARQUIVO = {
    "PDF": ("pdf",),
    "WORD": ("doc", "docx", "rtf", "odt"),
    "EXCEL": ("xls", "xlsx", "xlsm", "csv", "ods"),
    "APRESENTACAO": ("ppt", "pptx", "odp"),
    "IMAGEM": ("png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"),
    "VIDEO": ("mp4", "avi", "mkv", "mov", "wmv"),
    "COMPACTADO": ("zip", "rar", "7z"),
}

ROTULOS_GRUPO_ARQUIVO = {
    "PDF": "PDF",
    "WORD": "Word",
    "EXCEL": "Excel / planilha",
    "APRESENTACAO": "Apresentação",
    "IMAGEM": "Imagem",
    "VIDEO": "Vídeo",
    "COMPACTADO": "Arquivo compactado",
    "LINK": "Link externo",
    "OUTRO": "Outro formato",
}


def sem_acento(texto: str | None) -> str:
    """Texto em minúsculas e sem acentos, para a busca não depender de acentuação."""
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def grupo_do_arquivo(nome_arquivo: str | None) -> str:
    """Classifica o arquivo pela extensão (PDF, WORD, EXCEL, ...)."""
    if not nome_arquivo or "." not in nome_arquivo:
        return "OUTRO"
    ext = nome_arquivo.rsplit(".", 1)[-1].strip().lower()
    for grupo, extensoes in GRUPOS_ARQUIVO.items():
        if ext in extensoes:
            return grupo
    return "OUTRO"


def _legivel(tamanho: int | None) -> str:
    tam = float(tamanho or 0)
    for unidade in ("B", "KB", "MB", "GB"):
        if tam < 1024 or unidade == "GB":
            return f"{tam:.0f} {unidade}" if unidade == "B" else f"{tam:.1f} {unidade}"
        tam /= 1024
    return f"{tam:.1f} GB"


class Recurso(Base):
    """Um item da biblioteca: documento, modelo, norma, treinamento ou link.

    O arquivo em si fica em `RecursoArquivo`, uma linha por versão, de modo
    que a revisão anterior continua disponível para consulta e auditoria.
    """

    __tablename__ = "recursos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    secao: Mapped[str] = mapped_column(Unicode(30), nullable=False, default="PROCEDIMENTOS")
    titulo: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    codigo: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    descricao: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    palavras_chave: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)

    tipo_midia: Mapped[str] = mapped_column(Unicode(20), nullable=False, default="ARQUIVO")
    url: Mapped[str | None] = mapped_column(Unicode(600), nullable=True)

    versao_atual: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    data_revisao: Mapped[date | None] = mapped_column(Date, nullable=True)
    proxima_revisao: Mapped[date | None] = mapped_column(Date, nullable=True)

    responsavel_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    responsavel: Mapped["Usuario | None"] = relationship(lazy="joined")
    arquivos: Mapped[list["RecursoArquivo"]] = relationship(
        back_populates="recurso",
        cascade="all, delete-orphan",
        order_by="desc(RecursoArquivo.versao)",
        lazy="selectin",
    )

    # ------------------------------------------------------------ rótulos
    @property
    def secao_label(self) -> str:
        return SECOES_RECURSO.get(self.secao, self.secao)

    @property
    def icone(self) -> str:
        return ICONE_SECAO.get(self.secao, "▣")

    @property
    def e_link(self) -> bool:
        return self.tipo_midia == "LINK"

    @property
    def arquivo_atual(self) -> "RecursoArquivo | None":
        """Versão mais recente do arquivo (a lista já vem ordenada)."""
        return self.arquivos[0] if self.arquivos else None

    @property
    def versoes_anteriores(self) -> list["RecursoArquivo"]:
        return list(self.arquivos[1:])

    @property
    def grupo_arquivo(self) -> str:
        if self.e_link:
            return "LINK"
        atual = self.arquivo_atual
        return grupo_do_arquivo(atual.nome_arquivo) if atual else "OUTRO"

    @property
    def grupo_label(self) -> str:
        return ROTULOS_GRUPO_ARQUIVO.get(self.grupo_arquivo, self.grupo_arquivo)

    @property
    def extensao(self) -> str:
        if self.e_link:
            return "LINK"
        atual = self.arquivo_atual
        if not atual or "." not in atual.nome_arquivo:
            return "DOC"
        return atual.nome_arquivo.rsplit(".", 1)[-1].upper()[:4]

    @property
    def tamanho_legivel(self) -> str:
        atual = self.arquivo_atual
        return _legivel(atual.tamanho) if atual else "-"

    @property
    def destino(self) -> str:
        """Para onde o botão 'Abrir' aponta."""
        return self.url if self.e_link else f"/recursos/{self.id}/arquivo"

    @property
    def data_referencia(self) -> date:
        """Data usada nas ordenações e no filtro por período."""
        if self.data_revisao:
            return self.data_revisao
        return (self.atualizado_em or self.criado_em or datetime.now()).date()

    @property
    def revisao_vencida(self) -> bool:
        return bool(self.proxima_revisao and self.proxima_revisao < date.today())

    def texto_busca(self) -> str:
        partes = [self.titulo, self.codigo or "", self.descricao or "",
                  self.palavras_chave or "", self.secao_label]
        atual = self.arquivo_atual
        if atual:
            partes.append(atual.nome_arquivo)
        return sem_acento(" ".join(partes))


class RecursoArquivo(Base):
    """Uma versão do arquivo de um recurso. O conteúdo fica no banco."""

    __tablename__ = "recurso_arquivos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recurso_id: Mapped[int] = mapped_column(ForeignKey("recursos.id"), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    nome_arquivo: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    tamanho: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    data_revisao: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    enviado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    enviado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    recurso: Mapped["Recurso"] = relationship(back_populates="arquivos")
    enviado_por: Mapped["Usuario | None"] = relationship(lazy="joined")

    @property
    def tamanho_legivel(self) -> str:
        return _legivel(self.tamanho)

    @property
    def extensao(self) -> str:
        if "." not in self.nome_arquivo:
            return "DOC"
        return self.nome_arquivo.rsplit(".", 1)[-1].upper()[:4]


# =====================================================================
# Kit Ambiental (informativo: o que cada kit tem e onde encontrar)
# =====================================================================

# Perfis que mantêm os kits e os pontos de coleta.
PAPEIS_KIT = ("MEIO_AMBIENTE", "SEGURANCA", "ADMIN")

# Unidades usadas na quantidade de cada item do kit.
UNIDADES_ITEM = ["un", "par", "kg", "L", "m", "rolo", "caixa", "saco", "pacote"]


class KitAmbiental(Base):
    """Um tipo de kit (Kit A, Kit B, ...).

    A composição é definida por TIPO e vale para toda a Tenaris: as
    fábricas apenas informam quantos kits têm e onde eles ficam.
    """

    __tablename__ = "kits_ambientais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(20), nullable=False, unique=True)
    nome: Mapped[str] = mapped_column(Unicode(120), nullable=False)
    utilidade: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    quando_usar: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    atualizado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )

    atualizado_por: Mapped["Usuario | None"] = relationship(lazy="joined")
    itens: Mapped[list["ItemKit"]] = relationship(
        back_populates="kit",
        cascade="all, delete-orphan",
        order_by="ItemKit.ordem, ItemKit.id",
        lazy="selectin",
    )
    pontos: Mapped[list["PontoColetaKit"]] = relationship(
        back_populates="kit",
        cascade="all, delete-orphan",
        order_by="PontoColetaKit.fabrica, PontoColetaKit.local",
        lazy="selectin",
    )

    @property
    def itens_ativos(self) -> list["ItemKit"]:
        return [i for i in self.itens if i.ativo]

    @property
    def pontos_ativos(self) -> list["PontoColetaKit"]:
        return [p for p in self.pontos if p.ativo]

    @property
    def fabricas(self) -> list[str]:
        """Fábricas que têm pelo menos um kit deste tipo."""
        vistas = []
        for ponto in self.pontos_ativos:
            if ponto.fabrica not in vistas:
                vistas.append(ponto.fabrica)
        return vistas

    @property
    def sem_composicao(self) -> bool:
        return not self.itens_ativos


class ItemKit(Base):
    """Um item que compõe o kit, com quantidade, utilidade e foto."""

    __tablename__ = "kit_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kit_id: Mapped[int] = mapped_column(ForeignKey("kits_ambientais.id"), nullable=False)
    nome: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    utilidade: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    quantidade: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    unidade: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)
    # Quando o item é um produto químico já cadastrado, o vínculo dá
    # acesso direto à FDS dele.
    produto_id: Mapped[int | None] = mapped_column(ForeignKey("produtos.id"), nullable=True)
    foto: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    foto_tipo: Mapped[str | None] = mapped_column(Unicode(60), nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    kit: Mapped["KitAmbiental"] = relationship(back_populates="itens")
    produto: Mapped["Produto | None"] = relationship(lazy="joined")

    @property
    def tem_foto(self) -> bool:
        return bool(self.foto)

    @property
    def quantidade_label(self) -> str:
        if not self.quantidade:
            return "-"
        return f"{self.quantidade} {self.unidade or ''}".strip()


class PontoColetaKit(Base):
    """Onde um kit de determinado tipo pode ser encontrado."""

    __tablename__ = "kit_pontos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kit_id: Mapped[int] = mapped_column(ForeignKey("kits_ambientais.id"), nullable=False)
    fabrica: Mapped[str] = mapped_column(Unicode(60), nullable=False)
    local: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    responsavel: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    ramal: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    kit: Mapped["KitAmbiental"] = relationship(back_populates="pontos")

    @property
    def contato(self) -> str | None:
        if self.responsavel and self.ramal:
            return f"{self.responsavel} - ramal {self.ramal}"
        return self.responsavel or (f"Ramal {self.ramal}" if self.ramal else None)
