"""
=====================================================================
 Gestão de Produtos Químicos - Tenaris
 Aplicação web em FastHTML (Python)
 ---------------------------------------------------------------------
 Como executar:
     pip install -r requirements.txt
     python main.py
     Abrir http://127.0.0.1:5001
=====================================================================
"""

import secrets
from datetime import date, datetime
from urllib.parse import quote, unquote

from fasthtml.common import *  # noqa: F403
from sqlalchemy import desc, select

import config
import extracao
import notificacoes
import servicos
import ui
from database import criar_tabelas, db_session, descricao_conexao
from models import (
    AREAS_SOLICITANTES,
    CATEGORIAS,
    CLASSES_RISCO,
    DOCUMENTOS_OBRIGATORIOS,
    ESTADOS_FISICOS,
    FABRICAS,
    FDS_ALERTA_MESES,
    FDS_VALIDADE_ANOS,
    FLUXO_APROVACAO,
    MOTIVOS_REPROVACAO,
    ORGAOS_CONTROLADORES,
    PAPEIS,
    SITUACOES_FDS,
    STATUS,
    STATUS_ABERTOS,
    TIPOS_DOCUMENTO,
    TIPOS_PRODUTO,
    Documento,
    LogAuditoria,
    Notificacao,
    Produto,
    Usuario,
)
from security import gerar_hash, verificar_senha

# =====================================================================
# Autenticacao (Beforeware)
# =====================================================================

#
# O site e' PUBLICO por padrão: qualquer pessoa na rede interna consulta
# produtos, fichas FDS e histórico sem login. O Beforeware abaixo apenas
# IDENTIFICA quem esta logado - ele nunca bloqueia.
#
# O login e' exigido explicitamente, rota por rota, pelos helpers
# `exigir_login` e `exigir_papel`.
#


def carregar_usuario(req, sess):
    """Carrega o usuario da sessao, se houver. Nunca redireciona."""
    req.scope["usuario"] = None
    req.scope["pendencias"] = 0
    uid = sess.get("uid")
    if not uid:
        return
    with db_session() as s:
        usuario = s.get(Usuario, uid)
        if usuario and usuario.ativo:
            req.scope["usuario"] = usuario
            req.scope["pendencias"] = servicos.contar_pendencias(s, usuario)
        else:
            sess.pop("uid", None)


bware = Beforeware(carregar_usuario)

app, rt = fast_app(
    pico=False,
    surreal=False,
    before=bware,
    secret_key=config.SECRET_KEY,
    title=config.APP_NOME,
    canonical=False,
)


def eu(req) -> Usuario | None:
    return req.scope.get("usuario")


def pend(req) -> int:
    return req.scope.get("pendencias", 0)


def logado(req) -> bool:
    return req.scope.get("usuario") is not None


def exigir_login(req):
    """Devolve um redirecionamento para /login quando não há usuario logado.

    Uso no inicio da rota:
        barrado = exigir_login(req)
        if barrado:
            return barrado
    """
    if logado(req):
        return None
    destino = quote(req.url.path, safe="/")
    if req.url.query:
        destino += "%3F" + quote(req.url.query, safe="")
    return RedirectResponse(f"/login?proximo={destino}", status_code=303)


def exigir_papel(req, *papeis: str):
    """Exige login E um dos papeis informados (ADMIN sempre passa)."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    if usuario.papel == "ADMIN" or usuario.papel in papeis:
        return None
    return RedirectResponse(
        "/?erro=" + quote("Seu perfil não tem permissão para acessar essa área."),
        status_code=303,
    )


def _msg(url: str, chave: str, texto: str) -> str:
    """Monta URL com mensagem devidamente codificada (acentos e espaços)."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{chave}={quote(texto)}"


def _data(valor) -> date | None:
    """Converte o texto de um <input type=date> (AAAA-MM-DD) em date."""
    if not valor or not isinstance(valor, str):
        return None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        return None


def _ler_controles(form) -> list[dict]:
    """Monta a lista de órgãos controladores marcados no formulário."""
    marcados = [v for v in form.getlist("orgaos") if v in ORGAOS_CONTROLADORES]
    return [
        {
            "orgao": chave,
            "numero_licenca": form.get(f"licenca_{chave}") or None,
            "validade_licenca": _data(form.get(f"validade_{chave}")),
        }
        for chave in marcados
    ]


@rt("/static/{fname:path}.{ext:static}")
def arquivos_estaticos(fname: str, ext: str):
    return FileResponse(config.BASE_DIR / "static" / f"{fname}.{ext}")


# =====================================================================
# Login / Logout
# =====================================================================


def _tela_login(mensagem: str | None = None, email: str = "", proximo: str = "/"):
    return (
        *ui.cabeca("Acesso ao sistema"),
        Div(
            Div(
                Div(
                    B(config.APP_EMPRESA),
                    Span("Gestão de Produtos Químicos"),
                    cls="topo",
                ),
                Div(
                    I(style="background:var(--verde)"),
                    I(style="background:var(--verde-claro)"),
                    I(style="background:var(--azul-claro)"),
                    I(style="background:var(--roxo)"),
                    cls="faixa",
                ),
                Div(
                    H2("Entrar"),
                    P(
                        "A identificação é necessária apenas para enviar novas "
                        "solicitações e registrar pareceres de aprovação.",
                        cls="texto-mudo pequeno",
                    ),
                    ui.alerta(mensagem, "erro") if mensagem else None,
                    Form(
                        ui.campo("E-mail corporativo", "email", "email", email, True),
                        ui.campo("Senha", "senha", "password", None, True),
                        Input(type="hidden", name="proximo", value=proximo),
                        Button("Entrar", cls="btn", type="submit"),
                        method="post",
                        action="/login",
                    ),
                    Div(
                        P(
                            "Consulta de produtos e FDS não exige login: ",
                            A("voltar ao início", href="/"),
                        ),
                        Div(
                            "Usuários de teste: ",
                            Code("ana.silva@tenaris.com"),
                            " ... senha ",
                            Code("tenaris123"),
                            cls="pequeno",
                        ),
                        cls="login-dicas",
                    ),
                    cls="corpo",
                ),
                cls="login-caixa",
            ),
            cls="login-fundo",
        ),
    )


@rt("/login")
def get(proximo: str = "/"):
    return _tela_login(proximo=proximo or "/")


@rt("/login")
async def post(req, sess):
    form = await req.form()
    email = (form.get("email") or "").strip().lower()
    senha = form.get("senha") or ""
    proximo = form.get("proximo") or "/"
    with db_session() as s:
        usuario = s.scalar(select(Usuario).where(Usuario.email == email))
        if not usuario or not usuario.ativo or not verificar_senha(senha, usuario.senha_hash):
            return _tela_login("E-mail ou senha inválidos.", email, proximo)
        sess["uid"] = usuario.id
        servicos.registrar_log(s, "LOGIN", f"Acesso de {usuario.email}", usuario.id)
    destino = unquote(proximo)
    return RedirectResponse(destino if destino.startswith("/") else "/", status_code=303)


@rt("/logout")
def get(sess):
    sess.pop("uid", None)
    return RedirectResponse("/", status_code=303)


# =====================================================================
# Dashboard
# =====================================================================


@rt("/")
def get(req, erro: str = "", ok: str = ""):
    """Pagina inicial PUBLICA: hero de busca + atalhos para as areas do sistema."""
    usuario = eu(req)
    with db_session() as s:
        ind = servicos.indicadores(s)

    aprovados = ind["por_status"].get("APROVADO", 0)

    atalhos = [
        ui.cartao_atalho(
            ui.ICONES["fds"], "FDS",
            "Consulte as Fichas de Dados de Segurança dos produtos químicos cadastrados.",
            "/fds", "verde",
        ),
        ui.cartao_atalho(
            ui.ICONES["nova"], "Cadastro",
            "Cadastre um novo produto químico anexando a FDS e inicie o fluxo de aprovação.",
            "/solicitacoes/nova", "azul", etiqueta=None if usuario else "login",
        ),
        ui.cartao_atalho(
            ui.ICONES["kit"], "Kit Ambiental",
            "Produtos e materiais aprovados para compor os kits de contenção ambiental.",
            "/kit-ambiental", "verde",
        ),
        ui.cartao_atalho(
            ui.ICONES["controlados"], "Produtos Controlados",
            "Produtos sujeitos a controle da Polícia Federal e do Exército, com "
            "autorização e validade.",
            "/produtos-controlados", "azul",
        ),
        ui.cartao_atalho(
            ui.ICONES["recursos"], "Recursos e Documentos",
            "Procedimentos, formulários, normas externas e material de treinamento.",
            "/recursos", "verde",
        ),
        ui.cartao_atalho(
            ui.ICONES["aprovacoes"], "Aprovações",
            "Acompanhe o fluxo de aprovação e o status das solicitações.",
            "/aprovacoes", "azul", etiqueta=None if usuario else "login",
        ),
    ]

    resumo = Div(
        Span(B(str(aprovados)), " produtos aprovados"),
        Span("•", cls="ponto"),
        Span(B(str(ind["total_fds"])), " fichas FDS disponíveis"),
        Span("•", cls="ponto"),
        Span(B(str(ind["por_status"].get("EM_ANALISE", 0))), " em análise"),
        cls="resumo-publico",
    )

    return ui.molde_simples(
        "Início",
        ui.hero(),
        Div(
            ui.alerta(erro, "erro") if erro else None,
            ui.alerta(ok, "sucesso") if ok else None,
            Div(*atalhos, cls="atalhos"),
            resumo,
            cls="faixa-atalhos",
        ),
        usuario=usuario,
    )


@rt("/painel")
def get(req):
    """Dashboard com indicadores. Exige login."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    with db_session() as s:
        ind = servicos.indicadores(s)
        recentes = list(
            s.scalars(select(Produto).order_by(desc(Produto.criado_em)).limit(8)).unique()
        )
        minhas_pendencias = (
            servicos.buscar_produtos(s, status="EM_ANALISE", limite=5)
            if usuario.papel == "ADMIN"
            else [
                p
                for p in servicos.buscar_produtos(s, status="EM_ANALISE", limite=100)
                if p.etapa_atual == usuario.papel
            ][:5]
        )

    kpis = Div(
        A(
            Div("Total de produtos", cls="rotulo"),
            Div(str(ind["total"]), cls="valor"),
            Div("cadastrados no sistema", cls="nota"),
            href="/historico",
            cls="kpi",
        ),
        A(
            Div("Em andamento", cls="rotulo"),
            Div(
                str(
                    ind["por_status"].get("PENDENTE", 0)
                    + ind["por_status"].get("EM_ANALISE", 0)
                ),
                cls="valor",
            ),
            Div("pendentes + em análise", cls="nota"),
            href="/aprovacoes",
            cls="kpi ambar",
        ),
        A(
            Div("Aguardando correção", cls="rotulo"),
            Div(str(ind["por_status"].get("AGUARDANDO_CORRECAO", 0)), cls="valor"),
            Div("devolvidas ao solicitante", cls="nota"),
            href="/aprovacoes?status=AGUARDANDO_CORRECAO",
            cls="kpi roxo",
        ),
        A(
            Div("Aprovados", cls="rotulo"),
            Div(str(ind["por_status"].get("APROVADO", 0)), cls="valor"),
            Div("liberados para uso", cls="nota"),
            href="/produtos",
            cls="kpi verde",
        ),
        A(
            Div("Reprovados", cls="rotulo"),
            Div(str(ind["por_status"].get("REPROVADO", 0)), cls="valor"),
            Div("não liberados", cls="nota"),
            href="/historico?status=REPROVADO",
            cls="kpi vermelho",
        ),
        A(
            Div("Descontinuados", cls="rotulo"),
            Div(str(ind["por_status"].get("DESCONTINUADO", 0)), cls="valor"),
            Div("fora de uso", cls="nota"),
            href="/historico?status=DESCONTINUADO",
            cls="kpi roxo",
        ),
        A(
            Div("Fichas FDS", cls="rotulo"),
            Div(str(ind["total_fds"]), cls="valor"),
            Div(f"{ind['total_documentos']} documentos no total", cls="nota"),
            href="/fds",
            cls="kpi azul-claro",
        ),
        cls="grade grade-6",
        style="margin-bottom:1.15rem",
    )

    alertas = []
    if ind["sem_fds"]:
        alertas.append(
            ui.alerta(
                Span(
                    B(f"{ind['sem_fds']} produto(s) sem FDS anexada. "),
                    "A FDS é documento obrigatório para aprovação.",
                ),
                "aviso",
            )
        )
    if not config.SMTP_ATIVO:
        alertas.append(
            ui.alerta(
                Span(
                    "Servidor de e-mail (SMTP) não configurado: as notificações estão sendo ",
                    "gravadas na ",
                    A("caixa de saída", href="/notificacoes"),
                    " em vez de enviadas.",
                ),
                "info",
            )
        )

    graficos = Div(
        Div(
            Div(H2("Produtos por categoria"), cls="card-titulo"),
            ui.barras(ind["por_categoria"][:8]),
            cls="card",
        ),
        Div(
            Div(
                H2("Pendências por etapa do fluxo"),
                Span(cls="direita"),
                cls="card-titulo",
            ),
            ui.barras(ind["por_etapa"]) if ind["por_etapa"] else ui.vazio("Nenhuma pendência.", "✓"),
            cls="card",
        ),
        cls="grade grade-2",
    )

    tabela_recentes = Div(
        Div(
            H2("Últimas solicitações"),
            A("Ver histórico completo", href="/historico", cls="direita"),
            cls="card-titulo",
        ),
        _tabela_produtos(recentes),
        cls="card",
    )

    fila = Div(
        Div(H2("Aguardando sua análise"), cls="card-titulo"),
        _tabela_produtos(minhas_pendencias)
        if minhas_pendencias
        else ui.vazio("Nada pendente para o seu papel.", "✓"),
        cls="card",
    )

    return ui.pagina(
        "Painel de indicadores",
        *alertas,
        kpis,
        fila if usuario.papel != "SOLICITANTE" else None,
        graficos,
        tabela_recentes,
        usuario=usuario,
        subtitulo=f"Visão geral - banco: {descricao_conexao()}",
    )


# =====================================================================
# Componentes de listagem
# =====================================================================


def _tabela_produtos(produtos, prefixo: str = "", mostrar_fluxo: bool = True):
    if not produtos:
        return ui.vazio("Nenhum produto encontrado com os filtros informados.", "⌕")
    linhas = []
    for p in produtos:
        linhas.append(
            Tr(
                Td(A(p.codigo_interno, href=f"{prefixo}/produtos/{p.id}"), cls="mono nowrap"),
                Td(B(p.nome_comercial), Br(), Span(p.categoria or "-", cls="pequeno texto-mudo")),
                Td(p.fabricante),
                Td(p.fornecedor or "-"),
                Td(ui.badge(p.status)),
                Td(
                    ui.passos(p),
                    Br(),
                    Span(p.etapa_label or "-", cls="pequeno texto-mudo"),
                )
                if mostrar_fluxo
                else None,
                Td(
                    Span("FDS", cls="badge info") if p.fds else Span("sem FDS", cls="badge neutro")
                ),
                Td(p.atualizado_em.strftime("%d/%m/%Y"), cls="pequeno nowrap"),
            )
        )
    cabecalhos = ["Código", "Produto", "Fabricante", "Fornecedor", "Status"]
    if mostrar_fluxo:
        cabecalhos.append("Fluxo")
    cabecalhos += ["Docs", "Atualizado"]
    return Div(
        Table(
            Thead(Tr(*[Th(c) for c in cabecalhos])),
            Tbody(*linhas),
            cls="dados",
        ),
        style="overflow-x:auto",
    )


def _barra_filtros(acao: str, termo: str, status: str, categoria: str, com_status: bool = True):
    campos = [
        ui.campo(
            "Buscar",
            "q",
            valor=termo,
            placeholder="nome, fabricante, fornecedor, código ou CAS",
        )
    ]
    if com_status:
        campos.append(
            ui.campo(
                "Status",
                "status",
                valor=status,
                opcoes=[(k, v) for k, v in STATUS.items()],
            )
        )
    campos.append(ui.campo("Categoria", "categoria", valor=categoria, opcoes=CATEGORIAS))
    return Form(
        Div(
            *campos,
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href=acao, cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action=acao,
    )


# =====================================================================
# Nova solicitação
# =====================================================================


@rt("/solicitacoes/nova")
def get(req, erro: str = ""):
    """Passo 1: anexar a FDS. Os dados são extraídos dela no passo 2."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)

    formulario = Form(
        Fieldset(
            Legend("Ficha de Dados de Segurança"),
            P(
                "Anexe a FDS mais recente fornecida pelo fabricante, em PDF. "
                "O sistema lê o documento e preenche o que encontrar; você "
                "confere e completa o resto no passo seguinte.",
                cls="texto-mudo",
            ),
            Label(
                Span("Arquivo da FDS", Span(" *", cls="obr"), cls="rot"),
                Input(type="file", name="arquivo_fds", accept=".pdf", required=True),
                Span(
                    f"Somente PDF, até {config.MAX_UPLOAD_MB} MB. A leitura acontece "
                    "no próprio servidor - o arquivo não sai da rede interna.",
                    cls="ajuda",
                ),
                cls="campo",
            ),
            cls="secao",
        ),
        Div(
            Button("Ler a FDS e continuar", cls="btn verde", type="submit"),
            A("Cancelar", href="/", cls="btn secundario"),
            cls="barra-acoes",
        ),
        method="post",
        action="/solicitacoes/ler-fds",
        enctype="multipart/form-data",
    )

    return ui.pagina(
        "Nova solicitação de produto químico",
        ui.alerta(erro, "erro") if erro else None,
        Div(
            Div(
                Div(Span("1", cls="num"), Span("Anexar a FDS"), cls="etapa-form atual"),
                Div(Span("2", cls="num"), Span("Conferir e completar"), cls="etapa-form"),
                Div(Span("3", cls="num"), Span("Enviar para aprovação"), cls="etapa-form"),
                cls="passos-form",
            ),
            cls="card",
        ),
        Div(
            Div(H2("Passo 1 de 3 - documento do produto"), cls="card-titulo"),
            formulario,
            cls="card",
        ),
        usuario=usuario,
        subtitulo="A leitura da FDS preenche automaticamente parte do formulário",
    )


# ---------------------------------------------------------------------
# Rascunhos em memória
# ---------------------------------------------------------------------
# O PDF anexado no passo 1 fica guardado aqui entre os dois passos, para não
# obrigar o usuário a anexar duas vezes. É memória do processo: some quando o
# servidor reinicia, e isso é aceitável - basta refazer o passo 1.

_RASCUNHOS: dict[str, dict] = {}
_RASCUNHO_VALIDADE = 3600  # segundos
_RASCUNHO_MAXIMO = 50


def _limpar_rascunhos() -> None:
    agora = datetime.now().timestamp()
    velhos = [
        t for t, r in _RASCUNHOS.items() if agora - r["criado"] > _RASCUNHO_VALIDADE
    ]
    for t in velhos:
        _RASCUNHOS.pop(t, None)
    while len(_RASCUNHOS) > _RASCUNHO_MAXIMO:
        _RASCUNHOS.pop(next(iter(_RASCUNHOS)), None)


def _guardar_rascunho(conteudo: bytes, nome: str, content_type: str | None) -> str:
    _limpar_rascunhos()
    token = secrets.token_urlsafe(16)
    _RASCUNHOS[token] = {
        "conteudo": conteudo,
        "nome": nome,
        "content_type": content_type,
        "criado": datetime.now().timestamp(),
    }
    return token


@rt("/solicitacoes/ler-fds")
async def post(req):
    """Recebe a FDS, extrai o que consegue e mostra o formulário do passo 2."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    enviado = form.get("arquivo_fds")
    if enviado is None or not getattr(enviado, "filename", ""):
        return RedirectResponse(
            _msg("/solicitacoes/nova", "erro", "Selecione o arquivo da FDS."),
            status_code=303,
        )
    conteudo = await enviado.read()
    if len(conteudo) > config.MAX_UPLOAD_BYTES:
        return RedirectResponse(
            _msg("/solicitacoes/nova", "erro",
                 f"O arquivo excede o limite de {config.MAX_UPLOAD_MB} MB."),
            status_code=303,
        )
    if not conteudo[:5].startswith(b"%PDF"):
        return RedirectResponse(
            _msg("/solicitacoes/nova", "erro",
                 "O arquivo não é um PDF válido. Anexe a FDS em PDF."),
            status_code=303,
        )

    dados, preenchidos, aviso = extracao.extrair_de_pdf(conteudo)
    token = _guardar_rascunho(
        conteudo, enviado.filename, getattr(enviado, "content_type", None)
    )
    return _formulario_solicitacao(
        usuario, token, enviado.filename, dados, preenchidos, aviso
    )


def _formulario_solicitacao(usuario, token, nome_arquivo, dados, preenchidos,
                            aviso=None, erro=None):
    """Passo 2: formulário com o que a FDS forneceu, para conferir e completar."""

    def auto(campo: str) -> str | None:
        return "Preenchido pela FDS - confira." if campo in preenchidos else None

    riscos_marcados = set(dados.get("riscos") or [])
    duplicado = dados.get("_duplicado")

    formulario = Form(
        Input(type="hidden", name="token", value=token),
        # Depois de ver o aviso de duplicidade, reenviar confirma que é outro produto.
        Input(type="hidden", name="confirmar_duplicado", value="1") if duplicado else None,
        Fieldset(
            Legend("Identificação do produto"),
            Div(
                ui.campo("Nome comercial", "nome_comercial",
                         valor=dados.get("nome_comercial", ""), obrigatório=True,
                         ajuda=auto("nome_comercial")),
                ui.campo("Nome do fabricante", "fabricante",
                         valor=dados.get("fabricante", ""), obrigatório=True,
                         ajuda=auto("fabricante")),
                cls="linha-form",
            ),
            Div(
                ui.campo("Fornecedor", "fornecedor", valor=dados.get("fornecedor", ""),
                         obrigatório=True,
                         ajuda="Quem fornece o produto para a Tenaris."),
                ui.campo("Número CAS", "numero_cas", valor=dados.get("numero_cas", ""),
                         obrigatório=True, ajuda=auto("numero_cas") or "Ex.: 67-64-1"),
                cls="linha-form",
            ),
            Div(
                ui.campo("Tipo de produto", "tipo_produto",
                         valor=dados.get("tipo_produto", ""), opcoes=TIPOS_PRODUTO,
                         obrigatório=True, ajuda=auto("tipo_produto")),
                ui.campo("Categoria química", "categoria",
                         valor=dados.get("categoria", ""), opcoes=CATEGORIAS,
                         obrigatório=True),
                ui.campo("Estado físico", "estado_fisico",
                         valor=dados.get("estado_fisico", ""), opcoes=ESTADOS_FISICOS,
                         obrigatório=True, ajuda=auto("estado_fisico")),
                cls="linha-form",
            ),
            cls="secao",
        ),
        Fieldset(
            Legend("Uso na planta"),
            Div(
                ui.campo("Unidade solicitante", "unidade_solicitante",
                         valor=dados.get("unidade_solicitante", ""),
                         opcoes=FABRICAS, obrigatório=True,
                         ajuda="Onde o produto será utilizado."),
                ui.campo("Área solicitante", "area_solicitante",
                         valor=dados.get("area_solicitante", ""),
                         opcoes=AREAS_SOLICITANTES, obrigatório=True),
                cls="linha-form",
            ),
            ui.campo(
                "Finalidade de uso", "aplicacao", valor=dados.get("aplicacao", ""),
                linhas=3, obrigatório=True,
                ajuda="Por que o produto é necessário e como será aplicado.",
            ),
            Div(
                ui.campo("Prazo de utilização", "prazo_utilizacao",
                         valor=dados.get("prazo_utilizacao", ""), obrigatório=True,
                         placeholder="Ex.: 12 meses / uso contínuo"),
                ui.campo("Quantidade prevista", "consumo_estimado",
                         valor=dados.get("consumo_estimado", ""), obrigatório=True,
                         placeholder="Ex.: 200"),
                ui.campo("Unidade de medida", "unidade",
                         valor=dados.get("unidade", ""), obrigatório=True,
                         placeholder="L/mês, kg/mês..."),
                cls="linha-form",
            ),
            cls="secao",
        ),
        Fieldset(
            Legend("Classificação de risco e controle"),
            Div(
                Span("Classe de risco", Span(" *", cls="obr"), cls="rot"),
                Div(
                    *[
                        Label(
                            Input(type="checkbox", name="riscos", value=classe,
                                  checked=(classe in riscos_marcados)),
                            Span(classe),
                            cls="caixa-marcar",
                        )
                        for classe in CLASSES_RISCO
                    ],
                    cls="grupo-marcar",
                ),
                Span(
                    "Marcadas conforme as frases de perigo encontradas na FDS. "
                    "Ajuste se necessário."
                    if "riscos" in preenchidos
                    else "Marque as classes que constam na Seção 2 da FDS.",
                    cls="ajuda",
                ),
                cls="campo",
            ),
            Div(
                ui.campo("Produto controlado", "orgao_controlador",
                         opcoes=[("NAO", "Não controlado")]
                         + [(k, v) for k, v in ORGAOS_CONTROLADORES.items()],
                         valor=dados.get("orgao_controlador") or "NAO",
                         obrigatório=True),
                ui.campo("Número da licença", "numero_licenca",
                         valor=dados.get("numero_licenca", ""),
                         ajuda="Somente para produto controlado."),
                ui.campo("Validade da licença", "validade_licenca", tipo="date",
                         valor=dados.get("validade_licenca", ""),
                         ajuda="Somente para produto controlado."),
                cls="linha-form",
            ),
            Div(
                ui.campo("Classificação GHS", "classificacao_ghs",
                         valor=dados.get("classificacao_ghs", ""), obrigatório=True,
                         ajuda=auto("classificacao_ghs")),
                ui.campo("Número ONU", "onu_numero", valor=dados.get("onu_numero", ""),
                         ajuda=auto("onu_numero") or "Deixe vazio se não aplicável."),
                cls="linha-form",
            ),
            cls="secao",
        ),
        Fieldset(
            Legend("Documento e observações"),
            Div(
                Div(
                    Span("FDS anexada", cls="rot"),
                    Div(
                        Span("PDF", cls="icone fds"),
                        Span(B(nome_arquivo), cls="nome"),
                        cls="doc anexado",
                    ),
                    cls="campo",
                ),
                ui.campo("Data de revisão da FDS", "data_revisao_fds", tipo="date",
                         valor=dados.get("data_revisao_fds", ""), obrigatório=True,
                         ajuda=auto("data_revisao_fds")
                         or f"Consta na ficha. Vale por {FDS_VALIDADE_ANOS} anos."),
                cls="linha-form",
            ),
            ui.campo("Observações", "observacoes", valor=dados.get("observacoes", ""),
                     linhas=3, obrigatório=True,
                     ajuda="Informações complementares para os aprovadores."),
            cls="secao",
        ),
        Div(
            Button("Enviar para aprovação", cls="btn verde", type="submit"),
            A("Trocar a FDS", href="/solicitacoes/nova", cls="btn secundario"),
            Span(
                "Ao enviar, a solicitação segue para Meio Ambiente.",
                cls="pequeno texto-mudo direita",
            ),
            cls="barra-acoes",
        ),
        method="post",
        action="/solicitacoes/nova",
    )

    resumo_leitura = (
        ui.alerta(
            Span(
                B(f"{len(preenchidos)} campo(s) preenchidos pela FDS. "),
                "Confira os valores antes de enviar - a leitura automática é uma "
                "sugestão, não substitui a conferência.",
            ),
            "sucesso",
        )
        if preenchidos
        else None
    )

    return ui.pagina(
        "Nova solicitação de produto químico",
        Div(
            Div(
                Div(Span("✓", cls="num"), Span("Anexar a FDS"), cls="etapa-form feita"),
                Div(Span("2", cls="num"), Span("Conferir e completar"),
                    cls="etapa-form atual"),
                Div(Span("3", cls="num"), Span("Enviar para aprovação"), cls="etapa-form"),
                cls="passos-form",
            ),
            cls="card",
        ),
        ui.alerta(erro, "erro") if erro else None,
        ui.alerta(aviso, "aviso") if aviso else None,
        ui.alerta(
            Span(
                B("Produto possivelmente já cadastrado: "),
                A(duplicado, href=dados.get("_duplicado_url", "#")),
                ". Verifique antes de enviar para não duplicar o cadastro.",
            ),
            "aviso",
        )
        if duplicado
        else None,
        resumo_leitura,
        Div(
            Div(
                H2("Passo 2 de 3 - conferir e completar"),
                Span("Todos os campos são obrigatórios", cls="direita"),
                cls="card-titulo",
            ),
            formulario,
            cls="card",
        ),
        usuario=usuario,
        subtitulo="Campos marcados como preenchidos pela FDS devem ser conferidos",
    )


@rt("/solicitacoes/nova")
async def post(req):
    """Passo 3: valida tudo, grava a solicitação e dispara o fluxo."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}

    token = dados.get("token") or ""
    rascunho = _RASCUNHOS.get(token)
    if not rascunho:
        return RedirectResponse(
            _msg("/solicitacoes/nova", "erro",
                 "A sessão do formulário expirou. Anexe a FDS novamente."),
            status_code=303,
        )

    riscos = [r for r in form.getlist("riscos") if r in CLASSES_RISCO]
    unidade_solicitante = dados.get("unidade_solicitante") or ""
    orgao = dados.get("orgao_controlador") or "NAO"
    revisao = _data(dados.get("data_revisao_fds"))

    def voltar(mensagem: str):
        """Reapresenta o passo 2 com o que o usuário já digitou."""
        preservado = dict(dados)
        preservado["riscos"] = riscos
        return _formulario_solicitacao(
            usuario, token, rascunho["nome"], preservado,
            preenchidos=[], erro=mensagem,
        )

    # --- validações automáticas (todos os campos são obrigatórios) ---
    obrigatorios = [
        ("nome_comercial", "Nome comercial"),
        ("fabricante", "Nome do fabricante"),
        ("fornecedor", "Fornecedor"),
        ("numero_cas", "Número CAS"),
        ("tipo_produto", "Tipo de produto"),
        ("categoria", "Categoria química"),
        ("estado_fisico", "Estado físico"),
        ("area_solicitante", "Área solicitante"),
        ("aplicacao", "Finalidade de uso"),
        ("prazo_utilizacao", "Prazo de utilização"),
        ("consumo_estimado", "Quantidade prevista"),
        ("unidade", "Unidade de medida"),
        ("classificacao_ghs", "Classificação GHS"),
        ("observacoes", "Observações"),
    ]
    faltando = [rotulo for campo, rotulo in obrigatorios if not dados.get(campo)]
    if unidade_solicitante not in FABRICAS:
        faltando.append("Unidade solicitante")
    if not riscos:
        faltando.append("Classe de risco")
    if revisao is None:
        faltando.append("Data de revisão da FDS")
    if faltando:
        return voltar("Preencha os campos obrigatórios: " + ", ".join(faltando) + ".")

    if orgao != "NAO" and orgao in ORGAOS_CONTROLADORES and not dados.get("numero_licenca"):
        return voltar(
            "Produto controlado exige o número da licença do órgão selecionado."
        )
    if revisao > date.today():
        return voltar("A data de revisão da FDS não pode estar no futuro.")

    dados["fabricas"] = [unidade_solicitante]
    dados["setor_solicitante"] = dados.get("area_solicitante")
    dados["riscos"] = riscos
    dados["controles"] = (
        [
            {
                "orgao": orgao,
                "numero_licenca": dados.get("numero_licenca"),
                "validade_licenca": _data(dados.get("validade_licenca")),
            }
        ]
        if orgao in ORGAOS_CONTROLADORES
        else []
    )

    arquivos = [
        {
            "tipo": "FDS",
            "nome": rascunho["nome"],
            "content_type": rascunho["content_type"],
            "conteudo": rascunho["conteudo"],
            "data_revisao": revisao,
        }
    ]

    with db_session() as s:
        duplicado = servicos.produto_duplicado(
            s, dados["nome_comercial"], dados["fabricante"]
        )
        if duplicado and not dados.get("confirmar_duplicado"):
            info = dict(dados)
            info["riscos"] = riscos
            info["_duplicado"] = f"{duplicado.codigo_interno} - {duplicado.nome_comercial}"
            info["_duplicado_url"] = f"/produtos/{duplicado.id}"
            return _formulario_solicitacao(
                usuario, token, rascunho["nome"], info, preenchidos=[],
                erro="Já existe um cadastro com esse nome comercial e fabricante. "
                     "Confira o registro indicado acima; se ainda assim for outro "
                     "produto, reenvie o formulário para confirmar.",
            )
        dados["codigo_interno"] = servicos.proximo_codigo(s)
        produto = servicos.criar_solicitacao(s, dados, s.get(Usuario, usuario.id), arquivos)
        pid = produto.id

    _RASCUNHOS.pop(token, None)
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok", "Solicitação enviada para aprovação."),
        status_code=303,
    )


# =====================================================================
# Minhas solicitações / Aprovações pendentes
# =====================================================================


@rt("/minhas")
def get(req):
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    with db_session() as s:
        produtos = list(
            s.scalars(
                select(Produto)
                .where(Produto.solicitante_id == usuario.id)
                .order_by(desc(Produto.criado_em))
            ).unique()
        )
    return ui.pagina(
        "Minhas solicitações",
        Div(_tabela_produtos(produtos), cls="card"),
        usuario=usuario,
        ativo="/minhas",
        subtitulo=f"{len(produtos)} solicitação(ões) enviada(s) por você",
        acoes=[A("+ Nova solicitação", href="/solicitacoes/nova", cls="btn")],
        pendencias=pend(req),
    )


def _tabela_solicitacoes(produtos, papel_usuario: str):
    """Tabela do módulo de aprovações, com as colunas que o aprovador precisa."""
    if not produtos:
        return ui.vazio("Nenhuma solicitação encontrada com esses filtros.", "☑")
    linhas = []
    for p in produtos:
        minha = (
            p.status in ("PENDENTE", "EM_ANALISE")
            and p.etapa_atual == papel_usuario
        )
        linhas.append(
            Tr(
                Td(A(p.codigo_interno, href=f"/produtos/{p.id}"), cls="mono nowrap"),
                Td(
                    B(p.nome_comercial),
                    Br(),
                    Span(p.categoria or "sem categoria", cls="pequeno texto-mudo"),
                ),
                Td(p.fabricante),
                Td(p.solicitante.nome, Br(),
                   Span(p.setor_solicitante or "-", cls="pequeno texto-mudo")),
                Td(
                    Div(*[Span(n, cls="chip fabrica") for n in p.fabricas_nomes],
                        cls="fds-etiquetas")
                    if p.fabricas_nomes
                    else Span("-", cls="texto-mudo")
                ),
                Td(
                    p.criado_em.strftime("%d/%m/%Y"),
                    Br(),
                    Span(
                        f"{p.dias_em_aberto} dias em aberto" if p.aberta else "encerrada",
                        cls="pequeno texto-mudo",
                    ),
                    cls="nowrap",
                ),
                Td(
                    ui.badge(p.status),
                    Br(),
                    Span(p.etapa_label or "-", cls="pequeno texto-mudo"),
                ),
                Td(
                    A("Analisar", href=f"/produtos/{p.id}", cls="btn pequeno")
                    if minha
                    else A("Abrir", href=f"/produtos/{p.id}", cls="btn pequeno secundario"),
                    cls="nowrap",
                ),
                cls="minha-etapa" if minha else None,
            )
        )
    return Div(
        Table(
            Thead(
                Tr(Th("Nº"), Th("Produto"), Th("Fabricante"), Th("Solicitante"),
                   Th("Unidade"), Th("Data"), Th("Status"), Th(""))
            ),
            Tbody(*linhas),
            cls="dados",
        ),
        style="overflow-x:auto",
    )


@rt("/aprovacoes")
def get(req, status: str = "", fabrica: str = "", solicitante: str = "",
        de: str = "", ate: str = "", q: str = ""):
    """Gestão do fluxo de aprovação. Exige login."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)

    with db_session() as s:
        # Todo aprovador vê todas as solicitações abertas; agir, só na sua etapa.
        produtos = servicos.buscar_produtos(
            s, q, status=status, fabrica=fabrica,
            solicitante_id=int(solicitante) if solicitante.isdigit() else None,
            data_de=_data(de), data_ate=_data(ate),
            somente_abertas=not status,
            limite=None,
        )
        contagem = {
            chave: sum(1 for p in produtos if p.status == chave)
            for chave in STATUS_ABERTOS
        }
        minhas = sum(
            1
            for p in produtos
            if p.status in ("PENDENTE", "EM_ANALISE") and p.etapa_atual == usuario.papel
        )
        solicitantes = list(
            s.scalars(select(Usuario).order_by(Usuario.nome)).unique()
        )
        opcoes_solicitante = [(str(u.id), u.nome) for u in solicitantes]

    painel = Div(
        A(
            Div(str(minhas), cls="valor"),
            Div("Aguardando você", cls="rotulo"),
            href="/aprovacoes",
            cls="kpi-fds destaque",
        ),
        A(
            Div(str(contagem.get("PENDENTE", 0)), cls="valor"),
            Div("Pendentes - ninguém analisou", cls="rotulo"),
            href="/aprovacoes?status=PENDENTE",
            cls="kpi-fds",
        ),
        A(
            Div(str(contagem.get("EM_ANALISE", 0)), cls="valor"),
            Div("Em análise", cls="rotulo"),
            href="/aprovacoes?status=EM_ANALISE",
            cls="kpi-fds",
        ),
        A(
            Div(str(contagem.get("AGUARDANDO_CORRECAO", 0)), cls="valor"),
            Div("Aguardando correção", cls="rotulo"),
            href="/aprovacoes?status=AGUARDANDO_CORRECAO",
            cls="kpi-fds",
        ),
        cls="painel-fds",
    )

    filtros = Form(
        Div(
            ui.campo("Buscar", "q", valor=q, placeholder="produto, fabricante ou código"),
            ui.campo("Status", "status", valor=status,
                     opcoes=[(k, STATUS[k]) for k in
                             ("PENDENTE", "EM_ANALISE", "AGUARDANDO_CORRECAO",
                              "APROVADO", "REPROVADO")]),
            ui.campo("Unidade", "fabrica", valor=fabrica, opcoes=FABRICAS),
            ui.campo("Solicitante", "solicitante", valor=solicitante,
                     opcoes=opcoes_solicitante),
            ui.campo("Data inicial", "de", tipo="date", valor=de),
            ui.campo("Data final", "ate", tipo="date", valor=ate),
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href="/aprovacoes", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/aprovacoes",
    )

    return ui.pagina(
        "Aprovações",
        painel,
        Div(filtros, cls="card"),
        ui.alerta(
            Span(
                "Sem filtro de status a lista mostra apenas as solicitações ",
                B("em aberto"),
                ". As linhas destacadas são as que dependem do seu parecer como ",
                B(PAPEIS.get(usuario.papel, usuario.papel)),
                ".",
            ),
            "info",
        ),
        Div(
            Div(
                H2("Solicitações"),
                Span(f"{len(produtos)} registro(s)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_solicitacoes(produtos, usuario.papel),
            cls="card",
        ),
        usuario=usuario,
        subtitulo="Gestão do fluxo de validação dos produtos químicos",
    )


# =====================================================================
# Consulta de produtos / historico
# =====================================================================


@rt("/produtos")
def get(req, q: str = "", status: str = "", categoria: str = ""):
    """Consulta aberta. Sem login, apenas produtos APROVADOS aparecem."""
    usuario = eu(req)
    publico = usuario is None
    if publico:
        status = "APROVADO"
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, status or "APROVADO", categoria, somente_aprovados=not status
        )
    return ui.pagina(
        "Produtos químicos",
        Div(
            _barra_filtros(
                "/produtos", q, status or "APROVADO", categoria, com_status=not publico
            ),
            cls="card",
        ),
        ui.alerta(
            "Consulta pública: são exibidos apenas os produtos aprovados e liberados "
            "para uso. Para ver solicitações em análise, reprovadas ou descontinuadas, "
            "é necessário entrar no sistema.",
            "info",
        )
        if publico
        else None,
        Div(
            Div(
                H2("Resultado da consulta"),
                Span(f"{len(produtos)} produto(s)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_produtos(produtos, mostrar_fluxo=not publico),
            cls="card",
        ),
        usuario=usuario,
        subtitulo="Catálogo de produtos químicos cadastrados",
    )


@rt("/classificacao")
def get(req, q: str = "", categoria: str = ""):
    """Consulta aberta de classificação de perigo (GHS, ONU, EPI)."""
    usuario = eu(req)
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, categoria=categoria, somente_aprovados=usuario is None, limite=None
        )
    linhas = [
        Tr(
            Td(A(p.codigo_interno, href=f"/produtos/{p.id}"), cls="mono nowrap"),
            Td(B(p.nome_comercial), Br(),
               Span(p.fabricante, cls="pequeno texto-mudo")),
            Td(p.categoria or "-"),
            Td(p.estado_fisico or "-"),
            Td(p.classificacao_ghs or Span("não informada", cls="texto-mudo")),
            Td(Span(p.onu_numero, cls="mono") if p.onu_numero else "-", cls="nowrap"),
            Td(p.epi_recomendado or "-", cls="pequeno"),
            Td(ui.badge(p.status)),
        )
        for p in produtos
    ]
    tabela = (
        Div(
            Table(
                Thead(
                    Tr(
                        Th("Código"), Th("Produto"), Th("Categoria"), Th("Estado físico"),
                        Th("Classificação GHS"), Th("ONU"), Th("EPI recomendado"), Th("Status"),
                    )
                ),
                Tbody(*linhas),
                cls="dados",
            ),
            style="overflow-x:auto",
        )
        if linhas
        else ui.vazio("Nenhum produto encontrado.", "◈")
    )
    busca = Form(
        Div(
            ui.campo("Buscar", "q", valor=q,
                     placeholder="produto, fabricante, código, CAS ou classificação"),
            ui.campo("Categoria", "categoria", valor=categoria, opcoes=CATEGORIAS),
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href="/classificacao", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/classificacao",
    )
    return ui.pagina(
        "Classificação de perigo",
        Div(busca, cls="card"),
        ui.alerta(
            "A classificação abaixo reproduz o que consta na FDS do produto. "
            "Em caso de divergência, a FDS do fabricante prevalece.",
            "aviso",
        ),
        Div(
            Div(
                H2("Classificação, riscos e cuidados"),
                Span(f"{len(produtos)} produto(s)", cls="direita"),
                cls="card-titulo",
            ),
            tabela,
            cls="card",
        ),
        usuario=usuario,
        subtitulo="Classificação GHS, número ONU e EPI recomendado por produto",
    )


# =====================================================================
# Áreas novas - ainda em construção (layout aprovado, dados pendentes)
# =====================================================================


def _em_construcao(titulo: str, subtitulo: str, resumo, itens, tecnico=None,
                   usuario=None, atalhos=None):
    """Molde das páginas cujo escopo já foi definido mas os dados ainda não."""
    return ui.pagina(
        titulo,
        ui.alerta(
            Span(
                B("Área em construção. "),
                "O escopo desta página já está definido (veja abaixo), mas o "
                "cadastro dos dados ainda não foi implementado.",
            ),
            "aviso",
        ),
        Div(
            Div(H2("O que esta área vai conter"), cls="card-titulo"),
            P(resumo),
            Ul(*[Li(t) for t in itens], style="line-height:1.8;margin:0;padding-left:1.2rem"),
            cls="card",
        ),
        Div(
            Div(H2("O que falta no sistema"), cls="card-titulo"),
            Ul(*[Li(t) for t in tecnico],
               style="line-height:1.8;margin:0;padding-left:1.2rem"),
            cls="card",
        )
        if tecnico
        else None,
        Div(*(atalhos or []), cls="barra-acoes") if atalhos else None,
        usuario=usuario,
        subtitulo=subtitulo,
    )


@rt("/kit-ambiental")
def get(req):
    """Kit Ambiental: produtos e materiais aprovados para os kits de contenção."""
    usuario = eu(req)
    with db_session() as s:
        candidatos = servicos.buscar_produtos(
            s, "", somente_aprovados=True, limite=None
        )
    return _em_construcao(
        "Kit Ambiental",
        "Produtos e materiais aprovados para compor os kits de contenção ambiental",
        "Lista dos produtos químicos e materiais absorventes liberados para uso nos "
        "kits ambientais da planta, para que quem monta ou repõe um kit saiba "
        "exatamente o que pode entrar nele.",
        [
            "Relação dos itens aprovados para compor o kit (absorventes, "
            "neutralizantes, barreiras de contenção, EPI).",
            "Quantidade mínima de cada item por kit.",
            "Link direto para a FDS e a Ficha de Emergência de cada item.",
            "Indicação de quais produtos químicos da planta cada item atende.",
        ],
        [
            "Marcar no cadastro do produto se ele integra o kit ambiental "
            "(campo novo em `produtos`).",
            "Tabela de itens do kit para os materiais que não são produtos "
            "químicos cadastrados (absorvente, manta, pá antifaísca).",
            "Definir quem mantém essa lista - sugestão: Meio Ambiente.",
        ],
        usuario=usuario,
        atalhos=[
            A(f"Ver os {len(candidatos)} produtos aprovados", href="/produtos",
              cls="btn secundario"),
            A("Consultar FDS", href="/fds", cls="btn secundario"),
        ],
    )


@rt("/produtos-controlados")
def get(req, q: str = "", orgao: str = ""):
    """Produtos sujeitos a controle legal, com licença e validade."""
    usuario = eu(req)
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, somente_aprovados=usuario is None,
            orgao=orgao or "QUALQUER", limite=None,
        )

    vencidas = sum(1 for p in produtos if p.licenca_vencida)

    linhas = []
    for p in produtos:
        for c in p.controles:
            if orgao and c.orgao != orgao:
                continue
            linhas.append(
                Tr(
                    Td(A(p.codigo_interno, href=f"/produtos/{p.id}"), cls="mono nowrap"),
                    Td(B(p.nome_comercial), Br(),
                       Span(p.fabricante, cls="pequeno texto-mudo")),
                    Td(B(c.orgao_label), cls="nowrap"),
                    Td(c.numero_licenca or Span("-", cls="texto-mudo"), cls="mono pequeno"),
                    Td(
                        Span(
                            c.validade_licenca.strftime("%d/%m/%Y"),
                            cls="badge reprovado" if c.vencida else "badge aprovado",
                        )
                        if c.validade_licenca
                        else Span("não informada", cls="texto-mudo pequeno"),
                        cls="nowrap",
                    ),
                    Td(_pontos_semaforo(p.fds_situacao), cls="nowrap"),
                    Td(ui.badge(p.status)),
                )
            )

    busca = Form(
        Div(
            ui.campo("Buscar", "q", valor=q, placeholder="produto, fabricante ou código"),
            ui.campo(
                "Órgão controlador", "orgao", valor=orgao,
                opcoes=[(k, v) for k, v in ORGAOS_CONTROLADORES.items()],
            ),
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href="/produtos-controlados", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/produtos-controlados",
    )

    return ui.pagina(
        "Produtos Controlados",
        ui.alerta(
            Span(
                B(f"{vencidas} produto(s) com licença vencida. "),
                "Operar com autorização expirada é irregular - renove antes do uso.",
            ),
            "erro",
        )
        if vencidas
        else None,
        Div(busca, cls="card"),
        Div(
            Div(
                H2("Produtos sujeitos a controle legal"),
                Span(f"{len(linhas)} vínculo(s)", cls="direita"),
                cls="card-titulo",
            ),
            Div(
                Table(
                    Thead(
                        Tr(Th("Código"), Th("Produto"), Th("Órgão"), Th("Licença"),
                           Th("Validade"), Th("FDS"), Th("Status"))
                    ),
                    Tbody(*linhas),
                    cls="dados",
                ),
                style="overflow-x:auto",
            )
            if linhas
            else ui.vazio("Nenhum produto controlado encontrado.", "⚿"),
            cls="card",
        ),
        usuario=usuario,
        subtitulo="Polícia Federal, Polícia Civil e Exército Brasileiro",
    )


@rt("/recursos")
def get(req):
    """Biblioteca de documentos, formulários, normas e treinamentos."""
    usuario = eu(req)
    return _em_construcao(
        "Recursos e Documentos",
        "Procedimentos, formulários, normas externas e material de treinamento",
        "Biblioteca de documentos que não pertencem a um produto específico, "
        "organizada em quatro seções, com download aberto a qualquer colaborador "
        "da rede interna.",
        [
            Span(
                B("Procedimentos e políticas internas"),
                " - procedimentos de manuseio, políticas de SSMA, instruções de trabalho.",
            ),
            Span(
                B("Formulários e modelos"),
                " - planilhas e formulários em branco para download "
                "(requisição, checklist de inspeção).",
            ),
            Span(
                B("Links e normas externas"),
                " - legislação e normas (ABNT, NRs, ANTT, CONAMA) e sites de "
                "órgãos reguladores.",
            ),
            Span(
                B("Treinamentos e material de apoio"),
                " - apresentações, cartilhas e vídeos sobre manuseio de produtos químicos.",
            ),
        ],
        [
            "Tabela nova de documentos gerais, com seção, título, versão, "
            "data de revisão e arquivo.",
            "Tela de upload restrita (sugestão: Saúde e Segurança, Meio Ambiente e Admin).",
            "Para a seção de links externos, guardar URL em vez de arquivo.",
        ],
        usuario=usuario,
    )


@rt("/historico")
def get(req, q: str = "", status: str = "", categoria: str = ""):
    usuario = eu(req)
    publico = usuario is None
    if publico:
        status = "APROVADO"
    with db_session() as s:
        produtos = servicos.buscar_produtos(s, q, status, categoria, limite=None)
        eventos = list(
            s.scalars(
                select(LogAuditoria).order_by(desc(LogAuditoria.criado_em)).limit(12)
            ).unique()
        )
    return ui.pagina(
        "Histórico completo",
        Div(
            _barra_filtros("/historico", q, status, categoria, com_status=not publico),
            cls="card",
        ),
        ui.alerta(
            "Consulta pública: apenas produtos aprovados. O histórico completo, "
            "com solicitações em análise e reprovadas, exige login.",
            "info",
        )
        if publico
        else None,
        Div(
            Div(
                H2("Produtos aprovados" if publico else "Todas as solicitações"),
                Span(f"{len(produtos)} registro(s)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_produtos(produtos, mostrar_fluxo=not publico),
            cls="card",
        ),
        Div(
            Div(H2("Movimentações recentes"),
                A("Auditoria completa", href="/auditoria", cls="direita"),
                cls="card-titulo"),
            _tabela_eventos(eventos),
            cls="card",
        )
        if not publico
        else None,
        usuario=usuario,
        subtitulo="Produtos aprovados" if publico
        else "Aprovados, reprovados, descontinuados e em análise",
    )


def _tabela_eventos(eventos):
    """Histórico de ações. Quando houve troca de status, mostra de onde para onde."""
    if not eventos:
        return ui.vazio("Nenhum evento registrado.")
    return Div(
        Table(
            Thead(
                Tr(Th("Data"), Th("Usuário"), Th("Ação"), Th("Status"), Th("Detalhe"),
                   Th("Produto"))
            ),
            Tbody(
                *[
                    Tr(
                        Td(e.criado_em.strftime("%d/%m/%Y %H:%M"), cls="pequeno nowrap"),
                        Td(
                            e.usuario.nome if e.usuario else "-",
                            Br(),
                            Span(e.usuario.papel_label if e.usuario else "sistema",
                                 cls="pequeno texto-mudo"),
                        ),
                        Td(Span(e.acao, cls="chip")),
                        Td(
                            Span(
                                Span(e.status_anterior_label, cls="badge neutro")
                                if e.status_anterior
                                else None,
                                Span(" → ", cls="texto-mudo") if e.status_anterior else None,
                                ui.badge(e.status_novo),
                                cls="transicao",
                            )
                            if e.status_novo
                            else Span("-", cls="texto-mudo"),
                            cls="nowrap",
                        ),
                        Td(e.detalhe or "-", cls="pequeno"),
                        Td(
                            A(e.produto.codigo_interno, href=f"/produtos/{e.produto_id}", cls="mono")
                            if e.produto
                            else "-"
                        ),
                    )
                    for e in eventos
                ]
            ),
            cls="dados",
        ),
        style="overflow-x:auto",
    )


# =====================================================================
# Detalhe do produto + decisao
# =====================================================================


@rt("/produtos/{pid}")
def get(req, pid: int, ok: str = "", erro: str = ""):
    usuario = eu(req)
    publico = usuario is None
    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return ui.pagina(
                "Produto não encontrado",
                ui.alerta("Registro inexistente.", "erro"),
                usuario=usuario,
            )
        if publico and produto.status != "APROVADO":
            return ui.pagina(
                "Produto não disponível para consulta pública",
                ui.alerta(
                    "Somente produtos aprovados ficam disponíveis sem login. "
                    "Se você participa do fluxo de aprovação, entre no sistema.",
                    "aviso",
                ),
                Div(
                    A("Entrar no sistema", href=f"/login?proximo=/produtos/{pid}", cls="btn"),
                    A("Consultar produtos aprovados", href="/produtos", cls="btn secundario"),
                    cls="barra-acoes",
                ),
                usuario=usuario,
            )
        u_atual = None if publico else s.get(Usuario, usuario.id)
        pode = False if publico else servicos.pode_decidir(u_atual, produto)
        pode_reenviar = False if publico else servicos.pode_corrigir(u_atual, produto)
        obs = [] if publico else servicos.observacoes(s, pid)
        eventos = (
            []
            if publico
            else list(
                s.scalars(
                    select(LogAuditoria)
                    .where(LogAuditoria.produto_id == pid)
                    .order_by(desc(LogAuditoria.criado_em))
                ).unique()
            )
        )

    ficha = Div(
        ui.item_ficha("Código interno", Span(produto.codigo_interno, cls="mono")),
        ui.item_ficha("Nome comercial", B(produto.nome_comercial)),
        ui.item_ficha("Nome técnico", produto.nome_tecnico),
        ui.item_ficha("Fabricante", produto.fabricante),
        ui.item_ficha("Fornecedor", produto.fornecedor),
        ui.item_ficha("Categoria", produto.categoria),
        ui.item_ficha("Tipo de produto", produto.tipo_produto),
        ui.item_ficha("Número CAS", produto.numero_cas),
        ui.item_ficha("Estado físico", produto.estado_fisico),
        ui.item_ficha(
            "Unidades autorizadas",
            Div(*[Span(n, cls="chip fabrica") for n in produto.fabricas_nomes],
                cls="fds-etiquetas")
            if produto.fabricas_nomes
            else None,
            largo=True,
        ),
        ui.item_ficha("Processo em que é utilizado", produto.processo),
        ui.item_ficha("Área solicitante", produto.area_solicitante
                      or produto.setor_solicitante),
        ui.item_ficha("Prazo de utilização", produto.prazo_utilizacao),
        ui.item_ficha("Local de armazenamento", produto.local_armazenamento),
        ui.item_ficha(
            "Consumo estimado",
            f"{produto.consumo_estimado} {produto.unidade or ''}".strip()
            if produto.consumo_estimado
            else None,
        ),
        ui.item_ficha("Classificação GHS", produto.classificacao_ghs),
        ui.item_ficha("Número ONU", produto.onu_numero),
        ui.item_ficha(
            "Classes de risco",
            Div(*[Span(r, cls="chip risco") for r in produto.riscos_nomes],
                cls="fds-etiquetas")
            if produto.riscos_nomes
            else None,
            largo=True,
        ),
        ui.item_ficha("Composição", produto.composicao, largo=True),
        ui.item_ficha("Aplicação / finalidade", produto.aplicacao, largo=True),
        ui.item_ficha("EPI recomendado", produto.epi_recomendado, largo=True),
        ui.item_ficha("Restrições de uso", produto.restricoes_uso, largo=True),
        ui.item_ficha("Observações", produto.observacoes, largo=True),
        ui.item_ficha(
            "Solicitante",
            (
                f"{produto.solicitante.nome} - {produto.criado_em.strftime('%d/%m/%Y')}"
                if publico
                else f"{produto.solicitante.nome} ({produto.solicitante.email}) - "
                f"{produto.criado_em.strftime('%d/%m/%Y %H:%M')}"
            ),
            largo=True,
        ),
        ui.item_ficha("Motivo do encerramento", produto.motivo_encerramento, largo=True)
        if produto.motivo_encerramento
        else None,
        cls="ficha",
    )

    form_decisao = (
        Form(
            ui.campo(
                "Parecer técnico",
                "parecer",
                linhas=3,
                obrigatório=True,
                ajuda="O parecer fica registrado no histórico do produto.",
            ),
            ui.campo(
                "Motivo (obrigatório ao reprovar)", "motivo", opcoes=MOTIVOS_REPROVACAO,
                ajuda="Só é usado quando a decisão é reprovar.",
            ),
            Div(
                Button("Aprovar etapa", cls="btn verde", type="submit", name="decisao",
                       value="APROVADO"),
                Button("Reprovar", cls="btn vermelho", type="submit", name="decisao",
                       value="REPROVADO"),
                cls="barra-acoes",
            ),
            method="post",
            action=f"/produtos/{produto.id}/decisao",
        )
        if pode
        else None
    )

    form_correcao = (
        Form(
            ui.campo(
                "O que precisa ser corrigido", "motivo", linhas=3, obrigatório=True,
                ajuda="O solicitante recebe esse texto por e-mail e reenvia depois "
                      "de corrigir. A análise volta para você.",
            ),
            Button("Solicitar correção", cls="btn", type="submit"),
            method="post",
            action=f"/produtos/{produto.id}/correcao",
        )
        if pode
        else None
    )

    form_observacao = (
        Form(
            ui.campo("Observação", "texto", linhas=2, obrigatório=True,
                     ajuda="Fica no histórico e não altera o status da solicitação."),
            Button("Registrar observação", cls="btn secundario", type="submit"),
            method="post",
            action=f"/produtos/{produto.id}/observacao",
        )
        if not publico
        else None
    )

    form_reenvio = (
        Form(
            ui.campo("O que foi corrigido", "resposta", linhas=3, obrigatório=True,
                     ajuda="Anexe os documentos atualizados antes de reenviar, se for o caso."),
            Button("Reenviar para análise", cls="btn verde", type="submit"),
            method="post",
            action=f"/produtos/{produto.id}/reenviar",
        )
        if pode_reenviar
        else None
    )

    cartao_observacoes = (
        Div(
            Div(
                H2("Observações da análise"),
                Span(f"{len(obs)} registro(s)", cls="direita"),
                cls="card-titulo",
            ),
            Div(
                *[
                    Div(
                        Div(
                            Span(o.usuario.iniciais if o.usuario else "?", cls="avatar"),
                            Span(
                                B(o.usuario.nome if o.usuario else "Sistema"),
                                " · ",
                                Span(
                                    o.usuario.papel_label if o.usuario else "-",
                                    cls="texto-mudo",
                                ),
                                cls="quem",
                            ),
                            Span(
                                o.criado_em.strftime("%d/%m/%Y %H:%M"),
                                cls="pequeno texto-mudo direita",
                            ),
                            cls="obs-topo",
                        ),
                        P(o.detalhe, cls="obs-texto"),
                        cls="obs",
                    )
                    for o in obs
                ],
                cls="lista-obs",
            )
            if obs
            else ui.vazio("Nenhuma observação registrada.", "✎"),
            Hr(style="border:0;border-top:1px solid var(--cinza-fundo);margin:1.1rem 0")
            if form_observacao
            else None,
            form_observacao,
            cls="card",
        )
        if not publico
        else None
    )

    docs_visiveis = (
        [d for d in produto.documentos if d.tipo in ("FDS", "FICHA_EMERGENCIA")]
        if publico
        else list(produto.documentos)
    )
    documentos = Div(
        Div(
            H2("Documentos de segurança" if publico else "Documentos anexados"),
            Span(f"{len(docs_visiveis)} arquivo(s)", cls="direita"),
            cls="card-titulo",
        ),
        Div(*[ui.cartao_documento(d) for d in docs_visiveis], cls="docs")
        if docs_visiveis
        else ui.vazio("Nenhum documento disponível.", "▣"),
        Hr(style="border:0;border-top:1px solid var(--cinza-fundo);margin:1.1rem 0")
        if not publico
        else None,
        Form(
            Div(
                ui.campo(
                    "Tipo do documento", "tipo", opcoes=[(k, v) for k, v in TIPOS_DOCUMENTO.items()],
                    obrigatório=True,
                ),
                Label(
                    Span("Arquivo", Span(" *", cls="obr"), cls="rot"),
                    Input(type="file", name="arquivo", required=True),
                    cls="campo",
                ),
                ui.campo("Data de revisão", "data_revisao", tipo="date",
                         ajuda="Obrigatória para FDS."),
                Div(Button("Anexar", cls="btn secundario", type="submit"), cls="acao"),
                cls="filtros",
            ),
            method="post",
            action=f"/produtos/{produto.id}/documentos",
            enctype="multipart/form-data",
        )
        if not publico
        else None,
        cls="card",
    )

    acoes_status = []
    if not publico and usuario.papel in ("ADMIN", "APROVADOR_FINAL", "QUIMICO_RESPONSAVEL"):
        if produto.status == "APROVADO":
            acoes_status.append(
                Form(
                    ui.campo("Motivo da descontinuação", "motivo", linhas=2, obrigatório=True),
                    Button("Descontinuar produto", cls="btn vermelho", type="submit"),
                    method="post",
                    action=f"/produtos/{produto.id}/descontinuar",
                )
            )
        elif produto.status == "DESCONTINUADO":
            acoes_status.append(
                Form(
                    P("Reativar este produto e devolvê-lo ao catálogo de aprovados."),
                    Button("Reativar produto", cls="btn verde", type="submit"),
                    method="post",
                    action=f"/produtos/{produto.id}/reativar",
                )
            )

    situacao = produto.fds_situacao
    fds = produto.fds
    if fds:
        linhas_fds = [
            Tr(
                Td(Span(f"v{d.versao}", cls="mono nowrap")),
                Td(
                    d.data_revisao.strftime("%d/%m/%Y")
                    if d.data_revisao
                    else Span("não informada", cls="texto-mudo"),
                    cls="nowrap",
                ),
                Td(d.vencimento.strftime("%d/%m/%Y"), cls="nowrap"),
                Td(A(d.nome_arquivo, href=f"/documentos/{d.id}"), cls="pequeno"),
                Td(
                    Span("vigente", cls="badge aprovado")
                    if d.id == fds.id
                    else Span("anterior", cls="badge neutro")
                ),
            )
            for d in produto.fds_versoes
        ]
        cartao_fds = Div(
            Div(
                H2("Ficha de Dados de Segurança"),
                Span(_pontos_semaforo(situacao), cls="direita"),
                cls="card-titulo",
            ),
            Div(
                Table(
                    Thead(Tr(Th("Versão"), Th("Revisão"), Th("Vence em"),
                             Th("Arquivo"), Th(""))),
                    Tbody(*linhas_fds),
                    cls="dados",
                ),
                style="overflow-x:auto",
            ),
            cls="card",
        )
    else:
        cartao_fds = Div(
            Div(
                H2("Ficha de Dados de Segurança"),
                Span(_pontos_semaforo("SEM_FDS"), cls="direita"),
                cls="card-titulo",
            ),
            ui.vazio("Nenhuma FDS anexada a este produto.", "▣"),
            cls="card",
        )

    if produto.controles:
        cartao_controle = Div(
            Div(
                H2("Controle regulatório"),
                Span("produto controlado", cls="badge roxo direita"),
                cls="card-titulo",
            ),
            Div(
                Table(
                    Thead(Tr(Th("Órgão"), Th("Licença"), Th("Validade"))),
                    Tbody(
                        *[
                            Tr(
                                Td(B(c.orgao_label)),
                                Td(c.numero_licenca or Span("-", cls="texto-mudo"),
                                   cls="mono pequeno"),
                                Td(
                                    Span(
                                        c.validade_licenca.strftime("%d/%m/%Y"),
                                        cls="badge reprovado" if c.vencida else "badge aprovado",
                                    )
                                    if c.validade_licenca
                                    else Span("não informada", cls="texto-mudo"),
                                    cls="nowrap",
                                ),
                            )
                            for c in produto.controles
                        ]
                    ),
                    cls="dados",
                ),
                style="overflow-x:auto",
            ),
            cls="card",
        )
    else:
        cartao_controle = None

    coluna_esq = Div(
        Div(Div(H2("Ficha do produto"), Span(ui.badge(produto.status), cls="direita"),
                cls="card-titulo"), ficha, cls="card"),
        cartao_fds,
        cartao_controle,
        documentos,
        cartao_observacoes,
        Div(Div(H2("Histórico de alterações"), cls="card-titulo"), _tabela_eventos(eventos),
            cls="card") if not publico else None,
    )
    coluna_dir = Div(
        Div(
            Div(
                H2("Fluxo de aprovação"),
                Span(
                    f"{produto.progresso[0]}/{produto.progresso[1]} etapas",
                    cls="direita",
                ),
                cls="card-titulo",
            ),
            ui.linha_fluxo(produto),
            cls="card",
        ),
        Div(
            Div(H2("Registrar parecer"), cls="card-titulo"),
            form_decisao
            or P(
                "Você não é o responsável pela etapa atual desta solicitação."
                if produto.status == "EM_ANALISE"
                else f"Solicitação encerrada com status: {produto.status_label}.",
                cls="texto-mudo pequeno",
            ),
            cls="card",
        )
        if not publico
        else None,
        Div(
            Div(H2("Solicitar correção"), cls="card-titulo"),
            form_correcao,
            cls="card",
        )
        if form_correcao
        else None,
        Div(
            Div(H2("Corrigir e reenviar"), cls="card-titulo"),
            P(
                "Esta solicitação foi devolvida para correção. Ajuste o que foi "
                "pedido e reenvie — a análise retoma com "
                f"{produto.etapa_label or 'a área responsável'}.",
                cls="pequeno texto-mudo",
            ),
            form_reenvio,
            cls="card",
        )
        if form_reenvio
        else None,
        *[Div(Div(H2("Situação do produto"), cls="card-titulo"), a, cls="card") for a in acoes_status],
    )

    return ui.pagina(
        produto.nome_comercial,
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        ui.alerta(
            Span(
                B("Aguardando correção do solicitante. "),
                produto.pendencia or "",
            ),
            "aviso",
        )
        if produto.aguardando_correcao
        else None,
        Div(
            coluna_esq,
            coluna_dir,
            cls="grade",
            style="grid-template-columns:minmax(0,1.65fr) minmax(280px,1fr)",
        ),
        usuario=usuario,
        subtitulo=f"{produto.codigo_interno} - {produto.fabricante}",
        acoes=[
            A("Editar ficha", href=f"/produtos/{produto.id}/editar", cls="btn")
            if not publico
            else None,
            A("Ver todos os produtos", href="/produtos", cls="btn secundario"),
        ],
    )


@rt("/produtos/{pid}/editar")
def get(req, pid: int, erro: str = ""):
    """Edita identificação, aplicação e controle regulatório de um produto."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return ui.pagina("Produto não encontrado",
                             ui.alerta("Registro inexistente.", "erro"), usuario=usuario)
        marcadas = set(produto.fabricas_nomes)
        controles = {c.orgao: c for c in produto.controles}
        dados = {
            "nome_comercial": produto.nome_comercial,
            "nome_tecnico": produto.nome_tecnico or "",
            "fornecedor": produto.fornecedor or "",
            "categoria": produto.categoria or "",
            "tipo_produto": produto.tipo_produto or "",
            "numero_cas": produto.numero_cas or "",
            "estado_fisico": produto.estado_fisico or "",
            "composicao": produto.composicao or "",
            "processo": produto.processo or "",
            "aplicacao": produto.aplicacao or "",
            "local_armazenamento": produto.local_armazenamento or "",
            "classificacao_ghs": produto.classificacao_ghs or "",
            "onu_numero": produto.onu_numero or "",
            "epi_recomendado": produto.epi_recomendado or "",
            "restricoes_uso": produto.restricoes_uso or "",
            "observacoes": produto.observacoes or "",
            "area_solicitante": produto.area_solicitante or "",
            "prazo_utilizacao": produto.prazo_utilizacao or "",
            "consumo_estimado": produto.consumo_estimado or "",
            "unidade": produto.unidade or "",
        }
        riscos_marcados = set(produto.riscos_nomes)
        codigo, nome = produto.codigo_interno, produto.nome_comercial

    formulario = Form(
        Fieldset(
            Legend("Identificação"),
            Div(
                ui.campo("Nome técnico", "nome_tecnico", valor=dados["nome_tecnico"]),
                ui.campo("Fornecedor", "fornecedor", valor=dados["fornecedor"]),
                cls="linha-form",
            ),
            Div(
                ui.campo("Categoria", "categoria", valor=dados["categoria"], opcoes=CATEGORIAS),
                ui.campo("Tipo de produto", "tipo_produto", valor=dados["tipo_produto"],
                         opcoes=TIPOS_PRODUTO),
                ui.campo("Estado físico", "estado_fisico", valor=dados["estado_fisico"],
                         opcoes=ESTADOS_FISICOS),
                ui.campo("Número CAS", "numero_cas", valor=dados["numero_cas"]),
                cls="linha-form",
            ),
            ui.campo("Composição", "composicao", valor=dados["composicao"], linhas=2),
            cls="secao",
        ),
        Fieldset(
            Legend("Aplicação e unidades"),
            Div(
                ui.campo("Processo em que é utilizado", "processo", valor=dados["processo"]),
                ui.campo("Local de armazenamento", "local_armazenamento",
                         valor=dados["local_armazenamento"]),
                cls="linha-form",
            ),
            ui.campo("Aplicação / finalidade", "aplicacao", valor=dados["aplicacao"], linhas=3),
            Div(
                ui.campo("Área solicitante", "area_solicitante",
                         valor=dados["area_solicitante"], opcoes=AREAS_SOLICITANTES),
                ui.campo("Prazo de utilização", "prazo_utilizacao",
                         valor=dados["prazo_utilizacao"]),
                ui.campo("Quantidade prevista", "consumo_estimado",
                         valor=dados["consumo_estimado"]),
                ui.campo("Unidade de medida", "unidade", valor=dados["unidade"]),
                cls="linha-form",
            ),
            Div(
                Span("Unidades autorizadas", cls="rot"),
                Div(
                    *[
                        Label(
                            Input(type="checkbox", name="fabricas", value=n,
                                  checked=(n in marcadas)),
                            Span(n),
                            cls="caixa-marcar",
                        )
                        for n in FABRICAS
                    ],
                    cls="grupo-marcar",
                ),
                cls="campo",
            ),
            cls="secao",
        ),
        Fieldset(
            Legend("Segurança"),
            Div(
                ui.campo("Classificação GHS", "classificacao_ghs",
                         valor=dados["classificacao_ghs"]),
                ui.campo("Número ONU", "onu_numero", valor=dados["onu_numero"]),
                cls="linha-form",
            ),
            Div(
                Span("Classes de risco", cls="rot"),
                Div(
                    *[
                        Label(
                            Input(type="checkbox", name="riscos", value=c,
                                  checked=(c in riscos_marcados)),
                            Span(c),
                            cls="caixa-marcar",
                        )
                        for c in CLASSES_RISCO
                    ],
                    cls="grupo-marcar",
                ),
                cls="campo",
            ),
            ui.campo("EPI recomendado", "epi_recomendado", valor=dados["epi_recomendado"],
                     linhas=2),
            ui.campo("Restrições de uso", "restricoes_uso", valor=dados["restricoes_uso"],
                     linhas=2),
            ui.campo("Observações", "observacoes", valor=dados["observacoes"], linhas=2),
            cls="secao",
        ),
        Fieldset(
            Legend("Controle regulatório"),
            P("Desmarque um órgão para remover o controle correspondente.",
              cls="pequeno texto-mudo"),
            *[
                Div(
                    Label(
                        Input(type="checkbox", name="orgaos", value=chave,
                              checked=(chave in controles)),
                        Span(B(rotulo)),
                        cls="caixa-marcar destacada",
                    ),
                    Div(
                        ui.campo(
                            "Número da licença", f"licenca_{chave}",
                            valor=(controles[chave].numero_licenca or ""
                                   if chave in controles else ""),
                        ),
                        ui.campo(
                            "Validade da licença", f"validade_{chave}", tipo="date",
                            valor=(
                                controles[chave].validade_licenca.isoformat()
                                if chave in controles and controles[chave].validade_licenca
                                else ""
                            ),
                        ),
                        cls="linha-form",
                    ),
                    cls="bloco-orgao",
                )
                for chave, rotulo in ORGAOS_CONTROLADORES.items()
            ],
            cls="secao",
        ),
        Div(
            Button("Salvar alterações", cls="btn verde", type="submit"),
            A("Cancelar", href=f"/produtos/{pid}", cls="btn secundario"),
            cls="barra-acoes",
        ),
        method="post",
        action=f"/produtos/{pid}/editar",
    )

    return ui.pagina(
        f"Editar: {nome}",
        ui.alerta(erro, "erro") if erro else None,
        ui.alerta(
            "Alterações aqui não reabrem o fluxo de aprovação. Toda mudança fica "
            "registrada no histórico do produto.",
            "info",
        ),
        Div(formulario, cls="card"),
        usuario=usuario,
        subtitulo=f"{codigo} - dados de identificação, aplicação e controle",
        acoes=[A("Voltar à ficha", href=f"/produtos/{pid}", cls="btn secundario")],
    )


@rt("/produtos/{pid}/editar")
async def post(req, pid: int):
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
    dados["fabricas"] = [f for f in form.getlist("fabricas") if f in FABRICAS]
    dados["controles"] = _ler_controles(form)
    dados["riscos"] = [r for r in form.getlist("riscos") if r in CLASSES_RISCO]

    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return RedirectResponse("/produtos", status_code=303)
        servicos.atualizar_ficha(s, produto, dados, s.get(Usuario, usuario.id))
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok", "Ficha atualizada."), status_code=303
    )


@rt("/produtos/{pid}/decisao")
async def post(req, pid: int):
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    decisao = (form.get("decisao") or "").upper()
    parecer = (form.get("parecer") or "").strip()
    motivo = (form.get("motivo") or "").strip()
    if decisao not in ("APROVADO", "REPROVADO"):
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro", "Decisão inválida."), status_code=303
        )
    if not parecer:
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro", "Informe o parecer técnico."), status_code=303
        )
    if decisao == "REPROVADO":
        if not motivo:
            return RedirectResponse(
                _msg(f"/produtos/{pid}", "erro",
                     "Selecione o motivo da reprovação."),
                status_code=303,
            )
        parecer = f"[{motivo}] {parecer}"
    with db_session() as s:
        produto = s.get(Produto, pid)
        u = s.get(Usuario, usuario.id)
        if not produto or not servicos.pode_decidir(u, produto):
            return RedirectResponse(
                f"/produtos/{pid}?erro=Você+não+pode+decidir+esta+etapa.", status_code=303
            )
        servicos.registrar_decisao(s, produto, u, decisao, parecer)
    return RedirectResponse(f"/produtos/{pid}?ok=Parecer+registrado.", status_code=303)


@rt("/produtos/{pid}/correcao")
async def post(req, pid: int):
    """O aprovador devolve a solicitação ao solicitante, sem reprovar."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    motivo = (form.get("motivo") or "").strip()
    if not motivo:
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro", "Descreva o que precisa ser corrigido."),
            status_code=303,
        )
    with db_session() as s:
        produto = s.get(Produto, pid)
        u = s.get(Usuario, usuario.id)
        if not produto or not servicos.pode_decidir(u, produto):
            return RedirectResponse(
                _msg(f"/produtos/{pid}", "erro",
                     "Você não é o responsável pela etapa atual desta solicitação."),
                status_code=303,
            )
        servicos.solicitar_correcao(s, produto, u, motivo)
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok", "Correção solicitada ao solicitante."),
        status_code=303,
    )


@rt("/produtos/{pid}/reenviar")
async def post(req, pid: int):
    """O solicitante devolve a solicitação para análise após corrigir."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    resposta = (form.get("resposta") or "").strip()
    if not resposta:
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro", "Descreva o que foi corrigido."),
            status_code=303,
        )
    with db_session() as s:
        produto = s.get(Produto, pid)
        u = s.get(Usuario, usuario.id)
        if not produto or not servicos.pode_corrigir(u, produto):
            return RedirectResponse(
                _msg(f"/produtos/{pid}", "erro",
                     "Somente o solicitante pode reenviar esta solicitação."),
                status_code=303,
            )
        servicos.reenviar_apos_correcao(s, produto, u, resposta)
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok", "Solicitação reenviada para análise."),
        status_code=303,
    )


@rt("/produtos/{pid}/observacao")
async def post(req, pid: int):
    """Observação de análise: entra no histórico e não muda o status."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    texto = (form.get("texto") or "").strip()
    if not texto:
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro", "Escreva a observação."), status_code=303
        )
    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return RedirectResponse("/aprovacoes", status_code=303)
        servicos.registrar_observacao(s, produto, s.get(Usuario, usuario.id), texto)
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok", "Observação registrada."), status_code=303
    )


@rt("/produtos/{pid}/descontinuar")
async def post(req, pid: int):
    barrado = exigir_papel(req, "APROVADOR_FINAL", "QUIMICO_RESPONSAVEL")
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    motivo = (form.get("motivo") or "").strip()
    if not motivo:
        return RedirectResponse(f"/produtos/{pid}?erro=Informe+o+motivo.", status_code=303)
    with db_session() as s:
        produto = s.get(Produto, pid)
        servicos.descontinuar(s, produto, s.get(Usuario, usuario.id), motivo)
    return RedirectResponse(f"/produtos/{pid}?ok=Produto+descontinuado.", status_code=303)


@rt("/produtos/{pid}/reativar")
async def post(req, pid: int):
    barrado = exigir_papel(req, "APROVADOR_FINAL", "QUIMICO_RESPONSAVEL")
    if barrado:
        return barrado
    usuario = eu(req)
    with db_session() as s:
        produto = s.get(Produto, pid)
        servicos.reativar(s, produto, s.get(Usuario, usuario.id))
    return RedirectResponse(f"/produtos/{pid}?ok=Produto+reativado.", status_code=303)


@rt("/produtos/{pid}/documentos")
async def post(req, pid: int):
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    enviado = form.get("arquivo")
    tipo = form.get("tipo") or "OUTRO"
    if enviado is None or not getattr(enviado, "filename", ""):
        return RedirectResponse(f"/produtos/{pid}?erro=Selecione+um+arquivo.", status_code=303)
    conteudo = await enviado.read()
    if len(conteudo) > config.MAX_UPLOAD_BYTES:
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro",
                 f"Arquivo maior que {config.MAX_UPLOAD_MB} MB."),
            status_code=303,
        )
    revisao = _data(form.get("data_revisao"))
    if tipo == "FDS" and revisao is None:
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro",
                 "Informe a data de revisão da FDS para calcular a validade."),
            status_code=303,
        )
    with db_session() as s:
        anteriores = s.scalars(
            select(Documento).where(Documento.produto_id == pid, Documento.tipo == tipo)
        ).all()
        s.add(
            Documento(
                produto_id=pid,
                tipo=tipo,
                nome_arquivo=enviado.filename,
                content_type=getattr(enviado, "content_type", None),
                tamanho=len(conteudo),
                conteudo=conteudo,
                versao=len(anteriores) + 1,
                data_revisao=revisao,
                enviado_por_id=usuario.id,
            )
        )
        servicos.registrar_log(
            s,
            "DOCUMENTO_ANEXADO",
            f"{TIPOS_DOCUMENTO.get(tipo, tipo)}: {enviado.filename}",
            usuario.id,
            pid,
        )
        produto = s.get(Produto, pid)
        if produto and produto.aberta:
            notificacoes.notificar_documento(
                s, produto, enviado.filename, TIPOS_DOCUMENTO.get(tipo, tipo)
            )
    return RedirectResponse(f"/produtos/{pid}?ok=Documento+anexado.", status_code=303)


# =====================================================================
# FDS e download de documentos
# =====================================================================


def _pontos_semaforo(situacao: str, texto: str | None = None):
    """Bolinha colorida + rótulo da situação da FDS."""
    classe = situacao.lower().replace("_", "-")
    return Span(
        I(cls="ponto"),
        texto or SITUACOES_FDS.get(situacao, situacao),
        cls=f"semaforo {classe}",
    )


def _cartao_fds(produto, publico: bool = False):
    """Um produto na página de FDS: identificação, situação e documentos."""
    situacao = produto.fds_situacao
    fds = produto.fds
    docs = [d for d in produto.documentos if d.tipo in ("FDS", "FICHA_EMERGENCIA")]

    if fds:
        venc = fds.vencimento.strftime("%d/%m/%Y")
        dias = produto.fds_dias_restantes
        if situacao == "VENCIDA":
            prazo = f"venceu em {venc} ({abs(dias)} dias atrás)"
        elif situacao == "PROXIMA":
            prazo = f"vence em {venc} (faltam {dias} dias)"
        else:
            prazo = f"válida até {venc}"
        revisao = (
            f"revisão de {fds.data_revisao.strftime('%d/%m/%Y')}"
            if fds.data_revisao
            else f"anexada em {fds.enviado_em.strftime('%d/%m/%Y')}"
        )
        linha_prazo = Div(
            Span(f"v{fds.versao}", cls="chip versao"),
            Span(revisao, cls="pequeno texto-mudo"),
            Span("·", cls="pequeno texto-mudo"),
            Span(prazo, cls="pequeno texto-mudo"),
            cls="fds-prazo",
        )
    else:
        linha_prazo = Div(
            Span("Nenhuma FDS anexada a este produto.", cls="pequeno texto-mudo"),
            cls="fds-prazo",
        )

    etiquetas = []
    for nome in produto.fabricas_nomes:
        etiquetas.append(Span(nome, cls="chip fabrica"))
    if produto.tipo_produto:
        etiquetas.append(Span(produto.tipo_produto, cls="chip tipo"))
    for risco in produto.riscos_nomes:
        etiquetas.append(Span(risco, cls="chip risco"))
    for controle in produto.controles:
        etiquetas.append(
            Span(
                controle.orgao_label,
                cls="chip controlado" + (" vencida" if controle.vencida else ""),
                title=(
                    f"Licença {controle.numero_licenca or 'sem número'}"
                    + (
                        f" - válida até {controle.validade_licenca.strftime('%d/%m/%Y')}"
                        if controle.validade_licenca
                        else ""
                    )
                ),
            )
        )

    return Div(
        Div(
            Div(
                H3(produto.nome_comercial),
                Div(
                    Span(produto.codigo_interno, cls="mono"),
                    Span("·", cls="sep"),
                    Span(produto.fabricante),
                    Span("·", cls="sep"),
                    Span(produto.categoria or "sem categoria"),
                    cls="fds-sub",
                ),
                cls="fds-ident",
            ),
            _pontos_semaforo(situacao),
            cls="fds-topo",
        ),
        Div(*etiquetas, cls="fds-etiquetas") if etiquetas else None,
        linha_prazo,
        Div(*[ui.cartao_documento(d) for d in docs], cls="docs") if docs else None,
        Div(
            A("Ver ficha completa", href=f"/produtos/{produto.id}", cls="btn pequeno secundario"),
            cls="fds-acoes",
        ),
        cls="card cartao-fds",
    )


def _filtros_fds(q, fabrica, tipo_produto, orgao, situacao):
    return Form(
        Div(
            ui.campo(
                "Buscar", "q", valor=q,
                placeholder="produto, nome técnico, fabricante, código ou CAS",
            ),
            ui.campo("Fábrica", "fabrica", valor=fabrica, opcoes=FABRICAS),
            ui.campo("Tipo de produto", "tipo_produto", valor=tipo_produto, opcoes=TIPOS_PRODUTO),
            ui.campo(
                "Produto controlado", "orgao", valor=orgao,
                opcoes=[("QUALQUER", "Qualquer órgão")]
                + [(k, v) for k, v in ORGAOS_CONTROLADORES.items()],
            ),
            ui.campo(
                "Situação da FDS", "situacao", valor=situacao,
                opcoes=[(k, v) for k, v in SITUACOES_FDS.items()],
            ),
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href="/fds", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/fds",
    )


@rt("/fds")
def get(req, q: str = "", fabrica: str = "", tipo_produto: str = "",
        orgao: str = "", situacao: str = ""):
    """Repositório único de consulta das Fichas de Dados de Segurança."""
    usuario = eu(req)
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, somente_aprovados=True, fabrica=fabrica, tipo_produto=tipo_produto,
            orgao=orgao, limite=None,
        )
        resumo = servicos.resumo_fds(produtos)
        produtos = servicos.filtrar_por_situacao_fds(produtos, situacao)
        # O que exige acao aparece primeiro: vencidas, depois a vencer.
        ordem = {"VENCIDA": 0, "PROXIMA": 1, "SEM_FDS": 2, "VIGENTE": 3}
        produtos.sort(key=lambda p: (ordem.get(p.fds_situacao, 9), p.nome_comercial))

    painel = Div(
        A(
            Div(str(resumo["VIGENTE"]), cls="valor"),
            Div(_pontos_semaforo("VIGENTE", "Vigentes"), cls="rotulo"),
            href="/fds?situacao=VIGENTE",
            cls="kpi-fds",
        ),
        A(
            Div(str(resumo["PROXIMA"]), cls="valor"),
            Div(_pontos_semaforo("PROXIMA", "A vencer em 6 meses"), cls="rotulo"),
            href="/fds?situacao=PROXIMA",
            cls="kpi-fds",
        ),
        A(
            Div(str(resumo["VENCIDA"]), cls="valor"),
            Div(_pontos_semaforo("VENCIDA", "Vencidas"), cls="rotulo"),
            href="/fds?situacao=VENCIDA",
            cls="kpi-fds",
        ),
        A(
            Div(str(resumo["SEM_FDS"]), cls="valor"),
            Div(_pontos_semaforo("SEM_FDS", "Sem FDS"), cls="rotulo"),
            href="/fds?situacao=SEM_FDS",
            cls="kpi-fds",
        ),
        cls="painel-fds",
    )

    alertas = []
    if resumo["VENCIDA"]:
        alertas.append(
            ui.alerta(
                Span(
                    B(f"{resumo['VENCIDA']} produto(s) com FDS vencida. "),
                    "A ficha precisa ser atualizada junto ao fabricante antes do uso.",
                ),
                "erro",
            )
        )

    cartoes = [_cartao_fds(p) for p in produtos]

    return ui.pagina(
        "Fichas de Dados de Segurança",
        painel,
        Div(_filtros_fds(q, fabrica, tipo_produto, orgao, situacao), cls="card"),
        *alertas,
        Div(
            Div(
                H2("Resultado da consulta"),
                Span(f"{len(produtos)} produto(s)", cls="direita"),
                cls="card-titulo",
            ),
            P(
                "Somente produtos aprovados aparecem aqui. A validade é contada a "
                f"partir da data de revisão da ficha, com prazo de {FDS_VALIDADE_ANOS} "
                f"anos e alerta nos últimos {FDS_ALERTA_MESES} meses.",
                cls="pequeno texto-mudo",
                style="margin:0",
            ),
            cls="card",
        ),
        *(cartoes if cartoes else [Div(ui.vazio("Nenhuma FDS encontrada com esses filtros.", "▣"), cls="card")]),
        usuario=usuario,
        subtitulo="Repositório único de consulta dos produtos químicos aprovados",
    )


@rt("/documentos/{did}")
def get(req, did: int):
    """Download aberto. Sem login, apenas FDS e Ficha de Emergência de
    produtos APROVADOS podem ser baixadas."""
    publico = eu(req) is None
    with db_session() as s:
        doc = s.get(Documento, did)
        if not doc:
            return Response("Documento não encontrado", status_code=404)
        if publico and (
            doc.tipo not in ("FDS", "FICHA_EMERGENCIA")
            or doc.produto.status != "APROVADO"
        ):
            return Response(
                "Documento disponível apenas para usuários autenticados.", status_code=403
            )
        conteudo, nome, tipo = doc.conteudo, doc.nome_arquivo, doc.content_type
    return Response(
        conteudo,
        media_type=tipo or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


# =====================================================================
# Administração: usuarios, notificacoes, auditoria
# =====================================================================


@rt("/usuarios")
def get(req, ok: str = "", erro: str = ""):
    barrado = exigir_papel(req, "ADMIN")
    if barrado:
        return barrado
    usuario = eu(req)
    with db_session() as s:
        usuarios = list(s.scalars(select(Usuario).order_by(Usuario.nome)))
    tabela = Table(
        Thead(Tr(Th("Nome"), Th("E-mail"), Th("Papel"), Th("Setor"), Th("Situação"))),
        Tbody(
            *[
                Tr(
                    Td(B(u.nome)),
                    Td(u.email, cls="pequeno"),
                    Td(Span(u.papel_label, cls="badge info")),
                    Td(u.setor or "-"),
                    Td(
                        Span("Ativo", cls="badge aprovado")
                        if u.ativo
                        else Span("Inativo", cls="badge neutro")
                    ),
                )
                for u in usuarios
            ]
        ),
        cls="dados",
    )
    formulario = Form(
        Div(
            ui.campo("Nome completo", "nome", obrigatório=True),
            ui.campo("E-mail", "email", "email", obrigatório=True),
            cls="linha-form",
        ),
        Div(
            ui.campo("Papel", "papel", opcoes=[(k, v) for k, v in PAPEIS.items()],
                     obrigatório=True),
            ui.campo("Setor", "setor"),
            ui.campo("Senha inicial", "senha", "password", obrigatório=True),
            cls="linha-form",
        ),
        Div(Button("Cadastrar usuário", cls="btn", type="submit"), cls="barra-acoes"),
        method="post",
        action="/usuarios",
    )
    return ui.pagina(
        "Usuários e papéis",
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        Div(Div(H2("Usuários cadastrados"), cls="card-titulo"), tabela, cls="card"),
        Div(Div(H2("Novo usuário"), cls="card-titulo"), formulario, cls="card"),
        usuario=usuario,
        ativo="/usuarios",
        subtitulo="Cada papel corresponde a uma etapa do fluxo de aprovação",
        pendencias=pend(req),
    )


@rt("/usuarios")
async def post(req):
    barrado = exigir_papel(req, "ADMIN")
    if barrado:
        return barrado
    form = await req.form()
    nome = (form.get("nome") or "").strip()
    email = (form.get("email") or "").strip().lower()
    papel = form.get("papel") or "SOLICITANTE"
    senha = form.get("senha") or ""
    if not (nome and email and senha):
        return RedirectResponse("/usuarios?erro=Preencha+todos+os+campos.", status_code=303)
    with db_session() as s:
        if s.scalar(select(Usuario).where(Usuario.email == email)):
            return RedirectResponse("/usuarios?erro=E-mail+ja+cadastrado.", status_code=303)
        s.add(
            Usuario(
                nome=nome,
                email=email,
                senha_hash=gerar_hash(senha),
                papel=papel,
                setor=(form.get("setor") or "").strip() or None,
            )
        )
        servicos.registrar_log(s, "USUARIO_CRIADO", f"{nome} <{email}> como {papel}", eu(req).id)
    return RedirectResponse("/usuarios?ok=Usuario+cadastrado.", status_code=303)


@rt("/notificacoes")
def get(req):
    usuario = eu(req)
    with db_session() as s:
        itens = list(
            s.scalars(select(Notificacao).order_by(desc(Notificacao.criado_em)).limit(150)).unique()
        )
    tabela = Table(
        Thead(Tr(Th("Data"), Th("Destinatário"), Th("Assunto"), Th("Produto"), Th("Situação"))),
        Tbody(
            *[
                Tr(
                    Td(n.criado_em.strftime("%d/%m/%Y %H:%M"), cls="pequeno nowrap"),
                    Td(n.destinatario, cls="pequeno"),
                    Td(n.assunto, cls="pequeno"),
                    Td(
                        A(n.produto.codigo_interno, href=f"/produtos/{n.produto_id}", cls="mono")
                        if n.produto
                        else "-"
                    ),
                    Td(
                        Span("Enviado", cls="badge aprovado")
                        if n.enviado
                        else Span("Não enviado", cls="badge em-analise", title=n.erro or "")
                    ),
                )
                for n in itens
            ]
        ),
        cls="dados",
    )
    aviso = (
        ui.alerta(
            Span(
                B("SMTP não configurado. "),
                "Um servidor SMTP é o serviço que efetivamente envia e-mails "
                "(no caso da Tenaris, o servidor de e-mail corporativo). Enquanto o endereco "
                "não for informado no arquivo .env, o sistema apenas registra aqui o que seria "
                "enviado - nada sai para a caixa de entrada de ninguem.",
            ),
            "aviso",
        )
        if not config.SMTP_ATIVO
        else ui.alerta(f"Enviando e-mails via {config.SMTP_HOST}:{config.SMTP_PORT}.", "sucesso")
    )
    return ui.pagina(
        "Notificações",
        aviso,
        Div(Div(H2("Caixa de saída"), cls="card-titulo"),
            tabela if itens else ui.vazio("Nenhuma notificação gerada ainda.", "✉"), cls="card"),
        usuario=usuario,
        ativo="/notificacoes",
        subtitulo="Todo e-mail disparado pelo fluxo de aprovação fica registrado aqui",
        pendencias=pend(req),
    )


@rt("/auditoria")
def get(req, q: str = ""):
    usuario = eu(req)
    with db_session() as s:
        consulta = select(LogAuditoria).order_by(desc(LogAuditoria.criado_em)).limit(300)
        if q:
            like = f"%{q}%"
            consulta = select(LogAuditoria).where(
                LogAuditoria.acao.like(like) | LogAuditoria.detalhe.like(like)
            ).order_by(desc(LogAuditoria.criado_em)).limit(300)
        eventos = list(s.scalars(consulta).unique())
    busca = Form(
        Div(
            ui.campo("Buscar no log", "q", valor=q, placeholder="ação ou detalhe"),
            Div(
                Button("Buscar", cls="btn", type="submit"),
                A("Limpar", href="/auditoria", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/auditoria",
    )
    return ui.pagina(
        "Log de auditoria",
        Div(busca, cls="card"),
        Div(
            Div(H2("Eventos"), Span(f"{len(eventos)} registro(s)", cls="direita"), cls="card-titulo"),
            _tabela_eventos(eventos),
            cls="card",
        ),
        usuario=usuario,
        ativo="/auditoria",
        subtitulo="Rastreabilidade de todas as ações do sistema",
        pendencias=pend(req),
    )


# =====================================================================
# Compatibilidade: as rotas /portal/* existiam quando a consulta publica
# era separada. Agora o site inteiro e' publico, entao elas apenas
# redirecionam para as rotas definitivas (links antigos continuam validos).
# =====================================================================


@rt("/portal")
def get(q: str = "", categoria: str = ""):
    destino = "/produtos"
    parametros = [f"q={quote(q)}" for q in [q] if q] + [
        f"categoria={quote(categoria)}" for categoria in [categoria] if categoria
    ]
    if parametros:
        destino += "?" + "&".join(parametros)
    return RedirectResponse(destino, status_code=301)


@rt("/portal/fds")
def get(q: str = ""):
    return RedirectResponse(f"/fds?q={quote(q)}" if q else "/fds", status_code=301)


@rt("/portal/produtos/{pid}")
def get(pid: int):
    return RedirectResponse(f"/produtos/{pid}", status_code=301)


@rt("/portal/documentos/{did}")
def get(did: int):
    return RedirectResponse(f"/documentos/{did}", status_code=301)


# =====================================================================
# Inicializacao
# =====================================================================

criar_tabelas()

if __name__ == "__main__":
    print("=" * 62)
    print(f" {config.APP_EMPRESA} | {config.APP_NOME}")
    print(f" Banco: {descricao_conexao()}")
    print(f" SMTP : {'ativo - ' + config.SMTP_HOST if config.SMTP_ATIVO else 'não configurado'}")
    print(" URL  : http://127.0.0.1:5001")
    print("=" * 62)
    serve(port=5001, reload=False)
