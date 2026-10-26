"""Tradução da interface para inglês e espanhol.

Como funciona
-------------
O sistema continua sendo escrito em português no código. Na hora de montar
a página, a árvore de componentes é percorrida e cada texto que existir no
dicionário `idiomas_textos.TEXTOS` é trocado pela versão no idioma escolhido.

Isso traduz **a interface** (menus, títulos, rótulos, botões, mensagens).
O conteúdo digitado pelas pessoas - nome do produto, parecer técnico, texto
da FDS - continua no idioma em que foi escrito, como deve ser: um parecer
técnico não pode ser traduzido por máquina sem perder valor legal.

Para corrigir uma tradução, edite `idiomas_textos.py` e reinicie o sistema.
"""

from __future__ import annotations

import re
from contextvars import ContextVar

from fastcore.xml import FT, NotStr, Safe

from idiomas_textos import TEXTOS

# --------------------------------------------------------------- Idiomas
PADRAO = "pt"

IDIOMAS: dict[str, dict[str, str]] = {
    "pt": {"rotulo": "PT", "nome": "Português", "html": "pt-BR"},
    "en": {"rotulo": "EN", "nome": "English", "html": "en"},
    "es": {"rotulo": "ES", "nome": "Español", "html": "es"},
}

_atual: ContextVar[str] = ContextVar("idioma", default=PADRAO)


def normalizar(codigo: str | None) -> str:
    """Devolve sempre um código válido ('pt', 'en' ou 'es')."""
    codigo = (codigo or "").strip().lower()[:2]
    return codigo if codigo in IDIOMAS else PADRAO


def definir(codigo: str | None) -> str:
    codigo = normalizar(codigo)
    _atual.set(codigo)
    return codigo


def atual() -> str:
    return _atual.get()


class Middleware:
    """Lê o idioma da sessão no início de cada requisição.

    Precisa ser uma camada ASGI, e não o Beforeware: o Beforeware roda numa
    thread auxiliar, e o que ele guardar ali não chega na hora de montar a
    página. Aqui a escolha é feita na mesma tarefa que atende a requisição,
    então vale do começo ao fim dela.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            sessao = scope.get("session") or {}
            definir(sessao.get("idioma"))
        await self.app(scope, receive, send)


def instalar(app) -> None:
    """Pendura o Middleware por dentro da sessão (precisa dela já lida)."""
    from starlette.middleware import Middleware as _Camada

    app.user_middleware.append(_Camada(Middleware))
    app.middleware_stack = None  # força remontar a pilha na próxima subida


def lang_html() -> str:
    return IDIOMAS[atual()]["html"]


# --------------------------------------------- Textos montados em tempo real
# Frases em que entra um número ou um nome ("3 arquivo(s)", "Parecer de Ana").
# O dicionário não dá conta delas porque o texto só existe quando a página é
# montada; aqui a tradução é feita por padrão. Os grupos listados em
# `traduzir_grupos` são, eles próprios, passados pelo dicionário.

def _r(padrao, en, es, traduzir_grupos=()):
    return (re.compile(padrao), {"en": en, "es": es}, traduzir_grupos)


REGRAS = [
    # Título da aba do navegador -------------------------------------------
    _r(r"^(.+) \| Gestão de Produtos Químicos - Tenaris$",
       "{0} | Chemical Product Management - Tenaris",
       "{0} | Gestión de Productos Químicos - Tenaris", (0,)),
    # Contadores -----------------------------------------------------------
    _r(r"^(\d+) arquivo\(s\)$", "{0} file(s)", "{0} archivo(s)"),
    _r(r"^(\d+) documento\(s\)$", "{0} document(s)", "{0} documento(s)"),
    _r(r"^(\d+) produto\(s\)$", "{0} product(s)", "{0} producto(s)"),
    _r(r"^(\d+) item\(ns\)$", "{0} item(s)", "{0} artículo(s)"),
    _r(r"^(\d+) registro\(s\)$", "{0} record(s)", "{0} registro(s)"),
    _r(r"^(\d+) versão\(ões\)$", "{0} version(s)", "{0} versión(es)"),
    _r(r"^(\d+) vínculo\(s\)$", "{0} link(s)", "{0} vínculo(s)"),
    _r(r"^(\d+) download\(s\)$", "{0} download(s)", "{0} descarga(s)"),
    _r(r"^(\d+) kit\(s\)$", "{0} kit(s)", "{0} kit(s)"),
    _r(r"^(\d+) colaborador\(es\)$", "{0} employee(s)", "{0} empleado(s)"),
    _r(r"^(\d+) ponto\(s\) de coleta$", "{0} collection point(s)",
       "{0} punto(s) de recolección"),
    _r(r"^(\d+) ponto\(s\)$", "{0} point(s)", "{0} punto(s)"),
    _r(r"^(\d+) campo\(s\) preenchidos pela FDS\.", "{0} field(s) filled from the SDS.",
       "{0} campo(s) rellenados por la FDS."),
    _r(r"^(\d+) solicitação\(ões\) enviada\(s\) por você$",
       "{0} request(s) submitted by you", "{0} solicitud(es) enviada(s) por usted"),
    _r(r"^(\d+) solicitação\(ões\) cobrada\(s\)\.$", "{0} request(s) chased.",
       "{0} solicitud(es) recordada(s)."),
    _r(r"^(\d+)/(\d+) etapas$", "{0}/{1} steps", "{0}/{1} etapas"),
    _r(r"^(\d+) áreas$", "{0} areas", "{0} áreas"),
    # Consumo com unidade ("60 L/mês").
    _r(r"^([\d.,]+) ((?:L|mL|kg|g|t|un)/(?:mês|ano))$", "{0} {1}", "{0} {1}", (1,)),
    _r(r"^(\d+) documentos no total$", "{0} documents in total", "{0} documentos en total"),
    _r(r"^(\d+) documentos publicados$", "{0} published documents",
       "{0} documentos publicados"),
    _r(r"^(\d+) arquivos para download$", "{0} files to download",
       "{0} archivos para descargar"),
    _r(r"^(\d+) links úteis$", "{0} useful links", "{0} enlaces útiles"),
    _r(r"^(\d+) dias em aberto$", "{0} days open", "{0} días abiertos"),
    _r(r"^\((\d+) dias atrás\)$", "({0} days ago)", "(hace {0} días)"),
    _r(r"^(.*) \((\d+) dias\)$", "{0} ({1} days)", "{0} ({1} días)", (0,)),
    # Fluxo de aprovação ---------------------------------------------------
    _r(r"^(.+): (aprovado|reprovado|aguardando|não iniciada)$", "{0}: {1}", "{0}: {1}",
       (0, 1)),
    _r(r"^(Aprovado|Reprovado) por (.+) em (.+)$", "{0} by {1} on {2}",
       "{0} por {1} el {2}", (0,)),
    _r(r"^Parecer de (.+)$", "Opinion from {0}", "Dictamen de {0}"),
    _r(r"^Aprovador removido de (.+)\.$", "Approver removed from {0}.",
       "Aprobador eliminado de {0}.", (0,)),
    _r(r"^(.+) passou a aprovar por (.+)\.$", "{0} now approves for {1}.",
       "{0} ahora aprueba por {1}.", (1,)),
    _r(r"^Pronto! A solicitação foi registrada com o protocolo (.+)$",
       "Done! The request was registered under reference {0}",
       "¡Listo! La solicitud se registró con el protocolo {0}"),
    _r(r"^Preencha os campos obrigatórios: (.+)$", "Fill in the required fields: {0}",
       "Complete los campos obligatorios: {0}"),
    _r(r'^A área "(.*)" não é da unidade (.+)\. Escolha uma área da unidade '
       r"selecionada\.$",
       'The area "{0}" does not belong to unit {1}. Pick an area of the '
       "selected unit.",
       'El área "{0}" no es de la unidad {1}. Elija un área de la unidad '
       "seleccionada.", (0,)),
    _r(r'^A área "(.*)" não pertence a nenhuma das unidades autorizadas '
       r"deste produto\.$",
       'The area "{0}" does not belong to any of this product\'s authorized units.',
       'El área "{0}" no pertenece a ninguna de las unidades autorizadas '
       "de este producto.", (0,)),
    _r(r"^Número CAS fora do formato: (.+)\. O formato é 67-64-1\.$",
       "CAS number in the wrong format: {0}. The format is 67-64-1.",
       "Número CAS con formato incorrecto: {0}. El formato es 67-64-1."),
    _r(r"^(\d+) produto\(s\) - página (\d+) de (\d+)$",
       "{0} product(s) - page {1} of {2}",
       "{0} producto(s) - página {1} de {2}"),
    _r(r"^Solicitação de empresa terceira: preencha também (.+)$",
       "Third-party request: also fill in {0}",
       "Solicitud de empresa tercera: complete también {0}"),
    # Avisos com contagem --------------------------------------------------
    _r(r"^(\d+) produto\(s\) com FDS vencida\.$", "{0} product(s) with an expired SDS.",
       "{0} producto(s) con FDS vencida."),
    _r(r"^(\d+) produto\(s\) com licença vencida\.$",
       "{0} product(s) with an expired license.",
       "{0} producto(s) con licencia vencida."),
    _r(r"^(\d+) documento\(s\) com revisão vencida\.$",
       "{0} document(s) with an overdue revision.",
       "{0} documento(s) con revisión vencida."),
    _r(r"^Somente produtos aprovados aparecem aqui\. A validade é contada a partir da "
       r"data de revisão da ficha, com prazo de (\d+) anos e alerta nos últimos (\d+) meses\.$",
       "Only approved products appear here. Validity is counted from the sheet's "
       "revision date, with a {0}-year term and a warning in the last {1} months.",
       "Aquí solo aparecen los productos aprobados. La vigencia se cuenta desde la "
       "fecha de revisión de la ficha, con un plazo de {0} años y aviso en los "
       "últimos {1} meses."),
    _r(r"^Somente PDF, até (.+)\. A leitura acontece no próprio servidor - o arquivo "
       r"não sai da rede interna\.$",
       "PDF only, up to {0}. The file is read on the server itself - it never "
       "leaves the internal network.",
       "Solo PDF, hasta {0}. La lectura ocurre en el propio servidor - el archivo "
       "no sale de la red interna."),
    # Documentos e versões -------------------------------------------------
    _r(r"^(.+) - (.+) - enviado em (.+)$", "{0} - {1} - uploaded on {2}",
       "{0} - {1} - enviado el {2}", (0,)),
    _r(r"^FDS - (.+)$", "SDS - {0}", "FDS - {0}"),
    _r(r"^Versão v(\d+)$", "Version v{0}", "Versión v{0}"),
    _r(r"^(.+) • versão (.+)$", "{0} • version {1}", "{0} • versión {1}", (0,)),
    _r(r"^(.+) • revisão (.+)$", "{0} • revision {1}", "{0} • revisión {1}", (0,)),
    _r(r"^(.+) • enviado em (.+)$", "{0} • uploaded on {1}", "{0} • enviado el {1}", (0,)),
    _r(r"^Link externo • atualizado em (.+)$", "External link • updated on {0}",
       "Enlace externo • actualizado el {0}"),
    _r(r"^anexada em (.+)$", "attached on {0}", "adjuntada el {0}"),
    _r(r"^revisão de (.+)$", "revised on {0}", "revisión de {0}"),
    _r(r"^Editar: (.+)$", "Edit: {0}", "Editar: {0}"),
    _r(r"^(.+) - dados de identificação, aplicação e controle$",
       "{0} - identification, use and control data",
       "{0} - datos de identificación, aplicación y control"),
    _r(r"^Editar item - (.+)$", "Edit item - {0}", "Editar artículo - {0}"),
    _r(r"^Item do (.+)$", "Item of {0}", "Artículo de {0}"),
    # Validade -------------------------------------------------------------
    _r(r"^vence em (.+) \(faltam (\d+) dias\)$",
       "expires on {0} ({1} days left)", "vence el {0} (faltan {1} días)"),
    _r(r"^venceu em (.+) \((\d+) dias atrás\)$",
       "expired on {0} ({1} days ago)", "venció el {0} (hace {1} días)"),
    _r(r"^vence em (.+)$", "expires on {0}", "vence el {0}"),
    _r(r"^venceu em (.+)$", "expired on {0}", "venció el {0}"),
    _r(r"^válida até (.+)$", "valid until {0}", "válida hasta {0}"),
    _r(r"^Licença (.+)$", "License {0}", "Licencia {0}"),
    _r(r"^Até (.+)$", "Up to {0}", "Hasta {0}"),
    _r(r"^Ramal (.+)$", "Ext. {0}", "Ext. {0}"),
    _r(r"^Acesso de (.+)$", "Access for {0}", "Acceso de {0}"),
    # Limites de arquivo ---------------------------------------------------
    _r(r"^Somente PDF, até (.+)$", "PDF only, up to {0}", "Solo PDF, hasta {0}"),
    _r(r"^JPG ou PNG, até (.+)$", "JPG or PNG, up to {0}", "JPG o PNG, hasta {0}"),
    _r(r"^O arquivo excede o limite de (.+)$", "The file exceeds the {0} limit",
       "El archivo supera el límite de {0}"),
    _r(r"^A imagem excede o limite de (.+)$", "The image exceeds the {0} limit",
       "La imagen supera el límite de {0}"),
    _r(r"^Arquivo maior que (.+)$", "File larger than {0}", "Archivo mayor que {0}"),
    _r(r"^Pelo menos (.+)$", "At least {0}", "Al menos {0}"),
    _r(r"^A nova senha precisa de pelo menos (\d+) caracteres\.$",
       "The new password needs at least {0} characters.",
       "La nueva contraseña necesita al menos {0} caracteres."),
]

# Pedaços que aparecem sozinhos dentro de uma frase montada (o número ou o
# nome vem num elemento ao lado, por isso não casam com o dicionário).
EXTRAS = {
    "aprovado": {"en": "approved", "es": "aprobado"},
    "reprovado": {"en": "rejected", "es": "rechazado"},
    "aguardando": {"en": "waiting", "es": "en espera"},
    "não iniciada": {"en": "not started", "es": "no iniciada"},
    "Você administra o sistema, mas o parecer de cada área é exclusivo de "
    "quem responde por ela. Para opinar, é preciso estar cadastrado como "
    "aprovador da área em Aprovações.": {
        "en": "You administer the system, but each area's opinion belongs "
              "only to whoever answers for it. To submit one, you must be "
              "registered as an approver for that area under Approvals.",
        "es": "Usted administra el sistema, pero el dictamen de cada área es "
              "exclusivo de quien responde por ella. Para opinar, hay que "
              "estar registrado como aprobador del área en Aprobaciones.",
    },
    "Você não responde pela área escolhida nesta solicitação.": {
        "en": "You do not answer for the area you selected on this request.",
        "es": "Usted no responde por el área seleccionada en esta solicitud.",
    },
    "FDS": {"en": "SDS", "es": "FDS"},
    "login": {"en": "login", "es": "acceso"},
    "Produto": {"en": "Product", "es": "Producto"},
    "Documento": {"en": "Document", "es": "Documento"},
    "Recurso": {"en": "Resource", "es": "Recurso"},
    "documentos publicados": {"en": "published documents", "es": "documentos publicados"},
    "documentos no total": {"en": "documents in total", "es": "documentos en total"},
    "arquivos para download": {"en": "files to download", "es": "archivos para descargar"},
    "links úteis": {"en": "useful links", "es": "enlaces útiles"},
    "dias em aberto": {"en": "days open", "es": "días abiertos"},
    "cadastrados no sistema": {"en": "registered in the system", "es": "registrados en el sistema"},
    "liberados para uso": {"en": "cleared for use", "es": "liberados para uso"},
    "não liberados": {"en": "not cleared", "es": "no liberados"},
    "em análise pelas áreas": {"en": "under review by the areas", "es": "en análisis por las áreas"},
    "pendentes + em análise": {"en": "pending + under review", "es": "pendientes + en análisis"},
    "Consulta de produtos e FDS não exige login:": {
        "en": "Browsing products and SDS does not require a login:",
        "es": "La consulta de productos y FDS no exige inicio de sesión:",
    },
    "Usuários de teste:": {"en": "Test users:", "es": "Usuarios de prueba:"},
    "... senha": {"en": "... password", "es": "... contraseña"},
    "Banco:": {"en": "Database:", "es": "Base de datos:"},
    "Servidor de e-mail (SMTP) não configurado: as notificações estão sendo": {
        "en": "Mail server (SMTP) not configured: notifications are being",
        "es": "Servidor de correo (SMTP) no configurado: las notificaciones se están",
    },
    "gravadas na": {"en": "saved in the", "es": "guardando en la"},
    "em vez de enviadas.": {"en": "instead of sent.", "es": "en vez de enviadas."},
    "Visão geral - banco:": {"en": "Overview - database:", "es": "Visión general - base de datos:"},
    "anos.": {"en": "years.", "es": "años."},
    "meses.": {"en": "months.", "es": "meses."},
    "caracteres.": {"en": "characters.", "es": "caracteres."},
    "revisão vencida": {"en": "overdue revision", "es": "revisión vencida"},
    "produto controlado": {"en": "controlled product", "es": "producto controlado"},
    "sem FDS": {"en": "no SDS", "es": "sin FDS"},
    "sem categoria": {"en": "no category", "es": "sin categoría"},
    "sem foto": {"en": "no photo", "es": "sin foto"},
    "sem número": {"en": "no number", "es": "sin número"},
    "não informada": {"en": "not provided", "es": "no informada"},
    "não configurado": {"en": "not configured", "es": "no configurado"},
    "fora de uso": {"en": "out of use", "es": "fuera de uso"},
    "composição a definir": {"en": "composition to be defined", "es": "composición por definir"},
}


# --------------------------------------------------------------- Tradução
def t(texto: str, idioma: str | None = None) -> str:
    """Traduz um texto solto. Devolve o original quando não há tradução."""
    idioma = idioma or atual()
    if idioma == PADRAO or not isinstance(texto, str) or not texto.strip():
        return texto

    # Espaços nas pontas são de formatação: preserva e traduz só o miolo.
    miolo = texto.strip()
    esquerda = texto[: len(texto) - len(texto.lstrip())]
    direita = texto[len(texto.rstrip()):]

    pronto = TEXTOS.get(miolo) or EXTRAS.get(miolo)
    if pronto:
        return esquerda + pronto.get(idioma, miolo) + direita

    for padrao, modelos, traduzir_grupos in REGRAS:
        achado = padrao.match(miolo)
        if not achado:
            continue
        grupos = [
            t(g, idioma) if i in traduzir_grupos else g
            for i, g in enumerate(achado.groups())
        ]
        return esquerda + modelos[idioma].format(*grupos) + direita

    # Listas montadas na hora ("Saúde, Segurança, Aprovador Final"): só traduz
    # quando TODOS os pedaços são conhecidos, para não mexer em texto de FDS.
    if ", " in miolo:
        partes = miolo.split(", ")
        traduzidas = [(TEXTOS.get(p) or EXTRAS.get(p) or {}).get(idioma) for p in partes]
        if all(traduzidas):
            return esquerda + ", ".join(traduzidas) + direita

    return texto


# Atributos cujo valor é lido pela pessoa (ou pelo leitor de tela).
ATRIBUTOS = ("placeholder", "title", "alt", "aria-label", "aria-description")


def traduzir(no, idioma: str | None = None):
    """Percorre a árvore de componentes trocando os textos conhecidos.

    Não altera os objetos originais: devolve cópias. Assim um componente
    guardado numa constante do módulo nunca é corrompido.
    """
    idioma = idioma or atual()
    if idioma == PADRAO:
        return no
    return _percorrer(no, idioma)


def _percorrer(no, idioma):
    if no is None or isinstance(no, (bool, int, float)):
        return no
    # NotStr/Safe são HTML cru (ícones SVG): não se mexe.
    if isinstance(no, (NotStr, Safe)):
        return no
    if isinstance(no, str):
        return t(no, idioma)
    if isinstance(no, FT):
        filhos = tuple(_percorrer(f, idioma) for f in no.children)
        atributos = dict(no.attrs)
        for chave in ATRIBUTOS:
            if isinstance(atributos.get(chave), str):
                atributos[chave] = t(atributos[chave], idioma)
        novo = FT(no.tag, filhos, atributos, void_=no.void_)
        return novo
    if isinstance(no, (list, tuple)):
        convertido = [_percorrer(f, idioma) for f in no]
        return type(no)(convertido) if isinstance(no, list) else tuple(convertido)
    return no


# ------------------------------------------------------------- Componente
def seletor():
    """PT · EN · ES para a barra superior (sem JavaScript)."""
    from fasthtml.common import A, Span  # import tardio: evita ciclo

    agora = atual()
    itens = []
    for codigo, info in IDIOMAS.items():
        if itens:
            itens.append(Span("·", cls="sep-idioma"))
        itens.append(
            A(
                info["rotulo"],
                href=f"/idioma/{codigo}",
                title=info["nome"],
                cls="idioma ativo" if codigo == agora else "idioma",
            )
        )
    return Span(*itens, cls="seletor-idioma")
