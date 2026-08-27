"""Regras de negócio: criação de solicitacoes, fluxo de aprovacao e auditoria."""

from datetime import datetime

from sqlalchemy import func, select

import notificacoes
from models import (
    FLUXO_APROVACAO,
    Aprovacao,
    Documento,
    LogAuditoria,
    Produto,
    Usuario,
)


# ------------------------------------------------------------ Auditoria
def registrar_log(sessao, acao: str, detalhe: str = "", usuario_id=None, produto_id=None):
    sessao.add(
        LogAuditoria(
            acao=acao, detalhe=detalhe, usuario_id=usuario_id, produto_id=produto_id
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
        fabricante=dados["fabricante"],
        fornecedor=dados.get("fornecedor"),
        categoria=dados.get("categoria"),
        numero_cas=dados.get("numero_cas"),
        composicao=dados.get("composicao"),
        estado_fisico=dados.get("estado_fisico"),
        setor_solicitante=dados.get("setor_solicitante") or solicitante.setor,
        aplicacao=dados.get("aplicacao"),
        consumo_estimado=dados.get("consumo_estimado"),
        unidade=dados.get("unidade"),
        local_armazenamento=dados.get("local_armazenamento"),
        classificacao_ghs=dados.get("classificacao_ghs"),
        onu_numero=dados.get("onu_numero"),
        epi_recomendado=dados.get("epi_recomendado"),
        observacoes=dados.get("observacoes"),
        status="EM_ANALISE",
        etapa_atual=FLUXO_APROVACAO[0][0],
        solicitante_id=solicitante.id,
    )
    sessao.add(produto)
    sessao.flush()

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
    )
    sessao.refresh(produto)
    notificacoes.notificar_etapa_pendente(sessao, produto, produto.etapa_atual)
    return produto


def pode_decidir(usuario: Usuario, produto: Produto) -> bool:
    """O usuário é responsável pela etapa atual do produto?"""
    if produto.status != "EM_ANALISE" or not produto.etapa_atual:
        return False
    return usuario.papel == produto.etapa_atual or usuario.papel == "ADMIN"


def registrar_decisao(
    sessao, produto: Produto, usuario: Usuario, decisao: str, parecer: str
) -> Produto:
    """Aprova ou reprova a etapa atual e avança (ou encerra) o fluxo."""
    etapa = produto.etapa_atual
    aprovacao = next((a for a in produto.aprovacoes if a.etapa == etapa), None)
    if aprovacao is None:
        raise ValueError("Etapa de aprovação não encontrada para este produto.")

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
        else:
            produto.status = "APROVADO"
            produto.etapa_atual = None
            produto.concluido_em = datetime.now()

    produto.atualizado_em = datetime.now()
    sessao.flush()

    registrar_log(
        sessao,
        f"ETAPA_{decisao}",
        f"Etapa {dict(FLUXO_APROVACAO).get(etapa, etapa)} - {decisao.lower()} por {usuario.nome}."
        + (f" Parecer: {parecer}" if parecer else ""),
        usuario.id,
        produto.id,
    )

    notificacoes.notificar_decisao(sessao, produto, etapa, decisao, parecer)
    if produto.status in ("APROVADO", "REPROVADO"):
        notificacoes.notificar_conclusao(sessao, produto)
    elif produto.etapa_atual:
        notificacoes.notificar_etapa_pendente(sessao, produto, produto.etapa_atual)
    return produto


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
                    Produto.status == "EM_ANALISE", Produto.etapa_atual == usuario.papel
                )
            )
            or 0
        )
    if usuario.papel == "ADMIN":
        return (
            sessao.scalar(
                select(func.count(Produto.id)).where(Produto.status == "EM_ANALISE")
            )
            or 0
        )
    return 0


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
        .where(Produto.status == "EM_ANALISE")
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
    limite: int | None = 200,
):
    consulta = select(Produto)
    if termo:
        like = f"%{termo.strip()}%"
        consulta = consulta.where(
            Produto.nome_comercial.like(like)
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
    if somente_aprovados:
        consulta = consulta.where(Produto.status == "APROVADO")
    if somente_com_fds:
        consulta = consulta.where(Produto.documentos.any(Documento.tipo == "FDS"))
    consulta = consulta.order_by(Produto.atualizado_em.desc())
    if limite:
        consulta = consulta.limit(limite)
    return list(sessao.scalars(consulta).unique())
