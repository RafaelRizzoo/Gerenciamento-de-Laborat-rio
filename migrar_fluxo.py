"""Migração do banco existente para o novo fluxo de aprovação.

O que mudou:
  * "Saúde e Segurança" virou DUAS áreas: Saúde e Segurança.
  * As áreas não têm ordem: analisam em paralelo. Só o Aprovador Final é
    fixo, e entra depois das demais.
  * Quem aprova cada área passou a ficar na tabela `area_aprovadores`,
    editável na tela de Aprovações.
  * "Fábrica" virou "Unidade", e a lista antiga, que misturava unidade com
    área, foi separada: COSE e MC SCON2 eram áreas, não unidades.
  * Tipo de produto, forma de aplicação e prazo de utilização mudaram de
    grafia e de conteúdo.
  * O número CAS, que era um só por produto, virou uma lista.

Este script ajusta os dados já cadastrados. Pode ser rodado mais de uma
vez sem efeito colateral.

Uso:
    .venv\\Scripts\\python.exe migrar_fluxo.py
"""

from sqlalchemy import select

import servicos
from database import criar_tabelas, db_session
from models import (
    AREAS_APROVACAO,
    ETAPA_FINAL,
    UNIDADES,
    Aprovacao,
    PontoColetaKit,
    Produto,
    ProdutoCAS,
    ProdutoFabrica,
    Usuario,
)

# De "fábrica" para "unidade".
#
# A lista antiga misturava os dois conceitos: "COSE" e "MC SCON2" são áreas
# dentro de uma unidade, não unidades. Aqui cada valor antigo vai para a
# unidade a que pertence de fato.
UNIDADE_ANTIGA = {
    "Pinda Tubos": "Pinda",
    "COSE": "Pinda",
    "MC SCON2": "MC",
    "MC TCHB": "MC",
    "RDO": "RDO",
}


# Vocabulários que mudaram de grafia ou de conteúdo. Chave = valor antigo,
# valor = valor novo. O que não estiver aqui fica como está e aparece na tela
# marcado como "(valor atual)".
VOCABULARIO_ANTIGO = {
    "tipo_produto": {
        "Lubrificante": "Óleo Lubrificante",
        "Hidráulico": "Óleo Hidráulico",
    },
    "forma_aplicacao": {
        "Manual (pincel, pano, rolo)": "Aplicação Manual (Pano, Pincel ou Rolo)",
        "Pulverização / spray": "Pulverização / Spray",
        "Dosagem automática": "Dosagem Automática",
        "Circulação em sistema fechado": "Circulação em Sistema Fechado",
        "Mistura em tanque": "Mistura ou Diluição em Tanque",
        "Aplicação por terceiro": "Aplicação por Terceiros",
    },
    "prazo_utilizacao": {
        "Uso único / pontual": "Uso Único",
        "Até 6 meses": "Até 6 Meses",
        "De 6 a 12 meses": "Até 1 Ano",
        "De 1 a 2 anos": "Até 2 Anos",
        "Acima de 2 anos": "Acima de 2 Anos",
        "Uso contínuo (sem prazo definido)": "Uso Contínuo",
    },
    "estado_fisico": {
        # "Pasta / Gel" e "Aerossol" saíram da lista e não têm equivalente:
        # ficam como estão, visíveis como "(valor atual)" até alguém editar.
    },
}


def _converter_vocabulario(s) -> None:
    """Atualiza os valores de tipo, forma de aplicação e prazo."""
    trocas = 0
    for produto in s.scalars(select(Produto)):
        for campo, mapa in VOCABULARIO_ANTIGO.items():
            atual = getattr(produto, campo, None)
            novo = mapa.get(atual)
            if novo and novo != atual:
                setattr(produto, campo, novo)
                trocas += 1
    s.flush()
    if trocas:
        print(f"{trocas} valor(es) de lista convertidos para a grafia nova.")


def _converter_cas(s) -> None:
    """Move o CAS único do produto para a tabela de vários CAS."""
    criados = 0
    for produto in s.scalars(select(Produto)):
        if not produto.numero_cas or produto.cas:
            continue
        for numero in [n.strip() for n in produto.numero_cas.split(",")]:
            if numero:
                s.add(ProdutoCAS(produto_id=produto.id, numero=numero))
                criados += 1
    s.flush()
    if criados:
        print(f"{criados} número(s) CAS movidos para a lista do produto.")


def _converter_unidades(s) -> None:
    """Troca os nomes antigos de fábrica pelos nomes de unidade."""
    # Produtos. Um produto autorizado em "Pinda Tubos" E em "COSE" viraria
    # dois registros "Pinda" iguais, o que a chave única não aceita: o
    # segundo é descartado.
    vistos: set[tuple[int, str]] = set()
    trocados = descartados = 0
    for vinculo in list(s.scalars(select(ProdutoFabrica).order_by(ProdutoFabrica.id))):
        nova = UNIDADE_ANTIGA.get(vinculo.fabrica, vinculo.fabrica)
        chave = (vinculo.produto_id, nova)
        if chave in vistos:
            s.delete(vinculo)
            descartados += 1
            continue
        vistos.add(chave)
        if nova != vinculo.fabrica:
            vinculo.fabrica = nova
            trocados += 1
    s.flush()
    if trocados:
        print(f"{trocados} vínculo(s) de produto convertidos para a unidade nova.")
    if descartados:
        print(f"{descartados} vínculo(s) repetidos removidos após a conversão.")

    # Pontos de coleta dos kits ambientais.
    pontos = 0
    for ponto in s.scalars(select(PontoColetaKit)):
        nova = UNIDADE_ANTIGA.get(ponto.fabrica, ponto.fabrica)
        if nova != ponto.fabrica:
            ponto.fabrica = nova
            pontos += 1
    s.flush()
    if pontos:
        print(f"{pontos} ponto(s) de coleta convertidos para a unidade nova.")

    fora = sorted(
        {v.fabrica for v in s.scalars(select(ProdutoFabrica))
         if v.fabrica not in UNIDADES}
        | {p.fabrica for p in s.scalars(select(PontoColetaKit))
           if p.fabrica not in UNIDADES}
    )
    if fora:
        print("  [AVISO] unidades fora da lista nova, revise na mão: " + ", ".join(fora))


def executar() -> None:
    criar_tabelas()  # cria area_aprovadores e a coluna de lembrete
    with db_session() as s:
        # 1) papel dos usuários -----------------------------------------
        antigos = list(s.scalars(select(Usuario).where(Usuario.papel == "SAUDE_SEGURANCA")))
        for usuario in antigos:
            usuario.papel = "SAUDE"
        if antigos:
            print(f"{len(antigos)} usuário(s) de 'Saúde e Segurança' movidos para 'Saúde'.")
            print("  Revise em Aprovações quem deve responder por 'Segurança'.")

        # 2) etapas já gravadas -----------------------------------------
        convertidas = 0
        criadas = 0
        for aprovacao in list(s.scalars(select(Aprovacao).where(
            Aprovacao.etapa == "SAUDE_SEGURANCA"
        ))):
            aprovacao.etapa = "SAUDE"
            convertidas += 1
            # A antiga etapa valia pelas duas áreas: replica a decisão.
            gemea = s.scalar(
                select(Aprovacao).where(
                    Aprovacao.produto_id == aprovacao.produto_id,
                    Aprovacao.etapa == "SEGURANCA",
                )
            )
            if not gemea:
                s.add(
                    Aprovacao(
                        produto_id=aprovacao.produto_id,
                        etapa="SEGURANCA",
                        ordem=aprovacao.ordem,
                        decisao=aprovacao.decisao,
                        parecer=aprovacao.parecer,
                        aprovador_id=aprovacao.aprovador_id,
                        decidido_em=aprovacao.decidido_em,
                    )
                )
                criadas += 1
        s.flush()
        if convertidas:
            print(f"{convertidas} etapa(s) convertidas para 'Saúde' e "
                  f"{criadas} etapa(s) de 'Segurança' criadas.")

        # 3) garante uma etapa por área em cada solicitação --------------
        faltantes = 0
        esperadas = [chave for chave, _ in AREAS_APROVACAO] + [ETAPA_FINAL]
        for produto in s.scalars(select(Produto)):
            existentes = {a.etapa for a in produto.aprovacoes}
            for ordem, etapa in enumerate(esperadas, start=1):
                if etapa not in existentes:
                    s.add(
                        Aprovacao(
                            produto_id=produto.id, etapa=etapa,
                            ordem=ordem, decisao="PENDENTE",
                        )
                    )
                    faltantes += 1
        s.flush()
        if faltantes:
            print(f"{faltantes} etapa(s) que faltavam foram criadas.")

        # 4) aprovadores por área ---------------------------------------
        vinculos = servicos.sincronizar_aprovadores(s)
        if vinculos:
            print(f"{vinculos} vínculo(s) de aprovador criados a partir dos papéis.")

        # 5) recalcula de quem é a vez -----------------------------------
        ajustados = 0
        for produto in s.scalars(select(Produto)):
            s.refresh(produto)
            if not produto.aberta:
                novo = None
            else:
                novo = ETAPA_FINAL if produto.areas_concluidas else None
            if produto.etapa_atual != novo:
                produto.etapa_atual = novo
                ajustados += 1
        s.flush()
        if ajustados:
            print(f"{ajustados} solicitação(ões) tiveram a etapa recalculada.")

        # 6) fábrica -> unidade ------------------------------------------
        _converter_unidades(s)

        # 7) vocabulários e números CAS -----------------------------------
        _converter_vocabulario(s)
        _converter_cas(s)

    print("\nMigração concluída.")
    print("Confira em Aprovações > Aprovadores por área quem responde por cada uma.")


if __name__ == "__main__":
    executar()
