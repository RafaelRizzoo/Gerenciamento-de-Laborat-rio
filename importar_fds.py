"""Importa um lote de FDS (um .zip de PDFs) como produtos JÁ APROVADOS.

Serve para carregar FDS que foram aprovadas fora do sistema. Cada PDF passa
pela leitura automática (extracao.py) e vira um produto com:

  - a unidade, a área e o solicitante informados na linha de comando;
  - a aprovação registrada como "aprovada fora do sistema" (nenhum parecer
    de área é inventado);
  - a validade de 3 anos contando da data da importação;
  - nenhum e-mail enviado às áreas.

Por padrão só SIMULA: lista o que seria cadastrado e não grava nada. Para
gravar, acrescente --gravar (antes, o banco SQLite é copiado como backup).

Uso:
    .venv\\Scripts\\python.exe importar_fds.py "zip FDS.zip" ^
        --solicitante "Nome Sobrenome" --email nome@empresa.com ^
        --unidade Pinda --area "Manutenção - ETE"
    (acrescente --gravar para valer)
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import config
import extracao
import notificacoes
import servicos
from database import criar_tabelas, db_session
from models import AREAS_POR_UNIDADE, UNIDADES, ETAPA_FINAL  # noqa: F401


def _ler_zip(caminho: Path) -> list[tuple[str, bytes]]:
    """PDFs do zip, lidos direto da memória (nada é extraído para o disco)."""
    pdfs = []
    with zipfile.ZipFile(caminho) as z:
        for info in z.infolist():
            nome = info.filename
            if info.is_dir() or not nome.lower().endswith(".pdf"):
                continue
            conteudo = z.read(info)
            pdfs.append((Path(nome).name, conteudo))
    return pdfs


def _dados_do_produto(extraido: dict, unidade: str, area: str, nome_arquivo: str) -> dict:
    cas = extraido.get("numero_cas") or ""
    hoje = datetime.now().strftime("%d/%m/%Y")
    return {
        "nome_comercial": extraido.get("nome_comercial") or "",
        "fabricante": extraido.get("fabricante") or "",
        "tipo_produto": extraido.get("tipo_produto") or None,
        "numero_cas": cas or None,
        "cas": [cas] if cas else [],
        "estado_fisico": extraido.get("estado_fisico") or None,
        "aplicacao": extraido.get("aplicacao") or None,
        "classificacao_ghs": extraido.get("classificacao_ghs") or None,
        "onu_numero": extraido.get("onu_numero") or None,
        "inflamavel": extraido.get("inflamavel") or None,
        "cancerigeno": extraido.get("cancerigeno") or None,
        "ponto_fulgor": extraido.get("ponto_fulgor") or None,
        "riscos": extraido.get("riscos") or [],
        "unidade_solicitante": unidade,
        "area_solicitante": area,
        "setor_solicitante": area,
        "fabricas": [unidade],
        "observacoes": (
            f"Importado em {hoje} do lote de FDS aprovadas fora do sistema "
            f"(arquivo: {nome_arquivo}). Campos que a FDS não traz ficam em "
            "branco para completar depois."
        ),
    }


def executar(args) -> int:
    caminho = Path(args.zip)
    if not caminho.is_file():
        print(f"Arquivo não encontrado: {caminho}")
        return 1
    if args.unidade not in UNIDADES:
        print(f"Unidade inválida. Use uma de: {', '.join(UNIDADES)}")
        return 1
    if args.area not in AREAS_POR_UNIDADE.get(args.unidade, []):
        print(f"A área \"{args.area}\" não existe em {args.unidade}.")
        return 1

    criar_tabelas()
    pdfs = _ler_zip(caminho)
    print(f"{len(pdfs)} PDF(s) em {caminho.name}\n")

    if args.gravar and config.DB_ENGINE == "sqlite":
        origem = Path(config.SQLITE_PATH)
        if not origem.is_absolute():
            origem = config.BASE_DIR / origem
        backup = origem.with_name(
            f"{origem.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}{origem.suffix}"
        )
        shutil.copy2(origem, backup)
        print(f"Backup do banco: {backup.name}\n")

    # Sem e-mail às áreas: são FDS que já estão aprovadas.
    original = notificacoes.notificar_envio
    notificacoes.notificar_envio = lambda sessao, produto: None
    criados = pulados = 0
    try:
        with db_session() as s:
            solicitante = servicos.obter_ou_criar_solicitante(
                s, args.solicitante, args.email
            )
            agora = datetime.now()
            for nome_arquivo, conteudo in pdfs:
                if not conteudo[:5].startswith(b"%PDF"):
                    print(f"- {nome_arquivo}: não é PDF, pulado.")
                    pulados += 1
                    continue
                extraido, _preenchidos, _aviso = extracao.extrair_de_pdf(conteudo, nome_arquivo)
                dados = _dados_do_produto(extraido, args.unidade, args.area, nome_arquivo)
                if not dados["nome_comercial"] or not dados["fabricante"]:
                    print(f"- {nome_arquivo}: sem nome ou fabricante, pulado.")
                    pulados += 1
                    continue
                if servicos.produto_duplicado(s, dados["nome_comercial"], dados["fabricante"]):
                    print(f"- {nome_arquivo}: já cadastrado ({dados['nome_comercial']}), pulado.")
                    pulados += 1
                    continue

                faltam = [
                    rotulo for campo, rotulo in (
                        ("tipo_produto", "tipo"), ("numero_cas", "CAS"),
                        ("estado_fisico", "estado físico"),
                    ) if not dados.get(campo)
                ]
                print(
                    f"- {dados['nome_comercial']}  |  {dados['fabricante']}  |  "
                    f"{dados['tipo_produto'] or 'SEM TIPO'}"
                    + (f"  |  sem: {', '.join(faltam)}" if faltam else "")
                )
                if not args.gravar:
                    criados += 1
                    continue

                revisao = extraido.get("data_revisao_fds")
                from datetime import date as _date
                try:
                    data_revisao = _date.fromisoformat(revisao) if revisao else None
                except ValueError:
                    data_revisao = None
                produto = servicos.criar_solicitacao(
                    s, dados, solicitante,
                    [{
                        "tipo": "FDS", "nome": nome_arquivo,
                        "content_type": "application/pdf", "conteudo": conteudo,
                        "data_revisao": data_revisao,
                    }],
                )
                for aprovacao in produto.aprovacoes:
                    aprovacao.decisao = "APROVADO"
                    aprovacao.parecer = (
                        "Aprovada fora do sistema; cadastro importado em "
                        f"{agora:%d/%m/%Y}."
                    )
                    aprovacao.aprovador_id = None
                    aprovacao.decidido_em = agora
                produto.status = "APROVADO"
                produto.etapa_atual = None
                produto.concluido_em = agora
                produto.aprovado_em = agora
                produto.em_renovacao = False
                servicos.registrar_log(
                    s, "IMPORTACAO_APROVADA",
                    f"Produto importado já aprovado (aprovação feita fora do "
                    f"sistema). Lote: {caminho.name}.",
                    solicitante.id, produto.id,
                    status_anterior="PENDENTE", status_novo="APROVADO",
                )
                criados += 1
    finally:
        notificacoes.notificar_envio = original

    verbo = "gravado(s)" if args.gravar else "seriam cadastrado(s) (simulação, nada foi gravado)"
    print(f"\n{criados} produto(s) {verbo}; {pulados} pulado(s).")
    if not args.gravar:
        print("Para gravar de verdade, rode de novo com --gravar.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("zip", help="caminho do .zip com as FDS em PDF")
    ap.add_argument("--solicitante", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--unidade", required=True)
    ap.add_argument("--area", required=True)
    ap.add_argument("--gravar", action="store_true", help="grava no banco (sem isto, só simula)")
    sys.exit(executar(ap.parse_args()))
