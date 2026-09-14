"""Envio de notificacoes por e-mail.

Se o SMTP não estiver configurado no .env, a mensagem NAO e' descartada:
ela fica gravada na tabela `notificacoes` (visivel em /notificacoes),
que funciona como caixa de saida para conferencia durante os testes.
"""

import smtplib
from datetime import datetime
from email.message import EmailMessage

import config
from models import (
    AREAS_APROVACAO,
    ETAPA_FINAL,
    FLUXO_APROVACAO,
    AreaAprovador,
    Notificacao,
    Produto,
    Usuario,
)


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


def destinatarios_da_area(sessao, area: str) -> list[Usuario]:
    """Quem recebe e-mail por uma área.

    Usa a lista mantida na tela de Aprovações e, por compatibilidade,
    também quem tem o papel da área no cadastro de usuários.
    """
    pessoas: dict[int, Usuario] = {}
    vinculos = sessao.query(AreaAprovador).filter(
        AreaAprovador.area == area, AreaAprovador.ativo.is_(True)
    ).all()
    for vinculo in vinculos:
        if vinculo.usuario and vinculo.usuario.ativo:
            pessoas[vinculo.usuario.id] = vinculo.usuario
    for usuario in sessao.query(Usuario).filter(
        Usuario.papel == area, Usuario.ativo.is_(True)
    ).all():
        pessoas[usuario.id] = usuario
    return list(pessoas.values())


def _resumo_produto(produto: Produto) -> str:
    return (
        f"Produto:     {produto.nome_comercial}\n"
        f"Código:      {produto.codigo_interno}\n"
        f"Fabricante:  {produto.fabricante}\n"
        f"Solicitante: {produto.solicitante.nome}\n"
    )


def notificar_etapa_pendente(sessao, produto: Produto, etapa: str):
    """Avisa os responsaveis pela etapa que existe uma análise pendente."""
    rotulo = dict(FLUXO_APROVACAO).get(etapa, etapa)
    responsaveis = destinatarios_da_area(sessao, etapa)
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


def notificar_envio(sessao, produto: Produto):
    """Solicitação enviada: avisa TODAS as áreas de uma vez (elas analisam
    em paralelo) e confirma o envio para o solicitante."""
    for area, _rotulo in AREAS_APROVACAO:
        notificar_etapa_pendente(sessao, produto, area)

    assunto = f"[Produtos Químicos] Solicitação enviada - {produto.nome_comercial}"
    areas = ", ".join(rotulo for _, rotulo in AREAS_APROVACAO)
    corpo = (
        f"Olá {produto.solicitante.nome},\n\n"
        f"Sua solicitação foi enviada para aprovação e já está com as áreas "
        f"{areas}, que analisam em paralelo. Concluídas as quatro, a "
        f"solicitação segue para o Aprovador Final.\n\n"
        f"{_resumo_produto(produto)}\n"
        f"Acompanhe por aqui: {_url_produto(produto)}\n\n"
        f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
    )
    notificar(sessao, produto.solicitante.email, assunto, corpo, produto.id)


def notificar_lembrete(sessao, produto: Produto):
    """Cobrança periódica: vai para as áreas que ainda não deram parecer e
    para o solicitante, com uma cópia do que está faltando."""
    pendentes = [a for a in produto.areas_pendentes if produto.aguarda(a)]
    if not pendentes:
        pendentes = produto.areas_pendentes
    faltando = ", ".join(dict(FLUXO_APROVACAO).get(a, a) for a in pendentes) or "-"
    dias = (datetime.now() - produto.criado_em).days if produto.criado_em else 0

    assunto = f"[Produtos Químicos] Lembrete: análise pendente há {dias} dia(s) - {produto.nome_comercial}"
    for area in pendentes:
        rotulo = dict(FLUXO_APROVACAO).get(area, area)
        for usuario in destinatarios_da_area(sessao, area):
            corpo = (
                f"Olá {usuario.nome},\n\n"
                f"A solicitação abaixo está aguardando o parecer de {rotulo} há "
                f"{dias} dia(s).\n\n"
                f"{_resumo_produto(produto)}"
                f"Situação:    {produto.status_label}\n"
                f"Aguardando:  {faltando}\n\n"
                f"Registre seu parecer em: {_url_produto(produto)}\n\n"
                f"Este lembrete se repete a cada 7 dias enquanto a solicitação "
                f"não for concluída.\n\n"
                f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
            )
            notificar(sessao, usuario.email, assunto, corpo, produto.id)

    corpo_solicitante = (
        f"Olá {produto.solicitante.nome},\n\n"
        f"Sua solicitação do produto {produto.nome_comercial} "
        f"({produto.codigo_interno}) continua em análise há {dias} dia(s).\n\n"
        f"Aguardando: {faltando}\n"
        f"Situação:   {produto.status_label}\n\n"
        f"As áreas pendentes foram cobradas automaticamente nesta data.\n"
        f"Acompanhe por aqui: {_url_produto(produto)}\n\n"
        f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
    )
    notificar(sessao, produto.solicitante.email, assunto, corpo_solicitante, produto.id)


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


def notificar_reenvio(sessao, produto: Produto, resposta: str):
    """Avisa as áreas que ainda faltam de que a correção foi reenviada."""
    assunto = f"[Produtos Químicos] Correção reenviada - {produto.nome_comercial}"
    pendentes = [a for a in produto.areas_pendentes if produto.aguarda(a)]
    for area in pendentes:
        rotulo = dict(FLUXO_APROVACAO).get(area, area)
        for usuario in destinatarios_da_area(sessao, area):
            corpo = (
                f"Olá {usuario.nome},\n\n"
                f"{produto.solicitante.nome} reenviou a solicitação do produto "
                f"{produto.nome_comercial} ({produto.codigo_interno}) após a "
                f"correção solicitada.\n\n"
                f"Observação do solicitante: {resposta or '(sem observação)'}\n\n"
                f"A análise de {rotulo} está liberada: {_url_produto(produto)}\n\n"
                f"-- {config.APP_EMPRESA} | {config.APP_NOME}"
            )
            notificar(sessao, usuario.email, assunto, corpo, produto.id)


def notificar_documento(sessao, produto: Produto, nome_arquivo: str, tipo_label: str):
    """Avisa quem ainda precisa analisar que a documentação foi atualizada."""
    pendentes = [a for a in produto.areas_pendentes if produto.aguarda(a)]
    if not pendentes:
        return
    assunto = f"[Produtos Químicos] Documentação atualizada - {produto.nome_comercial}"
    for area in pendentes:
        rotulo = dict(FLUXO_APROVACAO).get(area, area)
        for usuario in destinatarios_da_area(sessao, area):
            corpo = (
                f"Olá {usuario.nome},\n\n"
                f"Um novo documento foi anexado à solicitação do produto "
                f"{produto.nome_comercial} ({produto.codigo_interno}), que "
                f"aguarda o parecer de {rotulo}.\n\n"
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
