"""Popula o banco com usuarios e produtos de exemplo (dados fictícios).

Uso:  python seed.py
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select

import servicos
from database import criar_tabelas, db_session
from models import (
    Aprovacao,
    ControleOrgao,
    Documento,
    LogAuditoria,
    Notificacao,
    Produto,
    ProdutoFabrica,
    ProdutoRisco,
    Usuario,
    somar_meses,
)
from security import gerar_hash

SENHA_PADRAO = "tenaris123"

USUARIOS = [
    ("Ana Silva", "ana.silva@tenaris.com", "SOLICITANTE", "Laboratório"),
    ("Bruno Costa", "bruno.costa@tenaris.com", "MEIO_AMBIENTE", "Meio Ambiente"),
    ("Carla Mendes", "carla.mendes@tenaris.com", "SAUDE_SEGURANCA", "SSO"),
    ("Diego Ramos", "diego.ramos@tenaris.com", "QUIMICO_RESPONSAVEL", "Laboratório"),
    ("Eduardo Lima", "eduardo.lima@tenaris.com", "APROVADOR_FINAL", "Operações"),
    ("Rafael Rizzo", "rafael.rizzo@tenaris.com", "ADMIN", "TI / Laboratório"),
]

PRODUTOS = [
    {
        "nome_comercial": "Acetona Técnica 99%",
        "fabricante": "Quimibras Indústrias Químicas",
        "fornecedor": "Distribuidora Sul Química",
        "categoria": "Solvente",
        "numero_cas": "67-64-1",
        "estado_fisico": "Líquido",
        "composicao": "Acetona (propan-2-ona) 99,5%",
        "setor_solicitante": "Laboratório",
        "aplicacao": "Limpeza e desengraxe de corpos de prova antes dos ensaios metalográficos.",
        "consumo_estimado": "60",
        "unidade": "L/mês",
        "local_armazenamento": "Armário de inflamáveis - Lab. 2",
        "classificacao_ghs": "Líquido inflamável Cat. 2; Irritação ocular Cat. 2A",
        "onu_numero": "UN1090",
        "epi_recomendado": "Luva nitrílica, óculos de segurança, avental, exaustão local.",
        "_decisoes": 4,
        "_dias": 45,
    },
    {
        "nome_comercial": "Nital 3% Solução de Ataque",
        "fabricante": "Reagentes Brasil Ltda",
        "fornecedor": "Reagentes Brasil Ltda",
        "categoria": "Reagente de laboratório",
        "numero_cas": "7697-37-2",
        "estado_fisico": "Líquido",
        "composicao": "Ácido nítrico 3% em etanol",
        "setor_solicitante": "Laboratório",
        "aplicacao": "Ataque químico para revelação de microestrutura em aços.",
        "consumo_estimado": "8",
        "unidade": "L/mês",
        "local_armazenamento": "Capela de exaustão - Lab. Metalografia",
        "classificacao_ghs": "Líquido inflamável Cat. 2; Corrosivo para metais Cat. 1",
        "onu_numero": "UN1992",
        "epi_recomendado": "Luva nitrílica, protetor facial, avental de PVC, capela.",
        "_decisoes": 4,
        "_dias": 30,
    },
    {
        "nome_comercial": "Óleo Solúvel CorteMax 220",
        "fabricante": "Lubrificantes Andina S.A.",
        "fornecedor": "Comercial Técnica Ferramentas",
        "categoria": "Óleo / Lubrificante",
        "numero_cas": "Mistura",
        "estado_fisico": "Líquido",
        "composicao": "Óleo mineral parafínico, emulsificantes, biocida (< 1%)",
        "setor_solicitante": "Usinagem",
        "aplicacao": "Fluido de corte para usinagem de roscas em tubos.",
        "consumo_estimado": "1200",
        "unidade": "L/mês",
        "local_armazenamento": "Central de fluidos - Galpão 3",
        "classificacao_ghs": "Irritação cutânea Cat. 2",
        "onu_numero": "Não aplicável",
        "epi_recomendado": "Luva de PVC, óculos, creme de proteção dérmica.",
        "_decisoes": 4,
        "_dias": 20,
    },
    {
        "nome_comercial": "Desengraxante Alcalino BioClean AX",
        "fabricante": "Chemtech do Brasil",
        "fornecedor": "Chemtech do Brasil",
        "categoria": "Detergente / Limpeza",
        "numero_cas": "1310-73-2",
        "estado_fisico": "Líquido",
        "composicao": "Hidróxido de sódio 8%, tensoativos não iônicos",
        "setor_solicitante": "Manutenção",
        "aplicacao": "Limpeza de peças e pisos da área de manutenção mecânica.",
        "consumo_estimado": "300",
        "unidade": "L/mês",
        "local_armazenamento": "Depósito de químicos - Manutenção",
        "classificacao_ghs": "Corrosão cutânea Cat. 1A; Lesão ocular grave Cat. 1",
        "onu_numero": "UN1824",
        "epi_recomendado": "Luva de borracha, protetor facial, bota e avental impermeável.",
        "_decisoes": 2,
        "_dias": 8,
    },
    {
        "nome_comercial": "Tinta Epóxi Primer EP-500 Cinza",
        "fabricante": "Revestimentos Titan",
        "fornecedor": "Suprimentos Industriais Norte",
        "categoria": "Tinta / Revestimento",
        "numero_cas": "Mistura",
        "estado_fisico": "Líquido",
        "composicao": "Resina epóxi, xileno 15%, pigmentos inorgânicos",
        "setor_solicitante": "Pintura",
        "aplicacao": "Primer anticorrosivo aplicado na extremidade dos tubos.",
        "consumo_estimado": "450",
        "unidade": "L/mês",
        "local_armazenamento": "Cabine de pintura - área ventilada",
        "classificacao_ghs": "Líquido inflamável Cat. 3; Toxicidade sistêmica Cat. 2",
        "onu_numero": "UN1263",
        "epi_recomendado": "Respirador com filtro para vapores orgânicos, luva, óculos, macacão.",
        "_decisoes": 1,
        "_dias": 4,
    },
    {
        "nome_comercial": "Removedor Clorado StripFast CL",
        "fabricante": "Solventes Continental",
        "fornecedor": "Solventes Continental",
        "categoria": "Solvente",
        "numero_cas": "75-09-2",
        "estado_fisico": "Líquido",
        "composicao": "Diclorometano 70%, metanol 20%",
        "setor_solicitante": "Manutenção",
        "aplicacao": "Remoção de tinta de estruturas metálicas.",
        "consumo_estimado": "80",
        "unidade": "L/mês",
        "local_armazenamento": "Depósito de inflamáveis",
        "classificacao_ghs": "Carcinogenicidade Cat. 2; Toxicidade sistêmica Cat. 2",
        "onu_numero": "UN1593",
        "epi_recomendado": "Respirador autônomo, luva de PVA, protetor facial.",
        "_decisoes": "reprovado",
        "_dias": 60,
    },
    {
        "nome_comercial": "Inibidor de Corrosão Antiferrum 12",
        "fabricante": "Quimibras Indústrias Químicas",
        "fornecedor": "Distribuidora Sul Química",
        "categoria": "Aditivo de processo",
        "numero_cas": "Mistura",
        "estado_fisico": "Líquido",
        "composicao": "Aminas graxas, álcool isopropílico 10%",
        "setor_solicitante": "Tratamento térmico",
        "aplicacao": "Aditivo do banho de resfriamento para evitar corrosão superficial.",
        "consumo_estimado": "150",
        "unidade": "kg/mês",
        "local_armazenamento": "Área de tratamento térmico",
        "classificacao_ghs": "Irritação cutânea Cat. 2; Perigoso ao meio ambiente aquático Cat. 2",
        "onu_numero": "UN1993",
        "epi_recomendado": "Luva nitrílica, óculos, avental.",
        "_decisoes": "descontinuado",
        "_dias": 400,
    },
]


# Dados do módulo de FDS, por posição na lista PRODUTOS acima.
#   _revisao_meses: há quantos meses a FDS foi revisada. Como a validade é de
#   5 anos (60 meses) com alerta nos últimos 6, os valores abaixo produzem
#   propositalmente os três estados do semáforo.
EXTRAS = [
    {   # 0 - Acetona: vigente (verde), controlada pela Policia Federal
        "nome_tecnico": "Propan-2-ona",
        "processo": "Preparação metalográfica",
        "restricoes_uso": "Manusear somente sob exaustão. Manter longe de fontes de ignição.",
        "_fabricas": ["Pinda Tubos", "MC SCON2"],
        "_orgaos": [("POLICIA_FEDERAL", "PF-2024-004821", 20)],
        "_revisao_meses": 14,
        "_riscos": ["Inflamável", "Irritante"],
        "area_solicitante": "Laboratório",
        "prazo_utilizacao": "Uso contínuo",
    },
    {   # 1 - Nital: FDS proxima do vencimento (amarelo) + licenca vencida
        "nome_tecnico": "Ácido nítrico em etanol",
        "processo": "Ataque químico - metalografia",
        "restricoes_uso": "Preparar apenas no volume de uso diário. Não estocar diluído.",
        "_fabricas": ["Pinda Tubos"],
        "_orgaos": [("POLICIA_FEDERAL", "PF-2019-001177", -3),
                    ("EXERCITO", "EB-2023-00912", 15)],
        "_revisao_meses": 56,
        "_riscos": ["Inflamável", "Corrosivo", "Tóxico"],
        "area_solicitante": "Laboratório",
        "prazo_utilizacao": "Uso contínuo",
    },
    {   # 2 - Oleo soluvel: FDS VENCIDA (vermelho), emulsao, 3 fabricas
        "nome_tecnico": "Óleo mineral emulsionável",
        "processo": "Usinagem e corte de tubos",
        "restricoes_uso": "Trocar a emulsão conforme controle microbiológico do laboratório.",
        "tipo_produto": "Emulsão",
        "_fabricas": ["Pinda Tubos", "COSE", "RDO"],
        "_orgaos": [],
        "_revisao_meses": 68,
        "_riscos": ["Irritante", "Perigoso ao Meio Ambiente"],
        "area_solicitante": "Produção",
        "prazo_utilizacao": "24 meses",
    },
    {   # 3 - Desengraxante: em analise
        "nome_tecnico": "Solução alcalina de hidróxido de potássio",
        "processo": "Lavagem de peças",
        "_fabricas": ["MC TCHB"],
        "_orgaos": [],
        "_revisao_meses": 6,
        "_riscos": ["Corrosivo"],
        "area_solicitante": "Manutenção",
        "prazo_utilizacao": "12 meses",
    },
    {   # 4 - Tinta epoxi: em analise
        "nome_tecnico": "Resina epóxi bicomponente",
        "processo": "Pintura de acabamento",
        "_fabricas": ["MC SCON2", "MC TCHB"],
        "_orgaos": [],
        "_revisao_meses": 9,
        "_riscos": ["Inflamável", "Nocivo"],
        "area_solicitante": "Produção",
        "prazo_utilizacao": "18 meses",
    },
    {   # 5 - Removedor clorado: reprovado, controlado por Policia Civil
        "nome_tecnico": "Diclorometano",
        "processo": "Remoção de tinta",
        "restricoes_uso": "Uso proibido - reprovado pela área de Saúde e Segurança.",
        "_fabricas": ["RDO"],
        "_orgaos": [("POLICIA_CIVIL", "PC-SP-2024-0330", 8)],
        "_revisao_meses": 30,
        "_riscos": ["Tóxico", "Perigoso ao Meio Ambiente"],
        "area_solicitante": "Manutenção",
        "prazo_utilizacao": "6 meses",
    },
    {   # 6 - Inibidor de corrosao: descontinuado, hidraulico
        "nome_tecnico": "Aminas graxas etoxiladas",
        "processo": "Tratamento de água de processo",
        "tipo_produto": "Hidráulico",
        "_fabricas": ["COSE"],
        "_orgaos": [],
        "_revisao_meses": 40,
        "_riscos": ["Nocivo"],
        "area_solicitante": "Engenharia",
        "prazo_utilizacao": "12 meses",
    },
]


def _pdf_exemplo(titulo: str, produto: dict) -> bytes:
    """Gera um PDF simples de uma página (FDS de exemplo)."""
    linhas = [
        titulo,
        "",
        f"Produto: {produto['nome_comercial']}",
        f"Fabricante: {produto['fabricante']}",
        f"Número CAS: {produto['numero_cas']}",
        f"Estado físico: {produto['estado_fisico']}",
        "",
        "1. Identificação - documento de exemplo gerado para teste do sistema.",
        f"2. Composição: {produto['composicao']}",
        f"3. Perigos: {produto['classificacao_ghs']}",
        f"4. EPI: {produto['epi_recomendado']}",
        f"5. Transporte: {produto['onu_numero']}",
        "6. Medidas de emergência: isolar a área, usar EPI e acionar a brigada.",
        "",
        "ATENÇÃO: conteudo fictício, sem valor técnico ou legal.",
    ]
    texto = "BT /F1 11 Tf 56 780 Td 16 TL\n"
    for linha in linhas:
        seguro = linha.replace("\\", "").replace("(", "[").replace(")", "]")
        texto += f"({seguro}) Tj T*\n"
    texto += "ET"

    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(texto)} >>\nstream\n{texto}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    saida = "%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida += f"{i} 0 obj\n{obj}\nendobj\n"
    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        saida += f"{off:010d} 00000 n \n"
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n"
    )
    return saida.encode("latin-1", errors="replace")


def limpar(sessao):
    for modelo in (Notificacao, LogAuditoria, Documento, Aprovacao,
                   ControleOrgao, ProdutoFabrica, ProdutoRisco, Produto, Usuario):
        sessao.query(modelo).delete()


def executar(recriar: bool = True):
    criar_tabelas()
    with db_session() as s:
        if recriar:
            limpar(s)
            s.flush()

        usuarios = {}
        for nome, email, papel, setor in USUARIOS:
            existente = s.scalar(select(Usuario).where(Usuario.email == email))
            if existente:
                usuarios[papel] = existente
                continue
            u = Usuario(
                nome=nome,
                email=email,
                senha_hash=gerar_hash(SENHA_PADRAO),
                papel=papel,
                setor=setor,
            )
            s.add(u)
            usuarios[papel] = u
        s.flush()

        solicitante = usuarios["SOLICITANTE"]
        pareceres = {
            "MEIO_AMBIENTE": "Sem restrição ambiental. Destinação de resíduos conforme PGRS.",
            "SAUDE_SEGURANCA": "EPI compatível com o risco. Treinamento previsto para a equipe.",
            "QUIMICO_RESPONSAVEL": "FDS conforme ABNT NBR 14725. Compatibilidade de armazenamento verificada.",
            "APROVADOR_FINAL": "Aprovado para uso nas condições descritas na solicitação.",
        }

        for i, dados in enumerate(PRODUTOS):
            marcador = dados.pop("_decisoes")
            dias = dados.pop("_dias")

            extra = dict(EXTRAS[i]) if i < len(EXTRAS) else {}
            fabricas = extra.pop("_fabricas", [])
            orgaos = extra.pop("_orgaos", [])
            revisao_meses = extra.pop("_revisao_meses", 12)
            riscos = extra.pop("_riscos", [])
            dados.update(extra)
            dados["fabricas"] = fabricas
            dados["riscos"] = riscos
            dados["controles"] = [
                {
                    "orgao": orgao,
                    "numero_licenca": numero,
                    "validade_licenca": somar_meses(date.today(), meses),
                }
                for orgao, numero, meses in orgaos
            ]

            arquivos = [
                {
                    "tipo": "FDS",
                    "nome": f"FDS_{dados['nome_comercial'].split()[0].upper()}.pdf",
                    "content_type": "application/pdf",
                    "conteudo": _pdf_exemplo("FICHA DE DADOS DE SEGURANCA (FDS)", dados),
                    "data_revisao": somar_meses(date.today(), -revisao_meses),
                }
            ]
            if i % 2 == 0:
                arquivos.append(
                    {
                        "tipo": "FICHA_EMERGENCIA",
                        "nome": f"FE_{dados['nome_comercial'].split()[0].upper()}.pdf",
                        "content_type": "application/pdf",
                        "conteudo": _pdf_exemplo("FICHA DE EMERGENCIA", dados),
                    }
                )
            produto = servicos.criar_solicitacao(s, dict(dados), solicitante, arquivos)
            produto.criado_em = datetime.now() - timedelta(days=dias)
            s.flush()

            etapas = ["MEIO_AMBIENTE", "SAUDE_SEGURANCA", "QUIMICO_RESPONSAVEL", "APROVADOR_FINAL"]
            if marcador == "reprovado":
                servicos.registrar_decisao(
                    s, produto, usuarios["MEIO_AMBIENTE"], "APROVADO", pareceres["MEIO_AMBIENTE"]
                )
                servicos.registrar_decisao(
                    s,
                    produto,
                    usuarios["SAUDE_SEGURANCA"],
                    "REPROVADO",
                    "Produto contém diclorometano (suspeita de carcinogenicidade). "
                    "Solicitar alternativa isenta de solventes clorados.",
                )
            elif marcador == "descontinuado":
                for etapa in etapas:
                    servicos.registrar_decisao(
                        s, produto, usuarios[etapa], "APROVADO", pareceres[etapa]
                    )
                servicos.descontinuar(
                    s,
                    produto,
                    usuarios["QUIMICO_RESPONSAVEL"],
                    "Substituído por produto de menor impacto ambiental (Antiferrum 15).",
                )
            else:
                for etapa in etapas[: int(marcador)]:
                    servicos.registrar_decisao(
                        s, produto, usuarios[etapa], "APROVADO", pareceres[etapa]
                    )

        print("Base populada com sucesso.")
        print(f"Usuarios criados ({len(USUARIOS)}) - senha padrão: {SENHA_PADRAO}")
        for nome, email, papel, _ in USUARIOS:
            print(f"  {email:34s} {papel}")


if __name__ == "__main__":
    executar()
