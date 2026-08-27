"""Componentes visuais reutilizaveis (identidade Tenaris)."""

from fasthtml.common import *  # noqa: F403

import config
from models import FLUXO_APROVACAO, STATUS

# ---------------------------------------------------------------- Menu
MENU = [
    (
        "Painel",
        [
            ("/", "Dashboard", "▤", None),
            ("/solicitacoes/nova", "Nova solicitação", "+", None),
            ("/minhas", "Minhas solicitações", "☰", None),
            ("/aprovacoes", "Aprovações pendentes", "✔", "pendencias"),
        ],
    ),
    (
        "Consultas",
        [
            ("/produtos", "Produtos químicos", "⌕", None),
            ("/fds", "Fichas de segurança (FDS)", "▣", None),
            ("/historico", "Histórico completo", "⏱", None),
        ],
    ),
    (
        "Administração",
        [
            ("/usuarios", "Usuários e papéis", "⚙", None),
            ("/notificacoes", "Notificações enviadas", "✉", None),
            ("/auditoria", "Log de auditoria", "⎗", None),
        ],
    ),
]


def cabeca(titulo: str):
    return (
        Title(f"{titulo} | {config.APP_NOME} - {config.APP_EMPRESA}"),
        Link(rel="stylesheet", href="/static/styles.css"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
    )


def topbar(usuario=None):
    direita = []
    if usuario:
        direita = [
            Div(
                Div(usuario.nome, Small(usuario.papel_label), cls="nome"),
                Div(usuario.iniciais, cls="avatar"),
                A("Sair", href="/logout", cls="sair"),
                cls="usuario",
            )
        ]
    else:
        direita = [A("Entrar", href="/login", cls="sair")]
    return Header(
        A(B(config.APP_EMPRESA), Span("Gestão de Produtos Químicos"), href="/", cls="marca"),
        Div(cls="espaco"),
        *direita,
        cls="topbar",
    )


def lateral(ativo: str = "", pendencias: int = 0, papel: str = ""):
    blocos = []
    for grupo, itens in MENU:
        if grupo == "Administração" and papel not in ("ADMIN", "APROVADOR_FINAL"):
            continue
        blocos.append(Div(grupo, cls="grupo"))
        for href, rotulo, icone, marca in itens:
            filhos = [Span(icone, cls="ic"), Span(rotulo)]
            if marca == "pendencias" and pendencias:
                filhos.append(Span(str(pendencias), cls="contador"))
            blocos.append(
                A(*filhos, href=href, cls="ativo" if href == ativo else None)
            )
    return Nav(*blocos, cls="lateral")


def pagina(
    titulo: str,
    *conteudo,
    usuario=None,
    ativo: str = "",
    subtitulo: str | None = None,
    acoes=None,
    pendencias: int = 0,
    mostrar_menu: bool = True,
):
    """Molde padrão de pagina interna."""
    cabecalho = Div(
        Div(H1(titulo), P(subtitulo, cls="sub") if subtitulo else None),
        Div(*(acoes or []), cls="acoes") if acoes else None,
        cls="cabecalho-pagina",
    )
    corpo = [
        topbar(usuario),
        lateral(ativo, pendencias, getattr(usuario, "papel", "")) if mostrar_menu else None,
        Main(
            cabecalho,
            *conteudo,
            Div(
                f"{config.APP_EMPRESA} - {config.APP_NOME} | Protótipo interno",
                cls="rodape",
            ),
            cls="conteudo" if mostrar_menu else "conteudo cheio",
        ),
    ]
    return (*cabeca(titulo), *[c for c in corpo if c is not None])


# ------------------------------------------------------------ Elementos
def badge(status: str):
    classe = status.lower().replace("_", "-")
    return Span(STATUS.get(status, status), cls=f"badge {classe}")


def alerta(mensagem, tipo: str = "info"):
    if not mensagem:
        return None
    return Div(mensagem, cls=f"alerta {tipo}" if tipo != "info" else "alerta")


def passos(produto):
    """Mini indicador visual do andamento das etapas."""
    itens = []
    for ap in produto.aprovacoes:
        if ap.decisao == "APROVADO":
            classe = "ok"
        elif ap.decisao == "REPROVADO":
            classe = "recusado"
        elif produto.etapa_atual == ap.etapa and produto.status == "EM_ANALISE":
            classe = "atual"
        else:
            classe = ""
        itens.append(I(cls=classe or None, title=f"{ap.etapa_label}: {ap.decisao.title()}"))
    if not itens:
        itens = [I() for _ in FLUXO_APROVACAO]
    return Span(*itens, cls="passos")


def campo(
    rotulo: str,
    nome: str,
    tipo: str = "text",
    valor: str | None = None,
    obrigatório: bool = False,
    ajuda: str | None = None,
    opcoes: list | None = None,
    placeholder: str | None = None,
    linhas: int | None = None,
):
    rot = Span(
        rotulo, Span(" *", cls="obr") if obrigatório else None, cls="rot"
    )
    if opcoes is not None:
        entrada = Select(
            Option("Selecione...", value="", selected=not valor),
            *[
                Option(
                    texto if isinstance(texto, str) else texto[1],
                    value=texto if isinstance(texto, str) else texto[0],
                    selected=(valor == (texto if isinstance(texto, str) else texto[0])),
                )
                for texto in opcoes
            ],
            name=nome,
            required=obrigatório,
        )
    elif linhas:
        entrada = Textarea(
            valor or "", name=nome, rows=str(linhas), required=obrigatório,
            placeholder=placeholder,
        )
    else:
        entrada = Input(
            type=tipo, name=nome, value=valor or "", required=obrigatório,
            placeholder=placeholder,
        )
    return Label(rot, entrada, Span(ajuda, cls="ajuda") if ajuda else None, cls="campo")


def item_ficha(rotulo: str, valor, largo: bool = False):
    return Div(
        Div(rotulo, cls="rot"),
        Div(valor if (valor not in (None, "")) else Span("-", cls="texto-mudo"), cls="val"),
        cls="item largo" if largo else "item",
    )


def vazio(mensagem: str, icone: str = "◌"):
    return Div(Span(icone, cls="ic"), mensagem, cls="vazio")


def barras(dados: list[tuple[str, int]], cor_por_indice: bool = True):
    """Gráfico de barras horizontais em CSS puro. dados = [(rotulo, valor)]"""
    if not dados:
        return vazio("Sem dados para exibir.")
    maximo = max(v for _, v in dados) or 1
    linhas = []
    for i, (rotulo, valor) in enumerate(dados):
        cor = f"c{(i % 6) + 1}" if cor_por_indice else "c1"
        linhas.append(
            Div(
                Div(rotulo, cls="nowrap", title=rotulo),
                Div(I(cls=cor, style=f"width:{max(2, round(valor / maximo * 100))}%"), cls="trilha"),
                Div(str(valor), cls="qtd"),
                cls="linha",
            )
        )
    return Div(*linhas, cls="barras")


def linha_fluxo(produto):
    """Timeline das etapas de aprovacao."""
    itens = []
    for ap in produto.aprovacoes:
        if ap.decisao == "APROVADO":
            classe, marca = "aprovado", "✓"
        elif ap.decisao == "REPROVADO":
            classe, marca = "reprovado", "✕"
        elif produto.etapa_atual == ap.etapa and produto.status == "EM_ANALISE":
            classe, marca = "atual", str(ap.ordem)
        else:
            classe, marca = "", str(ap.ordem)
        if ap.decisao == "PENDENTE":
            meta = (
                "Aguardando análise"
                if classe == "atual"
                else "Não iniciada"
            )
        else:
            quem = ap.aprovador.nome if ap.aprovador else "-"
            quando = ap.decidido_em.strftime("%d/%m/%Y %H:%M") if ap.decidido_em else "-"
            meta = f"{ap.decisao.title()} por {quem} em {quando}"
        itens.append(
            Li(
                Div(marca, cls="marcador"),
                Div(ap.etapa_label, cls="etapa"),
                Div(meta, cls="meta"),
                Div(ap.parecer, cls="parecer") if ap.parecer else None,
                cls=classe or None,
            )
        )
    return Ul(*itens, cls="fluxo")


def cartao_documento(doc, prefixo: str = ""):
    ext = (doc.nome_arquivo.rsplit(".", 1)[-1] if "." in doc.nome_arquivo else "DOC").upper()[:4]
    return Div(
        Div(ext, cls="icone fds" if doc.tipo == "FDS" else "icone"),
        Div(
            Div(doc.nome_arquivo, cls="nome"),
            Div(
                f"{doc.tipo_label} - {doc.tamanho_legivel} - "
                f"enviado em {doc.enviado_em.strftime('%d/%m/%Y')}",
                cls="meta",
            ),
            cls="info",
        ),
        A("Baixar", href=f"{prefixo}/documentos/{doc.id}", cls="btn pequeno secundario"),
        cls="doc",
    )
