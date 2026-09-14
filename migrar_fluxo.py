"""Migração do banco existente para o novo fluxo de aprovação.

O que mudou:
  * "Saúde e Segurança" virou DUAS áreas: Saúde e Segurança.
  * As áreas não têm ordem: analisam em paralelo. Só o Aprovador Final é
    fixo, e entra depois das demais.
  * Quem aprova cada área passou a ficar na tabela `area_aprovadores`,
    editável na tela de Aprovações.

Este script ajusta os dados já cadastrados. Pode ser rodado mais de uma
vez sem efeito colateral.

Uso:
    .venv\\Scripts\\python.exe migrar_fluxo.py
"""

from sqlalchemy import select

import servicos
from database import criar_tabelas, db_session
from models import AREAS_APROVACAO, ETAPA_FINAL, Aprovacao, Produto, Usuario


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

    print("\nMigração concluída.")
    print("Confira em Aprovações > Aprovadores por área quem responde por cada uma.")


if __name__ == "__main__":
    executar()
