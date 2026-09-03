"""Envio de notificacoes por e-mail.

Se o SMTP não estiver configurado no .env, a mensagem NAO e' descartada:
ela fica gravada na tabela `notificacoes` (visivel em /notificacoes),
que funciona como caixa de saida para conferencia durante os testes.
"""

import smtplib
from email.message import EmailMessage

import config
from models import FLUXO_APROVACAO, Notificacao, Produto, Usuario


def _enviar_smtp(destinatario: str, assunto: str, corpo: str) -> str | None:
    """Retorna None em caso de sucesso ou a mensagem de erro."""
    if not config.SMTP_ATIVO:
        return "SMTP não configurado (.env) - mensagem apenas registrada."
    try:
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = config.SMTP_FROM
        msg["To"] = destinatario
        msg.set_content(corpo)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as servidor:
            if config.SMTP_TLS:
                servidor.starttls()
            if config.SMTP_USER:
                servidor.login(config.SMTP_USER, config.SMTP_PASSWORD)
            servidor.send_message(msg)
        return None
    except Exception as exc:  # pragma: no cover
        return f"{type(exc).__name__}: {exc}"


def notificar(sessao, destinatario: str, assunto: str, corpo: str, produto_id: int | None = None):
    """Registra e tenta enviar uma notificacao."""
    if not destinatario:
        return None
    erro = _enviar_smtp(destinatario, assunto, corpo)
    registro = Notificacao(
        produto_id=produto_id,
        destinatario=destinatario,
        assunto=assunto,
        corpo=corpo,
        enviado=erro is None,
        erro=erro,
    )
    sessao.add(registro)
    return registro


def _url_produto(produto: Produto) -> str:
    return f"/produtos/{produto.id}"


def notificar_etapa_pendente(sessao, produto: Produto, etapa: str):
    """Avisa os responsaveis pela etapa que existe uma análise pendente."""
    rotulo = dict(FLUXO_APROVACAO).get(etapa, etapa)
    responsaveis = (
        sessao.query(Usuario).filter(Usuario.papel == etapa, Usuario.ativo.is_(True)).all()
    )
    assunto = f"[Produtos Químicos] Análise pendente - {produto.nome_comercial}"
    for usuario in responsaveis:
        corpo = (
            f"Olá {usuario.nome},\n\n"
            f"Existe uma solicitação de cadastro de produto químico aguardando a análise "
            f"de {rotulo}.\n\n"
            f"Produto:   {produto.nome_comercial}\n"
            f"Código:    {produto.codigo_interno}\n"
            f"Fabricante:{produto.fabricante}\n"
            f"Solicitante: {produto.solicitante.nome}\n\n"
            f"Acesse o sistema para registrar seu parecer: {_url_produto(produto)}\n\n"
            f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
        )
        notificar(sessao, usuario.email, assunto, corpo, produto.id)


def notificar_decisao(sessao, produto: Produto, etapa: str, decisao: str, parecer: str | None):
    """Avisa o solicitante sobre a decisao de uma etapa."""
    rotulo = dict(FLUXO_APROVACAO).get(etapa, etapa)
    palavra = "aprovada" if decisao == "APROVADO" else "reprovada"
    assunto = f"[Produtos Químicos] Etapa {rotulo} {palavra} - {produto.nome_comercial}"
    corpo = (
        f"Olá {produto.solicitante.nome},\n\n"
        f"A etapa '{rotulo}' da solicitação do produto {produto.nome_comercial} "
        f"({produto.codigo_interno}) foi {palavra}.\n\n"
        f"Parecer: {parecer or '(sem parecer registrado)'}\n"
        f"Situação atual da solicitação: {produto.status_label}\n\n"
        f"Detalhes: {_url_produto(produto)}\n\n"
        f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
    )
    notificar(sessao, produto.solicitante.email, assunto, corpo, produto.id)


def notificar_correcao(sessao, produto: Produto, etapa: str, motivo: str):
    """Avisa o solicitante de que a solicitação voltou para correção."""
    rotulo = dict(FLUXO_APROVACAO).get(etapa, etapa)
    assunto = (
        f"[Produtos Químicos] Correção solicitada - {produto.nome_comercial}"
    )
    corpo = (
        f"Olá {produto.solicitante.nome},\n\n"
        f"A área de {rotulo} solicitou uma correção na solicitação do produto "
        f"{produto.nome_comercial} ({produto.codigo_interno}) antes de dar o parecer.\n\n"
        f"O que precisa ser corrigido:\n{motivo}\n\n"
        f"A solicitação NÃO foi reprovada. Depois de corrigir, reenvie pelo sistema: "
        f"a análise retoma com {rotulo}, e as etapas já aprovadas continuam valendo.\n\n"
        f"Acesse: {_url_produto(produto)}\n\n"
        f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
    )
    notificar(sessao, produto.solicitante.email, assunto, corpo, produto.id)


def notificar_reenvio(sessao, produto: Produto, etapa: str, resposta: str):
    """Avisa os responsáveis pela etapa de que a correção foi reenviada."""
    rotulo = dict(FLUXO_APROVACAO).get(etapa, etapa)
    responsaveis = (
        sessao.query(Usuario).filter(Usuario.papel == etapa, Usuario.ativo.is_(True)).all()
    )
    assunto = f"[Produtos Químicos] Correção reenviada - {produto.nome_comercial}"
    for usuario in responsaveis:
        corpo = (
            f"Olá {usuario.nome},\n\n"
            f"{produto.solicitante.nome} reenviou a solicitação do produto "
            f"{produto.nome_comercial} ({produto.codigo_interno}) após a correção "
            f"pedida por {rotulo}.\n\n"
            f"Observação do solicitante: {resposta or '(sem observação)'}\n\n"
            f"A análise está de volta com você: {_url_produto(produto)}\n\n"
            f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
        )
        notificar(sessao, usuario.email, assunto, corpo, produto.id)


def notificar_documento(sessao, produto: Produto, nome_arquivo: str, tipo_label: str):
    """Avisa a etapa atual de que a documentação do produto foi atualizada."""
    etapa = produto.etapa_atual
    if not etapa:
        return
    rotulo = dict(FLUXO_APROVACAO).get(etapa, etapa)
    responsaveis = (
        sessao.query(Usuario).filter(Usuario.papel == etapa, Usuario.ativo.is_(True)).all()
    )
    assunto = f"[Produtos Químicos] Documentação atualizada - {produto.nome_comercial}"
    for usuario in responsaveis:
        corpo = (
            f"Olá {usuario.nome},\n\n"
            f"Um novo documento foi anexado à solicitação do produto "
            f"{produto.nome_comercial} ({produto.codigo_interno}), que está "
            f"na etapa de {rotulo}.\n\n"
            f"Documento: {tipo_label} - {nome_arquivo}\n\n"
            f"Consulte antes de dar o parecer: {_url_produto(produto)}\n\n"
            f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
        )
        notificar(sessao, usuario.email, assunto, corpo, produto.id)


def notificar_conclusao(sessao, produto: Produto):
    """Avisa o solicitante que o fluxo terminou."""
    assunto = (
        f"[Produtos Químicos] Produto {produto.status_label.upper()} - {produto.nome_comercial}"
    )
    corpo = (
        f"Olá {produto.solicitante.nome},\n\n"
        f"O fluxo de aprovação do produto {produto.nome_comercial} "
        f"({produto.codigo_interno}) foi concluído com a situação: {produto.status_label}.\n\n"
        f"Detalhes e pareceres: {_url_produto(produto)}\n\n"
        f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
    )
    notificar(sessao, produto.solicitante.email, assunto, corpo, produto.id)
