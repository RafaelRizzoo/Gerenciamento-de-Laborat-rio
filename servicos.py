"""Regras de negócio: criação de solicitacoes, fluxo de aprovacao e auditoria."""

from datetime import date, datetime, time

from sqlalchemy import func, select

import notificacoes
from models import (
    FLUXO_APROVACAO,
    ORGAOS_CONTROLADORES,
    STATUS,
    STATUS_ABERTOS,
    Aprovacao,
    ControleOrgao,
    Documento,
    LogAuditoria,
    Produto,
    ProdutoFabrica,
    ProdutoRisco,
    Usuario,
)


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


# --------------------------------------------------------- Solicitação
def criar_solicitacao(sessao, dados: dict, solicitante: Usuario, arquivos: list[dict]) -> Produto:
    """Cria o produto, as 4 etapas de aprovacao, anexa documentos e notifica."""
    produto = Produto(
        codigo_interno=dados.get("codigo_interno") or proximo_codigo(sessao),
        nome_comercial=dados["nome_comercial"],
        nome_tecnico=dados.get("nome_tecnico"),
        fabricante=dados["fabricante"],
        fornecedor=dados.get("fornecedor"),
        categoria=dados.get("categoria"),
        tipo_produto=dados.get("tipo_produto"),
        numero_cas=dados.get("numero_cas"),
        composicao=dados.get("composicao"),
        estado_fisico=dados.get("estado_fisico"),
        setor_solicitante=dados.get("setor_solicitante") or solicitante.setor,
        area_solicitante=dados.get("area_solicitante"),
        prazo_utilizacao=dados.get("prazo_utilizacao"),
        aplicacao=dados.get("aplicacao"),
        processo=dados.get("processo"),
        consumo_estimado=dados.get("consumo_estimado"),
        unidade=dados.get("unidade"),
        local_armazenamento=dados.get("local_armazenamento"),
        classificacao_ghs=dados.get("classificacao_ghs"),
        onu_numero=dados.get("onu_numero"),
        epi_recomendado=dados.get("epi_recomendado"),
        restricoes_uso=dados.get("restricoes_uso"),
        observacoes=dados.get("observacoes"),
        status="PENDENTE",
        etapa_atual=FLUXO_APROVACAO[0][0],
        solicitante_id=solicitante.id,
    )
    sessao.add(produto)
    sessao.flush()

    aplicar_fabricas(sessao, produto, dados.get("fabricas") or [])
    aplicar_controles(sessao, produto, dados.get("controles") or [])
    aplicar_riscos(sessao, produto, dados.get("riscos") or [])

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
    notificacoes.notificar_etapa_pendente(sessao, produto, produto.etapa_atual)
    return produto


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
        "nome_tecnico", "fornecedor", "categoria", "tipo_produto", "numero_cas",
        "composicao", "estado_fisico", "aplicacao", "processo",
        "area_solicitante", "prazo_utilizacao", "consumo_estimado", "unidade",
        "local_armazenamento", "classificacao_ghs", "onu_numero",
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

    if "fabricas" in dados:
        antes = set(produto.fabricas_nomes)
        aplicar_fabricas(sessao, produto, dados["fabricas"])
        if antes != set(produto.fabricas_nomes):
            alterados.append("fábricas")

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
    registrar_log(
        sessao,
        "FICHA_ATUALIZADA",
        "Campos alterados: " + (", ".join(alterados) if alterados else "nenhum"),
        usuario.id,
        produto.id,
    )
    return produto


def pode_decidir(usuario: Usuario, produto: Produto) -> bool:
    """O usuário é responsável pela etapa atual do produto?

    Vale para PENDENTE (ninguém decidiu ainda) e EM_ANALISE. Enquanto o
    produto está AGUARDANDO_CORRECAO a bola está com o solicitante.
    """
    if produto.status not in ("PENDENTE", "EM_ANALISE") or not produto.etapa_atual:
        return False
    return usuario.papel == produto.etapa_atual or usuario.papel == "ADMIN"


def pode_corrigir(usuario: Usuario, produto: Produto) -> bool:
    """Só o solicitante (ou o admin) reenvia uma solicitação devolvida."""
    if produto.status != "AGUARDANDO_CORRECAO":
        return False
    return usuario.id == produto.solicitante_id or usuario.papel == "ADMIN"


def registrar_decisao(
    sessao, produto: Produto, usuario: Usuario, decisao: str, parecer: str
) -> Produto:
    """Aprova ou reprova a etapa atual e avança (ou encerra) o fluxo."""
    etapa = produto.etapa_atual
    aprovacao = next((a for a in produto.aprovacoes if a.etapa == etapa), None)
    if aprovacao is None:
        raise ValueError("Etapa de aprovação não encontrada para este produto.")

    status_antes = produto.status
    aprovacao.decisao = decisao
    aprovacao.parecer = parecer or None
    aprovacao.aprovador_id = usuario.id
    aprovacao.decidido_em = datetime.now()

    if decisao == "REPROVADO":
        produto.status = "REPROVADO"
        produto.etapa_atual = None
        produto.concluido_em = datetime.now()
    else:
        etapas = [e for e, _ in FLUXO_APROVACAO]
        indice = etapas.index(etapa)
        if indice + 1 < len(etapas):
            produto.etapa_atual = etapas[indice + 1]
            produto.status = "EM_ANALISE"
        else:
            produto.status = "APROVADO"
            produto.etapa_atual = None
            produto.concluido_em = datetime.now()

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
    elif produto.etapa_atual:
        notificacoes.notificar_etapa_pendente(sessao, produto, produto.etapa_atual)
    return produto


def solicitar_correcao(sessao, produto: Produto, usuario: Usuario, motivo: str) -> Produto:
    """Devolve a solicitação ao solicitante sem reprovar.

    A etapa atual NÃO muda: quando o solicitante reenviar, a análise retoma
    exatamente com quem pediu a correção. As etapas já aprovadas continuam
    valendo.
    """
    status_antes = produto.status
    etapa = produto.etapa_atual
    produto.status = "AGUARDANDO_CORRECAO"
    produto.pendencia = motivo
    produto.atualizado_em = datetime.now()
    sessao.flush()

    registrar_log(
        sessao,
        "CORRECAO_SOLICITADA",
        f"{dict(FLUXO_APROVACAO).get(etapa, etapa)} solicitou correção: {motivo}",
        usuario.id,
        produto.id,
        status_anterior=status_antes,
        status_novo=produto.status,
    )
    notificacoes.notificar_correcao(sessao, produto, etapa, motivo)
    return produto


def reenviar_apos_correcao(sessao, produto: Produto, usuario: Usuario, resposta: str) -> Produto:
    """O solicitante devolve a solicitação para análise após corrigir."""
    status_antes = produto.status
    decididas = any(a.decisao != "PENDENTE" for a in produto.aprovacoes)
    produto.status = "EM_ANALISE" if decididas else "PENDENTE"
    produto.pendencia = None
    produto.atualizado_em = datetime.now()
    sessao.flush()

    registrar_log(
        sessao,
        "CORRECAO_REENVIADA",
        f"{usuario.nome} reenviou a solicitação após correção. {resposta}".strip(),
        usuario.id,
        produto.id,
        status_anterior=status_antes,
        status_novo=produto.status,
    )
    if produto.etapa_atual:
        notificacoes.notificar_reenvio(sessao, produto, produto.etapa_atual, resposta)
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
def contar_pendencias(sessao, usuario: Usuario) -> int:
    """Quantas solicitações aguardam a análise deste usuario."""
    if usuario.papel in [e for e, _ in FLUXO_APROVACAO]:
        return (
            sessao.scalar(
                select(func.count(Produto.id)).where(
                    Produto.status.in_(("PENDENTE", "EM_ANALISE")),
                    Produto.etapa_atual == usuario.papel,
                )
            )
            or 0
        )
    if usuario.papel == "ADMIN":
        return (
            sessao.scalar(
                select(func.count(Produto.id)).where(
                    Produto.status.in_(("PENDENTE", "EM_ANALISE"))
                )
            )
            or 0
        )
    return 0


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
    por_etapa = sessao.execute(
        select(Produto.etapa_atual, func.count(Produto.id))
        .where(Produto.status.in_(("PENDENTE", "EM_ANALISE")))
        .group_by(Produto.etapa_atual)
    ).all()
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
            (dict(FLUXO_APROVACAO).get(e, e or "-"), n) for e, n in por_etapa
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
        )
    if status:
        consulta = consulta.where(Produto.status == status)
    if categoria:
        consulta = consulta.where(Produto.categoria == categoria)
    if fabrica:
        consulta = consulta.where(Produto.fabricas.any(ProdutoFabrica.fabrica == fabrica))
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
