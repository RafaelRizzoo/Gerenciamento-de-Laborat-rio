"""Componentes visuais reutilizaveis (identidade Tenaris).

Regras de navegacao adotadas:
  * A barra superior contem APENAS a marca + "Gestão de Produtos Químicos".
  * A navegacao acontece pelos cartoes da pagina inicial e pelo link "Início".
  * Quando existe usuario autenticado, uma faixa fina abaixo da barra mostra
    quem esta logado e o link para sair.
"""

from fasthtml.common import *  # noqa: F403

import config
from models import AREAS_APROVACAO, ETAPA_FINAL, FLUXO_APROVACAO, STATUS


# ------------------------------------------------------- Cache do CSS
def css_url() -> str:
    """URL da folha de estilo com a data do arquivo embutida.

    Sem isso o navegador continua servindo o CSS antigo do cache depois de
    cada alteração, e é preciso pedir Ctrl+Shift+R para o usuário. Com o
    parâmetro de versão, mudar o arquivo já invalida o cache sozinho.
    """
    try:
        marca = int((config.BASE_DIR / "static" / "styles.css").stat().st_mtime)
    except OSError:
        marca = 0
    return f"/static/styles.css?v={marca}"


# ---------------------------------------------------------------- Marca
LOGO = "/static/img/logo.png"


def marca_tenaris(tamanho: str = "normal"):
    """Símbolo oficial (static/img/logo.png) + wordmark."""
    return Span(
        Img(src=LOGO, alt="Tenaris", cls="sinal"),
        Span("Tenaris", cls="wordmark"),
        cls=f"marca-tenaris {tamanho}",
    )


def cabeca(titulo: str):
    return (
        Title(f"{titulo} | {config.APP_NOME} - {config.APP_EMPRESA}"),
        Link(rel="icon", type="image/png", href=LOGO),
        Link(rel="apple-touch-icon", href=LOGO),
        Link(rel="stylesheet", href=css_url()),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
    )


# ------------------------------------------------------------- Estrutura
def topbar():
    """Barra superior: somente a marca e o nome do sistema. Nada mais."""
    return Header(
        A(
            marca_tenaris(),
            Span(cls="divisor"),
            Span(Span("Gestão de"), B("Produtos Químicos"), cls="sistema"),
            href="/",
            cls="marca",
        ),
        cls="topbar",
    )


def faixa_usuario(usuario=None):
    """Faixa fina exibida somente para quem esta autenticado."""
    if not usuario:
        return None
    return Div(
        Div(usuario.iniciais, cls="avatar"),
        Span(B(usuario.nome), " - ", usuario.papel_label, cls="quem"),
        Div(cls="espaco"),
        A("Início", href="/"),
        A("Nova solicitação", href="/solicitacoes/nova"),
        A("Minhas solicitações", href="/minhas"),
        A("Aprovações", href="/aprovacoes"),
        A("Painel", href="/painel"),
        A("Sair", href="/logout", cls="sair"),
        cls="faixa-usuario",
    )


def rodape():
    return Footer(
        Div(marca_tenaris("pequeno"), cls="fim-marca"),
        Div(
            B("Segurança que transforma"),
            Span(" • ", cls="ponto"),
            B("Qualidade que constrói o futuro"),
            cls="fim-lema",
        ),
        Div(
            Span("Segurança", cls="pilar"),
            Span("Qualidade", cls="pilar"),
            Span("Sustentabilidade", cls="pilar"),
            cls="fim-pilares",
        ),
        cls="rodape-site",
    )


def pagina(
    titulo: str,
    *conteudo,
    usuario=None,
    subtitulo: str | None = None,
    acoes=None,
    voltar: str | None = "/",
    largura: str = "normal",
    **_compat,
):
    """Molde padrão de qualquer pagina interna (sem menu lateral).

    `**_compat` absorve os antigos parametros `ativo` e `pendencias`, que
    deixaram de existir com a remocao do menu lateral.
    """
    barra_acoes = list(acoes or [])
    if voltar:
        barra_acoes.insert(
            0, A("‹ Início", href=voltar, cls="btn secundario")
        )
    cabecalho = Div(
        Div(H1(titulo), P(subtitulo, cls="sub") if subtitulo else None),
        Div(*barra_acoes, cls="acoes") if barra_acoes else None,
        cls="cabecalho-pagina",
    )
    return (
        *cabeca(titulo),
        topbar(),
        faixa_usuario(usuario),
        Main(cabecalho, *conteudo, cls=f"conteudo {largura}"),
        rodape(),
    )


def molde_simples(titulo: str, *conteudo, usuario=None):
    """Molde sem cabecalho de pagina (usado pela home e pelo login)."""
    return (
        *cabeca(titulo),
        topbar(),
        faixa_usuario(usuario),
        Main(*conteudo, cls="conteudo aberto"),
        rodape(),
    )


# --------------------------------------------------------- Home publica
def hero(busca_acao: str = "/produtos", termo: str = ""):
    return Section(
        Div(
            Div(
                P("Bem-vindo ao Sistema de", cls="hero-linha"),
                H1(Span("Gestão de "), Span("Produtos Químicos", cls="verde")),
                P(
                    "Consulte informações, cadastre novas solicitações e acompanhe "
                    "todo o processo de aprovação de produtos químicos.",
                    cls="hero-texto",
                ),
                cls="hero-texto-bloco",
            ),
            Form(
                Span("⌕", cls="lupa"),
                Input(
                    type="search",
                    name="q",
                    value=termo,
                    placeholder="Pesquise por produto, fabricante, código interno, CAS...",
                    aria_label="Pesquisar produtos químicos",
                ),
                Button("Buscar", type="submit", cls="btn verde"),
                method="get",
                action=busca_acao,
                cls="hero-busca",
            ),
            cls="hero-interno",
        ),
        cls="hero",
    )


def _svg(*corpo: str, preenchido: str = "") -> NotStr:
    """SVG inline 24x24 que herda a cor do contêiner (currentColor)."""
    return NotStr(
        '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" '
        'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{"".join(corpo)}</svg>'
    )


# Ícones dos cartoes da pagina inicial (traço, sem dependencia externa).
ICONES = {
    "fds": _svg(
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>',
        '<path d="M14 3v5h5"/>',
        '<text x="12" y="17.4" font-size="5.4" font-family="Segoe UI, Arial, sans-serif"'
        ' font-weight="700" text-anchor="middle" stroke="none" fill="currentColor">FDS</text>',
    ),
    "identificacao": _svg(
        '<path d="M10 2h4v3h-4z"/>',
        '<path d="M9 5h6l1.6 3.2A4 4 0 0 1 17 10v9a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-9'
        'a4 4 0 0 1 .4-1.8z"/>',
        '<path d="M8 13h8"/>',
    ),
    "classificacao": _svg(
        '<path d="M12 2.6 21.4 12 12 21.4 2.6 12z"/>',
        '<path d="M12 8v4.6"/>',
        '<circle cx="12" cy="16.1" r=".9" fill="currentColor" stroke="none"/>',
    ),
    "aprovacoes": _svg(
        '<path d="M9 3h6v3H9z"/>',
        '<path d="M15 4.5h2a2 2 0 0 1 2 2V20a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6.5a2 2 0 0 1 2-2h2"/>',
        '<path d="M8.6 13.4l2.1 2.1 4.2-4.2"/>',
    ),
    "nova": _svg(
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
        '<path d="M14 3v5h5"/>',
        '<path d="M18.5 3.5v5M16 6h5"/>',
    ),
    "historico": _svg(
        '<path d="M3.2 12a8.8 8.8 0 1 0 2.6-6.2"/>',
        '<path d="M3 4.2V8h3.8"/>',
        '<path d="M12 7.6V12l3.2 1.9"/>',
    ),
    "relatorios": _svg(
        '<path d="M4 20h16"/>',
        '<path d="M7 20V12"/>',
        '<path d="M12 20V6"/>',
        '<path d="M17 20v-5.5"/>',
    ),
    "consultar": _svg(
        '<circle cx="10.8" cy="10.8" r="6.4"/>',
        '<path d="M15.6 15.6 21 21"/>',
    ),
    "kit": _svg(
        '<path d="M9.4 6.2V4.7A1.7 1.7 0 0 1 11.1 3h1.8a1.7 1.7 0 0 1 1.7 1.7v1.5"/>',
        '<rect x="3" y="6.2" width="18" height="14" rx="2"/>',
        '<path d="M12 10.6v5.2M9.4 13.2h5.2"/>',
    ),
    "controlados": _svg(
        '<rect x="4.6" y="10.4" width="14.8" height="10.2" rx="2"/>',
        '<path d="M8 10.4V7.9a4 4 0 0 1 8 0v2.5"/>',
        '<circle cx="12" cy="15.5" r="1.15" fill="currentColor" stroke="none"/>',
    ),
    "recursos": _svg(
        '<path d="M4 5.4A1.8 1.8 0 0 1 5.8 3.6h4a2.4 2.4 0 0 1 2.2 1.4v13.6'
        'a2.3 2.3 0 0 0-1.8-.9H4z"/>',
        '<path d="M20 5.4a1.8 1.8 0 0 0-1.8-1.8h-4A2.4 2.4 0 0 0 12 5v13.6'
        'a2.3 2.3 0 0 1 1.8-.9H20z"/>',
    ),
}


def cartao_atalho(icone, titulo: str, descricao: str, href: str, cor: str = "azul",
                  etiqueta: str | None = None):
    return A(
        Div(Span(icone, cls="glifo"), cls=f"atalho-icone {cor}"),
        Div(
            H3(titulo, Span(etiqueta, cls="etiqueta") if etiqueta else None),
            P(descricao),
            cls="atalho-texto",
        ),
        Span("›", cls="seta"),
        href=href,
        cls="atalho",
    )


# ------------------------------------------------------------ Elementos
def badge(status: str):
    classe = status.lower().replace("_", "-")
    return Span(STATUS.get(status, status), cls=f"badge {classe}")


def alerta(mensagem, tipo: str = "info"):
    if not mensagem:
        return None
    return Div(mensagem, cls=f"alerta {tipo}" if tipo != "info" else "alerta")


def passos(produto):
    """Mini indicador do andamento: um traço por área, sem ordem."""
    itens = []
    for ap in produto.aprovacoes:
        if ap.decisao == "APROVADO":
            classe = "ok"
        elif ap.decisao == "REPROVADO":
            classe = "recusado"
        elif produto.aguarda(ap.etapa):
            classe = "atual"
        else:
            classe = ""
        situacao = {"APROVADO": "aprovado", "REPROVADO": "reprovado"}.get(
            ap.decisao, "aguardando" if classe == "atual" else "não iniciada"
        )
        itens.append(I(cls=classe or None, title=f"{ap.etapa_label}: {situacao}"))
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


def _parecer_area(ap, produto, mostrar_parecer: bool = True):
    """Cartão com a situação de uma área (sem número de ordem)."""
    if ap.decisao == "APROVADO":
        classe, sinal, situacao = "aprovado", "✓", "Aprovado"
    elif ap.decisao == "REPROVADO":
        classe, sinal, situacao = "reprovado", "✕", "Reprovado"
    elif produto.aguarda(ap.etapa):
        classe, sinal, situacao = "atual", "•", "Aguardando análise"
    else:
        classe, sinal, situacao = "", "•", (
            "Aguarda as demais áreas" if ap.etapa == ETAPA_FINAL else "Não iniciada"
        )

    if ap.decisao == "PENDENTE":
        meta = situacao
    else:
        quem = ap.aprovador.nome if ap.aprovador else "-"
        quando = ap.decidido_em.strftime("%d/%m/%Y %H:%M") if ap.decidido_em else "-"
        meta = f"{situacao} por {quem} em {quando}"

    return Div(
        Div(sinal, cls="marcador"),
        Div(
            Div(ap.etapa_label, cls="etapa"),
            Div(meta, cls="meta"),
            Div(ap.parecer, cls="parecer") if (ap.parecer and mostrar_parecer) else None,
            cls="txt",
        ),
        cls=f"area-parecer {classe}".strip(),
    )


def linha_fluxo(produto, mostrar_parecer: bool = True):
    """Pareceres por área.

    Não existe ordem entre Meio Ambiente, Saúde, Segurança e Químico
    Responsável: as quatro analisam ao mesmo tempo. O Aprovador Final é o
    único passo fixo e aparece destacado, depois das áreas.
    """
    por_etapa = {ap.etapa: ap for ap in produto.aprovacoes}
    areas = [por_etapa[chave] for chave, _ in AREAS_APROVACAO if chave in por_etapa]
    final = por_etapa.get(ETAPA_FINAL)

    blocos = [
        Div(
            *[_parecer_area(ap, produto, mostrar_parecer) for ap in areas],
            cls="areas-parecer",
        )
    ]
    if final is not None:
        blocos.append(
            Div(
                Span("Depois das áreas", cls="rotulo-final"),
                _parecer_area(final, produto, mostrar_parecer),
                cls="bloco-final",
            )
        )
    return Div(*blocos, cls="pareceres")


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
