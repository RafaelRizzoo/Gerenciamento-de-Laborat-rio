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

import json
import re
import secrets
from datetime import date, datetime
from urllib.parse import quote, unquote

from fasthtml.common import *  # noqa: F403
from sqlalchemy import desc, select

import config
import extracao
import idiomas
import notificacoes
import servicos
import ui
from database import criar_tabelas, db_session, descricao_conexao
from models import (
    AREAS_APROVACAO,
    AREAS_POR_UNIDADE,
    AREAS_SOLICITANTES,
    CATEGORIAS,
    CLASSES_RISCO,
    DOCUMENTOS_OBRIGATORIOS,
    ESTADOS_FISICOS,
    PRAZOS_UTILIZACAO,
    ETAPA_FINAL,
    UNIDADES,
    FDS_ALERTA_MESES,
    FDS_VALIDADE_ANOS,
    FLUXO_APROVACAO,
    MOTIVOS_REPROVACAO,
    ORGAOS_CONTROLADORES,
    PAPEIS,
    DESCRICAO_SECAO,
    ICONE_SECAO,
    ROTULOS_GRUPO_ARQUIVO,
    SECOES_RECURSO,
    EPIS,
    FORMAS_APLICACAO,
    SIM_NAO,
    SITUACOES_FDS,
    SITUACOES_FDS_FILTRO,
    SITUACOES_FDS_TELA,
    TIPOS_MIDIA,
    STATUS,
    STATUS_ABERTOS,
    TECNICO_POR_AREA,
    TECNICOS_SEGURANCA,
    TIPOS_DOCUMENTO,
    TIPOS_PRODUTO,
    UNIDADES_CONSUMO,
    UNIDADES_ITEM,
    Documento,
    LogAuditoria,
    Notificacao,
    AreaAprovador,
    ItemKit,
    PontoColetaKit,
    Produto,
    Recurso,
    RecursoArquivo,
    Usuario,
    par_valido,
    tecnico_da_area,
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

# Idioma da interface (PT / EN / ES) - ver idiomas.py.
idiomas.instalar(app)


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

    Quem entrou com senha provisória é desviado para a troca de senha antes
    de chegar a qualquer tela que exija login.
    """
    if logado(req):
        usuario = eu(req)
        if getattr(usuario, "precisa_trocar_senha", False) and (
            req.url.path != "/trocar-senha"
        ):
            return RedirectResponse("/trocar-senha", status_code=303)
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


# Formato de um número CAS: 2 a 7 dígitos, hífen, 2 dígitos, hífen, 1 dígito.
_CAS_FORMATO = re.compile(r"\d{2,7}-\d{2}-\d")


def _ler_cas(texto) -> list[str]:
    """Lê o campo de números CAS: um por linha, sem repetir.

    Aceita também vírgula e ponto-e-vírgula como separador, porque é o que
    sai quando alguém copia a lista da FDS numa linha só.
    """
    if not texto or not isinstance(texto, str):
        return []
    bruto = texto.replace(",", "\n").replace(";", "\n")
    numeros: list[str] = []
    for linha in bruto.splitlines():
        numero = linha.strip()
        if numero and numero not in numeros:
            numeros.append(numero)
    return numeros


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
    return idiomas.traduzir((
        *ui.cabeca("Acesso ao sistema"),
        Div(
            Div(
                Div(
                    B(config.APP_EMPRESA),
                    Span("Gestão de Produtos Químicos"),
                    idiomas.seletor(),
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
    ))


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


# ---------------------------------------------------------------------
# Idioma da interface
# ---------------------------------------------------------------------
# O seletor PT · EN · ES da barra superior aponta para cá. A escolha fica
# guardada na sessão e a pessoa volta para a página em que estava.


@rt("/idioma/{codigo}")
def get(req, sess, codigo: str):
    sess["idioma"] = idiomas.definir(codigo)
    volta = req.headers.get("referer") or "/"
    # Só aceita voltar para dentro do próprio sistema.
    if "://" in volta:
        corte = volta.split("://", 1)[1]
        volta = "/" + corte.split("/", 1)[1] if "/" in corte else "/"
    return RedirectResponse(volta if volta.startswith("/") else "/", status_code=303)


# ---------------------------------------------------------------------
# Troca de senha
# ---------------------------------------------------------------------
# Quem recebeu senha provisória cai aqui antes de qualquer tela que exija
# login (ver `exigir_login`), e só sai depois de escolher uma senha sua.

SENHA_MINIMA = 8


@rt("/trocar-senha")
def get(req, erro: str = "", ok: str = ""):
    if not logado(req):
        return RedirectResponse("/login?proximo=/trocar-senha", status_code=303)
    usuario = eu(req)
    obrigatoria = bool(getattr(usuario, "precisa_trocar_senha", False))

    formulario = Form(
        ui.campo("Senha atual", "atual", tipo="password", obrigatório=True,
                 ajuda="A provisória que você recebeu." if obrigatoria else None),
        ui.campo("Nova senha", "nova", tipo="password", obrigatório=True,
                 ajuda=f"Pelo menos {SENHA_MINIMA} caracteres."),
        ui.campo("Repita a nova senha", "confirma", tipo="password", obrigatório=True),
        Div(
            Button("Salvar senha", cls="btn verde", type="submit"),
            A("Cancelar", href="/", cls="btn secundario") if not obrigatoria else None,
            cls="barra-acoes",
        ),
        method="post",
        action="/trocar-senha",
    )

    return ui.pagina(
        "Trocar senha",
        ui.alerta(erro, "erro") if erro else None,
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(
            "Seu acesso foi criado com uma senha provisória. Escolha uma senha "
            "sua para continuar.",
            "aviso",
        ) if obrigatoria else None,
        Div(formulario, cls="card"),
        usuario=usuario,
        voltar=None if obrigatoria else "/",
        subtitulo=usuario.email,
    )


@rt("/trocar-senha")
async def post(req, sess):
    if not logado(req):
        return RedirectResponse("/login", status_code=303)
    usuario = eu(req)
    form = await req.form()
    atual = form.get("atual") or ""
    nova = form.get("nova") or ""
    confirma = form.get("confirma") or ""

    def voltar(texto):
        return RedirectResponse(_msg("/trocar-senha", "erro", texto), status_code=303)

    with db_session() as s:
        pessoa = s.get(Usuario, usuario.id)
        if not verificar_senha(atual, pessoa.senha_hash):
            return voltar("A senha atual não confere.")
        if len(nova) < SENHA_MINIMA:
            return voltar(f"A nova senha precisa de pelo menos {SENHA_MINIMA} caracteres.")
        if nova != confirma:
            return voltar("As duas senhas digitadas não são iguais.")
        if verificar_senha(nova, pessoa.senha_hash):
            return voltar("A nova senha precisa ser diferente da atual.")
        servicos.definir_senha(s, pessoa, nova)
    return RedirectResponse(
        _msg("/", "ok", "Senha alterada. Bom trabalho!"), status_code=303
    )


# =====================================================================
# Dashboard
# =====================================================================


@rt("/")
def get(req, erro: str = "", ok: str = ""):
    """Pagina inicial PUBLICA: hero de busca + atalhos para as areas do sistema."""
    usuario = eu(req)

    atalhos = [
        ui.cartao_atalho(
            ui.ICONES["fds"], "FDS",
            "Consulte as Fichas de Dados de Segurança dos produtos químicos cadastrados.",
            "/fds", "verde",
        ),
        ui.cartao_atalho(
            ui.ICONES["nova"], "Cadastro",
            "Cadastre um novo produto químico anexando a FDS e inicie o fluxo de aprovação.",
            "/solicitacoes/nova", "azul",
        ),
        ui.cartao_atalho(
            ui.ICONES["fdsr"], "FDSR",
            "Ficha com Dados de Segurança de Resíduos Químicos: o que é e qual "
            "norma a orienta.",
            "/fdsr", "verde",
        ),
        ui.cartao_atalho(
            ui.ICONES["kit"], "Kit Ambiental",
            "O que cada kit de contenção possui, para que serve e onde encontrar.",
            "/kit-ambiental", "azul",
        ),
        ui.cartao_atalho(
            ui.ICONES["controlados"], "Produtos Controlados",
            "Produtos sujeitos a controle da Polícia Federal e do Exército, com "
            "autorização e validade.",
            "/produtos-controlados", "verde",
        ),
        ui.cartao_atalho(
            ui.ICONES["recursos"], "Recursos e Documentos",
            "Procedimentos, formulários, normas externas e material de treinamento.",
            "/recursos", "azul",
        ),
        ui.cartao_atalho(
            ui.ICONES["aprovacoes"], "Aprovações",
            "Acompanhe o fluxo de aprovação e o status das solicitações.",
            "/aprovacoes", "verde", etiqueta=None if usuario else "login",
        ),
    ]

    return ui.molde_simples(
        "Início",
        ui.hero(),
        Div(
            ui.alerta(erro, "erro") if erro else None,
            ui.alerta(ok, "sucesso") if ok else None,
            Div(*atalhos, cls="atalhos"),
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
        minhas_pendencias = servicos.solicitacoes_pendentes_de(
            s, s.get(Usuario, usuario.id)
        )[:5]

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
            Div("Produtos Aprovados", cls="rotulo"),
            Div(str(ind["por_status"].get("APROVADO", 0)), cls="valor"),
            Div("liberados para uso", cls="nota"),
            href="/produtos",
            cls="kpi verde",
        ),
        A(
            Div("Produtos Reprovados", cls="rotulo"),
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
                H2("Pendências por área"),
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
    cabecalhos = ["Código", "Produto", "Fabricante", "Status"]
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
            placeholder="nome, fabricante, código ou CAS",
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
    """Passo 1: anexar a FDS. Os dados são extraídos dela no passo 2.

    Aberto: qualquer colaborador cadastra sem login. Quem não está
    identificado informa nome e e-mail no passo 2.
    """
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

    dados, preenchidos, aviso = extracao.extrair_de_pdf(conteudo, enviado.filename or "")
    token = _guardar_rascunho(
        conteudo, enviado.filename, getattr(enviado, "content_type", None)
    )
    return _formulario_solicitacao(
        usuario, token, enviado.filename, dados, preenchidos, aviso
    )


def _campo_tecnico_seguranca(unidade: str, area: str, escolhido: str = ""):
    """Técnico de Segurança responsável, definido pela unidade e pela área.

    Com responsável fixo, o campo vem preenchido e bloqueado. Sem (hoje só
    Rio das Ostras), o solicitante escolhe na lista. A tela acompanha a
    escolha de unidade e área sem recarregar; o servidor, de qualquer forma,
    refaz a conta no envio e não confia no que o navegador mandou.
    """
    fixo = tecnico_da_area(unidade, area)
    conhecido = (unidade or "", area or "") in TECNICO_POR_AREA
    if fixo:
        estado, valor = "fixo", fixo
    elif conhecido:
        estado, valor = "manual", escolhido
    else:
        estado, valor = "vazio", ""

    mapa = {f"{u}|{a}": (n or "") for (u, a), n in TECNICO_POR_AREA.items()}
    script = (
        "(function(){var m=" + json.dumps(mapa, ensure_ascii=False) + ";"
        "var u=document.querySelector('[name=unidade_solicitante]'),"
        "a=document.querySelector('[name=area_solicitante]'),"
        "s=document.getElementById('tecnico-seguranca');"
        "if(!u||!a||!s)return;"
        "function ajuda(e){['vazio','fixo','manual'].forEach(function(x){"
        "var el=document.getElementById('ajuda-tec-'+x);"
        "if(el)el.style.display=(x===e)?'':'none';});}"
        "function atualizar(){var k=u.value+'|'+a.value,e='vazio',n='';"
        "if(u.value&&a.value&&(k in m)){n=m[k];e=n?'fixo':'manual';}"
        "s.disabled=(e!=='manual');s.required=(e==='manual');"
        "if(e==='fixo')s.value=n;else if(e==='vazio')s.value='';"
        "ajuda(e);}"
        "u.addEventListener('change',atualizar);"
        "a.addEventListener('change',atualizar);atualizar();})();"
    )
    ajudas = {
        "vazio": "Definido pela unidade e pela área escolhidas acima.",
        "fixo": "Responsável pela área escolhida. Não pode ser alterado.",
        "manual": "Esta área não tem responsável definido. Escolha o técnico de Segurança.",
    }
    return Div(
        Label(
            Span("Técnico de Segurança responsável", Span(" *", cls="obr"), cls="rot"),
            Select(
                Option("Selecione...", value="", selected=not valor),
                *[Option(n, value=n, selected=(n == valor)) for n in TECNICOS_SEGURANCA],
                id="tecnico-seguranca", name="tecnico_seguranca",
                disabled=(estado in ("fixo", "vazio")),
                required=(estado == "manual"),
            ),
            *[
                Span(texto, id=f"ajuda-tec-{chave}", cls="ajuda",
                     style=None if chave == estado else "display:none")
                for chave, texto in ajudas.items()
            ],
            cls="campo",
        ),
        Script(NotStr(script)),
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
        # Quem está pedindo. Aparece sempre, logado ou não: vem preenchido
        # com os dados de quem entrou, e dá para trocar quando alguém cadastra
        # em nome de um colega que não tem acesso ao sistema.
        Fieldset(
            Legend("Solicitante Tenaris"),
            P(
                "Quem está pedindo o produto. Recebe os avisos de aprovação."
                if usuario is not None else
                "Você não está identificado no sistema. Informe seu nome e e-mail "
                "corporativo para acompanhar a solicitação e receber os avisos de "
                "aprovação.",
                cls="texto-mudo",
            ),
            Div(
                ui.campo(
                    "Nome do solicitante", "solicitante_nome",
                    valor=dados.get("solicitante_nome", "")
                    or (usuario.nome if usuario else ""),
                    ajuda="Troque se estiver cadastrando para outra pessoa."
                    if usuario is not None else None,
                ),
                ui.campo(
                    "E-mail do solicitante", "solicitante_email", "email",
                    dados.get("solicitante_email", "")
                    or (usuario.email if usuario else ""),
                ),
                cls="linha-form",
            ),
            cls="secao",
        ),
        Fieldset(
            Legend("Solicitante terceiro"),
            P(
                "Preencha apenas quando a solicitação vier de uma empresa "
                "terceira. Em branco, vale o solicitante Tenaris acima.",
                cls="texto-mudo",
            ),
            Div(
                ui.campo("Nome do solicitante terceiro", "terceiro_nome",
                         valor=dados.get("terceiro_nome", ""),
                         placeholder="Ex.: João Pereira"),
                ui.campo("Empresa", "terceiro_empresa",
                         valor=dados.get("terceiro_empresa", ""),
                         placeholder="Ex.: Construtora Alfa"),
                cls="linha-form",
            ),
            Div(
                ui.campo("Gestor Tenaris do contrato", "gestor_contrato",
                         valor=dados.get("gestor_contrato", ""),
                         ajuda="Quem responde pelo contrato dessa empresa."),
                ui.campo("E-mail do gestor", "gestor_email", tipo="email",
                         valor=dados.get("gestor_email", ""),
                         placeholder="nome.sobrenome@tenaris.com"),
                cls="linha-form",
            ),
            cls="secao",
        ),
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
            # CAS (campo alto) de um lado, tipo e estado físico empilhados do
            # outro: as duas colunas ficam com a mesma altura, sem vão.
            Div(
                ui.campo(
                    "Números CAS", "numero_cas",
                    valor=dados.get("numero_cas", ""), linhas=5, obrigatório=True,
                    placeholder="67-64-1",
                    ajuda="Um número por linha. "
                          + (auto("numero_cas") or "Ex.: 67-64-1"),
                ),
                Div(
                    ui.campo("Tipo de produto", "tipo_produto",
                             valor=dados.get("tipo_produto", ""), opcoes=TIPOS_PRODUTO,
                             obrigatório=True, ajuda=auto("tipo_produto")),
                    ui.campo("Estado físico", "estado_fisico",
                             valor=dados.get("estado_fisico", ""), opcoes=ESTADOS_FISICOS,
                             obrigatório=True, ajuda=auto("estado_fisico")),
                    cls="coluna-form",
                ),
                cls="linha-dupla",
            ),
            cls="secao",
        ),
        Fieldset(
            Legend("Uso na planta"),
            Div(
                ui.campo("Unidade solicitante", "unidade_solicitante",
                         valor=dados.get("unidade_solicitante", ""),
                         opcoes=UNIDADES, obrigatório=True,
                         ajuda="Onde o produto será utilizado."),
                ui.campo("Área solicitante", "area_solicitante",
                         valor=dados.get("area_solicitante", ""),
                         grupos=AREAS_POR_UNIDADE, obrigatório=True,
                         ajuda="Escolha uma área da unidade selecionada."),
                _campo_tecnico_seguranca(
                    dados.get("unidade_solicitante", ""),
                    dados.get("area_solicitante", ""),
                    dados.get("tecnico_seguranca", ""),
                ),
                cls="linha-form linha-tres",
            ),
            Div(
                ui.campo(
                    "Finalidade de uso", "aplicacao", valor=dados.get("aplicacao", ""),
                    linhas=5, obrigatório=True,
                    ajuda="Onde e como o produto será aplicado no processo.",
                ),
                Div(
                    ui.campo("Forma de aplicação", "forma_aplicacao",
                             valor=dados.get("forma_aplicacao", ""),
                             opcoes=FORMAS_APLICACAO, obrigatório=True,
                             ajuda="Como o produto é aplicado no processo."),
                    ui.campo("Prazo de utilização", "prazo_utilizacao",
                             valor=dados.get("prazo_utilizacao", ""), obrigatório=True,
                             opcoes=PRAZOS_UTILIZACAO),
                    cls="coluna-form",
                ),
                cls="linha-dupla",
            ),
            Div(
                ui.campo("Quantidade prevista", "consumo_estimado",
                         valor=dados.get("consumo_estimado", ""), obrigatório=True,
                         placeholder="Ex.: 200",
                         ajuda="Consumo em condições máximas."),
                ui.campo("Unidade de medida", "unidade",
                         valor=dados.get("unidade", ""), obrigatório=True,
                         opcoes=UNIDADES_CONSUMO),
                cls="linha-dupla",
            ),
            # Funcionários expostos e função dos expostos saíram daqui: quem
            # avalia exposição ocupacional é a área de Saúde, no parecer.
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
                ui.campo("Inflamável", "inflamavel",
                         valor=dados.get("inflamavel", ""), obrigatório=True,
                         opcoes=[(k, v) for k, v in SIM_NAO.items()],
                         ajuda=auto("inflamavel") or "Seção 2 da FDS."),
                ui.campo("Cancerígeno", "cancerigeno",
                         valor=dados.get("cancerigeno", ""), obrigatório=True,
                         opcoes=[(k, v) for k, v in SIM_NAO.items()],
                         ajuda="Produto com agentes cancerígenos? Seção 11 da FDS."),
                ui.campo("Ponto de fulgor", "ponto_fulgor",
                         valor=dados.get("ponto_fulgor", ""),
                         placeholder="Ex.: 32 °C",
                         ajuda=auto("ponto_fulgor")
                               or "Obrigatório quando o produto for inflamável "
                                  "(seção 9 da FDS)."),
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
                         or "Consta na ficha."),
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
async def post(req, sess):
    """Passo 3: valida tudo, grava a solicitação e dispara o fluxo."""
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
        ("numero_cas", "Números CAS"),
        ("tipo_produto", "Tipo de produto"),
        ("estado_fisico", "Estado físico"),
        ("area_solicitante", "Área solicitante"),
        ("aplicacao", "Finalidade de uso"),
        ("forma_aplicacao", "Forma de aplicação"),
        ("prazo_utilizacao", "Prazo de utilização"),
        ("consumo_estimado", "Quantidade prevista"),
        ("unidade", "Unidade de medida"),
        ("inflamavel", "Inflamável"),
        ("cancerigeno", "Cancerígeno"),
        ("classificacao_ghs", "Classificação GHS"),
        ("observacoes", "Observações"),
    ]
    # O solicitante Tenaris pode ficar em branco quando a solicitação vem de
    # uma empresa terceira. Nesse caso o terceiro e o gestor do contrato
    # (que recebe os avisos) passam a ser obrigatórios.
    sem_solicitante_tenaris = not (
        dados.get("solicitante_nome") or dados.get("solicitante_email")
    )
    if sem_solicitante_tenaris:
        obrigatorios = [
            ("terceiro_nome", "Nome do solicitante terceiro"),
            ("terceiro_empresa", "Empresa do terceiro"),
            ("gestor_contrato", "Gestor Tenaris do contrato"),
            ("gestor_email", "E-mail do gestor"),
        ] + obrigatorios
    faltando =[rotulo for campo, rotulo in obrigatorios if not dados.get(campo)]
    if unidade_solicitante not in UNIDADES:
        faltando.append("Unidade solicitante")
    if not riscos:
        faltando.append("Classe de risco")
    if revisao is None:
        faltando.append("Data de revisão da FDS")
    if dados.get("inflamavel") not in SIM_NAO:
        faltando.append("Inflamável")
    if dados.get("cancerigeno") not in SIM_NAO:
        faltando.append("Cancerígeno")
    if dados.get("prazo_utilizacao") and dados["prazo_utilizacao"] not in PRAZOS_UTILIZACAO:
        faltando.append("Prazo de utilização")
    if dados.get("unidade") and dados["unidade"] not in UNIDADES_CONSUMO:
        faltando.append("Unidade de medida")
    if dados.get("forma_aplicacao") and dados["forma_aplicacao"] not in FORMAS_APLICACAO:
        faltando.append("Forma de aplicação")
    if faltando:
        return voltar("Preencha os campos obrigatórios: " + ", ".join(dict.fromkeys(faltando)) + ".")

    # A área tem de ser de fato da unidade escolhida: "Qualidade" existe em
    # Pinda e no MC, "TCHB" só no MC. Sem esta conferência o cadastro aceita
    # um par que não existe na planta.
    if not par_valido(unidade_solicitante, dados.get("area_solicitante")):
        return voltar(
            f"A área \"{dados.get('area_solicitante')}\" não é da unidade "
            f"{unidade_solicitante}. Escolha uma área da unidade selecionada."
        )

    # Solicitante terceiro é opcional, mas pela metade não serve: se a
    # solicitação vem de uma empresa terceira, precisamos saber de quem é a
    # empresa e quem na Tenaris responde pelo contrato.
    terceiro = {
        "terceiro_nome": "Nome do solicitante terceiro",
        "terceiro_empresa": "Empresa do terceiro",
        "gestor_contrato": "Gestor Tenaris do contrato",
    }
    if any(dados.get(c) for c in list(terceiro) + ["gestor_email"]):
        faltam_terceiro = [rot for c, rot in terceiro.items() if not dados.get(c)]
        if faltam_terceiro:
            return voltar(
                "Solicitação de empresa terceira: preencha também "
                + ", ".join(faltam_terceiro) + "."
            )
        if dados.get("gestor_email") and "@" not in dados["gestor_email"]:
            return voltar("Informe um e-mail válido para o gestor do contrato.")

    # O ponto de fulgor só faz sentido (e é exigido) para inflamáveis.
    if dados.get("inflamavel") == "SIM" and not dados.get("ponto_fulgor"):
        return voltar(
            "Produto inflamável: informe o ponto de fulgor (seção 9 da FDS)."
        )

    if dados.get("solicitante_email") and "@" not in dados["solicitante_email"]:
        return voltar("Informe um e-mail corporativo válido.")

    if revisao > date.today():
        return voltar("A data de revisão da FDS não pode estar no futuro.")

    # Um CAS por linha. A FDS traz um por substância da composição, então a
    # mistura tem vários; aqui só se confere o formato.
    cas = _ler_cas(dados.get("numero_cas"))
    invalidos = [c for c in cas if not _CAS_FORMATO.fullmatch(c)]
    if invalidos:
        return voltar(
            "Número CAS fora do formato: " + ", ".join(invalidos[:3])
            + ". O formato é 67-64-1."
        )
    if not cas:
        return voltar("Informe pelo menos um número CAS.")
    dados["cas"] = cas
    dados["numero_cas"] = cas[0]

    # Técnico de Segurança: área com responsável fixo manda; as demais pedem
    # a escolha do solicitante.
    tecnico = tecnico_da_area(unidade_solicitante, dados.get("area_solicitante"))
    if not tecnico:
        tecnico = (dados.get("tecnico_seguranca") or "").strip()
        if tecnico not in TECNICOS_SEGURANCA:
            return voltar(
                "Escolha o técnico de Segurança responsável por esta área."
            )
    dados["tecnico_seguranca"] = tecnico
    dados["unidade_solicitante"] = unidade_solicitante

    dados["fabricas"] = [unidade_solicitante]
    dados["setor_solicitante"] = dados.get("area_solicitante")
    dados["riscos"] = riscos
    # O controle regulatório (órgão, licença e validade) é preenchido pelo
    # Químico Responsável na análise: o solicitante não tem essa informação.

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
        # O solicitante vem do formulário, não de quem está logado: assim dá
        # para cadastrar em nome de um colega que não tem acesso ao sistema.
        # Quem não mexeu no campo cai no próprio cadastro de qualquer forma,
        # porque ele vem preenchido com os dados de quem entrou.
        if not servicos.tecnico_por_nome(s, dados["tecnico_seguranca"]):
            return voltar(
                f"O técnico {dados['tecnico_seguranca']} ainda não tem login no "
                "sistema. Peça ao administrador para cadastrá-lo em Aprovações."
            )
        if sem_solicitante_tenaris:
            # Pedido de terceiro: quem recebe os avisos é o gestor do contrato.
            solicitante = servicos.obter_ou_criar_solicitante(
                s, dados.get("gestor_contrato"), dados.get("gestor_email")
            )
        else:
            solicitante = servicos.obter_ou_criar_solicitante(
                s, dados.get("solicitante_nome"), dados.get("solicitante_email")
            )
        produto = servicos.criar_solicitacao(s, dados, solicitante, arquivos)
        pid = produto.id

    _RASCUNHOS.pop(token, None)
    # Quem cadastrou sem login precisa continuar enxergando o que acabou de
    # enviar - a ficha só fica pública depois de aprovada.
    _guardar_minha(sess, pid)
    return RedirectResponse(f"/solicitacoes/recibo/{pid}", status_code=303)


# ---------------------------------------------------------------------
# Comprovante do envio
# ---------------------------------------------------------------------
# Sem isto, quem cadastra sem login é jogado na ficha do produto - que ainda
# não está aprovada e, portanto, não é pública. A pessoa terminava o
# formulário e via "produto não disponível para consulta pública".

_MINHAS_NA_SESSAO = 20


def _guardar_minha(sess, pid: int) -> None:
    """Marca na sessão do navegador que esta pessoa enviou esta solicitação."""
    try:
        minhas = [int(x) for x in (sess.get("minhas") or [])]
    except (TypeError, ValueError):
        minhas = []
    if pid not in minhas:
        minhas.append(pid)
    sess["minhas"] = minhas[-_MINHAS_NA_SESSAO:]


def _e_minha(sess, pid: int) -> bool:
    try:
        return pid in [int(x) for x in (sess.get("minhas") or [])]
    except (TypeError, ValueError):
        return False


@rt("/solicitacoes/recibo/{pid:int}")
def get(req, sess, pid: int):
    """Confirmação do envio, com o protocolo e o que acontece daqui pra frente."""
    usuario = eu(req)
    if usuario is None and not _e_minha(sess, pid):
        return RedirectResponse(f"/produtos/{pid}", status_code=303)

    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return ui.pagina("Solicitação não encontrada",
                             ui.alerta("Registro inexistente.", "erro"), usuario=usuario)
        codigo = produto.codigo_interno
        nome = produto.nome_comercial
        fabricante = produto.fabricante or "-"
        email = produto.solicitante.email if produto.solicitante else ""
        tecnico = produto.tecnico_seguranca.nome if produto.tecnico_seguranca else None

    areas = ", ".join(rotulo for _, rotulo in AREAS_APROVACAO)

    return ui.pagina(
        "Solicitação enviada",
        ui.alerta(
            f"Pronto! A solicitação foi registrada com o protocolo {codigo}.", "ok"
        ),
        Div(
            Div(H2("Comprovante"), cls="card-titulo"),
            Div(
                ui.item_ficha("Protocolo", Span(codigo, cls="mono")),
                ui.item_ficha("Produto", B(nome)),
                ui.item_ficha("Fabricante", fabricante),
                ui.item_ficha("Avisos enviados para", email),
                cls="ficha",
            ),
            cls="card",
        ),
        Div(
            Div(H2("O que acontece agora"), cls="card-titulo"),
            Ol(
                Li(B("Análise das áreas. "),
                   f"A solicitação está com {areas} ao mesmo tempo - não há ordem "
                   "entre elas, cada uma dá o seu parecer quando puder."),
                Li(B("Técnico de Segurança. "),
                   "Na Segurança, só o técnico responsável recebe a solicitação: ",
                   tecnico, ".")
                if tecnico else None,
                Li(B("Aprovador Final. "),
                   "Concluídas as áreas, a solicitação segue para o "
                   "Aprovador Final, que fecha a aprovação."),
                Li(B("Avisos. "),
                   "Você recebe um e-mail a cada parecer registrado e outro quando "
                   "o fluxo terminar. Se nada se mover, as áreas são cobradas "
                   "automaticamente a cada 7 dias."),
                cls="lista-passos",
            ),
            P(
                "Enquanto o servidor de e-mail da Tenaris não estiver configurado, "
                "os avisos ficam registrados dentro do sistema em vez de sair por "
                "e-mail.",
                cls="pequeno texto-mudo",
            ) if not config.SMTP_ATIVO else None,
            cls="card",
        ),
        Div(
            A("Acompanhar esta solicitação", href=f"/produtos/{pid}", cls="btn"),
            A("Cadastrar outro produto", href="/solicitacoes/nova", cls="btn secundario"),
            A("Voltar ao início", href="/", cls="btn secundario"),
            cls="barra-acoes",
        ),
        usuario=usuario,
        subtitulo=f"{codigo} - {nome}",
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


def _gaveta_novo_aprovador(areas_geridas: list):
    """Painel lateral de cadastro — meia página, sem sair da tela de Aprovações."""
    if not areas_geridas:
        return None
    opcoes = [(a, dict(FLUXO_APROVACAO).get(a, a)) for a in areas_geridas]
    unica = opcoes[0] if len(opcoes) == 1 else None
    return Div(
        A(href="#", cls="gaveta-fundo", aria_label="Fechar"),
        Div(
            Div(
                H2("Novo aprovador", Br(),
                   Span(unica[1] if unica else "Escolha a área", cls="gaveta-sub")),
                A("✕", href="#", cls="gaveta-fechar", title="Fechar"),
                cls="gaveta-topo",
            ),
            P(
                "A pessoa passa a receber os avisos da área e pode registrar "
                "parecer. Se ela ainda não tiver acesso, o sistema cria o "
                "cadastro e gera uma senha provisória.",
                cls="pequeno texto-mudo",
            ),
            Form(
                (Input(type="hidden", name="area", value=unica[0]) if unica
                 else ui.campo("Área de aprovação", "area", opcoes=opcoes,
                               obrigatório=True)),
                ui.campo("Nome completo", "nome", obrigatório=True,
                         placeholder="Ex.: Luciana Oliveira"),
                ui.campo("E-mail corporativo", "email", tipo="email", obrigatório=True,
                         placeholder="nome.sobrenome@tenaris.com",
                         ajuda="É por ele que a pessoa entra no sistema."),
                ui.campo("Unidade", "setor", opcoes=UNIDADES,
                         ajuda="Opcional - só para saber de qual planta ela é."),
                Div(
                    Button("Salvar", cls="btn verde", type="submit"),
                    A("Cancelar", href="#", cls="btn secundario"),
                    cls="barra-acoes",
                ),
                method="post",
                action="/aprovadores/novo",
            ),
            cls="gaveta-painel",
        ),
        id="novo-aprovador",
        cls="gaveta",
    )


def _tabela_solicitacoes(produtos, areas_usuario, usuario_id=None):
    """Tabela do módulo de aprovações, com as colunas que o aprovador precisa."""
    if not produtos:
        return ui.vazio("Nenhuma solicitação encontrada com esses filtros.", "☑")
    areas_usuario = list(areas_usuario or [])
    linhas = []
    for p in produtos:
        minha = any(p.aguarda_usuario(area, usuario_id) for area in areas_usuario)
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
                    Span(
                        ", ".join(p.aguardando_labels) if p.aberta else "-",
                        cls="pequeno texto-mudo",
                    ),
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


@rt("/produtos/{pid:int}/tecnico-seguranca")
async def post(req, pid: int):
    """Administrador passa a análise de Segurança para outro técnico."""
    barrado = exigir_papel(req, "ADMIN")
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    try:
        novo_id = int(form.get("tecnico_id") or 0)
    except ValueError:
        novo_id = 0
    with db_session() as s:
        produto = s.get(Produto, pid)
        novo = s.get(Usuario, novo_id) if novo_id else None
        if not produto or not novo:
            return RedirectResponse(
                _msg(f"/produtos/{pid}", "erro", "Escolha um técnico válido."),
                status_code=303,
            )
        try:
            servicos.trocar_tecnico_seguranca(s, produto, novo, s.get(Usuario, usuario.id))
        except ValueError as exc:
            return RedirectResponse(_msg(f"/produtos/{pid}", "erro", str(exc)),
                                    status_code=303)
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok", f"Técnico de Segurança alterado para {novo.nome}."),
        status_code=303,
    )


@rt("/aprovacoes")
def get(req, sess, status: str = "", fabrica: str = "",
        de: str = "", ate: str = "", q: str = "", ok: str = "", erro: str = ""):
    """Gestão do fluxo de aprovação. Exige login."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)

    with db_session() as s:
        # Todo aprovador vê as solicitações abertas e age só na sua etapa. A
        # exceção é o técnico de Segurança: ele não vê as solicitações que
        # foram para o colega de outra área.
        u_fila = s.get(Usuario, usuario.id)
        produtos = [
            p for p in servicos.buscar_produtos(
                s, q, status=status, fabrica=fabrica,
                data_de=_data(de), data_ate=_data(ate),
                somente_abertas=not status,
                limite=None,
            )
            if servicos.visivel_na_fila(s, u_fila, p)
        ]
        contagem = {
            chave: sum(1 for p in produtos if p.status == chave)
            for chave in STATUS_ABERTOS
        }
        u_atual = s.get(Usuario, usuario.id)
        areas_usuario = servicos.areas_do_usuario(s, u_atual)
        minhas = sum(
            1 for p in produtos
            if any(p.aguarda_usuario(a, usuario.id) for a in areas_usuario)
        )
        # Quem pode cadastrar aprovador (gaveta lateral): Admin e Aprovador
        # Final cuidam de todas as áreas; um aprovador cuida apenas da própria.
        areas_geridas = servicos.areas_gerenciaveis(s, u_atual)
        gerencia = bool(areas_geridas)

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
        cls="painel-fds",
    )

    filtros = Form(
        Div(
            ui.campo("Buscar", "q", valor=q, placeholder="produto, fabricante ou código"),
            ui.campo("Status", "status", valor=status,
                     opcoes=[(k, STATUS[k]) for k in
                             ("PENDENTE", "EM_ANALISE",
                              "APROVADO", "REPROVADO")]),
            ui.campo("Unidade", "fabrica", valor=fabrica, opcoes=UNIDADES),
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

    # A senha provisória aparece uma única vez, para quem acabou de cadastrar.
    criado = sess.pop("senha_nova", None)
    aviso_senha = (
        Div(
            Div(H2("Acesso criado"), cls="card-titulo"),
            P(
                B(criado["nome"]), " já pode entrar no sistema. Passe estes dados "
                "para a pessoa — a senha aparece só desta vez.",
            ),
            Div(
                Div(Div("E-mail", cls="rot"), Div(criado["email"], cls="val mono"),
                    cls="item"),
                Div(Div("Senha provisória", cls="rot"),
                    Div(criado["senha"], cls="val mono senha-nova"), cls="item"),
                cls="ficha",
            ),
            P(
                "No primeiro acesso o sistema pede para ela trocar por uma senha "
                "própria. O aviso também ficou registrado em ",
                A("Notificações", href="/notificacoes"),
                ", e vai por e-mail assim que o servidor da Tenaris estiver "
                "configurado.",
                cls="pequeno texto-mudo",
            ),
            cls="card destaque-senha",
        )
        if criado and criado.get("senha")
        else None
    )

    return ui.pagina(
        "Aprovações",
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        aviso_senha,
        painel,
        Div(filtros, cls="card"),
        Div(
            Div(
                H2("Solicitações"),
                Span(f"{len(produtos)} registro(s)", cls="direita"),
                cls="card-titulo",
            ),
            _tabela_solicitacoes(produtos, areas_usuario, usuario.id),
            cls="card",
        ),
        _gaveta_novo_aprovador(areas_geridas),
        usuario=usuario,
        subtitulo="Gestão do fluxo de validação dos produtos químicos",
        acoes=[
            A("+ Novo aprovador", href="#novo-aprovador", cls="btn")
            if gerencia else None,
        ],
    )


def _erro_aprovadores(texto: str):
    return RedirectResponse(_msg("/aprovacoes", "erro", texto), status_code=303)


@rt("/aprovadores/novo")
async def post(req, sess):
    """Cadastra uma pessoa e já a vincula a uma área, pela gaveta lateral."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    area = (form.get("area") or "").strip()
    nome = (form.get("nome") or "").strip()
    email = (form.get("email") or "").strip().lower()
    setor = (form.get("setor") or "").strip() or None

    if not nome or "@" not in email:
        return _erro_aprovadores("Informe o nome completo e o e-mail corporativo.")

    with db_session() as s:
        autor = s.get(Usuario, usuario.id)
        geridas = servicos.areas_gerenciaveis(s, autor)
        if not geridas:
            return _erro_aprovadores(
                "Você não gerencia nenhuma área de aprovação."
            )
        if not area and len(geridas) == 1:
            area = geridas[0]
        if area not in geridas:
            return _erro_aprovadores(
                "Você só pode incluir aprovadores nas áreas que gerencia."
            )
        try:
            pessoa, senha = servicos.criar_aprovador(s, area, nome, email, setor, autor)
        except ValueError as exc:
            return _erro_aprovadores(str(exc))
        dados = {"nome": pessoa.nome, "email": pessoa.email, "senha": senha}
        rotulo = dict(FLUXO_APROVACAO).get(area, area)

    if senha:
        # A senha provisória não vai pela URL nem por e-mail: fica guardada na
        # sessão de quem cadastrou e aparece uma única vez na próxima tela.
        sess["senha_nova"] = dados
        return RedirectResponse("/aprovacoes", status_code=303)
    return RedirectResponse(
        _msg("/aprovacoes", "ok",
             f"{dados['nome']} passou a aprovar por {rotulo} com o acesso que já tinha."),
        status_code=303,
    )


@rt("/aprovadores/adicionar")
async def post(req):
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    area = (form.get("area") or "").strip()
    uid = (form.get("usuario_id") or "").strip()
    if area not in dict(FLUXO_APROVACAO) or not uid.isdigit():
        return _erro_aprovadores("Selecione a área e a pessoa.")
    with db_session() as s:
        autor = s.get(Usuario, usuario.id)
        if not servicos.pode_gerenciar_area(s, autor, area):
            return _erro_aprovadores(
                "Você só pode incluir aprovadores nas áreas que gerencia."
            )
        pessoa = s.get(Usuario, int(uid))
        if not pessoa:
            return _erro_aprovadores("Usuário não encontrado.")
        servicos.adicionar_aprovador(s, area, pessoa, autor)
        nome, rotulo = pessoa.nome, dict(FLUXO_APROVACAO).get(area, area)
    return RedirectResponse(
        _msg("/aprovacoes", "ok", f"{nome} passou a aprovar por {rotulo}."),
        status_code=303,
    )


@rt("/aprovadores/remover")
async def post(req):
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    area = (form.get("area") or "").strip()
    uid = (form.get("usuario_id") or "").strip()
    if area not in dict(FLUXO_APROVACAO) or not uid.isdigit():
        return _erro_aprovadores("Dados inválidos.")
    with db_session() as s:
        autor = s.get(Usuario, usuario.id)
        if not servicos.pode_gerenciar_area(s, autor, area):
            return _erro_aprovadores(
                "Você só pode remover aprovadores das áreas que gerencia."
            )
        servicos.remover_aprovador(s, area, int(uid), autor)
        rotulo = dict(FLUXO_APROVACAO).get(area, area)
    return RedirectResponse(
        _msg("/aprovacoes", "ok", f"Aprovador removido de {rotulo}."), status_code=303
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


# =====================================================================
# Kit Ambiental (informativo)
# =====================================================================
#
# A composição é definida por TIPO de kit (Kit A, Kit B, ...) e vale para
# toda a Tenaris. Cada fábrica informa apenas onde os seus kits ficam.
# Consulta aberta a qualquer colaborador; manutenção com Meio Ambiente,
# Segurança e Administrador.
#


def _pode_kit(req) -> bool:
    return servicos.pode_editar_kit(eu(req))


async def _foto_do_form(form, campo: str = "foto") -> tuple[dict | None, str | None]:
    enviado = form.get(campo)
    if enviado is None or not getattr(enviado, "filename", ""):
        return None, None
    conteudo = await enviado.read()
    if not conteudo:
        return None, None
    if len(conteudo) > config.MAX_UPLOAD_BYTES:
        return None, f"A imagem excede o limite de {config.MAX_UPLOAD_MB} MB."
    tipo = (getattr(enviado, "content_type", "") or "").lower()
    if not tipo.startswith("image/"):
        return None, "O arquivo da foto precisa ser uma imagem (JPG, PNG...)."
    return {"conteudo": conteudo, "content_type": tipo}, None


def _cartao_kit(kit, pode: bool):
    fabricas = kit.fabricas
    return Div(
        Div(
            Div(kit.codigo, cls="selo"),
            Div(
                H3(kit.nome),
                P(kit.utilidade or "Utilidade ainda não descrita.",
                  cls="texto-mudo" if not kit.utilidade else None),
                cls="txt",
            ),
            cls="kit-topo",
        ),
        Div(
            Span(f"{len(kit.itens_ativos)} item(ns)", cls="chip tipo"),
            Span(f"{len(kit.pontos_ativos)} ponto(s) de coleta", cls="chip"),
            *[Span(f, cls="chip fabrica") for f in fabricas],
            Span("composição a definir", cls="chip controlado vencida")
            if kit.sem_composicao
            else None,
            cls="tags",
        ),
        Div(
            A("Ver o que tem no kit", href=f"/kit-ambiental/{kit.id}", cls="btn"),
            A("Editar", href=f"/kit-ambiental/{kit.id}?editar=1", cls="btn secundario")
            if pode
            else None,
            cls="barra-acoes",
        ),
        cls="kit-card",
    )


def _tabela_pontos(agrupado: dict, mostrar_kit: bool = True, pode: bool = False):
    if not agrupado:
        return ui.vazio("Nenhum ponto de coleta cadastrado ainda.", "⌖")
    blocos = []
    for fabrica, pontos in agrupado.items():
        blocos.append(
            Div(
                Div(
                    H3(fabrica),
                    Span(f"{len(pontos)} kit(s)", cls="qtd"),
                    cls="fabrica-titulo",
                ),
                Div(
                    Table(
                        Thead(
                            Tr(
                                Th("Kit") if mostrar_kit else None,
                                Th("Onde fica"),
                                Th("Quem procurar"),
                                Th("Observações"),
                                Th("") if pode else None,
                            )
                        ),
                        Tbody(
                            *[
                                Tr(
                                    Td(
                                        A(p.kit.codigo, href=f"/kit-ambiental/{p.kit_id}",
                                          cls="mono")
                                    ) if mostrar_kit else None,
                                    Td(B(p.local)),
                                    Td(p.contato or Span("-", cls="texto-mudo"),
                                       cls="pequeno"),
                                    Td(p.observacoes or "-", cls="pequeno"),
                                    Td(
                                        Form(
                                            Button("remover", cls="tirar", type="submit"),
                                            method="post",
                                            action=f"/kit-ambiental/pontos/{p.id}/remover",
                                        ),
                                        cls="nowrap",
                                    )
                                    if pode
                                    else None,
                                )
                                for p in pontos
                            ]
                        ),
                        cls="dados",
                    ),
                    style="overflow-x:auto",
                ),
                cls="fabrica-bloco",
            )
        )
    return Div(*blocos, cls="fabricas")


@rt("/fdsr")
def get(req, fabrica: str = ""):
    """FDSR: filtro de unidade e a descrição da norma, só para consulta."""
    usuario = eu(req)
    if fabrica not in UNIDADES:
        fabrica = ""

    filtro = Form(
        Div(
            ui.campo("Unidade", "fabrica", valor=fabrica, opcoes=UNIDADES),
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href="/fdsr", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/fdsr",
    )

    return ui.pagina(
        "FDSR",
        Div(filtro, cls="card"),
        Div(
            Div(
                H2("Descrição da norma"),
                Span(f"Unidade: {fabrica}", cls="direita") if fabrica else None,
                cls="card-titulo",
            ),
            P(
                "A FDSR é um documento que apresenta informações sobre os riscos "
                "dos resíduos químicos, orientando sobre seu manuseio, "
                "armazenamento, transporte, medidas de segurança e procedimentos "
                "de emergência, visando à proteção da saúde humana e do meio "
                "ambiente."
            ),
            P(B("Referência normativa: "), "ABNT NBR 16725:2023."),
            P(
                B("Trecho de referência da norma: "),
                "A FDSR deve apresentar informações sobre os perigos dos resíduos "
                "químicos e recomendações de segurança relacionadas ao transporte, "
                "manuseio, armazenamento e procedimentos de emergência.",
            ),
            cls="card",
        ),
        usuario=usuario,
        subtitulo="Ficha com Dados de Segurança de Resíduos Químicos",
    )


@rt("/kit-ambiental")
def get(req, fabrica: str = "", ok: str = "", erro: str = ""):
    """Kit Ambiental: o que cada kit tem e onde encontrar."""
    usuario = eu(req)
    pode = _pode_kit(req)
    with db_session() as s:
        kits = servicos.listar_kits(s)
        resumo = servicos.resumo_kits(s)
        agrupado = servicos.pontos_por_fabrica(s, fabrica)

    filtro = Form(
        Div(
            ui.campo("Unidade", "fabrica", valor=fabrica, opcoes=UNIDADES),
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href="/kit-ambiental", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        method="get",
        action="/kit-ambiental",
    )

    aviso = (
        ui.alerta(
            Span(
                B("Composição pendente: "),
                "os kits ",
                ", ".join(k.codigo for k in resumo["sem_composicao"]),
                " ainda não têm itens cadastrados.",
            ),
            "aviso",
        )
        if pode and resumo["sem_composicao"]
        else None
    )

    return ui.pagina(
        "Kit Ambiental",
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        aviso,
        Div(
            Div(
                H2("Tipos de kit"),
                Span("A composição é a mesma em todas as fábricas", cls="direita"),
                cls="card-titulo",
            ),
            Div(*[_cartao_kit(k, pode) for k in kits], cls="kits-grade")
            if kits
            else ui.vazio("Nenhum kit cadastrado ainda.", "▣"),
            cls="card",
        ),
        Div(
            Div(
                H2("Onde encontrar"),
                Span(
                    f"{sum(len(p) for p in agrupado.values())} ponto(s)",
                    cls="direita",
                ),
                cls="card-titulo",
            ),
            filtro,
            Hr(style="border:0;border-top:1px solid var(--cinza-fundo);margin:1rem 0"),
            _tabela_pontos(agrupado, pode=pode),
            cls="card",
        ),
        usuario=usuario,
        subtitulo="O que cada kit de contenção possui, para que serve e onde encontrar",
        acoes=[A("+ Novo tipo de kit", href="/kit-ambiental/novo", cls="btn")]
        if pode
        else None,
    )


# ------------------------------------------------------------- Detalhe
def _grade_itens(kit, pode: bool):
    itens = kit.itens_ativos
    if not itens:
        return ui.vazio(
            "A composição deste kit ainda não foi cadastrada.", "▣"
        )
    cartoes = []
    for item in itens:
        cartoes.append(
            Div(
                Div(
                    Img(src=f"/kit-ambiental/itens/{item.id}/foto", alt=item.nome)
                    if item.tem_foto
                    else Span("sem foto", cls="sem-foto"),
                    cls="item-foto",
                ),
                Div(
                    Div(
                        B(item.nome),
                        Span(item.quantidade_label, cls="chip versao")
                        if item.quantidade
                        else None,
                        cls="item-nome",
                    ),
                    P(item.utilidade or "Utilidade não descrita.",
                      cls="item-uso" + ("" if item.utilidade else " texto-mudo")),
                    Div(
                        A(
                            f"FDS - {item.produto.nome_comercial}",
                            href=f"/produtos/{item.produto_id}",
                            cls="chip info",
                        )
                        if item.produto_id and item.produto
                        else None,
                        A("editar", href=f"/kit-ambiental/itens/{item.id}/editar",
                          cls="pequeno") if pode else None,
                        Form(
                            Button("remover", cls="tirar", type="submit"),
                            method="post",
                            action=f"/kit-ambiental/itens/{item.id}/remover",
                            style="display:inline",
                        ) if pode else None,
                        cls="item-acoes",
                    ),
                    cls="item-txt",
                ),
                cls="item-kit",
            )
        )
    return Div(*cartoes, cls="itens-kit")


@rt("/kit-ambiental/{kid:int}")
def get(req, kid: int, editar: str = "", ok: str = "", erro: str = ""):
    usuario = eu(req)
    pode = _pode_kit(req)
    with db_session() as s:
        kit = servicos.obter_kit(s, kid)
        if not kit:
            return RedirectResponse(
                _msg("/kit-ambiental", "erro", "Kit não encontrado."), status_code=303
            )
        produtos = servicos.buscar_produtos(s, somente_aprovados=True, limite=None)
        opcoes_produto = [
            (str(p.id), f"{p.codigo_interno} - {p.nome_comercial}") for p in produtos
        ]

    agrupado: dict = {}
    for ponto in kit.pontos_ativos:
        agrupado.setdefault(ponto.fabrica, []).append(ponto)

    ficha = Div(
        Div(
            Div(kit.codigo, cls="selo grande"),
            Div(
                Div("Para que serve", cls="rot"),
                Div(kit.utilidade or Span("Ainda não descrito.", cls="texto-mudo"),
                    cls="val"),
                Div("Quando usar", cls="rot", style="margin-top:.8rem"),
                Div(kit.quando_usar or Span("Ainda não descrito.", cls="texto-mudo"),
                    cls="val"),
                cls="txt",
            ),
            cls="kit-topo",
        ),
        cls="card",
    )

    form_editar = (
        Div(
            Div(H2("Dados do kit"), cls="card-titulo"),
            Form(
                Div(
                    ui.campo("Código", "codigo", valor=kit.codigo, obrigatório=True,
                             ajuda="Ex.: KIT A"),
                    ui.campo("Nome", "nome", valor=kit.nome, obrigatório=True),
                    cls="linha-form",
                ),
                ui.campo("Para que serve", "utilidade", valor=kit.utilidade or "",
                         linhas=2),
                ui.campo("Quando usar", "quando_usar", valor=kit.quando_usar or "",
                         linhas=2,
                         ajuda="Em que situação este kit deve ser acionado."),
                Div(
                    Button("Salvar", cls="btn verde", type="submit"),
                    A("Cancelar", href=f"/kit-ambiental/{kit.id}", cls="btn secundario"),
                    Form(
                        Input(type="hidden", name="ativo", value="0"),
                        Button("Arquivar kit", cls="btn vermelho", type="submit"),
                        method="post",
                        action=f"/kit-ambiental/{kit.id}/situacao",
                        style="margin-left:auto",
                    ),
                    cls="barra-acoes",
                ),
                method="post",
                action=f"/kit-ambiental/{kit.id}/editar",
            ),
            cls="card",
        )
        if (pode and editar)
        else None
    )

    form_item = (
        Div(
            Div(H2("Adicionar item ao kit"), cls="card-titulo"),
            Form(
                Div(
                    ui.campo("Item", "nome", obrigatório=True,
                             placeholder="Ex.: Manta absorvente oleofílica"),
                    ui.campo("Quantidade", "quantidade", placeholder="Ex.: 2"),
                    ui.campo("Unidade", "unidade", opcoes=UNIDADES_ITEM),
                    cls="linha-form",
                ),
                ui.campo("Para que serve", "utilidade", linhas=2,
                         ajuda="Uma linha explicando a utilidade do item no kit."),
                Div(
                    ui.campo("Produto químico vinculado", "produto_id",
                             opcoes=opcoes_produto,
                             ajuda="Opcional. Se o item for um produto cadastrado, "
                                   "o kit passa a mostrar o link para a FDS dele."),
                    Label(
                        Span("Foto do item", cls="rot"),
                        Input(type="file", name="foto", accept="image/*"),
                        Span(f"JPG ou PNG, até {config.MAX_UPLOAD_MB} MB.", cls="ajuda"),
                        cls="campo",
                    ),
                    cls="linha-form",
                ),
                Div(Button("Adicionar item", cls="btn verde", type="submit"),
                    cls="barra-acoes"),
                method="post",
                action=f"/kit-ambiental/{kit.id}/itens",
                enctype="multipart/form-data",
            ),
            cls="card",
        )
        if pode
        else None
    )

    form_ponto = (
        Div(
            Div(H2("Adicionar ponto de coleta"), cls="card-titulo"),
            Form(
                Div(
                    ui.campo("Unidade", "fabrica", opcoes=UNIDADES, obrigatório=True),
                    ui.campo("Onde fica", "local", obrigatório=True,
                             placeholder="Ex.: Corredor da expedição, ao lado do extintor"),
                    cls="linha-form",
                ),
                Div(
                    ui.campo("Responsável", "responsavel",
                             placeholder="Quem procurar naquele ponto"),
                    ui.campo("Ramal", "ramal", placeholder="Ex.: 4721"),
                    cls="linha-form",
                ),
                ui.campo("Observações", "observacoes", linhas=2),
                Div(Button("Adicionar ponto", cls="btn", type="submit"),
                    cls="barra-acoes"),
                method="post",
                action=f"/kit-ambiental/{kit.id}/pontos",
            ),
            cls="card",
        )
        if pode
        else None
    )

    lista_pontos = Div(
        Div(
            H2("Onde encontrar este kit"),
            Span(f"{len(kit.pontos_ativos)} ponto(s)", cls="direita"),
            cls="card-titulo",
        ),
        _tabela_pontos(agrupado, mostrar_kit=False, pode=pode)
        if agrupado
        else ui.vazio("Nenhum ponto cadastrado para este kit.", "⌖"),
        cls="card",
    )

    return ui.pagina(
        f"{kit.codigo} - {kit.nome}",
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        ui.alerta("Este kit está arquivado e não aparece na consulta.", "aviso")
        if not kit.ativo
        else None,
        ficha,
        form_editar,
        Div(
            Div(
                H2("O que tem no kit"),
                Span(f"{len(kit.itens_ativos)} item(ns)", cls="direita"),
                cls="card-titulo",
            ),
            _grade_itens(kit, pode),
            cls="card",
        ),
        form_item,
        lista_pontos,
        form_ponto,
        usuario=usuario,
        subtitulo="Composição válida para todas as fábricas",
        acoes=[A("‹ Kits ambientais", href="/kit-ambiental", cls="btn secundario")],
    )


@rt("/kit-ambiental/itens/{iid:int}/foto")
def get(iid: int):
    """Foto do item (aberta, como o resto da consulta)."""
    with db_session() as s:
        item = s.get(ItemKit, iid)
        if not item or not item.foto:
            return Response("Sem foto", status_code=404)
        dados, tipo = item.foto, item.foto_tipo
    return Response(dados, media_type=tipo or "image/jpeg")


# ------------------------------------------------------------ Manutenção
@rt("/kit-ambiental/novo")
def get(req, erro: str = ""):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    return ui.pagina(
        "Novo tipo de kit",
        ui.alerta(erro, "erro") if erro else None,
        Div(
            Div(H2("Dados do kit"), cls="card-titulo"),
            Form(
                Div(
                    ui.campo("Código", "codigo", obrigatório=True, placeholder="Ex.: KIT A"),
                    ui.campo("Nome", "nome", obrigatório=True,
                             placeholder="Ex.: Kit de contenção para óleos"),
                    cls="linha-form",
                ),
                ui.campo("Para que serve", "utilidade", linhas=2),
                ui.campo("Quando usar", "quando_usar", linhas=2),
                Div(
                    Button("Criar kit", cls="btn verde", type="submit"),
                    A("Cancelar", href="/kit-ambiental", cls="btn secundario"),
                    cls="barra-acoes",
                ),
                method="post",
                action="/kit-ambiental/novo",
            ),
            cls="card",
        ),
        usuario=eu(req),
        subtitulo="Os itens e os pontos de coleta são cadastrados depois",
        acoes=[A("‹ Kits ambientais", href="/kit-ambiental", cls="btn secundario")],
    )


@rt("/kit-ambiental/novo")
async def post(req):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
    if not dados.get("nome") or not dados.get("codigo"):
        return RedirectResponse(
            _msg("/kit-ambiental/novo", "erro", "Informe o código e o nome do kit."),
            status_code=303,
        )
    with db_session() as s:
        kit = servicos.criar_kit(s, dados, s.get(Usuario, eu(req).id))
        kid = kit.id
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok", "Kit criado. Agora cadastre os itens."),
        status_code=303,
    )


@rt("/kit-ambiental/{kid:int}/editar")
async def post(req, kid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
    with db_session() as s:
        kit = servicos.obter_kit(s, kid)
        if not kit:
            return RedirectResponse(
                _msg("/kit-ambiental", "erro", "Kit não encontrado."), status_code=303
            )
        servicos.atualizar_kit(s, kit, dados, s.get(Usuario, eu(req).id))
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok", "Dados do kit atualizados."), status_code=303
    )


@rt("/kit-ambiental/{kid:int}/situacao")
async def post(req, kid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    form = await req.form()
    ativo = (form.get("ativo") or "0") == "1"
    with db_session() as s:
        kit = servicos.obter_kit(s, kid)
        if kit:
            servicos.arquivar_kit(s, kit, s.get(Usuario, eu(req).id), ativo)
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok",
             "Kit restaurado." if ativo else "Kit arquivado."),
        status_code=303,
    )


@rt("/kit-ambiental/{kid:int}/itens")
async def post(req, kid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
    if not dados.get("nome"):
        return RedirectResponse(
            _msg(f"/kit-ambiental/{kid}", "erro", "Informe o nome do item."),
            status_code=303,
        )
    produto_id = dados.get("produto_id")
    dados["produto_id"] = int(produto_id) if str(produto_id).isdigit() else None
    foto, erro = await _foto_do_form(form)
    if erro:
        return RedirectResponse(_msg(f"/kit-ambiental/{kid}", "erro", erro), status_code=303)
    with db_session() as s:
        kit = servicos.obter_kit(s, kid)
        if not kit:
            return RedirectResponse(
                _msg("/kit-ambiental", "erro", "Kit não encontrado."), status_code=303
            )
        servicos.adicionar_item(s, kit, dados, foto, s.get(Usuario, eu(req).id))
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok", "Item adicionado ao kit."), status_code=303
    )


@rt("/kit-ambiental/itens/{iid:int}/editar")
def get(req, iid: int, erro: str = ""):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    with db_session() as s:
        item = s.get(ItemKit, iid)
        if not item:
            return RedirectResponse(
                _msg("/kit-ambiental", "erro", "Item não encontrado."), status_code=303
            )
        kid = item.kit_id
        codigo = item.kit.codigo
        produtos = servicos.buscar_produtos(s, somente_aprovados=True, limite=None)
        opcoes_produto = [
            (str(p.id), f"{p.codigo_interno} - {p.nome_comercial}") for p in produtos
        ]
    return ui.pagina(
        f"Editar item - {item.nome}",
        ui.alerta(erro, "erro") if erro else None,
        Div(
            Div(H2(f"Item do {codigo}"), cls="card-titulo"),
            Form(
                Div(
                    ui.campo("Item", "nome", valor=item.nome, obrigatório=True),
                    ui.campo("Quantidade", "quantidade", valor=item.quantidade or ""),
                    ui.campo("Unidade", "unidade", valor=item.unidade or "",
                             opcoes=UNIDADES_ITEM),
                    cls="linha-form",
                ),
                ui.campo("Para que serve", "utilidade", valor=item.utilidade or "",
                         linhas=2),
                Div(
                    ui.campo("Produto químico vinculado", "produto_id",
                             valor=str(item.produto_id or ""), opcoes=opcoes_produto),
                    Label(
                        Span("Trocar a foto", cls="rot"),
                        Input(type="file", name="foto", accept="image/*"),
                        Span("Deixe em branco para manter a foto atual.", cls="ajuda"),
                        cls="campo",
                    ),
                    cls="linha-form",
                ),
                Label(
                    Input(type="checkbox", name="remover_foto", value="1",
                          style="width:auto;margin-right:.4rem"),
                    "Remover a foto atual",
                    cls="pequeno",
                    style="display:block;margin-bottom:1rem",
                ) if item.tem_foto else None,
                Div(
                    Button("Salvar", cls="btn verde", type="submit"),
                    A("Cancelar", href=f"/kit-ambiental/{kid}", cls="btn secundario"),
                    cls="barra-acoes",
                ),
                method="post",
                action=f"/kit-ambiental/itens/{iid}/editar",
                enctype="multipart/form-data",
            ),
            cls="card",
        ),
        usuario=eu(req),
        acoes=[A("‹ Voltar ao kit", href=f"/kit-ambiental/{kid}", cls="btn secundario")],
    )


@rt("/kit-ambiental/itens/{iid:int}/editar")
async def post(req, iid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
    produto_id = dados.get("produto_id")
    dados["produto_id"] = int(produto_id) if str(produto_id).isdigit() else None
    dados["remover_foto"] = form.get("remover_foto") == "1"
    foto, erro = await _foto_do_form(form)
    if erro:
        return RedirectResponse(
            _msg(f"/kit-ambiental/itens/{iid}/editar", "erro", erro), status_code=303
        )
    with db_session() as s:
        item = s.get(ItemKit, iid)
        if not item:
            return RedirectResponse(
                _msg("/kit-ambiental", "erro", "Item não encontrado."), status_code=303
            )
        kid = item.kit_id
        servicos.atualizar_item(s, item, dados, foto, s.get(Usuario, eu(req).id))
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok", "Item atualizado."), status_code=303
    )


@rt("/kit-ambiental/itens/{iid:int}/remover")
async def post(req, iid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    with db_session() as s:
        item = s.get(ItemKit, iid)
        if not item:
            return RedirectResponse("/kit-ambiental", status_code=303)
        kid = item.kit_id
        servicos.remover_item(s, item, s.get(Usuario, eu(req).id))
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok", "Item removido."), status_code=303
    )


@rt("/kit-ambiental/{kid:int}/pontos")
async def post(req, kid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    form = await req.form()
    dados = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
    if dados.get("fabrica") not in UNIDADES or not dados.get("local"):
        return RedirectResponse(
            _msg(f"/kit-ambiental/{kid}", "erro",
                 "Informe a fábrica e onde o kit fica."),
            status_code=303,
        )
    with db_session() as s:
        kit = servicos.obter_kit(s, kid)
        if not kit:
            return RedirectResponse(
                _msg("/kit-ambiental", "erro", "Kit não encontrado."), status_code=303
            )
        servicos.adicionar_ponto(s, kit, dados, s.get(Usuario, eu(req).id))
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok", "Ponto de coleta adicionado."),
        status_code=303,
    )


@rt("/kit-ambiental/pontos/{pid:int}/remover")
async def post(req, pid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_KIT)
    if barrado:
        return barrado
    with db_session() as s:
        ponto = s.get(PontoColetaKit, pid)
        if not ponto:
            return RedirectResponse("/kit-ambiental", status_code=303)
        kid = ponto.kit_id
        servicos.remover_ponto(s, ponto, s.get(Usuario, eu(req).id))
    return RedirectResponse(
        _msg(f"/kit-ambiental/{kid}", "ok", "Ponto removido."), status_code=303
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


# =====================================================================
# Recursos e Documentos (biblioteca digital)
# =====================================================================
#
# Consulta e download: abertos a qualquer colaborador, sem login.
# Publicar / revisar / arquivar: Saúde e Segurança, Meio Ambiente,
# Químico Responsável e Administrador (servicos.PAPEIS_BIBLIOTECA).
#


def _pode_publicar(req) -> bool:
    return servicos.pode_publicar(eu(req))


def _icone_recurso(recurso):
    """Quadradinho colorido com a extensão do arquivo (ou 'LINK')."""
    grupo = recurso.grupo_arquivo
    cor = {
        "PDF": "pdf",
        "WORD": "word",
        "EXCEL": "excel",
        "APRESENTACAO": "slide",
        "IMAGEM": "imagem",
        "VIDEO": "video",
        "LINK": "link",
    }.get(grupo, "")
    return Div(recurso.extensao, cls=f"icone {cor}".strip())


def _chips_recurso(recurso):
    chips = [Span(recurso.secao_label, cls="chip tipo")]
    if recurso.codigo:
        chips.append(Span(recurso.codigo, cls="chip versao"))
    chips.append(Span(f"v{recurso.versao_atual}", cls="chip versao"))
    if recurso.revisao_vencida:
        chips.append(Span("revisão vencida", cls="chip controlado vencida"))
    if not recurso.ativo:
        chips.append(Span("arquivado", cls="chip"))
    return Div(*chips, cls="tags")


def _cartao_recurso(recurso):
    """Linha da lista da biblioteca."""
    if recurso.e_link:
        meta = f"Link externo • atualizado em {recurso.data_referencia.strftime('%d/%m/%Y')}"
    else:
        meta = (
            f"{recurso.grupo_label} • {recurso.tamanho_legivel} • "
            f"revisão {recurso.data_referencia.strftime('%d/%m/%Y')}"
        )
        if recurso.downloads:
            meta += f" • {recurso.downloads} download(s)"
    return Div(
        _icone_recurso(recurso),
        Div(
            A(B(recurso.titulo), href=f"/recursos/{recurso.id}", cls="nome"),
            Div(meta, cls="meta"),
            Div(recurso.descricao, cls="desc") if recurso.descricao else None,
            _chips_recurso(recurso),
            cls="info",
        ),
        Div(
            A(
                "Abrir" if recurso.e_link else "Baixar",
                href=recurso.destino,
                target="_blank" if recurso.e_link else None,
                rel="noopener" if recurso.e_link else None,
                cls="btn pequeno",
            ),
            A("Detalhes", href=f"/recursos/{recurso.id}", cls="btn pequeno secundario"),
            cls="acoes-doc",
        ),
        cls="doc recurso",
    )


def _filtros_recursos(q, secao, grupo, periodo, ordem, arquivados):
    grupos = [(g, ROTULOS_GRUPO_ARQUIVO.get(g, g)) for g in ROTULOS_GRUPO_ARQUIVO]
    return Form(
        Div(
            ui.campo("Pesquisar", "q", valor=q,
                     placeholder="nome do documento, palavra-chave, código..."),
            ui.campo("Categoria", "secao", valor=secao,
                     opcoes=[(k, v) for k, v in SECOES_RECURSO.items()]),
            ui.campo("Tipo de arquivo", "grupo", valor=grupo, opcoes=grupos),
            ui.campo("Atualização", "periodo", valor=periodo,
                     opcoes=[(k, v) for k, v in servicos.PERIODOS_RECURSO.items()]),
            ui.campo("Ordenar por", "ordem", valor=ordem,
                     opcoes=[(k, v) for k, v in servicos.ORDENACOES_RECURSO.items()]),
            Div(
                Button("Pesquisar", cls="btn", type="submit"),
                A("Limpar", href="/recursos", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros",
        ),
        Input(type="hidden", name="arquivados", value="1") if arquivados else None,
        method="get",
        action="/recursos",
    )


@rt("/recursos")
def get(req, q: str = "", secao: str = "", grupo: str = "", periodo: str = "",
        ordem: str = "recentes", arquivados: str = "", tudo: str = "",
        ok: str = "", erro: str = ""):
    """Biblioteca de documentos, formulários, normas, treinamentos e links."""
    usuario = eu(req)
    publica = _pode_publicar(req)
    ver_arquivados = bool(arquivados) and publica

    with db_session() as s:
        ind = servicos.indicadores_recursos(s)
        itens = servicos.buscar_recursos(
            s, q, secao, grupo, periodo, ordem, incluir_arquivados=ver_arquivados
        )
        recentes = servicos.buscar_recursos(s, ordem="recentes")[:6]

    filtrando = bool(q or secao or grupo or periodo or ver_arquivados or tudo)

    cartoes_secao = Div(
        *[
            A(
                Div(ICONE_SECAO.get(chave, "▣"), cls="ic"),
                Div(
                    H3(rotulo),
                    P(DESCRICAO_SECAO.get(chave, "")),
                    cls="txt",
                ),
                Span(str(ind["por_secao"].get(chave, 0)), cls="qtd"),
                href=f"/recursos?secao={chave}",
                cls="secao-item",
            )
            for chave, rotulo in SECOES_RECURSO.items()
        ],
        cls="secoes",
    )

    aviso_revisao = (
        ui.alerta(
            Span(
                B(f"{len(ind['revisao_vencida'])} documento(s) com revisão vencida. "),
                "Confira se ainda são a versão válida: ",
                *[
                    A(r.titulo, href=f"/recursos/{r.id}", style="margin-right:.6rem")
                    for r in ind["revisao_vencida"][:5]
                ],
            ),
            "aviso",
        )
        if publica and ind["revisao_vencida"]
        else None
    )

    resumo = Div(
        Span(B(str(ind["total"])), " documentos publicados"),
        Span("•", cls="ponto"),
        Span(B(str(ind["arquivos"])), " arquivos para download"),
        Span("•", cls="ponto"),
        Span(B(str(ind["links"])), " links úteis"),
        cls="resumo-publico",
    )

    if filtrando:
        corpo = Div(
            Div(
                H2("Resultado da pesquisa"),
                Span(f"{len(itens)} documento(s)", cls="direita"),
                cls="card-titulo",
            ),
            Div(*[_cartao_recurso(r) for r in itens], cls="docs")
            if itens
            else ui.vazio("Nenhum documento encontrado com esses filtros.", "⌕"),
            cls="card",
        )
    else:
        corpo = Div(
            Div(
                Div(H2("Categorias"), cls="card-titulo"),
                cartoes_secao,
                resumo,
                cls="card",
            ),
            Div(
                Div(
                    H2("Atualizados recentemente"),
                    A("Ver todos os documentos", href="/recursos?tudo=1", cls="direita"),
                    cls="card-titulo",
                ),
                Div(*[_cartao_recurso(r) for r in recentes], cls="docs")
                if recentes
                else ui.vazio(
                    "A biblioteca ainda não tem documentos publicados.", "▣"
                ),
                cls="card",
            ),
        )

    acoes = []
    if publica:
        acoes.append(A("+ Publicar documento", href="/recursos/novo", cls="btn"))
        acoes.append(
            A(
                "Ver ativos" if ver_arquivados else "Ver arquivados",
                href="/recursos" if ver_arquivados else "/recursos?arquivados=1",
                cls="btn secundario",
            )
        )

    return ui.pagina(
        "Recursos e Documentos",
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        aviso_revisao,
        Div(_filtros_recursos(q, secao, grupo, periodo, ordem, ver_arquivados), cls="card"),
        corpo,
        usuario=usuario,
        subtitulo="Procedimentos, etiquetas, formulários, normas, treinamentos e links úteis",
        acoes=acoes or None,
    )


# --------------------------------------------------------- Detalhe
@rt("/recursos/{rid:int}")
def get(req, rid: int, ok: str = "", erro: str = ""):
    usuario = eu(req)
    publica = _pode_publicar(req)
    with db_session() as s:
        recurso = s.get(Recurso, rid)
        if not recurso:
            return ui.pagina(
                "Documento não encontrado",
                ui.alerta("Este documento não existe ou foi removido.", "erro"),
                usuario=usuario,
                voltar="/recursos",
            )
        atual = recurso.arquivo_atual
        anteriores = recurso.versoes_anteriores

    ficha = Div(
        ui.item_ficha("Categoria", recurso.secao_label),
        ui.item_ficha("Código do documento", recurso.codigo),
        ui.item_ficha("Versão atual", f"v{recurso.versao_atual}"),
        ui.item_ficha(
            "Última revisão",
            recurso.data_revisao.strftime("%d/%m/%Y") if recurso.data_revisao else None,
        ),
        ui.item_ficha(
            "Próxima revisão",
            Span(
                recurso.proxima_revisao.strftime("%d/%m/%Y"),
                Span(" (vencida)", cls="chip controlado vencida")
                if recurso.revisao_vencida
                else None,
            )
            if recurso.proxima_revisao
            else None,
        ),
        ui.item_ficha("Criado em", recurso.criado_em.strftime("%d/%m/%Y")),
        ui.item_ficha(
            "Responsável pela atualização",
            recurso.responsavel.nome if recurso.responsavel else None,
        ),
        ui.item_ficha("Downloads", str(recurso.downloads or 0)),
        ui.item_ficha("Descrição", recurso.descricao, largo=True),
        ui.item_ficha(
            "Palavras-chave",
            Div(
                *[
                    Span(p.strip(), cls="chip")
                    for p in (recurso.palavras_chave or "").split(",")
                    if p.strip()
                ],
                cls="tags",
            )
            if recurso.palavras_chave
            else None,
            largo=True,
        ),
        cls="ficha",
    )

    if recurso.e_link:
        bloco_arquivo = Div(
            Div(H2("Link"), cls="card-titulo"),
            P(A(recurso.url, href=recurso.url, target="_blank", rel="noopener")),
            A("Abrir link", href=recurso.url, target="_blank", rel="noopener", cls="btn"),
            cls="card",
        )
    else:
        bloco_arquivo = Div(
            Div(
                H2("Versão vigente"),
                Span(f"v{recurso.versao_atual}", cls="direita"),
                cls="card-titulo",
            ),
            Div(
                _icone_recurso(recurso),
                Div(
                    Div(atual.nome_arquivo if atual else "-", cls="nome"),
                    Div(
                        f"{recurso.grupo_label} • {recurso.tamanho_legivel} • "
                        f"enviado em {atual.enviado_em.strftime('%d/%m/%Y')}"
                        if atual
                        else "Nenhum arquivo enviado.",
                        cls="meta",
                    ),
                    cls="info",
                ),
                A("Baixar", href=f"/recursos/{recurso.id}/arquivo", cls="btn"),
                cls="doc",
            )
            if atual
            else ui.vazio("Nenhum arquivo enviado para este item.", "▣"),
            cls="card",
        )

    historico = Div(
        Div(
            H2("Histórico de versões"),
            Span(f"{len(recurso.arquivos)} versão(ões)", cls="direita"),
            cls="card-titulo",
        ),
        Div(
            Table(
                Thead(
                    Tr(Th("Versão"), Th("Arquivo"), Th("Revisão"), Th("Responsável"),
                       Th("Enviado em"), Th("Alterações"), Th(""))
                ),
                Tbody(
                    *[
                        Tr(
                            Td(f"v{a.versao}", cls="mono nowrap"),
                            Td(a.nome_arquivo, cls="pequeno"),
                            Td(
                                a.data_revisao.strftime("%d/%m/%Y") if a.data_revisao else "-",
                                cls="pequeno nowrap",
                            ),
                            Td(a.enviado_por.nome if a.enviado_por else "-", cls="pequeno"),
                            Td(a.enviado_em.strftime("%d/%m/%Y %H:%M"), cls="pequeno nowrap"),
                            Td(a.notas or "-", cls="pequeno"),
                            Td(
                                A("Baixar", href=f"/recursos/arquivo/{a.id}",
                                  cls="btn pequeno secundario")
                            ),
                        )
                        for a in recurso.arquivos
                    ]
                ),
                cls="dados",
            ),
            style="overflow-x:auto",
        )
        if recurso.arquivos
        else ui.vazio("Sem versões registradas.", "⏱"),
        cls="card",
    )

    painel_gestao = None
    if publica:
        form_versao = (
            Form(
                P(
                    "Ao enviar um arquivo novo, a versão atual passa a ser a "
                    f"v{(recurso.versao_atual or 0) + 1} e a anterior continua "
                    "disponível no histórico.",
                    cls="pequeno texto-mudo",
                ),
                Label(
                    Span("Arquivo da nova versão", Span(" *", cls="obr"), cls="rot"),
                    Input(type="file", name="arquivo", required=True),
                    cls="campo",
                ),
                ui.campo("Data da revisão", "data_revisao", "date",
                         date.today().isoformat()),
                ui.campo("O que mudou nesta versão", "notas", linhas=2,
                         placeholder="Ex.: atualização do item 7 - armazenamento"),
                Button("Publicar nova versão", cls="btn verde", type="submit"),
                method="post",
                action=f"/recursos/{recurso.id}/versao",
                enctype="multipart/form-data",
            )
            if not recurso.e_link
            else P(
                "Itens do tipo link não têm versões de arquivo. Use 'Editar' para "
                "trocar o endereço.",
                cls="pequeno texto-mudo",
            )
        )
        painel_gestao = Div(
            Div(H2("Gestão do documento"), cls="card-titulo"),
            Div(
                A("Editar dados", href=f"/recursos/{recurso.id}/editar",
                  cls="btn secundario"),
                Form(
                    Button(
                        "Restaurar" if not recurso.ativo else "Arquivar",
                        cls="btn secundario" if not recurso.ativo else "btn vermelho",
                        type="submit",
                    ),
                    Input(type="hidden", name="ativo", value="1" if not recurso.ativo else "0"),
                    method="post",
                    action=f"/recursos/{recurso.id}/situacao",
                    style="display:inline",
                ),
                cls="barra-acoes",
            ),
            Hr(style="border:0;border-top:1px solid var(--cinza-fundo);margin:1.1rem 0"),
            H3("Nova versão"),
            form_versao,
            cls="card",
        )

    return ui.pagina(
        recurso.titulo,
        ui.alerta(ok, "sucesso") if ok else None,
        ui.alerta(erro, "erro") if erro else None,
        ui.alerta("Este documento está arquivado e não aparece na busca.", "aviso")
        if not recurso.ativo
        else None,
        Div(
            Div(
                Div(Div(H2("Ficha do documento"), cls="card-titulo"), ficha, cls="card"),
                bloco_arquivo,
                historico,
            ),
            Div(
                Div(
                    Div(H2("Identificação"), cls="card-titulo"),
                    _chips_recurso(recurso),
                    P(
                        "Consulta e download liberados a todos os colaboradores.",
                        cls="pequeno texto-mudo",
                        style="margin-top:.8rem",
                    ),
                    cls="card",
                ),
                painel_gestao,
            ),
            cls="grade",
            style="grid-template-columns:minmax(0,1.7fr) minmax(280px,1fr)",
        ),
        usuario=usuario,
        subtitulo=f"{recurso.secao_label} • versão {recurso.versao_atual}",
        acoes=[A("‹ Biblioteca", href="/recursos", cls="btn secundario")],
    )


# --------------------------------------------------------- Downloads
def _entregar(conteudo, nome, tipo):
    return Response(
        conteudo,
        media_type=tipo or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@rt("/recursos/{rid:int}/arquivo")
def get(rid: int):
    """Baixa a versão vigente. Aberto a qualquer colaborador."""
    with db_session() as s:
        recurso = s.get(Recurso, rid)
        if not recurso:
            return Response("Documento não encontrado", status_code=404)
        if recurso.e_link and recurso.url:
            return RedirectResponse(recurso.url, status_code=303)
        atual = recurso.arquivo_atual
        if not atual:
            return Response("Este documento não tem arquivo anexado.", status_code=404)
        servicos.registrar_download(s, recurso)
        dados = (atual.conteudo, atual.nome_arquivo, atual.content_type)
    return _entregar(*dados)


@rt("/recursos/arquivo/{aid:int}")
def get(aid: int):
    """Baixa uma versão específica do histórico."""
    with db_session() as s:
        arquivo = s.get(RecursoArquivo, aid)
        if not arquivo:
            return Response("Versão não encontrada", status_code=404)
        dados = (arquivo.conteudo, arquivo.nome_arquivo, arquivo.content_type)
    return _entregar(*dados)


# --------------------------------------------------------- Publicação
def _form_recurso(recurso=None, erro: str = ""):
    """Formulário usado tanto para publicar quanto para editar."""
    novo = recurso is None
    valor = (lambda campo, padrao="": getattr(recurso, campo, padrao) or padrao) \
        if recurso else (lambda campo, padrao="": padrao)
    acao = "/recursos/novo" if novo else f"/recursos/{recurso.id}/editar"
    return Form(
        Fieldset(
            Legend("Identificação"),
            Div(
                ui.campo("Categoria", "secao", valor=valor("secao", "PROCEDIMENTOS"),
                         obrigatório=True,
                         opcoes=[(k, v) for k, v in SECOES_RECURSO.items()]),
                ui.campo("Tipo", "tipo_midia", valor=valor("tipo_midia", "ARQUIVO"),
                         obrigatório=True,
                         opcoes=[(k, v) for k, v in TIPOS_MIDIA.items()],
                         ajuda="Arquivo para download ou atalho para um sistema/site."),
                cls="linha-form",
            ),
            Div(
                ui.campo("Título", "titulo", valor=valor("titulo"), obrigatório=True,
                         placeholder="Ex.: Etiqueta GHS - recipiente de 5 L"),
                ui.campo("Código do documento", "codigo", valor=valor("codigo"),
                         placeholder="Ex.: PR-HSE-012", ajuda="Opcional."),
                cls="linha-form",
            ),
            ui.campo("Descrição", "descricao", valor=valor("descricao"), linhas=2,
                     ajuda="Explique em uma ou duas linhas para que serve o documento."),
            ui.campo("Palavras-chave", "palavras_chave", valor=valor("palavras_chave"),
                     placeholder="etiqueta, GHS, rotulagem, armazenamento",
                     ajuda="Separadas por vírgula. Usadas na pesquisa."),
            cls="secao",
        ),
        Fieldset(
            Legend("Conteúdo"),
            ui.campo("Endereço (URL)", "url", valor=valor("url"),
                     placeholder="https://...",
                     ajuda="Preencha apenas quando o tipo for 'Link externo'."),
            Label(
                Span("Arquivo", cls="rot"),
                Input(type="file", name="arquivo"),
                Span(
                    "Obrigatório para documentos. "
                    + ("Deixe em branco para manter o arquivo atual."
                       if not novo else f"Até {config.MAX_UPLOAD_MB} MB."),
                    cls="ajuda",
                ),
                cls="campo",
            )
            if novo
            else None,
            cls="secao",
        ),
        Fieldset(
            Legend("Controle de versão"),
            Div(
                ui.campo("Data da revisão", "data_revisao", "date",
                         (recurso.data_revisao.isoformat()
                          if recurso and recurso.data_revisao else date.today().isoformat())),
                ui.campo("Próxima revisão prevista", "proxima_revisao", "date",
                         (recurso.proxima_revisao.isoformat()
                          if recurso and recurso.proxima_revisao else ""),
                         ajuda="Opcional. O sistema avisa quando a data passar."),
                cls="linha-form",
            ),
            cls="secao",
        ),
        Div(
            Button("Publicar" if novo else "Salvar alterações", cls="btn verde",
                   type="submit"),
            A("Cancelar", href="/recursos" if novo else f"/recursos/{recurso.id}",
              cls="btn secundario"),
            cls="barra-acoes",
        ),
        method="post",
        action=acao,
        enctype="multipart/form-data",
    )


@rt("/recursos/novo")
def get(req, erro: str = ""):
    barrado = exigir_papel(req, *servicos.PAPEIS_BIBLIOTECA)
    if barrado:
        return barrado
    return ui.pagina(
        "Publicar documento",
        ui.alerta(erro, "erro") if erro else None,
        Div(
            Div(H2("Novo item da biblioteca"), cls="card-titulo"),
            _form_recurso(),
            cls="card",
        ),
        usuario=eu(req),
        subtitulo="O documento fica disponível para consulta de todos os colaboradores",
        acoes=[A("‹ Biblioteca", href="/recursos", cls="btn secundario")],
    )


async def _arquivo_do_form(form) -> tuple[dict | None, str | None]:
    enviado = form.get("arquivo")
    if enviado is None or not getattr(enviado, "filename", ""):
        return None, None
    conteudo = await enviado.read()
    if not conteudo:
        return None, None
    if len(conteudo) > config.MAX_UPLOAD_BYTES:
        return None, f"O arquivo excede o limite de {config.MAX_UPLOAD_MB} MB."
    return {
        "nome": enviado.filename,
        "content_type": getattr(enviado, "content_type", None),
        "conteudo": conteudo,
    }, None


def _dados_do_form(form) -> dict:
    return {
        "secao": (form.get("secao") or "").strip(),
        "titulo": (form.get("titulo") or "").strip(),
        "codigo": (form.get("codigo") or "").strip(),
        "descricao": (form.get("descricao") or "").strip(),
        "palavras_chave": (form.get("palavras_chave") or "").strip(),
        "tipo_midia": (form.get("tipo_midia") or "ARQUIVO").strip(),
        "url": (form.get("url") or "").strip(),
        "data_revisao": _data(form.get("data_revisao")),
        "proxima_revisao": _data(form.get("proxima_revisao")),
        "notas": (form.get("notas") or "").strip(),
    }


@rt("/recursos/novo")
async def post(req):
    barrado = exigir_papel(req, *servicos.PAPEIS_BIBLIOTECA)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    dados = _dados_do_form(form)

    if not dados["titulo"] or dados["secao"] not in SECOES_RECURSO:
        return RedirectResponse(
            _msg("/recursos/novo", "erro", "Informe o título e a categoria."),
            status_code=303,
        )

    arquivo, erro = await _arquivo_do_form(form)
    if erro:
        return RedirectResponse(_msg("/recursos/novo", "erro", erro), status_code=303)

    if dados["tipo_midia"] == "LINK":
        if not dados["url"]:
            return RedirectResponse(
                _msg("/recursos/novo", "erro",
                     "Informe o endereço (URL) do link externo."),
                status_code=303,
            )
        arquivo = None
    elif arquivo is None:
        return RedirectResponse(
            _msg("/recursos/novo", "erro",
                 "Selecione o arquivo do documento (ou mude o tipo para 'Link externo')."),
            status_code=303,
        )

    with db_session() as s:
        recurso = servicos.criar_recurso(s, dados, s.get(Usuario, usuario.id), arquivo)
        rid = recurso.id
    return RedirectResponse(
        _msg(f"/recursos/{rid}", "ok", "Documento publicado na biblioteca."),
        status_code=303,
    )


@rt("/recursos/{rid:int}/editar")
def get(req, rid: int, erro: str = ""):
    barrado = exigir_papel(req, *servicos.PAPEIS_BIBLIOTECA)
    if barrado:
        return barrado
    with db_session() as s:
        recurso = s.get(Recurso, rid)
    if not recurso:
        return RedirectResponse(
            _msg("/recursos", "erro", "Documento não encontrado."), status_code=303
        )
    return ui.pagina(
        f"Editar: {recurso.titulo}",
        ui.alerta(erro, "erro") if erro else None,
        ui.alerta(
            "Alterar os dados aqui não cria versão nova. Para substituir o arquivo, "
            "use 'Publicar nova versão' na página do documento.",
            "info",
        ),
        Div(
            Div(H2("Dados do documento"), cls="card-titulo"),
            _form_recurso(recurso),
            cls="card",
        ),
        usuario=eu(req),
        subtitulo=recurso.secao_label,
        acoes=[A("‹ Voltar ao documento", href=f"/recursos/{rid}", cls="btn secundario")],
    )


@rt("/recursos/{rid:int}/editar")
async def post(req, rid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_BIBLIOTECA)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    dados = _dados_do_form(form)
    if not dados["titulo"]:
        return RedirectResponse(
            _msg(f"/recursos/{rid}/editar", "erro", "O título é obrigatório."),
            status_code=303,
        )
    with db_session() as s:
        recurso = s.get(Recurso, rid)
        if not recurso:
            return RedirectResponse(
                _msg("/recursos", "erro", "Documento não encontrado."), status_code=303
            )
        servicos.atualizar_recurso(s, recurso, dados, s.get(Usuario, usuario.id))
    return RedirectResponse(
        _msg(f"/recursos/{rid}", "ok", "Dados atualizados."), status_code=303
    )


@rt("/recursos/{rid:int}/versao")
async def post(req, rid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_BIBLIOTECA)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    arquivo, erro = await _arquivo_do_form(form)
    if erro or arquivo is None:
        return RedirectResponse(
            _msg(f"/recursos/{rid}", "erro", erro or "Selecione o arquivo da nova versão."),
            status_code=303,
        )
    with db_session() as s:
        recurso = s.get(Recurso, rid)
        if not recurso:
            return RedirectResponse(
                _msg("/recursos", "erro", "Documento não encontrado."), status_code=303
            )
        servicos.publicar_versao(
            s,
            recurso,
            arquivo,
            s.get(Usuario, usuario.id),
            data_revisao=_data(form.get("data_revisao")) or date.today(),
            notas=(form.get("notas") or "").strip() or None,
        )
        nova = recurso.versao_atual
    return RedirectResponse(
        _msg(f"/recursos/{rid}", "ok", f"Versão v{nova} publicada."), status_code=303
    )


@rt("/recursos/{rid:int}/situacao")
async def post(req, rid: int):
    barrado = exigir_papel(req, *servicos.PAPEIS_BIBLIOTECA)
    if barrado:
        return barrado
    usuario = eu(req)
    form = await req.form()
    ativo = (form.get("ativo") or "0") == "1"
    with db_session() as s:
        recurso = s.get(Recurso, rid)
        if not recurso:
            return RedirectResponse(
                _msg("/recursos", "erro", "Documento não encontrado."), status_code=303
            )
        servicos.arquivar_recurso(s, recurso, s.get(Usuario, usuario.id), ativo)
    return RedirectResponse(
        _msg(f"/recursos/{rid}", "ok",
             "Documento restaurado." if ativo else "Documento arquivado."),
        status_code=303,
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
def get(req, sess, pid: int, ok: str = "", erro: str = ""):
    usuario = eu(req)
    publico = usuario is None
    # Quem enviou a solicitação sem login acompanha a própria ficha enquanto
    # durar a sessão do navegador, mesmo antes da aprovação.
    minha = publico and _e_minha(sess, pid)
    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return ui.pagina(
                "Produto não encontrado",
                ui.alerta("Registro inexistente.", "erro"),
                usuario=usuario,
            )
        if publico and not minha and not produto.disponivel_publico:
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
        areas_permitidas = (
            [] if publico else servicos.areas_para_decidir(s, u_atual, produto)
        )
        pode = bool(areas_permitidas)
        # Renovação: o responsável pelo produto manda de volta para a aprovação
        # quando faltam 6 meses ou menos para vencer (ou já venceu).
        pode_renovar = (
            not publico and produto.pode_renovar
            and servicos.pode_renovar(u_atual, produto)
        )
        # Técnicos que podem assumir a Segurança (só o admin usa esta lista).
        tecnicos_troca = (
            servicos.aprovadores_da_area(s, "SEGURANCA")
            if (not publico and usuario is not None and usuario.papel == "ADMIN")
            else []
        )
        # Na ordem da lista oficial, não na ordem em que foram marcados.
        epis_marcados = set(produto.epis_nomes)
        epis_obrigatorios = [e for e in EPIS if e in epis_marcados]
        # Já existe controle registrado? O Químico edita em vez de recomeçar.
        controle_atual = {}
        for c in produto.controles:
            controle_atual = {
                "orgao": c.orgao,
                "numero_licenca": c.numero_licenca or "",
                "validade_licenca": (
                    c.validade_licenca.isoformat() if c.validade_licenca else ""
                ),
            }
            break
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
        ui.item_ficha("Categoria", produto.categoria),
        ui.item_ficha("Tipo de produto", produto.tipo_produto),
        ui.item_ficha(
            "Números CAS",
            Div(*[Span(c, cls="chip") for c in produto.cas_numeros], cls="chips")
            if produto.cas_numeros else None,
        ),
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
        ui.item_ficha("Unidade solicitante", produto.unidade_da_solicitacao),
        ui.item_ficha("Área solicitante", produto.area_solicitante
                      or produto.setor_solicitante),
        ui.item_ficha("Técnico de Segurança responsável",
                      produto.tecnico_seguranca.nome
                      if produto.tecnico_seguranca else None),
        ui.item_ficha("Forma de aplicação", produto.forma_aplicacao),
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
        ui.item_ficha("Inflamável", produto.inflamavel_label),
        ui.item_ficha("Cancerígeno", produto.cancerigeno_label),
        ui.item_ficha("Ponto de fulgor", produto.ponto_fulgor),
        ui.item_ficha("Funcionários expostos", produto.expostos_label),
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
        ui.item_ficha("Necessidade de uso", produto.necessidade_uso, largo=True),
        ui.item_ficha("Função dos colaboradores expostos", produto.funcoes_expostas,
                      largo=True),
        ui.item_ficha("Solicitante terceiro", produto.terceiro_label, largo=True),
        ui.item_ficha(
            "Gestor Tenaris do contrato",
            f"{produto.gestor_contrato} ({produto.gestor_email})"
            if produto.gestor_contrato and produto.gestor_email
            else produto.gestor_contrato,
            largo=True,
        ),
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

    # EPI definido pela Segurança: destaque, porque é o que quem vai manusear
    # o produto precisa ver primeiro.
    cartao_epi = (
        Div(
            Div(
                H2("EPI obrigatório"),
                Span(f"{len(epis_obrigatorios)} item(ns)", cls="direita"),
                cls="card-titulo",
            ),
            P("Definido pela área de Segurança na análise desta FDS.",
              cls="pequeno texto-mudo"),
            Div(*[Span(e, cls="chip epi") for e in epis_obrigatorios], cls="lista-epi"),
            cls="card destaque-epi",
        )
        if epis_obrigatorios
        else None
    )

    rotulos_areas = dict(FLUXO_APROVACAO)
    form_decisao = (
        Form(
            # Quem responde por mais de uma área escolhe por qual está opinando.
            ui.campo(
                "Registrar parecer como", "area", valor=areas_permitidas[0],
                obrigatório=True,
                opcoes=[(a, rotulos_areas.get(a, a)) for a in areas_permitidas],
            )
            if len(areas_permitidas) > 1
            else Input(type="hidden", name="area",
                       value=areas_permitidas[0] if areas_permitidas else ""),
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
            # A área de Segurança define o EPI obrigatório a partir da FDS.
            Div(
                Span("EPI obrigatório para este produto", cls="rot"),
                P(
                    "Marque o que a FDS exige. O que você marcar aqui aparece na "
                    "ficha do produto e no aviso de aprovação.",
                    cls="pequeno texto-mudo",
                ),
                Div(
                    *[
                        Label(
                            Input(type="checkbox", name="epis", value=e,
                                  checked=(e in epis_marcados)),
                            Span(e),
                            cls="caixa-marcar",
                        )
                        for e in EPIS
                    ],
                    cls="grupo-marcar",
                ),
                cls="campo",
            ) if "SEGURANCA" in areas_permitidas else None,
            # A área de Saúde avalia a exposição ocupacional: quantas pessoas
            # têm contato direto e em que função. Saiu do cadastro porque o
            # solicitante não sabe responder.
            Div(
                Span("Exposição ocupacional", cls="rot"),
                P(
                    "Avaliação da área de Saúde. Aparece na ficha do produto "
                    "depois de aprovado.",
                    cls="pequeno texto-mudo",
                ),
                Div(
                    ui.campo(
                        "Funcionários expostos", "funcionarios_expostos", "number",
                        valor=("" if produto.funcionarios_expostos is None
                               else str(produto.funcionarios_expostos)),
                        ajuda="Quantas pessoas têm contato direto com o produto.",
                    ),
                    ui.campo(
                        "Função dos colaboradores expostos", "funcoes_expostas",
                        valor=produto.funcoes_expostas or "",
                        placeholder="Ex.: operador de pintura, mecânico de manutenção",
                    ),
                    cls="linha-form",
                ),
                cls="campo",
            ) if "SAUDE" in areas_permitidas else None,
            # O Químico Responsável é quem sabe se o produto é controlado e
            # qual a licença - o solicitante não tem essa informação.
            Div(
                Span("Controle regulatório", cls="rot"),
                P(
                    "Produto sujeito a controle da Polícia Federal, Polícia Civil "
                    "ou Exército? Informe o órgão e a licença.",
                    cls="pequeno texto-mudo",
                ),
                Div(
                    ui.campo("Produto controlado", "orgao_controlador",
                             opcoes=[("NAO", "Não controlado")]
                             + [(k, v) for k, v in ORGAOS_CONTROLADORES.items()],
                             valor=controle_atual.get("orgao", "NAO")),
                    ui.campo("Número da licença", "numero_licenca",
                             valor=controle_atual.get("numero_licenca", "")),
                    ui.campo("Validade da licença", "validade_licenca", tipo="date",
                             valor=controle_atual.get("validade_licenca", "")),
                    cls="linha-form",
                ),
                cls="campo",
            ) if "QUIMICO_RESPONSAVEL" in areas_permitidas else None,
            Div(
                Button("Aprovar", cls="btn verde", type="submit", name="decisao",
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
                Td(
                    produto.fds_vencimento.strftime("%d/%m/%Y")
                    if d.id == fds.id and produto.fds_vencimento
                    else Span("-", cls="texto-mudo"),
                    cls="nowrap",
                ),
                Td(A(d.nome_arquivo, href=f"/documentos/{d.id}"), cls="pequeno"),
                Td(
                    Span("vigente", cls="badge aprovado")
                    if d.id == fds.id
                    else Span("anterior", cls="badge neutro")
                ),
            )
            for d in produto.fds_versoes
        ]
        venc_fds = produto.fds_vencimento
        if produto.data_aprovacao and venc_fds:
            resumo_validade = (
                f"Aprovada em {produto.data_aprovacao.strftime('%d/%m/%Y')}. "
                f"Validade de {FDS_VALIDADE_ANOS} anos: "
                + (
                    f"venceu em {venc_fds.strftime('%d/%m/%Y')}."
                    if situacao == "VENCIDA"
                    else f"vence em {venc_fds.strftime('%d/%m/%Y')}."
                )
            )
        else:
            resumo_validade = (
                f"A validade de {FDS_VALIDADE_ANOS} anos começa a contar quando "
                "o produto for aprovado."
            )
        bloco_renovacao = None
        if produto.em_renovacao:
            bloco_renovacao = ui.alerta(
                "Renovação em andamento: as áreas estão analisando de novo. O "
                "produto continua consultável com a aprovação atual até a "
                "nova aprovação sair.",
                "info",
            )
        elif pode_renovar:
            bloco_renovacao = Form(
                P(
                    "Esta aprovação está perto de vencer. Para renovar, o "
                    "produto passa pela aprovação de novo; não é preciso "
                    "cadastrar nada outra vez.",
                    cls="pequeno",
                ),
                Button("Renovar aprovação", cls="btn verde", type="submit"),
                method="post",
                action=f"/produtos/{produto.id}/renovar",
            )
        cartao_fds = Div(
            Div(
                H2("Ficha de Dados de Segurança"),
                Span(_pontos_semaforo(situacao), cls="direita"),
                cls="card-titulo",
            ),
            P(resumo_validade, cls="pequeno texto-mudo"),
            bloco_renovacao,
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

    # Só o administrador troca o técnico de Segurança de uma solicitação (por
    # ausência ou férias), e só enquanto a Segurança ainda não deu parecer.
    cartao_troca_tecnico = None
    if (
        not publico
        and usuario is not None
        and usuario.papel == "ADMIN"
        and produto.aberta
        and "SEGURANCA" in produto.areas_pendentes
        and tecnicos_troca
    ):
        atual = produto.tecnico_seguranca
        cartao_troca_tecnico = Div(
            Div(H2("Técnico de Segurança"), cls="card-titulo"),
            P(
                "Em caso de ausência, passe a análise de Segurança para outro "
                "técnico. A troca fica registrada no histórico.",
                cls="texto-mudo pequeno",
            ),
            Form(
                ui.campo(
                    "Responsável", "tecnico_id",
                    valor=str(atual.id) if atual else "",
                    opcoes=[(str(u.id), u.nome) for u in tecnicos_troca],
                    obrigatório=True,
                ),
                Div(Button("Trocar técnico", cls="btn", type="submit"), cls="barra-acoes"),
                method="post",
                action=f"/produtos/{produto.id}/tecnico-seguranca",
            ),
            cls="card",
        )

    coluna_esq = Div(
        Div(Div(H2("Ficha do produto"), Span(ui.badge(produto.status), cls="direita"),
                cls="card-titulo"), ficha, cls="card"),
        cartao_fds,
        cartao_controle,
        documentos,
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
        cartao_epi,
        cartao_troca_tecnico,
        # O cartão só aparece para quem tem alguma área pendente nesta
        # solicitação. Encerrada, ou de área que não é a sua, nem é exibido.
        Div(
            Div(H2("Registrar parecer"), cls="card-titulo"),
            form_decisao,
            cls="card",
        )
        if form_decisao is not None and not publico
        else None,
        # Aviso só para o administrador: sem isso ele procura um botão de
        # aprovar que, de propósito, não existe mais para o cargo dele.
        Div(
            P(
                "Você administra o sistema, mas o parecer de cada área é "
                "exclusivo de quem responde por ela. Para opinar, é preciso "
                "estar cadastrado como aprovador da área em Aprovações.",
                cls="texto-mudo pequeno",
            ),
            cls="card",
        )
        if (
            not publico
            and form_decisao is None
            and produto.aberta
            and usuario is not None
            and usuario.papel == "ADMIN"
        )
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
            "categoria": produto.categoria or "",
            "tipo_produto": produto.tipo_produto or "",
            "numero_cas": "\n".join(produto.cas_numeros),
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
            "necessidade_uso": produto.necessidade_uso or "",
            "forma_aplicacao": produto.forma_aplicacao or "",
            "funcionarios_expostos": (
                "" if produto.funcionarios_expostos is None
                else str(produto.funcionarios_expostos)
            ),
            "funcoes_expostas": produto.funcoes_expostas or "",
            "terceiro_nome": produto.terceiro_nome or "",
            "terceiro_empresa": produto.terceiro_empresa or "",
            "gestor_contrato": produto.gestor_contrato or "",
            "gestor_email": produto.gestor_email or "",
            "inflamavel": produto.inflamavel or "",
            "cancerigeno": produto.cancerigeno or "",
            "ponto_fulgor": produto.ponto_fulgor or "",
        }
        riscos_marcados = set(produto.riscos_nomes)
        codigo, nome = produto.codigo_interno, produto.nome_comercial

    formulario = Form(
        Fieldset(
            Legend("Identificação"),
            Div(
                ui.campo("Nome técnico", "nome_tecnico", valor=dados["nome_tecnico"]),
                ui.campo("Números CAS", "numero_cas", valor=dados["numero_cas"],
                         linhas=3, ajuda="Um número por linha."),
                cls="linha-form",
            ),
            Div(
                ui.campo("Categoria", "categoria", valor=dados["categoria"], opcoes=CATEGORIAS),
                ui.campo("Tipo de produto", "tipo_produto", valor=dados["tipo_produto"],
                         opcoes=TIPOS_PRODUTO),
                ui.campo("Estado físico", "estado_fisico", valor=dados["estado_fisico"],
                         opcoes=ESTADOS_FISICOS),
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
            ui.campo("Necessidade de uso", "necessidade_uso",
                     valor=dados["necessidade_uso"], linhas=3,
                     ajuda="Por que o produto é necessário e o que ele resolve."),
            Div(
                ui.campo("Forma de aplicação", "forma_aplicacao",
                         valor=dados["forma_aplicacao"], opcoes=FORMAS_APLICACAO,
                         ajuda="Como o produto é aplicado no processo."),
                ui.campo("Área solicitante", "area_solicitante",
                         valor=dados["area_solicitante"], grupos=AREAS_POR_UNIDADE,
                         ajuda="A área precisa ser de uma das unidades autorizadas."),
                ui.campo("Prazo de utilização", "prazo_utilizacao",
                         valor=dados["prazo_utilizacao"], opcoes=PRAZOS_UTILIZACAO),
                ui.campo("Quantidade prevista", "consumo_estimado",
                         valor=dados["consumo_estimado"]),
                ui.campo("Unidade de medida", "unidade", valor=dados["unidade"],
                         opcoes=UNIDADES_CONSUMO),
                cls="linha-form",
            ),
            Div(
                ui.campo("Funcionários expostos", "funcionarios_expostos", tipo="number",
                         valor=dados["funcionarios_expostos"],
                         ajuda="Quantidade de pessoas com contato direto."),
                ui.campo("Função dos colaboradores expostos", "funcoes_expostas",
                         valor=dados["funcoes_expostas"],
                         placeholder="Ex.: operador de laminação, analista de laboratório"),
                cls="linha-form",
            ),
            Div(
                ui.campo("Nome do solicitante terceiro", "terceiro_nome",
                         valor=dados["terceiro_nome"],
                         ajuda="Só quando a solicitação vem de empresa terceira."),
                ui.campo("Empresa do terceiro", "terceiro_empresa",
                         valor=dados["terceiro_empresa"]),
                cls="linha-form",
            ),
            Div(
                ui.campo("Gestor Tenaris do contrato", "gestor_contrato",
                         valor=dados["gestor_contrato"]),
                ui.campo("E-mail do gestor", "gestor_email", tipo="email",
                         valor=dados["gestor_email"]),
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
                        for n in UNIDADES
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
                ui.campo("Inflamável", "inflamavel", valor=dados["inflamavel"],
                         opcoes=[(k, v) for k, v in SIM_NAO.items()]),
                ui.campo("Cancerígeno", "cancerigeno", valor=dados["cancerigeno"],
                         opcoes=[(k, v) for k, v in SIM_NAO.items()]),
                ui.campo("Ponto de fulgor", "ponto_fulgor", valor=dados["ponto_fulgor"],
                         placeholder="Ex.: 42 °C", ajuda="Seção 9 da FDS."),
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
    dados["fabricas"] = [f for f in form.getlist("fabricas") if f in UNIDADES]
    dados["controles"] = _ler_controles(form)
    dados["riscos"] = [r for r in form.getlist("riscos") if r in CLASSES_RISCO]

    if "numero_cas" in form:
        cas = _ler_cas(dados.get("numero_cas"))
        invalidos = [c for c in cas if not _CAS_FORMATO.fullmatch(c)]
        if invalidos:
            return RedirectResponse(
                _msg(f"/produtos/{pid}/editar", "erro",
                     "Número CAS fora do formato: " + ", ".join(invalidos[:3])
                     + ". O formato é 67-64-1."),
                status_code=303,
            )
        dados["cas"] = cas

    expostos = (dados.get("funcionarios_expostos") or "").strip()
    if expostos:
        if not expostos.isdigit():
            return RedirectResponse(
                _msg(f"/produtos/{pid}/editar", "erro",
                     "Funcionários expostos deve ser um número (ex.: 4)."),
                status_code=303,
            )
        dados["funcionarios_expostos"] = int(expostos)
    else:
        dados["funcionarios_expostos"] = None

    if dados.get("inflamavel") == "SIM" and not (dados.get("ponto_fulgor") or "").strip():
        return RedirectResponse(
            _msg(f"/produtos/{pid}/editar", "erro",
                 "Produto inflamável: informe o ponto de fulgor (seção 9 da FDS)."),
            status_code=303,
        )

    # A área precisa pertencer a alguma das unidades autorizadas do produto.
    # Na edição o produto pode estar liberado em mais de uma unidade, então
    # basta a área ser de uma delas.
    area = (dados.get("area_solicitante") or "").strip()
    if area and dados["fabricas"] and not any(
        par_valido(u, area) for u in dados["fabricas"]
    ):
        return RedirectResponse(
            _msg(f"/produtos/{pid}/editar", "erro",
                 f'A área "{area}" não pertence a nenhuma das unidades '
                 "autorizadas deste produto."),
            status_code=303,
        )

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
    area = (form.get("area") or "").strip() or None
    epis = [e for e in form.getlist("epis") if e in EPIS]
    # Exposição ocupacional: só a área de Saúde preenche.
    expostos = None
    if "funcionarios_expostos" in form or "funcoes_expostas" in form:
        quantos = (form.get("funcionarios_expostos") or "").strip()
        if quantos and not quantos.isdigit():
            return RedirectResponse(
                _msg(f"/produtos/{pid}", "erro",
                     "Funcionários expostos deve ser um número (ex.: 4)."),
                status_code=303,
            )
        expostos = {
            "funcionarios_expostos": int(quantos) if quantos else None,
            "funcoes_expostas": form.get("funcoes_expostas") or "",
        }
    # Controle regulatório: só o Químico Responsável preenche.
    orgao = (form.get("orgao_controlador") or "NAO").strip()
    numero_licenca = (form.get("numero_licenca") or "").strip()
    validade_licenca = _data(form.get("validade_licenca"))
    if orgao in ORGAOS_CONTROLADORES and not numero_licenca:
        return RedirectResponse(
            _msg(f"/produtos/{pid}", "erro",
                 "Produto controlado exige o número da licença do órgão escolhido."),
            status_code=303,
        )
    with db_session() as s:
        produto = s.get(Produto, pid)
        u = s.get(Usuario, usuario.id)
        permitidas = servicos.areas_para_decidir(s, u, produto) if produto else []
        if not permitidas:
            return RedirectResponse(
                _msg(f"/produtos/{pid}", "erro",
                     "Você não responde por nenhuma área pendente desta solicitação."),
                status_code=303,
            )
        # Área vazia (formulário antigo, ou quem responde por uma só) assume
        # a única área possível. Já uma área PREENCHIDA que não é dele é
        # recusada, nunca trocada em silêncio pela dele: o parecer tem de
        # ficar registrado na área que a pessoa de fato assinou.
        if area is None:
            if len(permitidas) == 1:
                area = permitidas[0]
            else:
                return RedirectResponse(
                    _msg(f"/produtos/{pid}", "erro",
                         "Escolha por qual área está opinando."),
                    status_code=303,
                )
        elif area not in permitidas:
            return RedirectResponse(
                _msg(f"/produtos/{pid}", "erro",
                     "Você não responde pela área escolhida nesta solicitação."),
                status_code=303,
            )
        if area == "QUIMICO_RESPONSAVEL" and "orgao_controlador" in form:
            servicos.aplicar_controles(
                s, produto,
                [{
                    "orgao": orgao,
                    "numero_licenca": numero_licenca or None,
                    "validade_licenca": validade_licenca,
                }] if orgao in ORGAOS_CONTROLADORES else [],
            )
        servicos.registrar_decisao(
            s, produto, u, decisao, parecer, area=area,
            epis=epis if area == "SEGURANCA" else None,
            expostos=expostos if area == "SAUDE" else None,
        )
        rotulo = dict(FLUXO_APROVACAO).get(area, area)
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok", f"Parecer de {rotulo} registrado."),
        status_code=303,
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


@rt("/produtos/{pid}/renovar")
async def post(req, pid: int):
    """Manda o produto de volta para a aprovação (validade perto de vencer)."""
    barrado = exigir_login(req)
    if barrado:
        return barrado
    usuario = eu(req)
    with db_session() as s:
        produto = s.get(Produto, pid)
        if not produto:
            return RedirectResponse("/produtos", status_code=303)
        try:
            servicos.renovar_aprovacao(s, produto, s.get(Usuario, usuario.id))
        except ValueError as exc:
            return RedirectResponse(_msg(f"/produtos/{pid}", "erro", str(exc)), status_code=303)
    return RedirectResponse(
        _msg(f"/produtos/{pid}", "ok",
             "Renovação iniciada: as áreas foram avisadas e vão analisar de novo."),
        status_code=303,
    )


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
    # Só o PDF da FDS vigente aparece aqui; a Ficha de Emergência fica na
    # "Ver ficha completa".
    docs = [fds] if fds else []

    if fds:
        # A validade conta da aprovação no sistema (3 anos).
        data_validade = produto.fds_vencimento
        venc = data_validade.strftime("%d/%m/%Y") if data_validade else "-"
        dias = produto.fds_dias_restantes
        if dias is None:
            prazo = "validade começa na aprovação"
        elif situacao == "VENCIDA":
            prazo = f"venceu em {venc} ({abs(dias)} dias atrás)"
        elif situacao == "PROXIMA":
            prazo = f"vence em {venc} (faltam {dias} dias)"
        else:
            prazo = f"válida até {venc}"
        revisao = (
            f"aprovada em {produto.data_aprovacao.strftime('%d/%m/%Y')}"
            if produto.data_aprovacao
            else "aguardando aprovação"
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
            _pontos_semaforo(situacao, SITUACOES_FDS_TELA.get(situacao)),
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


def _filtros_fds(q, fabrica, area, tipo_produto, orgao, situacao, solicitante="",
                 solicitantes=()):
    return Form(
        Div(
            ui.campo(
                "Buscar", "q", valor=q,
                placeholder="produto, nome técnico, fabricante, código ou CAS",
            ),
            ui.campo("Unidade", "fabrica", valor=fabrica, opcoes=UNIDADES),
            ui.campo("Área", "area", valor=area, grupos=AREAS_POR_UNIDADE),
            ui.campo(
                "Solicitante", "solicitante", valor=solicitante,
                opcoes=list(solicitantes),
            ),
            ui.campo("Tipo de produto", "tipo_produto", valor=tipo_produto, opcoes=TIPOS_PRODUTO),
            ui.campo(
                "Produto controlado", "orgao", valor=orgao,
                opcoes=[("QUALQUER", "Qualquer órgão")]
                + [(k, v) for k, v in ORGAOS_CONTROLADORES.items()],
            ),
            ui.campo(
                "Situação da FDS", "situacao", valor=situacao,
                opcoes=[(k, v) for k, v in SITUACOES_FDS_FILTRO.items()],
            ),
            Div(
                Button("Filtrar", cls="btn", type="submit"),
                A("Limpar", href="/fds", cls="btn secundario"),
                cls="acao",
            ),
            cls="filtros filtros-linha",
        ),
        method="get",
        action="/fds",
    )


FDS_POR_PAGINA = 10


@rt("/fds")
def get(req, q: str = "", fabrica: str = "", area: str = "", tipo_produto: str = "",
        orgao: str = "", situacao: str = "", pagina: int = 1, solicitante: str = ""):
    """Repositório único de consulta das Fichas de Dados de Segurança."""
    usuario = eu(req)
    with db_session() as s:
        solicitantes = servicos.solicitantes_com_fds(s)
        produtos = servicos.buscar_produtos(
            s, q, somente_aprovados=True, fabrica=fabrica, area=area,
            tipo_produto=tipo_produto, orgao=orgao,
            solicitante_id=int(solicitante) if solicitante.isdigit() else None,
            limite=None,
        )
        produtos = servicos.filtrar_por_situacao_fds(produtos, situacao)
        # O que exige acao aparece primeiro: vencidas, depois a vencer.
        ordem = {"VENCIDA": 0, "PROXIMA": 1, "SEM_FDS": 2, "VIGENTE": 3}
        produtos.sort(key=lambda p: (ordem.get(p.fds_situacao, 9), p.nome_comercial))
        ind = servicos.indicadores(s)

    # Os mesmos três cartões da página inicial, para a leitura ser a mesma
    # em todo o sistema.
    pendentes = sum(ind["por_status"].get(e, 0) for e in STATUS_ABERTOS)
    painel = Div(
        A(
            Div("Produtos Aprovados", cls="rotulo"),
            Div(str(ind["por_status"].get("APROVADO", 0)), cls="valor"),
            Div("liberados para uso", cls="nota"),
            href="/produtos",
            cls="kpi-inicio verde",
        ),
        A(
            Div("Produtos Pendentes", cls="rotulo"),
            Div(str(pendentes), cls="valor"),
            Div("em análise pelas áreas", cls="nota"),
            href="/aprovacoes",
            cls="kpi-inicio ambar",
        ),
        A(
            Div("Produtos Reprovados", cls="rotulo"),
            Div(str(ind["por_status"].get("REPROVADO", 0)), cls="valor"),
            Div("não liberados", cls="nota"),
            href="/historico?status=REPROVADO",
            cls="kpi-inicio vermelho",
        ),
        cls="painel-inicio",
    )

    # 10 por página: acima disso a tela vira um rolar sem fim.
    total = len(produtos)
    paginas = max(1, -(-total // FDS_POR_PAGINA))
    pagina = min(max(1, pagina), paginas)
    inicio = (pagina - 1) * FDS_POR_PAGINA
    visiveis = produtos[inicio:inicio + FDS_POR_PAGINA]
    cartoes = [_cartao_fds(p) for p in visiveis]
    navegacao = ui.paginacao(
        pagina, total, FDS_POR_PAGINA, "/fds",
        {"q": q, "fabrica": fabrica, "area": area, "tipo_produto": tipo_produto,
         "orgao": orgao, "situacao": situacao, "solicitante": solicitante},
        setas_curtas=True,
    )

    return ui.pagina(
        "Fichas de Dados de Segurança",
        painel,
        Div(
            _filtros_fds(q, fabrica, area, tipo_produto, orgao, situacao,
                         solicitante, solicitantes),
            cls="card",
        ),
        H2("Resultado da consulta", cls="titulo-resultado"),
        *(cartoes if cartoes else [Div(ui.vazio("Nenhuma FDS encontrada com esses filtros.", "▣"), cls="card")]),
        navegacao,
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
            or not doc.produto.disponivel_publico
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
    return RedirectResponse(
        _msg("/usuarios", "ok", "Usuário cadastrado."), status_code=303
    )


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


# =====================================================================
# Cobrança automática (lembretes de 7 em 7 dias)
# =====================================================================


def _rotina_lembretes():
    """Verifica as solicitações paradas ao subir e a cada 12 horas.

    Quem preferir controlar pelo Agendador de Tarefas do Windows pode
    desligar com LEMBRETES_ATIVOS=0 no .env e chamar `lembretes.py`.
    """
    import threading
    import time as _time

    def laco():
        _time.sleep(20)  # deixa o servidor terminar de subir
        while True:
            try:
                with db_session() as s:
                    enviados = servicos.enviar_lembretes(s, config.LEMBRETE_DIAS)
                    avisados = servicos.enviar_avisos_vencimento(s)
                if enviados:
                    print(f"[lembretes] {enviados} solicitação(ões) cobrada(s).")
                if avisados:
                    print(f"[lembretes] {avisados} aviso(s) de vencimento enviado(s).")
            except Exception as exc:  # pragma: no cover
                print(f"[lembretes] falha ao verificar: {exc}")
            _time.sleep(12 * 60 * 60)

    threading.Thread(target=laco, daemon=True, name="lembretes").start()


if config.LEMBRETES_ATIVOS:
    _rotina_lembretes()

if __name__ == "__main__":
    print("=" * 62)
    print(f" {config.APP_EMPRESA} | {config.APP_NOME}")
    print(f" Banco: {descricao_conexao()}")
    print(f" SMTP : {'ativo - ' + config.SMTP_HOST if config.SMTP_ATIVO else 'não configurado'}")
    print(" URL  : http://127.0.0.1:5001")
    print("=" * 62)
    serve(port=5001, reload=False)
