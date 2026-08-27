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

from datetime import datetime

from fasthtml.common import *  # noqa: F403
from sqlalchemy import desc, select

import config
import servicos
import ui
from database import criar_tabelas, db_session, descricao_conexao
from models import (
    CATEGORIAS,
    DOCUMENTOS_OBRIGATORIOS,
    ESTADOS_FISICOS,
    FLUXO_APROVACAO,
    PAPEIS,
    STATUS,
    TIPOS_DOCUMENTO,
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

ROTAS_PUBLICAS = [
    r"/static/.*",
    r"/favicon\.ico",
    "/login",
    "/logout",
    r"/portal.*",
]


def autenticar(req, sess):
    """Carrega o usuario logado; redireciona para /login quando não houver."""
    req.scope["usuario"] = None
    uid = sess.get("uid")
    if uid:
        with db_session() as s:
            usuario = s.get(Usuario, uid)
            if usuario and usuario.ativo:
                req.scope["usuario"] = usuario
                req.scope["pendencias"] = servicos.contar_pendencias(s, usuario)
    if req.scope["usuario"] is None:
        sess.pop("uid", None)
        return RedirectResponse(f"/login?proximo={req.url.path}", status_code=303)


bware = Beforeware(autenticar, skip=ROTAS_PUBLICAS)

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


@rt("/static/{fname:path}.{ext:static}")
def arquivos_estaticos(fname: str, ext: str):
    return FileResponse(f"static/{fname}.{ext}")


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
                            "Consulta de produtos e FDS sem login: ",
                            A("portal do colaborador", href="/portal"),
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
    return RedirectResponse(proximo if proximo.startswith("/") else "/", status_code=303)


@rt("/logout")
def get(sess):
    sess.pop("uid", None)
    return RedirectResponse("/login", status_code=303)


# =====================================================================
# Dashboard
# =====================================================================


@rt("/")
def get(req):
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
            Div("Em análise", cls="rotulo"),
            Div(str(ind["por_status"].get("EM_ANALISE", 0)), cls="valor"),
            Div("aguardando aprovação", cls="nota"),
            href="/historico?status=EM_ANALISE",
            cls="kpi ambar",
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
        "Dashboard",
        *alertas,
        kpis,
        fila if usuario.papel != "SOLICITANTE" else None,
        graficos,
        tabela_recentes,
        usuario=usuario,
        ativo="/",
        subtitulo=f"Visão geral - banco: {descricao_conexao()}",
        pendencias=pend(req),
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
    usuario = eu(req)
    with db_session() as s:
        codigo = servicos.proximo_codigo(s)

    formulario = Form(
        Fieldset(
            Legend("Identificação do produto"),
            Div(
                ui.campo("Código interno", "codigo_interno", valor=codigo, obrigatório=True,
                         ajuda="Gerado automaticamente — pode ser ajustado."),
                ui.campo("Nome comercial", "nome_comercial", obrigatório=True),
                cls="linha-form",
            ),
            Div(
                ui.campo("Fabricante", "fabricante", obrigatório=True),
                ui.campo("Fornecedor", "fornecedor"),
                cls="linha-form",
            ),
            Div(
                ui.campo("Categoria", "categoria", opcoes=CATEGORIAS, obrigatório=True),
                ui.campo("Estado físico", "estado_fisico", opcoes=ESTADOS_FISICOS),
                ui.campo("Número CAS", "numero_cas", ajuda="Ex.: 67-64-1"),
                cls="linha-form",
            ),
            ui.campo("Composição / componentes perigosos", "composicao", linhas=2),
            cls="secao",
        ),
        Fieldset(
            Legend("Uso na planta"),
            Div(
                ui.campo("Setor solicitante", "setor_solicitante", valor=usuario.setor or ""),
                ui.campo("Local de armazenamento", "local_armazenamento"),
                cls="linha-form",
            ),
            Div(
                ui.campo("Consumo estimado", "consumo_estimado", placeholder="Ex.: 200"),
                ui.campo("Unidade", "unidade", placeholder="L/mês, kg/mês..."),
                cls="linha-form",
            ),
            ui.campo(
                "Aplicação / finalidade de uso", "aplicacao", linhas=3, obrigatório=True,
                ajuda="Descreva onde e como o produto será utilizado.",
            ),
            cls="secao",
        ),
        Fieldset(
            Legend("Segurança e meio ambiente"),
            Div(
                ui.campo("Classificação GHS", "classificacao_ghs",
                         placeholder="Ex.: Líquido inflamável - Categoria 2"),
                ui.campo("Número ONU", "onu_numero", placeholder="Ex.: UN1090"),
                cls="linha-form",
            ),
            ui.campo("EPI recomendado", "epi_recomendado", linhas=2),
            ui.campo("Observações ao aprovador", "observacoes", linhas=2),
            cls="secao",
        ),
        Fieldset(
            Legend("Documentação técnica"),
            ui.alerta(
                Span(
                    B("A FDS é obrigatória. "),
                    "Os demais documentos são opcionais e podem ser anexados depois.",
                ),
                "aviso",
            ),
            Label(
                Span("FDS - Ficha de Dados de Segurança", Span(" *", cls="obr"), cls="rot"),
                Input(type="file", name="arquivo_fds", accept=".pdf,.doc,.docx", required=True),
                Span(f"PDF ou Word, até {config.MAX_UPLOAD_MB} MB.", cls="ajuda"),
                cls="campo",
            ),
            Div(
                Label(
                    Span("Ficha de emergência", cls="rot"),
                    Input(type="file", name="arquivo_ficha_emergencia"),
                    cls="campo",
                ),
                Label(
                    Span("Laudo / certificado / licença", cls="rot"),
                    Input(type="file", name="arquivo_laudo"),
                    cls="campo",
                ),
                cls="linha-form",
            ),
            cls="secao",
        ),
        Div(
            Button("Enviar para aprovação", cls="btn verde", type="submit"),
            A("Cancelar", href="/", cls="btn secundario"),
            Span(
                "Ao enviar, a solicitação segue para Meio Ambiente.",
                cls="pequeno texto-mudo direita",
            ),
            cls="barra-acoes",
        ),
        method="post",
        action="/solicitacoes/nova",
        enctype="multipart/form-data",
    )

    return ui.pagina(
        "Nova solicitação de produto químico",
        ui.alerta(erro, "erro") if erro else None,
        Div(
            Div(
                H2("Formulário de cadastro"),
                Span(
                    "Fluxo: Meio Ambiente > Saúde e Segurança > Químico Responsável > Aprovador Final",
                    cls="direita",
                ),
                cls="card-titulo",
            ),
            formulario,
            cls="card",
        ),
        usuario=usuario,
        ativo="/solicitacoes/nova",
        subtitulo="Preencha os dados e anexe a documentacao técnica",
        pendencias=pend(req),
    )


CAMPOS_ARQUIVO = [
    ("arquivo_fds", "FDS"),
    ("arquivo_ficha_emergencia", "FICHA_EMERGENCIA"),
    ("arquivo_laudo", "LAUDO"),
]


async def _ler_arquivos(form) -> tuple[list[dict], str | None]:
    arquivos = []
    for campo_nome, tipo in CAMPOS_ARQUIVO:
        enviado = form.get(campo_nome)
        if enviado is None or not getattr(enviado, "filename", ""):
            continue
        conteudo = await enviado.read()
        if not conteudo:
            continue
        if len(conteudo) > config.MAX_UPLOAD_BYTES:
            return [], (
                f"O arquivo '{enviado.filename}' excede o limite de {config.MAX_UPLOAD_MB} MB."
            )
        arquivos.append(
            {
                "tipo": tipo,
                "nome": enviado.filename,
                "content_type": getattr(enviado, "content_type", None),
                "conteudo": conteudo,
            }
        )
    return arquivos, None


@rt("/solicitacoes/nova")
async def post(req):
    usuario = eu(req)
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}

    obrigatórios = ["nome_comercial", "fabricante", "categoria", "aplicacao"]
    faltando = [c for c in obrigatórios if not dados.get(c)]
    if faltando:
        return RedirectResponse(
            "/solicitacoes/nova?erro=Preencha+todos+os+campos+obrigatórios.", status_code=303
        )

    arquivos, erro = await _ler_arquivos(form)
    if erro:
        return RedirectResponse(f"/solicitacoes/nova?erro={erro}", status_code=303)
    tipos = {a["tipo"] for a in arquivos}
    if any(d not in tipos for d in DOCUMENTOS_OBRIGATORIOS):
        return RedirectResponse(
            "/solicitacoes/nova?erro=Anexe+a+FDS+do+produto+(documento+obrigatório).",
            status_code=303,
        )

    with db_session() as s:
        existente = s.scalar(
            select(Produto).where(Produto.codigo_interno == dados.get("codigo_interno"))
        )
        if existente:
            dados["codigo_interno"] = servicos.proximo_codigo(s)
        produto = servicos.criar_solicitacao(s, dados, s.get(Usuario, usuario.id), arquivos)
        pid = produto.id
    return RedirectResponse(f"/produtos/{pid}?ok=Solicitação+enviada+para+aprovação.", status_code=303)


# =====================================================================
# Minhas solicitações / Aprovações pendentes
# =====================================================================


@rt("/minhas")
def get(req):
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


@rt("/aprovacoes")
def get(req):
    usuario = eu(req)
    with db_session() as s:
        consulta = select(Produto).where(Produto.status == "EM_ANALISE")
        if usuario.papel != "ADMIN":
            consulta = consulta.where(Produto.etapa_atual == usuario.papel)
        pendentes = list(s.scalars(consulta.order_by(Produto.criado_em)).unique())
        todas = list(
            s.scalars(
                select(Produto).where(Produto.status == "EM_ANALISE").order_by(Produto.criado_em)
            ).unique()
        )

    minha_etapa = dict(FLUXO_APROVACAO).get(usuario.papel, usuario.papel_label)
    conteudo = [
        Div(
            Div(
                H2(f"Aguardando: {minha_etapa}"),
                Span(f"{len(pendentes)} item(ns)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_produtos(pendentes)
            if pendentes
            else ui.vazio("Nenhuma solicitação aguardando sua análise.", "✓"),
            cls="card",
        )
    ]
    if usuario.papel != "ADMIN":
        conteudo.append(
            Div(
                Div(H2("Demais solicitações em andamento"), cls="card-titulo"),
                _tabela_produtos([p for p in todas if p not in pendentes]),
                cls="card",
            )
        )
    return ui.pagina(
        "Aprovações pendentes",
        *conteudo,
        usuario=usuario,
        ativo="/aprovacoes",
        subtitulo="Solicitações que dependem de parecer",
        pendencias=pend(req),
    )


# =====================================================================
# Consulta de produtos / historico
# =====================================================================


@rt("/produtos")
def get(req, q: str = "", status: str = "", categoria: str = ""):
    usuario = eu(req)
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, status or "APROVADO", categoria, somente_aprovados=not status
        )
    return ui.pagina(
        "Produtos químicos",
        Div(_barra_filtros("/produtos", q, status or "APROVADO", categoria), cls="card"),
        Div(
            Div(
                H2("Resultado da consulta"),
                Span(f"{len(produtos)} produto(s)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_produtos(produtos),
            cls="card",
        ),
        usuario=usuario,
        ativo="/produtos",
        subtitulo="Catálogo de produtos químicos cadastrados",
        pendencias=pend(req),
    )


@rt("/historico")
def get(req, q: str = "", status: str = "", categoria: str = ""):
    usuario = eu(req)
    with db_session() as s:
        produtos = servicos.buscar_produtos(s, q, status, categoria, limite=None)
        eventos = list(
            s.scalars(
                select(LogAuditoria).order_by(desc(LogAuditoria.criado_em)).limit(12)
            ).unique()
        )
    return ui.pagina(
        "Histórico completo",
        Div(_barra_filtros("/historico", q, status, categoria), cls="card"),
        Div(
            Div(
                H2("Todas as solicitações"),
                Span(f"{len(produtos)} registro(s)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_produtos(produtos),
            cls="card",
        ),
        Div(
            Div(H2("Movimentações recentes"), A("Auditoria completa", href="/auditoria", cls="direita"), cls="card-titulo"),
            _tabela_eventos(eventos),
            cls="card",
        ),
        usuario=usuario,
        ativo="/historico",
        subtitulo="Aprovados, reprovados, descontinuados e em análise",
        pendencias=pend(req),
    )


def _tabela_eventos(eventos):
    if not eventos:
        return ui.vazio("Nenhum evento registrado.")
    return Div(
        Table(
            Thead(Tr(Th("Data"), Th("Usuário"), Th("Ação"), Th("Detalhe"), Th("Produto"))),
            Tbody(
                *[
                    Tr(
                        Td(e.criado_em.strftime("%d/%m/%Y %H:%M"), cls="pequeno nowrap"),
                        Td(e.usuario.nome if e.usuario else "-"),
                        Td(Span(e.acao, cls="chip")),
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
    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return ui.pagina(
                "Produto não encontrado",
                ui.alerta("Registro inexistente.", "erro"),
                usuario=usuario,
                pendencias=pend(req),
            )
        pode = servicos.pode_decidir(s.get(Usuario, usuario.id), produto)
        eventos = list(
            s.scalars(
                select(LogAuditoria)
                .where(LogAuditoria.produto_id == pid)
                .order_by(desc(LogAuditoria.criado_em))
            ).unique()
        )

    ficha = Div(
        ui.item_ficha("Código interno", Span(produto.codigo_interno, cls="mono")),
        ui.item_ficha("Nome comercial", B(produto.nome_comercial)),
        ui.item_ficha("Fabricante", produto.fabricante),
        ui.item_ficha("Fornecedor", produto.fornecedor),
        ui.item_ficha("Categoria", produto.categoria),
        ui.item_ficha("Número CAS", produto.numero_cas),
        ui.item_ficha("Estado físico", produto.estado_fisico),
        ui.item_ficha("Setor solicitante", produto.setor_solicitante),
        ui.item_ficha("Local de armazenamento", produto.local_armazenamento),
        ui.item_ficha(
            "Consumo estimado",
            f"{produto.consumo_estimado} {produto.unidade or ''}".strip()
            if produto.consumo_estimado
            else None,
        ),
        ui.item_ficha("Classificação GHS", produto.classificacao_ghs),
        ui.item_ficha("Número ONU", produto.onu_numero),
        ui.item_ficha("Composição", produto.composicao, largo=True),
        ui.item_ficha("Aplicação / finalidade", produto.aplicacao, largo=True),
        ui.item_ficha("EPI recomendado", produto.epi_recomendado, largo=True),
        ui.item_ficha("Observações", produto.observacoes, largo=True),
        ui.item_ficha(
            "Solicitante",
            f"{produto.solicitante.nome} ({produto.solicitante.email}) - "
            f"{produto.criado_em.strftime('%d/%m/%Y %H:%M')}",
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

    documentos = Div(
        Div(
            H2("Documentos anexados"),
            Span(f"{len(produto.documentos)} arquivo(s)", cls="direita"),
            cls="card-titulo",
        ),
        Div(*[ui.cartao_documento(d) for d in produto.documentos], cls="docs")
        if produto.documentos
        else ui.vazio("Nenhum documento anexado.", "▣"),
        Hr(style="border:0;border-top:1px solid var(--cinza-fundo);margin:1.1rem 0"),
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
                Div(Button("Anexar", cls="btn secundario", type="submit"), cls="acao"),
                cls="filtros",
            ),
            method="post",
            action=f"/produtos/{produto.id}/documentos",
            enctype="multipart/form-data",
        ),
        cls="card",
    )

    acoes_status = []
    if usuario.papel in ("ADMIN", "APROVADOR_FINAL", "QUIMICO_RESPONSAVEL"):
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

    coluna_esq = Div(
        Div(Div(H2("Ficha do produto"), Span(ui.badge(produto.status), cls="direita"),
                cls="card-titulo"), ficha, cls="card"),
        documentos,
        Div(Div(H2("Histórico de alterações"), cls="card-titulo"), _tabela_eventos(eventos),
            cls="card"),
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
        ),
        *[Div(Div(H2("Situação do produto"), cls="card-titulo"), a, cls="card") for a in acoes_status],
    )

    return ui.pagina(
        produto.nome_comercial,
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        Div(
            coluna_esq,
            coluna_dir,
            cls="grade",
            style="grid-template-columns:minmax(0,1.65fr) minmax(280px,1fr)",
        ),
        usuario=usuario,
        ativo="",
        subtitulo=f"{produto.codigo_interno} - {produto.fabricante}",
        acoes=[A("< Voltar", href="/historico", cls="btn secundario")],
        pendencias=pend(req),
    )


@rt("/produtos/{pid}/decisao")
async def post(req, pid: int):
    usuario = eu(req)
    form = await req.form()
    decisao = (form.get("decisao") or "").upper()
    parecer = (form.get("parecer") or "").strip()
    if decisao not in ("APROVADO", "REPROVADO"):
        return RedirectResponse(f"/produtos/{pid}?erro=Decisão+inválida.", status_code=303)
    if not parecer:
        return RedirectResponse(
            f"/produtos/{pid}?erro=Informe+o+parecer+técnico.", status_code=303
        )
    with db_session() as s:
        produto = s.get(Produto, pid)
        u = s.get(Usuario, usuario.id)
        if not produto or not servicos.pode_decidir(u, produto):
            return RedirectResponse(
                f"/produtos/{pid}?erro=Você+não+pode+decidir+esta+etapa.", status_code=303
            )
        servicos.registrar_decisao(s, produto, u, decisao, parecer)
    return RedirectResponse(f"/produtos/{pid}?ok=Parecer+registrado.", status_code=303)


@rt("/produtos/{pid}/descontinuar")
async def post(req, pid: int):
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
    usuario = eu(req)
    with db_session() as s:
        produto = s.get(Produto, pid)
        servicos.reativar(s, produto, s.get(Usuario, usuario.id))
    return RedirectResponse(f"/produtos/{pid}?ok=Produto+reativado.", status_code=303)


@rt("/produtos/{pid}/documentos")
async def post(req, pid: int):
    usuario = eu(req)
    form = await req.form()
    enviado = form.get("arquivo")
    tipo = form.get("tipo") or "OUTRO"
    if enviado is None or not getattr(enviado, "filename", ""):
        return RedirectResponse(f"/produtos/{pid}?erro=Selecione+um+arquivo.", status_code=303)
    conteudo = await enviado.read()
    if len(conteudo) > config.MAX_UPLOAD_BYTES:
        return RedirectResponse(
            f"/produtos/{pid}?erro=Arquivo+maior+que+{config.MAX_UPLOAD_MB}+MB.", status_code=303
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
    return RedirectResponse(f"/produtos/{pid}?ok=Documento+anexado.", status_code=303)


# =====================================================================
# FDS e download de documentos
# =====================================================================


def _pagina_fds(usuario, q, produtos, prefixo="", pendencias=0, publico=False):
    cartoes = []
    for p in produtos:
        docs = [d for d in p.documentos if d.tipo in ("FDS", "FICHA_EMERGENCIA")]
        if not docs:
            continue
        cartoes.append(
            Div(
                Div(
                    H3(p.nome_comercial),
                    Span(ui.badge(p.status), cls="direita"),
                    cls="card-titulo",
                ),
                Div(
                    Span(p.codigo_interno, cls="chip"),
                    " ",
                    Span(p.fabricante, cls="chip"),
                    " ",
                    Span(p.categoria or "sem categoria", cls="chip"),
                    style="margin-bottom:.7rem",
                ),
                Div(*[ui.cartao_documento(d, prefixo) for d in docs], cls="docs"),
                Div(
                    A("Ver ficha completa do produto", href=f"{prefixo}/produtos/{p.id}"),
                    cls="pequeno",
                    style="margin-top:.7rem",
                ),
                cls="card",
            )
        )
    busca = Form(
        Div(
            ui.campo("Buscar FDS", "q", valor=q,
                     placeholder="produto, fabricante, fornecedor, código ou CAS"),
            Div(
                Button("Buscar", cls="btn", type="submit"),
                A("Limpar", href=f"{prefixo}/fds", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action=f"{prefixo}/fds",
    )
    corpo = [
        Div(busca, cls="card"),
        ui.alerta(
            "Somente produtos aprovados têm a FDS disponibilizada para consulta.", "info"
        ),
        *(cartoes if cartoes else [Div(ui.vazio("Nenhuma FDS encontrada.", "▣"), cls="card")]),
    ]
    if publico:
        return corpo
    return ui.pagina(
        "Fichas de Dados de Segurança (FDS)",
        *corpo,
        usuario=usuario,
        ativo="/fds",
        subtitulo="Busca e download da documentacao de segurança",
        pendencias=pendencias,
    )


@rt("/fds")
def get(req, q: str = ""):
    usuario = eu(req)
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, somente_aprovados=True, somente_com_fds=True, limite=None
        )
    return _pagina_fds(usuario, q, produtos, pendencias=pend(req))


@rt("/documentos/{did}")
def get(did: int):
    with db_session() as s:
        doc = s.get(Documento, did)
        if not doc:
            return Response("Documento não encontrado", status_code=404)
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
# Portal publico (sem login) - consulta de produtos e FDS
# =====================================================================


def _molde_portal(titulo: str, *conteudo, subtitulo: str | None = None):
    return (
        *ui.cabeca(titulo),
        ui.topbar(None),
        Main(
            Div(
                Div(H1(titulo), P(subtitulo, cls="sub") if subtitulo else None),
                Div(
                    A("Produtos", href="/portal", cls="btn secundario"),
                    A("Fichas FDS", href="/portal/fds", cls="btn secundario"),
                    A("Área restrita", href="/login", cls="btn"),
                    cls="acoes",
                ),
                cls="cabecalho-pagina",
            ),
            *conteudo,
            Div(f"{config.APP_EMPRESA} - Portal de consulta de produtos químicos", cls="rodape"),
            cls="conteudo cheio",
        ),
    )


@rt("/portal")
def get(q: str = "", categoria: str = ""):
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, categoria=categoria, somente_aprovados=True, limite=None
        )
    busca = Form(
        Div(
            ui.campo("Buscar produto", "q", valor=q,
                     placeholder="nome comercial, fabricante, fornecedor, código ou categoria"),
            ui.campo("Categoria", "categoria", valor=categoria, opcoes=CATEGORIAS),
            Div(
                Button("Buscar", cls="btn", type="submit"),
                A("Limpar", href="/portal", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/portal",
    )
    return _molde_portal(
        "Consulta de produtos químicos aprovados",
        Div(busca, cls="card"),
        Div(
            Div(
                H2("Produtos liberados para uso"),
                Span(f"{len(produtos)} produto(s)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_produtos(produtos, prefixo="/portal", mostrar_fluxo=False),
            cls="card",
        ),
        subtitulo="Portal aberto aos colaboradores - somente produtos aprovados",
    )


@rt("/portal/fds")
def get(q: str = ""):
    with db_session() as s:
        produtos = servicos.buscar_produtos(
            s, q, somente_aprovados=True, somente_com_fds=True, limite=None
        )
    corpo = _pagina_fds(None, q, produtos, prefixo="/portal", publico=True)
    return _molde_portal(
        "Fichas de Dados de Segurança (FDS)",
        *corpo,
        subtitulo="Consulte e baixe a FDS dos produtos aprovados",
    )


@rt("/portal/produtos/{pid}")
def get(pid: int):
    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto or produto.status not in ("APROVADO", "DESCONTINUADO"):
            return _molde_portal(
                "Produto não disponível",
                ui.alerta("Este produto não está disponível para consulta pública.", "erro"),
            )
        docs = [d for d in produto.documentos if d.tipo in ("FDS", "FICHA_EMERGENCIA")]
    return _molde_portal(
        produto.nome_comercial,
        Div(
            Div(H2("Ficha do produto"), Span(ui.badge(produto.status), cls="direita"),
                cls="card-titulo"),
            Div(
                ui.item_ficha("Código interno", Span(produto.codigo_interno, cls="mono")),
                ui.item_ficha("Fabricante", produto.fabricante),
                ui.item_ficha("Fornecedor", produto.fornecedor),
                ui.item_ficha("Categoria", produto.categoria),
                ui.item_ficha("Número CAS", produto.numero_cas),
                ui.item_ficha("Estado físico", produto.estado_fisico),
                ui.item_ficha("Classificação GHS", produto.classificacao_ghs),
                ui.item_ficha("Número ONU", produto.onu_numero),
                ui.item_ficha("Local de armazenamento", produto.local_armazenamento),
                ui.item_ficha("Aplicação", produto.aplicacao, largo=True),
                ui.item_ficha("EPI recomendado", produto.epi_recomendado, largo=True),
                cls="ficha",
            ),
            cls="card",
        ),
        Div(
            Div(H2("Documentos de segurança"), cls="card-titulo"),
            Div(*[ui.cartao_documento(d, "/portal") for d in docs], cls="docs")
            if docs
            else ui.vazio("Nenhum documento disponível.", "▣"),
            cls="card",
        ),
        subtitulo=f"{produto.codigo_interno} - {produto.fabricante}",
    )


@rt("/portal/documentos/{did}")
def get(did: int):
    with db_session() as s:
        doc = s.get(Documento, did)
        if not doc or doc.produto.status not in ("APROVADO", "DESCONTINUADO"):
            return Response("Documento não disponível", status_code=404)
        if doc.tipo not in ("FDS", "FICHA_EMERGENCIA"):
            return Response("Documento não disponível", status_code=404)
        conteudo, nome, tipo = doc.conteudo, doc.nome_arquivo, doc.content_type
    return Response(
        conteudo,
        media_type=tipo or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


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
