"""Cria três solicitações de exemplo a partir de FDS reais, cada uma num
estágio diferente do fluxo. Serve para demonstração ao vivo.

    PQ-xxx  Coagulante Suall Nanocog 220E   -> APROVADO (as 5 etapas)
    PQ-xxx  Qualypav Demarcação             -> 2 áreas aprovaram, 2 pendentes
    PQ-xxx  Ratol Granulado GS              -> recém-enviado, 4 áreas pendentes

É seguro repetir: se um produto de exemplo já existir, ele é pulado. Nada
do que já está cadastrado é apagado.

Uso:  iniciar.bat exemplos
      (ou:  .venv\\Scripts\\python.exe exemplos_demo.py)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

import servicos
from database import db_session
from models import Produto, Usuario

PASTA_FDS = Path(__file__).resolve().parent / "exemplos"

# ---------------------------------------------------------------------
# Os três produtos, com os dados que a FDS traz + o que o solicitante
# completaria na tela.
# ---------------------------------------------------------------------

EXEMPLOS = [
    {
        "_arquivo": "FDS_Coagulante_Suall.pdf",
        "_decisoes": "completo",
        "_dias": 26,
        "_solicitante": ("Ana Silva", "ana.silva@tenaris.com"),
        "nome_comercial": "Coagulante Suall Nanocog 220E",
        "fabricante": "SUALL Indústria e Comércio Ltda",
        "cas": ["7446-70-0", "7732-18-5"],
        "nome_tecnico": "Cloreto de alumínio em solução",
        "tipo_produto": "Outros",
        "categoria": "Aditivo de processo",
        "estado_fisico": "Líquido",
        "aplicacao": "Tratamento de água, esgotos domésticos e efluentes industriais.",
        "necessidade_uso": (
            "Sem o coagulante o efluente da estação não atinge o limite de "
            "turbidez exigido na licença de operação, e a água de processo não "
            "pode ser reaproveitada no circuito de resfriamento."
        ),
        "forma_aplicacao": "Dosagem Automática",
        "area_solicitante": "Manutenção - ETE",
        "setor_solicitante": "Produção",
        "prazo_utilizacao": "Uso Contínuo",
        "consumo_estimado": "800",
        "unidade": "L/mês",
        "funcionarios_expostos": 3,
        "funcoes_expostas": "Operador de utilidades, técnico de meio ambiente",
        "inflamavel": "NAO",
        "cancerigeno": "NAO",
        "ponto_fulgor": "Não aplicável (base aquosa)",
        "classificacao_ghs": (
            "Corrosivo para os metais - Categoria 1; Lesões oculares graves/"
            "irritação ocular - Categoria 1"
        ),
        "onu_numero": "UN2581",
        "local_armazenamento": "Contenção da ETE - tanque 2",
        "epi_recomendado": "Óculos de proteção, luva de PVC, avental e bota de segurança.",
        "restricoes_uso": "Armazenar em recipiente resistente à corrosão, longe de metais.",
        "observacoes": (
            "Substitui o coagulante anterior, de maior consumo por metro cúbico "
            "tratado. Dosagem definida em ensaio de bancada pelo laboratório."
        ),
        "fabricas": ["Pinda"],
        "riscos": ["Corrosivo", "Irritante"],
        "_revisao": date(2025, 7, 3),
    },
    {
        "_arquivo": "FDS_Qualypav_Demarcacao.pdf",
        "_decisoes": "parcial",
        "_dias": 9,
        "_solicitante": ("Julia Silva", "jusilva@tenaris.com"),
        "nome_comercial": "Qualypav Demarcação Branco e Cores",
        "fabricante": "Qualycril Soluções para a Construção Civil Ltda",
        "cas": ["108-88-3", "1330-20-7", "13463-67-7"],
        "nome_tecnico": "Tinta acrílica para demarcação viária",
        "tipo_produto": "Outros",
        "categoria": "Tinta / Revestimento",
        "estado_fisico": "Líquido",
        "aplicacao": "Indicado para demarcação viária horizontal.",
        "necessidade_uso": (
            "Repintura da sinalização de piso das rotas de pedestres e do "
            "trânsito de empilhadeiras, hoje apagada em boa parte da nave 3."
        ),
        "forma_aplicacao": "Pulverização / Spray",
        "area_solicitante": "Manutenção - Oficina",
        "setor_solicitante": "Manutenção",
        "prazo_utilizacao": "Até 6 Meses",
        "consumo_estimado": "200",
        "unidade": "L/mês",
        "funcionarios_expostos": 6,
        "funcoes_expostas": "Pintor industrial, ajudante de pintura",
        "inflamavel": "SIM",
        "cancerigeno": "SIM",
        "ponto_fulgor": "> 35 °C",
        "classificacao_ghs": (
            "Líquidos inflamáveis, Categoria 3; Carcinogenicidade, Categoria 2; "
            "Sensibilização da pele, Categoria 1"
        ),
        "onu_numero": "UN1263",
        "local_armazenamento": "Armário de inflamáveis - oficina de manutenção",
        "epi_recomendado": (
            "Respirador semifacial com filtro para vapores orgânicos, luva "
            "nitrílica, óculos de proteção e vestimenta de manga longa."
        ),
        "restricoes_uso": "Aplicar somente em área aberta ou com exaustão. Proibido fumar.",
        "observacoes": (
            "Aplicação externa, com exaustão natural. Substitui a tinta anterior "
            "à base de solvente clorado."
        ),
        "fabricas": ["Pinda"],
        "riscos": ["Inflamável", "Irritante", "Nocivo", "Perigoso ao Meio Ambiente"],
        "_revisao": date(2025, 5, 27),
    },
    {
        "_arquivo": "FDS_Ratol_Granulado.pdf",
        "_decisoes": "novo",
        "_dias": 1,
        "_solicitante": ("Ana Silva", "ana.silva@tenaris.com"),
        "nome_comercial": "Ratol Granulado GS - Profissional",
        "fabricante": "ChemoNE - Industrial Química do Nordeste EIRELI",
        "cas": ["56073-10-0"],
        "nome_tecnico": "Isca rodenticida granulada",
        "tipo_produto": "Outros",
        "categoria": "Outros",
        "estado_fisico": "Sólido",
        "aplicacao": "Controle de roedores.",
        "necessidade_uso": (
            "Controle de roedores no almoxarifado e nas galerias de cabos, onde "
            "houve dano a isolamento elétrico no último trimestre."
        ),
        "forma_aplicacao": "Aplicação por Terceiros",
        "area_solicitante": "Manutenção - Almoxarifado",
        "setor_solicitante": "Manutenção",
        "prazo_utilizacao": "Até 1 Ano",
        "consumo_estimado": "5",
        "unidade": "kg/mês",
        "funcionarios_expostos": 2,
        "funcoes_expostas": "Auxiliar de serviços gerais, técnico de facilities",
        "inflamavel": "NAO",
        "cancerigeno": "NAO",
        "ponto_fulgor": "",
        "classificacao_ghs": "Produto não classificado como perigoso pela ABNT NBR 14725:2023",
        "onu_numero": "",
        "local_armazenamento": "Armário trancado do almoxarifado de facilities",
        "epi_recomendado": "Luva descartável e lavagem das mãos após o manuseio.",
        "restricoes_uso": (
            "Aplicar somente em porta-iscas travados, em local de difícil acesso "
            "a pessoas e animais. Registrar cada ponto no mapa de iscas."
        ),
        "observacoes": "Aplicação por empresa terceira certificada, acompanhada pela Manutenção.",
        "terceiro_nome": "Marcos Andrade",
        "terceiro_empresa": "Sanivet Controle de Pragas Ltda",
        "gestor_contrato": "Eduardo Lima",
        "gestor_email": "eduardo.lima@tenaris.com",
        "fabricas": ["Pinda"],
        "riscos": ["Nocivo"],
        "_revisao": date(2024, 12, 21),
    },
]

PARECERES = {
    "MEIO_AMBIENTE": "Produto compatível com o plano de gerenciamento de resíduos. "
                     "Embalagem vazia segue para a área de resíduos classe I.",
    "SAUDE": "Exposição ocupacional aceitável nas condições descritas. "
             "Incluir os expostos no PCMSO com o exame correspondente.",
    "SEGURANCA": "Armazenamento e combate a incêndio conferidos. "
                 "EPI compatível com os riscos declarados na FDS.",
    "QUIMICO_RESPONSAVEL": "FDS conforme ABNT NBR 14725:2023. "
                           "Compatibilidade de armazenamento verificada.",
    "APROVADOR_FINAL": "Aprovado para uso nas condições descritas pelas áreas. "
                       "Revisar em 12 meses.",
}


def _usuarios(sessao) -> dict[str, Usuario]:
    """Um usuário por papel do fluxo, para assinar os pareceres."""
    pessoas = {}
    for papel in ("MEIO_AMBIENTE", "SAUDE", "SEGURANCA", "QUIMICO_RESPONSAVEL",
                  "APROVADOR_FINAL"):
        pessoas[papel] = sessao.scalar(
            select(Usuario).where(Usuario.papel == papel, Usuario.ativo.is_(True))
        )
    return pessoas


def executar() -> int:
    if not PASTA_FDS.is_dir():
        print(f"Pasta com as FDS não encontrada: {PASTA_FDS}")
        return 1

    criados = 0
    with db_session() as s:
        servicos.garantir_tecnicos_seguranca(s)
        aprovadores = _usuarios(s)
        faltando = [p for p, u in aprovadores.items() if u is None]
        if faltando:
            print("Sem aprovador cadastrado para: " + ", ".join(faltando))
            print("Rode o iniciar.bat uma vez para carregar os usuários de exemplo.")
            return 1

        for dados in EXEMPLOS:
            dados = dict(dados)
            arquivo = PASTA_FDS / dados.pop("_arquivo")
            marcador = dados.pop("_decisoes")
            dias = dados.pop("_dias")
            nome, email = dados.pop("_solicitante")
            revisao = dados.pop("_revisao")

            if s.scalar(select(Produto).where(
                Produto.nome_comercial == dados["nome_comercial"]
            )):
                print(f"- {dados['nome_comercial']}: já existe, pulando.")
                continue
            if not arquivo.is_file():
                print(f"- {dados['nome_comercial']}: FDS não encontrada ({arquivo.name}).")
                continue

            solicitante = servicos.obter_ou_criar_solicitante(s, nome, email)
            dados["codigo_interno"] = servicos.proximo_codigo(s)
            arquivos = [{
                "tipo": "FDS",
                "nome": arquivo.name,
                "content_type": "application/pdf",
                "conteudo": arquivo.read_bytes(),
                "data_revisao": revisao,
            }]
            produto = servicos.criar_solicitacao(s, dados, solicitante, arquivos)
            produto.criado_em = datetime.now() - timedelta(days=dias)
            s.flush()

            # A Segurança aprova primeiro; depois as outras áreas.
            if marcador == "completo":
                etapas = ["SEGURANCA", "MEIO_AMBIENTE", "SAUDE",
                          "QUIMICO_RESPONSAVEL", "APROVADOR_FINAL"]
            elif marcador == "parcial":
                etapas = ["SEGURANCA", "MEIO_AMBIENTE"]
            else:
                etapas = []

            for etapa in etapas:
                quem = aprovadores[etapa]
                if etapa == "SEGURANCA" and produto.tecnico_seguranca:
                    quem = produto.tecnico_seguranca
                servicos.registrar_decisao(
                    s, produto, quem, "APROVADO",
                    PARECERES[etapa], area=etapa,
                )
            criados += 1
            situacao = {
                "completo": "aprovado (5/5)",
                "parcial": "2 áreas aprovaram, 2 pendentes",
                "novo": "recém-enviado, 4 áreas pendentes",
            }[marcador]
            print(f"+ {produto.codigo_interno} {produto.nome_comercial} - {situacao}")

    print(f"\nExemplos criados: {criados}.")
    if criados:
        print("Abra http://localhost:5001/aprovacoes para ver a fila de aprovação.")
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())
