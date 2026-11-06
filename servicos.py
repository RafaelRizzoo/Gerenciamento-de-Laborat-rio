"""Regras de negócio: criação de solicitacoes, fluxo de aprovacao e auditoria."""

import secrets
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

import notificacoes
from security import gerar_hash
from models import (
    AREAS_APROVACAO,
    EPIS,
    ETAPA_FINAL,
    FLUXO_APROVACAO,
    ORGAOS_CONTROLADORES,
    STATUS,
    STATUS_ABERTOS,
    TECNICOS_SEGURANCA,
    Aprovacao,
    AreaAprovador,
    ControleOrgao,
    Documento,
    LogAuditoria,
    Produto,
    ProdutoCAS,
    ProdutoFabrica,
    ProdutoEPI,
    ProdutoRisco,
    Usuario,
    email_do_tecnico,
    email_provisorio_tecnico,
    par_valido,
    tecnico_da_area,
    unidade_da_area,
)

SENHA_PADRAO_TECNICO = "123456"


# ------------------------------------------------------------ Auditoria
def registrar_log(
    sessao,
    acao: str,
    detalhe: str = "",
    usuario_id=None,
    produto_id=None,
    status_anterior: str | None = None,
    status_novo: str | None = None,
):
    """Registra uma ação. Quando o status muda, guarda de onde para onde."""
    sessao.add(
        LogAuditoria(
            acao=acao,
            detalhe=detalhe,
            usuario_id=usuario_id,
            produto_id=produto_id,
            status_anterior=status_anterior,
            status_novo=status_novo,
        )
    )


# ------------------------------------------------------------- Códigos
def proximo_codigo(sessao) -> str:
    """Gera o proximo codigo interno no formato PQ-AAAA-0001."""
    ano = datetime.now().year
    prefixo = f"PQ-{ano}-"
    total = sessao.scalar(
        select(func.count(Produto.id)).where(Produto.codigo_interno.like(f"{prefixo}%"))
    )
    return f"{prefixo}{(total or 0) + 1:04d}"


# ------------------------------------------- Técnico de Segurança da área
def tecnico_por_nome(sessao, nome: str | None) -> Usuario | None:
    """Usuário ativo com esse nome que responde pela área de Segurança."""
    nome = (nome or "").strip()
    if not nome:
        return None
    candidatos = list(
        sessao.scalars(
            select(Usuario).where(Usuario.nome == nome, Usuario.ativo.is_(True))
        ).unique()
    )
    for usuario in candidatos:
        if "SEGURANCA" in areas_do_usuario(sessao, usuario):
            return usuario
    return None


def resolver_tecnico(sessao, unidade: str | None, area: str | None,
                     escolhido: str | None = None) -> Usuario | None:
    """Quem, na Segurança, analisa uma solicitação desta unidade e área.

    Área com responsável fixo: vale sempre o da tabela, mesmo que o
    formulário traga outro nome (o campo é bloqueado na tela, e aqui o
    servidor não confia no que veio). Área sem responsável: vale o técnico
    escolhido pelo solicitante, que precisa ser um dos técnicos da lista.
    """
    fixo = tecnico_da_area(unidade, area)
    if fixo:
        return tecnico_por_nome(sessao, fixo)
    if escolhido in TECNICOS_SEGURANCA:
        return tecnico_por_nome(sessao, escolhido)
    return None


def garantir_tecnicos_seguranca(sessao) -> int:
    """Cria o login dos técnicos de Segurança que ainda não existem.

    E-mail corporativo real e senha padrão, com troca obrigatória no primeiro
    acesso. Idempotente: quem já existe (por e-mail ou por nome) só é
    vinculado à área de Segurança. Contas criadas antes com o e-mail provisório
    (nome.sobrenome) passam para o e-mail real, e a senha volta ao padrão se a
    pessoa ainda não a trocou.
    """
    criados = 0
    for nome in TECNICOS_SEGURANCA:
        email = email_do_tecnico(nome)
        usuario = sessao.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None:
            usuario = sessao.scalar(
                select(Usuario).where(Usuario.nome == nome, Usuario.ativo.is_(True))
            )
            if usuario is not None and usuario.email == email_provisorio_tecnico(nome):
                usuario.email = email
                if usuario.precisa_trocar_senha:
                    usuario.senha_hash = gerar_hash(SENHA_PADRAO_TECNICO)
        if usuario is None:
            usuario = Usuario(
                nome=nome,
                email=email,
                senha_hash=gerar_hash(SENHA_PADRAO_TECNICO),
                papel="SEGURANCA",
                setor="Segurança do Trabalho",
                ativo=True,
                precisa_trocar_senha=True,
            )
            sessao.add(usuario)
            sessao.flush()
            criados += 1
        vinculo = sessao.scalar(
            select(AreaAprovador).where(
                AreaAprovador.area == "SEGURANCA", AreaAprovador.usuario_id == usuario.id
            )
        )
        if vinculo is None:
            sessao.add(AreaAprovador(area="SEGURANCA", usuario_id=usuario.id, ativo=True))
        elif not vinculo.ativo:
            vinculo.ativo = True
    sessao.flush()
    return criados


def visivel_na_fila(sessao, usuario: Usuario, produto: Produto) -> bool:
    """A solicitação aparece na tela de Aprovações para esta pessoa?

    Técnico de Segurança só enxerga as solicitações da sua área: as dos
    colegas não aparecem. Quem tem outra função de aprovação, o aprovador
    final e o administrador continuam vendo todas.
    """
    if usuario is None:
        return False
    if usuario.papel in ("ADMIN", "APROVADOR_FINAL"):
        return True
    if produto.solicitante_id == usuario.id:
        return True
    if not produto.tecnico_seguranca_id or produto.tecnico_seguranca_id == usuario.id:
        return True
    return any(a != "SEGURANCA" for a in areas_do_usuario(sessao, usuario))


def trocar_tecnico_seguranca(sessao, produto: Produto, novo: Usuario, autor: Usuario) -> Produto:
    """Passa a análise de Segurança para outro técnico (ausência, férias).

    Só vale enquanto a Segurança ainda não deu parecer. A troca fica no
    histórico e o novo técnico é avisado.
    """
    if "SEGURANCA" not in produto.areas_pendentes or not produto.aberta:
        raise ValueError("A Segurança já deu parecer: não há mais o que reatribuir.")
    if "SEGURANCA" not in areas_do_usuario(sessao, novo):
        raise ValueError("Escolha um técnico que responda pela Segurança.")
    anterior = produto.tecnico_seguranca
    if anterior and anterior.id == novo.id:
        return produto
    produto.tecnico_seguranca_id = novo.id
    sessao.flush()
    sessao.refresh(produto)
    registrar_log(
        sessao,
        "TECNICO_SEGURANCA_TROCADO",
        f"Técnico de Segurança alterado de {anterior.nome if anterior else 'ninguém definido'}"
        f" para {novo.nome}.",
        autor.id,
        produto.id,
    )
    notificacoes.notificar_etapa_pendente(sessao, produto, "SEGURANCA")
    return produto


def reavaliar_tecnico(sessao, produto: Produto, autor: Usuario) -> None:
    """Depois de editar a área do produto, confere se o técnico ainda é o certo.

    Só age enquanto a Segurança não deu parecer e quando a área tem
    responsável fixo; nas demais, a escolha feita no cadastro fica.
    """
    if not produto.seguranca_primeiro or "SEGURANCA" not in produto.areas_pendentes:
        return
    unidade = produto.unidade_da_solicitacao
    if not par_valido(unidade, produto.area_solicitante):
        unidade = unidade_da_area(produto.fabricas_nomes, produto.area_solicitante)
    produto.unidade_solicitante = unidade
    novo = resolver_tecnico(sessao, unidade, produto.area_solicitante)
    if novo and novo.id != produto.tecnico_seguranca_id:
        trocar_tecnico_seguranca(sessao, produto, novo, autor)


# --------------------------------------------------------- Solicitação
def criar_solicitacao(sessao, dados: dict, solicitante: Usuario, arquivos: list[dict]) -> Produto:
    """Cria o produto, as 4 etapas de aprovacao, anexa documentos e notifica."""
    produto = Produto(
        codigo_interno=dados.get("codigo_interno") or proximo_codigo(sessao),
        nome_comercial=dados["nome_comercial"],
        nome_tecnico=dados.get("nome_tecnico"),
        fabricante=dados["fabricante"],
        categoria=dados.get("categoria"),
        tipo_produto=dados.get("tipo_produto"),
        numero_cas=dados.get("numero_cas"),
        composicao=dados.get("composicao"),
        estado_fisico=dados.get("estado_fisico"),
        setor_solicitante=dados.get("setor_solicitante") or solicitante.setor,
        area_solicitante=dados.get("area_solicitante"),
        prazo_utilizacao=dados.get("prazo_utilizacao"),
        aplicacao=dados.get("aplicacao"),
        forma_aplicacao=dados.get("forma_aplicacao"),
        necessidade_uso=dados.get("necessidade_uso"),
        funcionarios_expostos=dados.get("funcionarios_expostos"),
        funcoes_expostas=dados.get("funcoes_expostas"),
        terceiro_nome=dados.get("terceiro_nome"),
        terceiro_empresa=dados.get("terceiro_empresa"),
        gestor_contrato=dados.get("gestor_contrato"),
        gestor_email=dados.get("gestor_email"),
        processo=dados.get("processo"),
        consumo_estimado=dados.get("consumo_estimado"),
        unidade=dados.get("unidade"),
        local_armazenamento=dados.get("local_armazenamento"),
        classificacao_ghs=dados.get("classificacao_ghs"),
        inflamavel=dados.get("inflamavel"),
        cancerigeno=dados.get("cancerigeno"),
        ponto_fulgor=dados.get("ponto_fulgor"),
        onu_numero=dados.get("onu_numero"),
        epi_recomendado=dados.get("epi_recomendado"),
        restricoes_uso=dados.get("restricoes_uso"),
        observacoes=dados.get("observacoes"),
        status="PENDENTE",
        etapa_atual=None,
        solicitante_id=solicitante.id,
        seguranca_primeiro=dados.get("seguranca_primeiro", True),
    )
    # Unidade onde o produto será usado e técnico de Segurança responsável.
    # Quando o formulário não traz a unidade (cargas de exemplo), ela sai da
    # área, olhando as unidades autorizadas.
    produto.unidade_solicitante = dados.get("unidade_solicitante") or unidade_da_area(
        dados.get("fabricas") or [], dados.get("area_solicitante")
    )
    tecnico = resolver_tecnico(
        sessao, produto.unidade_solicitante, dados.get("area_solicitante"),
        dados.get("tecnico_seguranca"),
    )
    produto.tecnico_seguranca_id = tecnico.id if tecnico else None
    sessao.add(produto)
    sessao.flush()

    aplicar_fabricas(sessao, produto, dados.get("fabricas") or [])
    aplicar_controles(sessao, produto, dados.get("controles") or [])
    aplicar_riscos(sessao, produto, dados.get("riscos") or [])
    if dados.get("cas") is not None:
        aplicar_cas(sessao, produto, dados.get("cas") or [])

    for ordem, (etapa, _rotulo) in enumerate(FLUXO_APROVACAO, start=1):
        sessao.add(
            Aprovacao(produto_id=produto.id, etapa=etapa, ordem=ordem, decisao="PENDENTE")
        )

    for arq in arquivos:
        sessao.add(
            Documento(
                produto_id=produto.id,
                tipo=arq["tipo"],
                nome_arquivo=arq["nome"],
                content_type=arq.get("content_type"),
                tamanho=len(arq["conteudo"]),
                conteudo=arq["conteudo"],
                data_revisao=arq.get("data_revisao"),
                enviado_por_id=solicitante.id,
            )
        )

    sessao.flush()
    registrar_log(
        sessao,
        "SOLICITACAO_CRIADA",
        f"Produto {produto.nome_comercial} ({produto.codigo_interno}) enviado para análise.",
        solicitante.id,
        produto.id,
        status_novo="PENDENTE",
    )
    sessao.refresh(produto)
    notificacoes.notificar_envio(sessao, produto)
    return produto


def obter_ou_criar_solicitante(sessao, nome: str | None, email: str | None) -> Usuario:
    """Solicitante de um cadastro feito sem login.

    Se o e-mail já existe, reaproveita a pessoa; senão cria um usuário
    Solicitante com senha aleatória (ele não precisa de login para
    cadastrar, mas passa a receber os avisos do fluxo).
    """
    email = (email or "").strip().lower()
    nome = (nome or "").strip() or (email.split("@")[0] if email else "Solicitante")
    usuario = sessao.scalar(select(Usuario).where(Usuario.email == email)) if email else None
    if usuario:
        if not usuario.nome:
            usuario.nome = nome
        return usuario
    usuario = Usuario(
        nome=nome,
        email=email or f"solicitante{int(datetime.now().timestamp())}@local",
        senha_hash=gerar_hash(secrets.token_urlsafe(16)),
        papel="SOLICITANTE",
        ativo=True,
    )
    sessao.add(usuario)
    sessao.flush()
    registrar_log(
        sessao,
        "SOLICITANTE_REGISTRADO",
        f"{usuario.nome} <{usuario.email}> cadastrado ao enviar uma solicitação sem login.",
        usuario.id,
    )
    return usuario


def aplicar_fabricas(sessao, produto: Produto, fabricas: list[str]) -> None:
    """Deixa a lista de fábricas do produto exatamente igual à informada."""
    desejadas = {f.strip() for f in fabricas if f and f.strip()}
    atuais = {f.fabrica: f for f in produto.fabricas}
    for nome, registro in atuais.items():
        if nome not in desejadas:
            sessao.delete(registro)
    for nome in desejadas - set(atuais):
        sessao.add(ProdutoFabrica(produto_id=produto.id, fabrica=nome))
    sessao.flush()


def aplicar_riscos(sessao, produto: Produto, classes: list[str]) -> None:
    """Deixa as classes de risco do produto exatamente iguais às informadas."""
    desejadas = {c.strip() for c in classes if c and c.strip()}
    atuais = {r.classe: r for r in produto.riscos}
    for classe, registro in atuais.items():
        if classe not in desejadas:
            sessao.delete(registro)
    for classe in desejadas - set(atuais):
        sessao.add(ProdutoRisco(produto_id=produto.id, classe=classe))
    sessao.flush()


def aplicar_epis(sessao, produto: Produto, epis: list[str]) -> None:
    """Deixa os EPIs obrigatórios do produto exatamente iguais aos informados.

    Só a área de Segurança mexe nisto, ao registrar o parecer.
    """
    permitidos = set(EPIS)
    desejados = {e.strip() for e in epis if e and e.strip() in permitidos}
    atuais = {e.epi: e for e in produto.epis}
    for epi, registro in atuais.items():
        if epi not in desejados:
            sessao.delete(registro)
    for epi in desejados - set(atuais):
        sessao.add(ProdutoEPI(produto_id=produto.id, epi=epi))
    sessao.flush()


def aplicar_cas(sessao, produto: Produto, numeros: list[str]) -> None:
    """Deixa os números CAS do produto exatamente iguais aos informados.

    A ordem informada é preservada, e repetidos são ignorados: a FDS às
    vezes repete o mesmo CAS em faixas de concentração diferentes.
    """
    desejados: list[str] = []
    for bruto in numeros or []:
        numero = (bruto or "").strip()
        if numero and numero not in desejados:
            desejados.append(numero)

    atuais = {c.numero: c for c in produto.cas}
    for numero, registro in atuais.items():
        if numero not in desejados:
            sessao.delete(registro)
    sessao.flush()
    for numero in desejados:
        if numero not in atuais:
            sessao.add(ProdutoCAS(produto_id=produto.id, numero=numero))
    sessao.flush()
    # O campo antigo acompanha o primeiro da lista, para a busca e os
    # relatórios que ainda olham para ele continuarem funcionando.
    produto.numero_cas = desejados[0] if desejados else None
    sessao.flush()


def produto_duplicado(sessao, nome_comercial: str, fabricante: str) -> Produto | None:
    """Já existe cadastro com o mesmo nome comercial e fabricante?

    Compara sem diferenciar maiúsculas nem espaços extras. Produtos reprovados
    não contam: o solicitante pode tentar de novo com dados corrigidos.
    """
    nome = " ".join((nome_comercial or "").split()).lower()
    fab = " ".join((fabricante or "").split()).lower()
    if not nome:
        return None
    candidatos = sessao.scalars(
        select(Produto).where(Produto.status != "REPROVADO")
    ).unique()
    for p in candidatos:
        if (
            " ".join((p.nome_comercial or "").split()).lower() == nome
            and " ".join((p.fabricante or "").split()).lower() == fab
        ):
            return p
    return None


def aplicar_controles(sessao, produto: Produto, controles: list[dict]) -> None:
    """Sincroniza os órgãos controladores do produto.

    `controles` = [{"orgao": "POLICIA_FEDERAL", "numero_licenca": "...",
                    "validade_licenca": date|None, "observacao": "..."}]
    """
    validos = [c for c in controles if c.get("orgao") in ORGAOS_CONTROLADORES]
    desejados = {c["orgao"]: c for c in validos}
    atuais = {c.orgao: c for c in produto.controles}

    for orgao, registro in atuais.items():
        if orgao not in desejados:
            sessao.delete(registro)

    for orgao, dados in desejados.items():
        registro = atuais.get(orgao)
        if registro is None:
            registro = ControleOrgao(produto_id=produto.id, orgao=orgao)
            sessao.add(registro)
        registro.numero_licenca = (dados.get("numero_licenca") or "").strip() or None
        registro.validade_licenca = dados.get("validade_licenca")
        registro.observacao = (dados.get("observacao") or "").strip() or None
    sessao.flush()


def atualizar_ficha(sessao, produto: Produto, dados: dict, usuario: Usuario) -> Produto:
    """Atualiza os dados de identificação, aplicação e controle regulatório."""
    campos = (
        "nome_tecnico", "categoria", "tipo_produto",
        "composicao", "estado_fisico", "aplicacao", "processo",
        "necessidade_uso", "forma_aplicacao",
        "terceiro_nome", "terceiro_empresa", "gestor_contrato", "gestor_email",
        "funcionarios_expostos", "funcoes_expostas",
        "area_solicitante", "prazo_utilizacao", "consumo_estimado", "unidade",
        "local_armazenamento", "classificacao_ghs", "onu_numero",
        "inflamavel", "cancerigeno", "ponto_fulgor",
        "epi_recomendado", "restricoes_uso", "observacoes",
    )
    alterados = []
    for campo in campos:
        if campo not in dados:
            continue
        novo = dados[campo]
        if isinstance(novo, str):
            novo = novo.strip() or None
        if getattr(produto, campo) != novo:
            setattr(produto, campo, novo)
            alterados.append(campo)

    if "cas" in dados:
        antes = list(produto.cas_numeros)
        aplicar_cas(sessao, produto, dados["cas"])
        if antes != list(produto.cas_numeros):
            alterados.append("números CAS")

    if "fabricas" in dados:
        antes = set(produto.fabricas_nomes)
        aplicar_fabricas(sessao, produto, dados["fabricas"])
        if antes != set(produto.fabricas_nomes):
            alterados.append("unidades")

    if "riscos" in dados:
        antes = set(produto.riscos_nomes)
        aplicar_riscos(sessao, produto, dados["riscos"])
        if antes != set(produto.riscos_nomes):
            alterados.append("classes de risco")

    if "controles" in dados:
        antes = set(c.orgao for c in produto.controles)
        aplicar_controles(sessao, produto, dados["controles"])
        if antes != set(c.orgao for c in produto.controles):
            alterados.append("órgãos controladores")
        else:
            alterados.append("licenças")

    produto.atualizado_em = datetime.now()
    sessao.flush()
    if "area_solicitante" in alterados or "unidades" in alterados:
        sessao.refresh(produto)
        reavaliar_tecnico(sessao, produto, usuario)
    registrar_log(
        sessao,
        "FICHA_ATUALIZADA",
        "Campos alterados: " + (", ".join(alterados) if alterados else "nenhum"),
        usuario.id,
        produto.id,
    )
    return produto


def areas_do_usuario(sessao, usuario: Usuario) -> list[str]:
    """Áreas pelas quais este usuário pode dar parecer.

    Vem da tabela de aprovadores (mantida na tela de Aprovações). O papel
    do cadastro continua valendo como atalho, para não quebrar bases
    antigas.

    O parecer de cada área é exclusivo de quem responde por ela: ninguém
    opina pela área de outro. **O administrador não é exceção** - ele
    administra o sistema, mas só assina parecer se estiver cadastrado como
    aprovador daquela área, como qualquer outro. Sem isso, o cargo de
    administrador seria um jeito de dar parecer químico sem ser o químico.

    Para quem administra os aprovadores, veja `areas_gerenciaveis()`, que é
    outra pergunta: "quem pode mexer na lista de aprovadores desta área?".
    """
    if not usuario:
        return []
    areas = set(
        sessao.scalars(
            select(AreaAprovador.area).where(
                AreaAprovador.usuario_id == usuario.id, AreaAprovador.ativo.is_(True)
            )
        )
    )
    if usuario.papel in dict(FLUXO_APROVACAO):
        areas.add(usuario.papel)
    return [chave for chave, _ in FLUXO_APROVACAO if chave in areas]


def areas_para_decidir(sessao, usuario: Usuario, produto: Produto) -> list[str]:
    """Etapas deste produto que o usuário pode decidir agora."""
    if produto.status not in ("PENDENTE", "EM_ANALISE"):
        return []
    return [
        area
        for area in areas_do_usuario(sessao, usuario)
        if produto.aguarda_usuario(area, usuario.id)
    ]


def pode_decidir(sessao, usuario: Usuario, produto: Produto) -> bool:
    """Há alguma etapa pendente que este usuário possa decidir?

    Vale para PENDENTE (ninguém decidiu ainda) e EM_ANALISE. Enquanto o
    produto está AGUARDANDO_CORRECAO a bola está com o solicitante.
    """
    return bool(areas_para_decidir(sessao, usuario, produto))


def registrar_decisao(
    sessao, produto: Produto, usuario: Usuario, decisao: str, parecer: str,
    area: str | None = None, epis: list[str] | None = None,
    expostos: dict | None = None,
) -> Produto:
    """Registra o parecer de UMA área e reavalia a situação do produto.

    Não existe ordem entre as áreas: cada uma decide quando quiser. O
    Aprovador Final só é acionado quando as demais concluírem, e é ele
    quem fecha a aprovação.
    """
    permitidas = areas_para_decidir(sessao, usuario, produto)
    if area is None:
        area = permitidas[0] if len(permitidas) == 1 else None
    if area is None or area not in permitidas:
        raise ValueError("Etapa de aprovação inválida para este usuário.")

    # Os EPIs obrigatórios são decisão da área de Segurança.
    if epis is not None and area == "SEGURANCA":
        aplicar_epis(sessao, produto, epis)

    # Quantos e quais funcionários ficam expostos é avaliação da área de
    # Saúde: o solicitante não tem como saber, e era por isso que estes dois
    # campos viviam em branco no cadastro.
    if expostos is not None and area == "SAUDE":
        if "funcionarios_expostos" in expostos:
            produto.funcionarios_expostos = expostos["funcionarios_expostos"]
        if "funcoes_expostas" in expostos:
            produto.funcoes_expostas = (expostos["funcoes_expostas"] or "").strip() or None
        sessao.flush()

    aprovacao = next((a for a in produto.aprovacoes if a.etapa == area), None)
    if aprovacao is None:
        raise ValueError("Etapa de aprovação não encontrada para este produto.")

    etapa = area
    status_antes = produto.status
    aprovacao.decisao = decisao
    aprovacao.parecer = parecer or None
    aprovacao.aprovador_id = usuario.id
    aprovacao.decidido_em = datetime.now()
    sessao.flush()

    if decisao == "REPROVADO":
        # Uma reprovação encerra o processo, venha de qual área vier.
        produto.status = "REPROVADO"
        produto.etapa_atual = None
        produto.concluido_em = datetime.now()
    elif etapa == ETAPA_FINAL:
        produto.status = "APROVADO"
        produto.etapa_atual = None
        produto.concluido_em = datetime.now()
    else:
        produto.status = "EM_ANALISE"
        # Concluídas as áreas, a bola passa para o Aprovador Final.
        produto.etapa_atual = ETAPA_FINAL if produto.areas_concluidas else None

    produto.pendencia = None
    produto.atualizado_em = datetime.now()
    sessao.flush()

    registrar_log(
        sessao,
        f"ETAPA_{decisao}",
        f"Etapa {dict(FLUXO_APROVACAO).get(etapa, etapa)} - {decisao.lower()} por {usuario.nome}."
        + (f" Parecer: {parecer}" if parecer else ""),
        usuario.id,
        produto.id,
        status_anterior=status_antes,
        status_novo=produto.status,
    )

    notificacoes.notificar_decisao(sessao, produto, etapa, decisao, parecer)
    if produto.status in ("APROVADO", "REPROVADO"):
        notificacoes.notificar_conclusao(sessao, produto)
    elif produto.etapa_atual == ETAPA_FINAL:
        # Só agora o Aprovador Final é chamado.
        notificacoes.notificar_etapa_pendente(sessao, produto, ETAPA_FINAL)
    return produto


def registrar_observacao(sessao, produto: Produto, usuario: Usuario, texto: str) -> Produto:
    """Observação de análise: fica no histórico e não altera o status."""
    registrar_log(
        sessao,
        "OBSERVACAO",
        texto,
        usuario.id,
        produto.id,
    )
    produto.atualizado_em = datetime.now()
    sessao.flush()
    return produto


def observacoes(sessao, produto_id: int) -> list:
    """Observações registradas pelos aprovadores, da mais recente para a mais antiga."""
    return list(
        sessao.scalars(
            select(LogAuditoria)
            .where(LogAuditoria.produto_id == produto_id, LogAuditoria.acao == "OBSERVACAO")
            .order_by(LogAuditoria.criado_em.desc())
        ).unique()
    )


def descontinuar(sessao, produto: Produto, usuario: Usuario, motivo: str) -> Produto:
    produto.status = "DESCONTINUADO"
    produto.etapa_atual = None
    produto.motivo_encerramento = motivo
    produto.atualizado_em = datetime.now()
    produto.concluido_em = datetime.now()
    sessao.flush()
    registrar_log(
        sessao,
        "PRODUTO_DESCONTINUADO",
        f"Produto {produto.codigo_interno} descontinuado. Motivo: {motivo}",
        usuario.id,
        produto.id,
    )
    notificacoes.notificar_conclusao(sessao, produto)
    return produto


def reativar(sessao, produto: Produto, usuario: Usuario) -> Produto:
    produto.status = "APROVADO"
    produto.motivo_encerramento = None
    produto.atualizado_em = datetime.now()
    sessao.flush()
    registrar_log(
        sessao,
        "PRODUTO_REATIVADO",
        f"Produto {produto.codigo_interno} reativado.",
        usuario.id,
        produto.id,
    )
    return produto


# ------------------------------------------------------------ Consultas
def solicitacoes_pendentes_de(sessao, usuario: Usuario) -> list[Produto]:
    """Solicitações que dependem de um parecer deste usuário agora."""
    areas = areas_do_usuario(sessao, usuario)
    if not areas:
        return []
    abertas = list(
        sessao.scalars(
            select(Produto)
            .where(Produto.status.in_(("PENDENTE", "EM_ANALISE")))
            .order_by(Produto.criado_em)
        ).unique()
    )
    return [p for p in abertas if any(p.aguarda_usuario(a, usuario.id) for a in areas)]


def contar_pendencias(sessao, usuario: Usuario) -> int:
    """Quantas solicitações aguardam a análise deste usuario."""
    return len(solicitacoes_pendentes_de(sessao, usuario))


def filtrar_por_situacao_fds(produtos: list, situacao: str) -> list:
    """A situação da FDS é calculada a partir da data de revisão, então o
    filtro acontece em Python e não no SQL."""
    if not situacao:
        return produtos
    return [p for p in produtos if p.fds_situacao == situacao]


def resumo_fds(produtos: list) -> dict:
    """Contagem por situação, para o cabeçalho da página de FDS."""
    resumo = {chave: 0 for chave in ("VIGENTE", "PROXIMA", "VENCIDA", "SEM_FDS")}
    for p in produtos:
        resumo[p.fds_situacao] = resumo.get(p.fds_situacao, 0) + 1
    return resumo


def indicadores(sessao) -> dict:
    """Números do dashboard."""
    por_status = dict(
        sessao.execute(select(Produto.status, func.count(Produto.id)).group_by(Produto.status)).all()
    )
    por_categoria = sessao.execute(
        select(Produto.categoria, func.count(Produto.id))
        .group_by(Produto.categoria)
        .order_by(func.count(Produto.id).desc())
    ).all()
    # Pendências por área: como as áreas analisam em paralelo, a contagem
    # vem das etapas ainda sem parecer, e não de uma "etapa atual".
    abertos = list(
        sessao.scalars(
            select(Produto).where(Produto.status.in_(("PENDENTE", "EM_ANALISE")))
        ).unique()
    )
    contagem = {chave: 0 for chave, _ in FLUXO_APROVACAO}
    for produto in abertos:
        for area in produto.areas_pendentes:
            if produto.aguarda(area):
                contagem[area] = contagem.get(area, 0) + 1
    por_etapa = [(chave, contagem.get(chave, 0)) for chave, _ in FLUXO_APROVACAO]
    por_fabricante = sessao.execute(
        select(Produto.fabricante, func.count(Produto.id))
        .group_by(Produto.fabricante)
        .order_by(func.count(Produto.id).desc())
        .limit(6)
    ).all()
    total_docs = sessao.scalar(select(func.count(Documento.id))) or 0
    total_fds = sessao.scalar(select(func.count(Documento.id)).where(Documento.tipo == "FDS")) or 0
    sem_fds = (
        sessao.scalar(
            select(func.count(Produto.id)).where(
                ~Produto.documentos.any(Documento.tipo == "FDS")
            )
        )
        or 0
    )
    return {
        "total": sum(por_status.values()),
        "por_status": por_status,
        "abertas": sum(por_status.get(s, 0) for s in STATUS_ABERTOS),
        "por_categoria": [(c or "Não informada", n) for c, n in por_categoria],
        "por_etapa": [
            (dict(FLUXO_APROVACAO).get(e, e or "-"), n) for e, n in por_etapa if n
        ],
        "por_fabricante": [(f or "-", n) for f, n in por_fabricante],
        "total_documentos": total_docs,
        "total_fds": total_fds,
        "sem_fds": sem_fds,
    }


def buscar_produtos(
    sessao,
    termo: str = "",
    status: str = "",
    categoria: str = "",
    somente_aprovados: bool = False,
    somente_com_fds: bool = False,
    fabrica: str = "",
    area: str = "",
    tipo_produto: str = "",
    orgao: str = "",
    solicitante_id: int | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
    somente_abertas: bool = False,
    limite: int | None = 200,
):
    consulta = select(Produto)
    if termo:
        like = f"%{termo.strip()}%"
        consulta = consulta.where(
            Produto.nome_comercial.like(like)
            | Produto.nome_tecnico.like(like)
            | Produto.fabricante.like(like)
            | Produto.fornecedor.like(like)
            | Produto.codigo_interno.like(like)
            | Produto.categoria.like(like)
            | Produto.numero_cas.like(like)
            | Produto.cas.any(ProdutoCAS.numero.like(like))
        )
    if status:
        consulta = consulta.where(Produto.status == status)
    if categoria:
        consulta = consulta.where(Produto.categoria == categoria)
    if fabrica:
        consulta = consulta.where(Produto.fabricas.any(ProdutoFabrica.fabrica == fabrica))
    if area:
        consulta = consulta.where(Produto.area_solicitante == area)
    if tipo_produto:
        consulta = consulta.where(Produto.tipo_produto == tipo_produto)
    if orgao == "QUALQUER":
        consulta = consulta.where(Produto.controles.any())
    elif orgao:
        consulta = consulta.where(Produto.controles.any(ControleOrgao.orgao == orgao))
    if somente_abertas:
        consulta = consulta.where(Produto.status.in_(STATUS_ABERTOS))
    if solicitante_id:
        consulta = consulta.where(Produto.solicitante_id == solicitante_id)
    if data_de:
        consulta = consulta.where(Produto.criado_em >= datetime.combine(data_de, time.min))
    if data_ate:
        consulta = consulta.where(Produto.criado_em <= datetime.combine(data_ate, time.max))
    if somente_aprovados:
        consulta = consulta.where(Produto.status == "APROVADO")
    if somente_com_fds:
        consulta = consulta.where(Produto.documentos.any(Documento.tipo == "FDS"))
    consulta = consulta.order_by(Produto.atualizado_em.desc())
    if limite:
        consulta = consulta.limit(limite)
    return list(sessao.scalars(consulta).unique())


# =====================================================================
# Recursos e Documentos (biblioteca)
# =====================================================================

from models import (  # noqa: E402  (agrupado aqui para isolar o módulo novo)
    SECOES_RECURSO,
    Recurso,
    RecursoArquivo,
    grupo_do_arquivo,
    sem_acento,
)

# Perfis autorizados a publicar, revisar e arquivar documentos da biblioteca.
PAPEIS_BIBLIOTECA = (
    "SAUDE",
    "SEGURANCA",
    "MEIO_AMBIENTE",
    "QUIMICO_RESPONSAVEL",
    "ADMIN",
)

PERIODOS_RECURSO = {
    "30": "Últimos 30 dias",
    "90": "Últimos 90 dias",
    "365": "Últimos 12 meses",
}

ORDENACOES_RECURSO = {
    "recentes": "Atualizados primeiro",
    "titulo": "Ordem alfabética",
    "baixados": "Mais baixados",
}


def pode_publicar(usuario) -> bool:
    return bool(usuario) and usuario.papel in PAPEIS_BIBLIOTECA


def criar_recurso(sessao, dados: dict, autor, arquivo: dict | None = None) -> Recurso:
    """Cria um item da biblioteca. `arquivo` é obrigatório quando não é link."""
    recurso = Recurso(
        secao=dados.get("secao") or "PROCEDIMENTOS",
        titulo=dados["titulo"],
        codigo=dados.get("codigo") or None,
        descricao=dados.get("descricao") or None,
        palavras_chave=dados.get("palavras_chave") or None,
        tipo_midia=dados.get("tipo_midia") or "ARQUIVO",
        url=dados.get("url") or None,
        versao_atual=1,
        data_revisao=dados.get("data_revisao"),
        proxima_revisao=dados.get("proxima_revisao"),
        responsavel_id=autor.id if autor else None,
    )
    sessao.add(recurso)
    sessao.flush()

    if arquivo:
        sessao.add(
            RecursoArquivo(
                recurso_id=recurso.id,
                versao=1,
                nome_arquivo=arquivo["nome"],
                content_type=arquivo.get("content_type"),
                tamanho=len(arquivo["conteudo"]),
                conteudo=arquivo["conteudo"],
                data_revisao=dados.get("data_revisao"),
                notas=dados.get("notas") or "Versão inicial.",
                enviado_por_id=autor.id if autor else None,
            )
        )
    sessao.flush()
    registrar_log(
        sessao,
        "RECURSO_PUBLICADO",
        f"{SECOES_RECURSO.get(recurso.secao, recurso.secao)}: {recurso.titulo}",
        autor.id if autor else None,
    )
    return recurso


def atualizar_recurso(sessao, recurso: Recurso, dados: dict, autor) -> Recurso:
    """Altera os metadados (não mexe no arquivo nem na versão)."""
    recurso.secao = dados.get("secao") or recurso.secao
    recurso.titulo = dados.get("titulo") or recurso.titulo
    recurso.codigo = dados.get("codigo") or None
    recurso.descricao = dados.get("descricao") or None
    recurso.palavras_chave = dados.get("palavras_chave") or None
    if recurso.e_link:
        recurso.url = dados.get("url") or recurso.url
    recurso.data_revisao = dados.get("data_revisao") or recurso.data_revisao
    recurso.proxima_revisao = dados.get("proxima_revisao")
    recurso.atualizado_em = datetime.now()
    sessao.flush()
    registrar_log(
        sessao,
        "RECURSO_EDITADO",
        f"Dados de '{recurso.titulo}' atualizados.",
        autor.id if autor else None,
    )
    return recurso


def publicar_versao(sessao, recurso: Recurso, arquivo: dict, autor,
                    data_revisao=None, notas: str | None = None) -> Recurso:
    """Sobe uma nova versão do arquivo, preservando as anteriores."""
    nova = (recurso.versao_atual or 0) + 1
    sessao.add(
        RecursoArquivo(
            recurso_id=recurso.id,
            versao=nova,
            nome_arquivo=arquivo["nome"],
            content_type=arquivo.get("content_type"),
            tamanho=len(arquivo["conteudo"]),
            conteudo=arquivo["conteudo"],
            data_revisao=data_revisao,
            notas=notas or None,
            enviado_por_id=autor.id if autor else None,
        )
    )
    recurso.versao_atual = nova
    recurso.data_revisao = data_revisao or date.today()
    recurso.responsavel_id = autor.id if autor else recurso.responsavel_id
    recurso.atualizado_em = datetime.now()
    sessao.flush()
    registrar_log(
        sessao,
        "RECURSO_NOVA_VERSAO",
        f"'{recurso.titulo}' atualizado para a versão {nova}."
        + (f" Alterações: {notas}" if notas else ""),
        autor.id if autor else None,
    )
    sessao.refresh(recurso)
    return recurso


def arquivar_recurso(sessao, recurso: Recurso, autor, ativo: bool = False) -> Recurso:
    recurso.ativo = ativo
    recurso.atualizado_em = datetime.now()
    sessao.flush()
    registrar_log(
        sessao,
        "RECURSO_RESTAURADO" if ativo else "RECURSO_ARQUIVADO",
        f"'{recurso.titulo}'",
        autor.id if autor else None,
    )
    return recurso


def registrar_download(sessao, recurso: Recurso) -> None:
    recurso.downloads = (recurso.downloads or 0) + 1
    sessao.flush()


def buscar_recursos(
    sessao,
    termo: str = "",
    secao: str = "",
    grupo: str = "",
    periodo: str = "",
    ordem: str = "recentes",
    incluir_arquivados: bool = False,
) -> list[Recurso]:
    """Busca por texto livre, seção, tipo de arquivo e período de atualização."""
    consulta = select(Recurso)
    if not incluir_arquivados:
        consulta = consulta.where(Recurso.ativo.is_(True))
    if secao in SECOES_RECURSO:
        consulta = consulta.where(Recurso.secao == secao)
    itens = list(sessao.scalars(consulta).unique())

    if termo:
        alvo = sem_acento(termo.strip())
        itens = [r for r in itens if alvo in r.texto_busca()]
    if grupo:
        itens = [r for r in itens if r.grupo_arquivo == grupo]
    if periodo and periodo.isdigit():
        limite = date.today() - timedelta(days=int(periodo))
        itens = [r for r in itens if r.data_referencia >= limite]

    if ordem == "titulo":
        itens.sort(key=lambda r: r.titulo.lower())
    elif ordem == "baixados":
        itens.sort(key=lambda r: (-(r.downloads or 0), r.titulo.lower()))
    else:
        itens.sort(key=lambda r: r.data_referencia, reverse=True)
    return itens


def indicadores_recursos(sessao) -> dict:
    """Números da biblioteca: total, por seção e revisões vencidas."""
    itens = list(sessao.scalars(select(Recurso).where(Recurso.ativo.is_(True))).unique())
    por_secao = {chave: 0 for chave in SECOES_RECURSO}
    for r in itens:
        por_secao[r.secao] = por_secao.get(r.secao, 0) + 1
    return {
        "total": len(itens),
        "por_secao": por_secao,
        "links": sum(1 for r in itens if r.e_link),
        "arquivos": sum(1 for r in itens if not r.e_link),
        "downloads": sum(r.downloads or 0 for r in itens),
        "revisao_vencida": [r for r in itens if r.revisao_vencida],
        "grupos": sorted({r.grupo_arquivo for r in itens}),
    }


# =====================================================================
# Aprovadores por área (mantidos pela tela de Aprovações)
# =====================================================================


def aprovadores_da_area(sessao, area: str) -> list[Usuario]:
    """Pessoas cadastradas para aprovar por esta área."""
    vinculos = sessao.scalars(
        select(AreaAprovador)
        .where(AreaAprovador.area == area, AreaAprovador.ativo.is_(True))
        .order_by(AreaAprovador.id)
    ).unique()
    pessoas = [v.usuario for v in vinculos if v.usuario and v.usuario.ativo]
    # Compatibilidade: quem tem o papel da área e ainda não foi vinculado.
    for usuario in sessao.scalars(
        select(Usuario).where(Usuario.papel == area, Usuario.ativo.is_(True))
    ):
        if usuario.id not in {p.id for p in pessoas}:
            pessoas.append(usuario)
    return pessoas


def mapa_aprovadores(sessao) -> dict[str, list[Usuario]]:
    """Dicionário {área: [pessoas]} para a tela de gestão."""
    return {chave: aprovadores_da_area(sessao, chave) for chave, _ in FLUXO_APROVACAO}


def areas_gerenciaveis(sessao, usuario: Usuario) -> list[str]:
    """Áreas em que esta pessoa pode incluir ou remover aprovadores.

    Admin e Aprovador Final cuidam de todas. Um aprovador cuida apenas da
    própria área: quem responde por Meio Ambiente só mexe em Meio Ambiente.
    """
    if usuario is None or not usuario.ativo:
        return []
    if usuario.papel in ("ADMIN", "APROVADOR_FINAL"):
        return [chave for chave, _ in FLUXO_APROVACAO]
    return [a for a in areas_do_usuario(sessao, usuario) if a in dict(FLUXO_APROVACAO)]


def pode_gerenciar_area(sessao, usuario: Usuario, area: str) -> bool:
    return area in areas_gerenciaveis(sessao, usuario)


def _senha_provisoria() -> str:
    """Senha temporária legível, para ser ditada ou colada uma única vez."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # sem I e O, que se confundem com 1 e 0
    letras = "".join(secrets.choice(alfabeto) for _ in range(4))
    numeros = "".join(secrets.choice("23456789") for _ in range(4))
    return f"{letras}-{numeros}"


def definir_senha(sessao, usuario: Usuario, nova: str) -> Usuario:
    """Troca a senha e tira a marca de senha provisória."""
    usuario.senha_hash = gerar_hash(nova)
    usuario.precisa_trocar_senha = False
    sessao.flush()
    registrar_log(sessao, "SENHA_ALTERADA", "Senha alterada pelo próprio usuário.",
                  usuario.id)
    return usuario


def criar_aprovador(sessao, area: str, nome: str, email: str,
                    setor: str | None = None, autor=None) -> tuple[Usuario, str | None]:
    """Cadastra a pessoa e já a vincula à área.

    Devolve (usuário, senha_provisória). A senha vem preenchida só quando o
    usuário foi criado agora - para quem já tinha cadastro, nada muda na
    senha, apenas o vínculo com a área.
    """
    email = (email or "").strip().lower()
    nome = (nome or "").strip()
    if not nome or "@" not in email:
        raise ValueError("Informe o nome e um e-mail válido.")
    if area not in dict(FLUXO_APROVACAO):
        raise ValueError("Área de aprovação inválida.")

    existente = sessao.scalar(select(Usuario).where(Usuario.email == email))
    senha = None
    if existente:
        usuario = existente
        usuario.ativo = True
        if setor and not usuario.setor:
            usuario.setor = setor
    else:
        senha = _senha_provisoria()
        usuario = Usuario(
            nome=nome,
            email=email,
            senha_hash=gerar_hash(senha),
            papel=area,
            setor=setor or None,
            ativo=True,
            precisa_trocar_senha=True,
        )
        sessao.add(usuario)
        sessao.flush()
        registrar_log(
            sessao,
            "USUARIO_CRIADO",
            f"{usuario.nome} <{usuario.email}> cadastrado como aprovador de "
            f"{dict(FLUXO_APROVACAO).get(area, area)}.",
            autor.id if autor else None,
        )

    adicionar_aprovador(sessao, area, usuario, autor=autor)
    notificacoes.notificar_novo_aprovador(sessao, usuario, area, senha)
    return usuario, senha


def adicionar_aprovador(sessao, area: str, usuario: Usuario, autor=None) -> AreaAprovador:
    """Vincula uma pessoa a uma área (idempotente)."""
    vinculo = sessao.scalar(
        select(AreaAprovador).where(
            AreaAprovador.area == area, AreaAprovador.usuario_id == usuario.id
        )
    )
    if vinculo:
        vinculo.ativo = True
    else:
        vinculo = AreaAprovador(area=area, usuario_id=usuario.id, ativo=True)
        sessao.add(vinculo)
    # Quem só era solicitante passa a ter o papel da área, para os acessos.
    if usuario.papel == "SOLICITANTE":
        usuario.papel = area
    sessao.flush()
    registrar_log(
        sessao,
        "APROVADOR_ADICIONADO",
        f"{usuario.nome} passou a aprovar por {dict(FLUXO_APROVACAO).get(area, area)}.",
        autor.id if autor else None,
    )
    return vinculo


def remover_aprovador(sessao, area: str, usuario_id: int, autor=None) -> None:
    """Desvincula a pessoa da área (o usuário continua existindo)."""
    usuario = sessao.get(Usuario, usuario_id)
    vinculo = sessao.scalar(
        select(AreaAprovador).where(
            AreaAprovador.area == area, AreaAprovador.usuario_id == usuario_id
        )
    )
    if vinculo:
        vinculo.ativo = False
    if usuario and usuario.papel == area:
        # Sem o vínculo, o papel deixaria a pessoa aprovando assim mesmo.
        usuario.papel = "SOLICITANTE"
    sessao.flush()
    registrar_log(
        sessao,
        "APROVADOR_REMOVIDO",
        f"{usuario.nome if usuario else usuario_id} deixou de aprovar por "
        f"{dict(FLUXO_APROVACAO).get(area, area)}.",
        autor.id if autor else None,
    )


def sincronizar_aprovadores(sessao) -> int:
    """Cria os vínculos a partir dos papéis já cadastrados (uma vez)."""
    criados = 0
    for area, _ in FLUXO_APROVACAO:
        for usuario in sessao.scalars(
            select(Usuario).where(Usuario.papel == area, Usuario.ativo.is_(True))
        ):
            existente = sessao.scalar(
                select(AreaAprovador).where(
                    AreaAprovador.area == area, AreaAprovador.usuario_id == usuario.id
                )
            )
            if not existente:
                sessao.add(AreaAprovador(area=area, usuario_id=usuario.id, ativo=True))
                criados += 1
    sessao.flush()
    return criados


# =====================================================================
# Lembretes automáticos (a cada 7 dias enquanto a solicitação não fecha)
# =====================================================================

DIAS_LEMBRETE = 7


def solicitacoes_atrasadas(sessao, dias: int = DIAS_LEMBRETE) -> list[Produto]:
    """Solicitações abertas que passaram do prazo sem novo lembrete."""
    limite = datetime.now() - timedelta(days=dias)
    abertas = list(
        sessao.scalars(
            select(Produto).where(Produto.status.in_(STATUS_ABERTOS)).order_by(Produto.criado_em)
        ).unique()
    )
    pendentes = []
    for produto in abertas:
        referencia = produto.ultimo_lembrete_em or produto.criado_em
        if referencia and referencia <= limite:
            pendentes.append(produto)
    return pendentes


def enviar_lembretes(sessao, dias: int = DIAS_LEMBRETE) -> int:
    """Cobra os aprovadores pendentes e avisa o solicitante. Retorna quantas
    solicitações foram cobradas."""
    enviados = 0
    for produto in solicitacoes_atrasadas(sessao, dias):
        notificacoes.notificar_lembrete(sessao, produto)
        produto.ultimo_lembrete_em = datetime.now()
        registrar_log(
            sessao,
            "LEMBRETE_ENVIADO",
            "Cobrança automática das áreas pendentes: "
            + (", ".join(produto.areas_pendentes_labels) or "-"),
            None,
            produto.id,
        )
        enviados += 1
    sessao.flush()
    return enviados


# =====================================================================
# Kit Ambiental
# =====================================================================

from models import (  # noqa: E402  (agrupado aqui para isolar o módulo)
    PAPEIS_KIT,
    ItemKit,
    KitAmbiental,
    PontoColetaKit,
)


def pode_editar_kit(usuario) -> bool:
    return bool(usuario) and usuario.papel in PAPEIS_KIT


def listar_kits(sessao, incluir_inativos: bool = False) -> list[KitAmbiental]:
    consulta = select(KitAmbiental).order_by(KitAmbiental.ordem, KitAmbiental.codigo)
    if not incluir_inativos:
        consulta = consulta.where(KitAmbiental.ativo.is_(True))
    return list(sessao.scalars(consulta).unique())


def obter_kit(sessao, kit_id: int) -> KitAmbiental | None:
    return sessao.get(KitAmbiental, kit_id)


def criar_kit(sessao, dados: dict, autor=None) -> KitAmbiental:
    total = sessao.scalar(select(func.count(KitAmbiental.id))) or 0
    kit = KitAmbiental(
        codigo=(dados.get("codigo") or "").strip() or f"KIT-{total + 1}",
        nome=(dados.get("nome") or "").strip(),
        utilidade=(dados.get("utilidade") or "").strip() or None,
        quando_usar=(dados.get("quando_usar") or "").strip() or None,
        ordem=total + 1,
        atualizado_por_id=autor.id if autor else None,
    )
    sessao.add(kit)
    sessao.flush()
    registrar_log(
        sessao, "KIT_CRIADO", f"{kit.codigo} - {kit.nome}", autor.id if autor else None
    )
    return kit


def atualizar_kit(sessao, kit: KitAmbiental, dados: dict, autor=None) -> KitAmbiental:
    kit.codigo = (dados.get("codigo") or kit.codigo).strip()
    kit.nome = (dados.get("nome") or kit.nome).strip()
    kit.utilidade = (dados.get("utilidade") or "").strip() or None
    kit.quando_usar = (dados.get("quando_usar") or "").strip() or None
    kit.atualizado_em = datetime.now()
    kit.atualizado_por_id = autor.id if autor else kit.atualizado_por_id
    sessao.flush()
    registrar_log(
        sessao, "KIT_EDITADO", f"{kit.codigo} - {kit.nome}", autor.id if autor else None
    )
    return kit


def arquivar_kit(sessao, kit: KitAmbiental, autor=None, ativo: bool = False):
    kit.ativo = ativo
    kit.atualizado_em = datetime.now()
    sessao.flush()
    registrar_log(
        sessao,
        "KIT_RESTAURADO" if ativo else "KIT_ARQUIVADO",
        f"{kit.codigo} - {kit.nome}",
        autor.id if autor else None,
    )


# --------------------------------------------------------------- Itens
def adicionar_item(sessao, kit: KitAmbiental, dados: dict, foto: dict | None = None,
                   autor=None) -> ItemKit:
    proxima = max([i.ordem for i in kit.itens], default=0) + 1
    item = ItemKit(
        kit_id=kit.id,
        nome=(dados.get("nome") or "").strip(),
        utilidade=(dados.get("utilidade") or "").strip() or None,
        quantidade=(dados.get("quantidade") or "").strip() or None,
        unidade=(dados.get("unidade") or "").strip() or None,
        produto_id=dados.get("produto_id"),
        ordem=proxima,
    )
    if foto:
        item.foto = foto["conteudo"]
        item.foto_tipo = foto.get("content_type")
    sessao.add(item)
    sessao.flush()
    registrar_log(
        sessao, "KIT_ITEM_ADICIONADO", f"{kit.codigo}: {item.nome}",
        autor.id if autor else None,
    )
    return item


def atualizar_item(sessao, item: ItemKit, dados: dict, foto: dict | None = None,
                   autor=None) -> ItemKit:
    item.nome = (dados.get("nome") or item.nome).strip()
    item.utilidade = (dados.get("utilidade") or "").strip() or None
    item.quantidade = (dados.get("quantidade") or "").strip() or None
    item.unidade = (dados.get("unidade") or "").strip() or None
    item.produto_id = dados.get("produto_id")
    if foto:
        item.foto = foto["conteudo"]
        item.foto_tipo = foto.get("content_type")
    if dados.get("remover_foto"):
        item.foto = None
        item.foto_tipo = None
    sessao.flush()
    registrar_log(
        sessao, "KIT_ITEM_EDITADO", f"{item.kit.codigo}: {item.nome}",
        autor.id if autor else None,
    )
    return item


def remover_item(sessao, item: ItemKit, autor=None) -> None:
    nome, codigo = item.nome, item.kit.codigo
    sessao.delete(item)
    sessao.flush()
    registrar_log(
        sessao, "KIT_ITEM_REMOVIDO", f"{codigo}: {nome}", autor.id if autor else None
    )


# ------------------------------------------------------- Pontos de coleta
def adicionar_ponto(sessao, kit: KitAmbiental, dados: dict, autor=None) -> PontoColetaKit:
    ponto = PontoColetaKit(
        kit_id=kit.id,
        fabrica=(dados.get("fabrica") or "").strip(),
        local=(dados.get("local") or "").strip(),
        responsavel=(dados.get("responsavel") or "").strip() or None,
        ramal=(dados.get("ramal") or "").strip() or None,
        observacoes=(dados.get("observacoes") or "").strip() or None,
    )
    sessao.add(ponto)
    sessao.flush()
    registrar_log(
        sessao, "KIT_PONTO_ADICIONADO",
        f"{kit.codigo} em {ponto.fabrica} - {ponto.local}",
        autor.id if autor else None,
    )
    return ponto


def remover_ponto(sessao, ponto: PontoColetaKit, autor=None) -> None:
    descricao = f"{ponto.kit.codigo} em {ponto.fabrica} - {ponto.local}"
    sessao.delete(ponto)
    sessao.flush()
    registrar_log(
        sessao, "KIT_PONTO_REMOVIDO", descricao, autor.id if autor else None
    )


# ------------------------------------------------------------ Consultas
def pontos_por_fabrica(sessao, fabrica: str = "") -> dict[str, list[PontoColetaKit]]:
    """{fábrica: [pontos]} — a visão de 'onde encontrar um kit'."""
    consulta = select(PontoColetaKit).where(PontoColetaKit.ativo.is_(True))
    if fabrica:
        consulta = consulta.where(PontoColetaKit.fabrica == fabrica)
    pontos = list(
        sessao.scalars(consulta.order_by(PontoColetaKit.fabrica, PontoColetaKit.local)).unique()
    )
    agrupado: dict[str, list[PontoColetaKit]] = {}
    for ponto in pontos:
        if ponto.kit and not ponto.kit.ativo:
            continue
        agrupado.setdefault(ponto.fabrica, []).append(ponto)
    return agrupado


def resumo_kits(sessao) -> dict:
    kits = listar_kits(sessao)
    pontos = [p for k in kits for p in k.pontos_ativos]
    fabricas = []
    for ponto in pontos:
        if ponto.fabrica not in fabricas:
            fabricas.append(ponto.fabrica)
    return {
        "kits": len(kits),
        "pontos": len(pontos),
        "fabricas": sorted(fabricas),
        "itens": sum(len(k.itens_ativos) for k in kits),
        "sem_composicao": [k for k in kits if k.sem_composicao],
    }
