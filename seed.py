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
    Recurso,
    RecursoArquivo,
    Usuario,
    somar_meses,
)
from security import gerar_hash

SENHA_PADRAO = "tenaris123"

USUARIOS = [
    ("Ana Silva", "ana.silva@tenaris.com", "SOLICITANTE", "Laboratório"),
    ("Bruno Costa", "bruno.costa@tenaris.com", "MEIO_AMBIENTE", "Meio Ambiente"),
    ("Carla Mendes", "carla.mendes@tenaris.com", "SAUDE", "Saúde Ocupacional"),
    ("Fábio Nunes", "fabio.nunes@tenaris.com", "SEGURANCA", "Segurança do Trabalho"),
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


# =====================================================================
# Biblioteca de Recursos e Documentos (conteúdo de exemplo)
# =====================================================================

def _pdf_simples(titulo: str, linhas: list[str]) -> bytes:
    """PDF de uma página com o título e as linhas informadas."""
    conteudo = [titulo, ""] + linhas + [
        "",
        "Documento de exemplo gerado para demonstração do sistema.",
    ]
    texto = "BT /F1 11 Tf 56 780 Td 16 TL\n"
    for linha in conteudo:
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


def _csv_exemplo(cabecalho: list[str], linhas: list[list[str]]) -> bytes:
    texto = ";".join(cabecalho) + "\n"
    for linha in linhas:
        texto += ";".join(linha) + "\n"
    return texto.encode("utf-8-sig")


# (seção, título, código, descrição, palavras-chave, arquivo, dias desde a revisão,
#  responsável, versões extras, meses até a próxima revisão)
BIBLIOTECA = [
    # ---------------------------------------------------------- Etiquetas
    {
        "secao": "ETIQUETAS", "titulo": "Etiqueta GHS - recipiente até 5 L",
        "codigo": "ET-GHS-05", "responsavel": "SAUDE", "dias": 40,
        "descricao": "Modelo de etiqueta GHS para frascos e galões de até 5 litros, "
                     "com pictogramas, palavra de advertência e frases H/P.",
        "chaves": "etiqueta, GHS, rotulagem, frasco, galão, pictograma",
        "arquivo": ("Etiqueta_GHS_ate_5L.pdf", "ETIQUETA GHS - RECIPIENTE ATÉ 5 L", [
            "Campos obrigatórios: nome do produto, pictogramas GHS, palavra de",
            "advertência, frases de perigo (H) e precaução (P), fornecedor.",
            "Imprimir em papel adesivo A4 - 4 etiquetas por folha.",
        ]),
        "versoes": [("Revisão dos pictogramas conforme ABNT NBR 14725:2023.", 400)],
        "proxima_meses": 12,
    },
    {
        "secao": "ETIQUETAS", "titulo": "Etiqueta GHS - tambor 200 L",
        "codigo": "ET-GHS-200", "responsavel": "SAUDE", "dias": 65,
        "descricao": "Modelo ampliado para tambores e contêineres, com área para "
                     "número ONU e classe de risco de transporte.",
        "chaves": "etiqueta, GHS, tambor, ONU, transporte",
        "arquivo": ("Etiqueta_GHS_tambor_200L.pdf", "ETIQUETA GHS - TAMBOR 200 L", [
            "Imprimir em A4 e fixar na lateral do tambor, acima da linha média.",
            "Informar número ONU e classe de risco quando houver transporte.",
        ]),
    },
    {
        "secao": "ETIQUETAS", "titulo": "Etiqueta de identificação de recipiente de transferência",
        "codigo": "ET-REC-01", "responsavel": "SAUDE", "dias": 95,
        "descricao": "Usada quando o produto é transferido da embalagem original para "
                     "um recipiente menor de uso na área.",
        "chaves": "etiqueta, recipiente, transferência, identificação, borrifador",
        "arquivo": ("Etiqueta_recipiente_transferencia.pdf",
                    "IDENTIFICAÇÃO DE RECIPIENTE DE TRANSFERÊNCIA", [
                        "Nunca utilizar embalagens de alimentos ou bebidas.",
                        "Informar produto, diluição, data e responsável pelo preenchimento.",
                    ]),
    },
    {
        "secao": "ETIQUETAS", "titulo": "Etiqueta de resíduo perigoso - Classe I",
        "codigo": "ET-RES-01", "responsavel": "MEIO_AMBIENTE", "dias": 20,
        "descricao": "Identificação de bombonas e tambores de resíduo perigoso "
                     "conforme a ABNT NBR 10004.",
        "chaves": "resíduo, perigoso, classe I, bombona, PGRS, descarte",
        "arquivo": ("Etiqueta_residuo_perigoso.pdf", "RESÍDUO PERIGOSO - CLASSE I", [
            "Preencher: origem do resíduo, composição, data de início do acúmulo,",
            "responsável pela área e destino previsto.",
            "Área de armazenamento temporário: máximo de 180 dias.",
        ]),
        "proxima_meses": 6,
    },
    {
        "secao": "ETIQUETAS", "titulo": "Etiqueta de produto controlado (PF / Exército)",
        "codigo": "ET-CTR-01", "responsavel": "QUIMICO_RESPONSAVEL", "dias": 130,
        "descricao": "Identificação obrigatória de produtos sob controle da Polícia "
                     "Federal e do Exército Brasileiro, com número da autorização.",
        "chaves": "controlado, polícia federal, exército, autorização, SisPCE",
        "arquivo": ("Etiqueta_produto_controlado.pdf", "PRODUTO QUÍMICO CONTROLADO", [
            "Informar número e validade da autorização do órgão controlador.",
            "Armazenar em local trancado, com controle de entrada e saída.",
        ]),
        "proxima_meses": -2,
    },
    {
        "secao": "ETIQUETAS", "titulo": "Placa de armazenamento - incompatibilidade química",
        "codigo": "ET-ARM-02", "responsavel": "SAUDE", "dias": 150,
        "descricao": "Placa para prateleiras indicando quais classes de produtos não "
                     "podem ser armazenadas juntas.",
        "chaves": "armazenamento, incompatibilidade, prateleira, segregação",
        "arquivo": ("Placa_incompatibilidade.pdf", "SEGREGAÇÃO POR INCOMPATIBILIDADE", [
            "Ácidos x bases: segregar. Inflamáveis x comburentes: segregar.",
            "Cianetos x ácidos: proibido no mesmo contenedor.",
        ]),
    },
    # ----------------------------------------------------- Procedimentos
    {
        "secao": "PROCEDIMENTOS",
        "titulo": "Manuseio e armazenamento de produtos químicos",
        "codigo": "PR-HSE-012", "responsavel": "SAUDE", "dias": 15,
        "descricao": "Procedimento geral de recebimento, manuseio, armazenagem e "
                     "transporte interno de produtos químicos na planta.",
        "chaves": "procedimento, manuseio, armazenamento, EPI, recebimento",
        "arquivo": ("PR-HSE-012_Manuseio_produtos_quimicos.pdf",
                    "PR-HSE-012 - MANUSEIO E ARMAZENAMENTO", [
                        "1. Objetivo e campo de aplicação.",
                        "2. Recebimento: conferir FDS, rótulo e integridade da embalagem.",
                        "3. Armazenagem: segregação por incompatibilidade e contenção.",
                        "4. Manuseio: EPI mínimo, ventilação e kit de emergência.",
                        "5. Transporte interno e descarte.",
                    ]),
        "versoes": [
            ("Inclusão do item 5 - descarte e destinação de embalagens.", 300),
            ("Revisão geral após auditoria interna de HSE.", 700),
        ],
        "proxima_meses": 18,
    },
    {
        "secao": "PROCEDIMENTOS",
        "titulo": "Descarte de resíduos químicos do laboratório",
        "codigo": "IT-LAB-004", "responsavel": "MEIO_AMBIENTE", "dias": 55,
        "descricao": "Instrução de trabalho para segregação, acondicionamento e "
                     "destinação dos resíduos gerados nos ensaios.",
        "chaves": "resíduo, descarte, laboratório, PGRS, destinação",
        "arquivo": ("IT-LAB-004_Descarte_residuos.pdf",
                    "IT-LAB-004 - DESCARTE DE RESÍDUOS QUÍMICOS", [
                        "Segregar por classe: ácidos, bases, solventes halogenados.",
                        "Nunca descartar resíduo químico na pia.",
                        "Registrar a geração na planilha mensal do PGRS.",
                    ]),
    },
    {
        "secao": "PROCEDIMENTOS", "titulo": "Política de Saúde, Segurança e Meio Ambiente",
        "codigo": "POL-HSE-001", "responsavel": "SAUDE", "dias": 210,
        "descricao": "Diretrizes corporativas de HSE aplicáveis a todas as áreas "
                     "e a todos os colaboradores e terceiros.",
        "chaves": "política, HSE, diretrizes, corporativo",
        "arquivo": ("POL-HSE-001_Politica_HSE.pdf", "POLÍTICA DE HSE", [
            "Compromisso com a prevenção de acidentes e a proteção ambiental.",
            "Responsabilidades da liderança e dos colaboradores.",
        ]),
    },
    # ------------------------------------------------------- Formulários
    {
        "secao": "FORMULARIOS", "titulo": "Requisição de novo produto químico",
        "codigo": "FR-HSE-001", "responsavel": "QUIMICO_RESPONSAVEL", "dias": 30,
        "descricao": "Planilha de apoio para levantar os dados do produto antes de "
                     "abrir a solicitação no sistema.",
        "chaves": "formulário, requisição, cadastro, planilha, solicitação",
        "arquivo_csv": ("FR-HSE-001_Requisicao_produto.csv",
                        ["Campo", "Preenchimento", "Obrigatório"],
                        [["Nome comercial", "", "Sim"],
                         ["Fabricante", "", "Sim"],
                         ["Fornecedor", "", "Não"],
                         ["Número CAS", "", "Não"],
                         ["Aplicação / finalidade", "", "Sim"],
                         ["Consumo estimado", "", "Sim"],
                         ["FDS anexada", "", "Sim"]]),
    },
    {
        "secao": "FORMULARIOS", "titulo": "Checklist de inspeção de armazenagem",
        "codigo": "FR-HSE-007", "responsavel": "SAUDE", "dias": 12,
        "descricao": "Checklist mensal das áreas de armazenagem: contenção, "
                     "sinalização, segregação e validade dos produtos.",
        "chaves": "checklist, inspeção, armazenagem, auditoria, contenção",
        "arquivo_csv": ("FR-HSE-007_Checklist_armazenagem.csv",
                        ["Item verificado", "Conforme", "Observação"],
                        [["Bacia de contenção íntegra", "", ""],
                         ["Produtos segregados por incompatibilidade", "", ""],
                         ["Rótulos legíveis e em português", "", ""],
                         ["FDS disponível na área", "", ""],
                         ["Kit de emergência completo", "", ""],
                         ["Extintor desobstruído e no prazo", "", ""]]),
        "proxima_meses": 12,
    },
    {
        "secao": "FORMULARIOS", "titulo": "Comunicação de incidente com produto químico",
        "codigo": "FR-HSE-015", "responsavel": "SAUDE", "dias": 80,
        "descricao": "Formulário de registro de derramamento, vazamento ou exposição "
                     "de colaborador a produto químico.",
        "chaves": "incidente, derramamento, vazamento, exposição, emergência",
        "arquivo": ("FR-HSE-015_Comunicacao_incidente.pdf",
                    "COMUNICAÇÃO DE INCIDENTE COM PRODUTO QUÍMICO", [
                        "Dados do evento: data, hora, local, produto e quantidade.",
                        "Pessoas envolvidas e atendimento prestado.",
                        "Medidas imediatas adotadas e ações preventivas.",
                    ]),
    },
    # ------------------------------------------------------------ Normas
    {
        "secao": "NORMAS", "titulo": "ABNT NBR 14725 - Rotulagem e FDS (resumo interno)",
        "codigo": "NR-EXT-01", "responsavel": "QUIMICO_RESPONSAVEL", "dias": 120,
        "descricao": "Resumo dos requisitos da norma brasileira de informações sobre "
                     "segurança de produtos químicos aplicáveis ao nosso cadastro.",
        "chaves": "ABNT, NBR 14725, FDS, rotulagem, GHS, norma",
        "arquivo": ("Resumo_NBR_14725.pdf", "ABNT NBR 14725 - RESUMO INTERNO", [
            "Estrutura obrigatória da FDS em 16 seções.",
            "Prazo de revisão recomendado: 5 anos.",
            "Elementos de rotulagem: pictograma, advertência, frases H e P.",
        ]),
        "proxima_meses": 24,
    },
    {
        "secao": "NORMAS", "titulo": "NR-26 - Sinalização de segurança (aplicação interna)",
        "codigo": "NR-EXT-02", "responsavel": "SAUDE", "dias": 170,
        "descricao": "Como a NR-26 se aplica à sinalização de tubulações, tanques e "
                     "áreas de armazenagem de produtos químicos da planta.",
        "chaves": "NR-26, sinalização, cores, tubulação, norma regulamentadora",
        "arquivo": ("NR-26_Aplicacao_interna.pdf", "NR-26 - SINALIZAÇÃO DE SEGURANÇA", [
            "Cores padronizadas para tubulações e identificação de conteúdo.",
            "Rotulagem preventiva de produtos químicos no ambiente de trabalho.",
        ]),
    },
    {
        "secao": "NORMAS", "titulo": "Requisitos de transporte de produtos perigosos (ANTT)",
        "codigo": "NR-EXT-03", "responsavel": "MEIO_AMBIENTE", "dias": 240,
        "descricao": "Exigências de documentação, rotulagem e ficha de emergência "
                     "para o transporte rodoviário de produtos perigosos.",
        "chaves": "ANTT, transporte, produto perigoso, ficha de emergência, ONU",
        "arquivo": ("Requisitos_transporte_ANTT.pdf",
                    "TRANSPORTE DE PRODUTOS PERIGOSOS - ANTT", [
                        "Documentos exigidos no transporte: FDS, ficha e envelope.",
                        "Rotulagem de risco e painéis de segurança no veículo.",
                    ]),
        "proxima_meses": -1,
    },
    # ------------------------------------------------------ Treinamentos
    {
        "secao": "TREINAMENTOS", "titulo": "Treinamento: como ler e usar a FDS",
        "codigo": "TR-HSE-003", "responsavel": "SAUDE", "dias": 25,
        "descricao": "Apresentação usada na integração e na reciclagem anual sobre "
                     "as 16 seções da Ficha de Dados de Segurança.",
        "chaves": "treinamento, FDS, integração, capacitação, apresentação",
        "arquivo": ("TR-HSE-003_Leitura_da_FDS.pdf", "TREINAMENTO - LEITURA DA FDS", [
            "O que é a FDS e quando consultá-la.",
            "As 16 seções e o que cada uma responde.",
            "Exercício prático com produtos da planta.",
        ]),
    },
    {
        "secao": "TREINAMENTOS", "titulo": "Guia rápido: cadastrar um produto no sistema",
        "codigo": "TR-SIS-001", "responsavel": "QUIMICO_RESPONSAVEL", "dias": 8,
        "descricao": "Passo a passo do preenchimento da solicitação, anexo da FDS e "
                     "acompanhamento das aprovações.",
        "chaves": "guia, manual, sistema, cadastro, passo a passo, tutorial",
        "arquivo": ("TR-SIS-001_Guia_rapido_cadastro.pdf",
                    "GUIA RÁPIDO - CADASTRO DE PRODUTO", [
                        "1. Acesse Cadastro e preencha os dados do produto.",
                        "2. Anexe a FDS (obrigatória) e a ficha de emergência.",
                        "3. Envie e acompanhe em Minhas solicitações.",
                        "4. Responda às solicitações de correção quando houver.",
                    ]),
    },
    {
        "secao": "TREINAMENTOS", "titulo": "Cartilha de boas práticas com solventes",
        "codigo": "TR-HSE-009", "responsavel": "SAUDE", "dias": 100,
        "descricao": "Cartilha ilustrada sobre manuseio seguro de solventes, "
                     "ventilação, eletricidade estática e EPI.",
        "chaves": "cartilha, solvente, boas práticas, inflamável, EPI",
        "arquivo": ("TR-HSE-009_Cartilha_solventes.pdf",
                    "BOAS PRÁTICAS COM SOLVENTES", [
                        "Mantenha os recipientes fechados e longe de fontes de ignição.",
                        "Use sempre ventilação local exaustora.",
                        "Aterre tambores durante a transferência.",
                    ]),
    },
    # --------------------------------------------------------- Links
    {
        "secao": "LINKS", "titulo": "SharePoint HSE", "codigo": None,
        "responsavel": "SAUDE", "dias": 18,
        "descricao": "Portal da equipe de HSE com atas, planos de ação e indicadores. "
                     "(Ajustar o endereço para o da sua planta.)",
        "chaves": "sharepoint, HSE, portal, intranet",
        "url": "https://tenaris.sharepoint.com/sites/hse",
    },
    {
        "secao": "LINKS", "titulo": "Power BI - Indicadores de HSE", "codigo": None,
        "responsavel": "SAUDE", "dias": 44,
        "descricao": "Painel com indicadores de segurança, resíduos e consumo de "
                     "produtos químicos. (Ajustar o endereço.)",
        "chaves": "power bi, indicadores, dashboard, KPI",
        "url": "https://app.powerbi.com/",
    },
    {
        "secao": "LINKS", "titulo": "Portal de Documentos corporativo", "codigo": None,
        "responsavel": "QUIMICO_RESPONSAVEL", "dias": 72,
        "descricao": "Repositório oficial de procedimentos e normas da companhia. "
                     "(Ajustar o endereço.)",
        "chaves": "portal, documentos, procedimentos, normas",
        "url": "https://tenaris.sharepoint.com/sites/documentos",
    },
    {
        "secao": "LINKS", "titulo": "IBAMA - Cadastro Técnico Federal", "codigo": None,
        "responsavel": "MEIO_AMBIENTE", "dias": 110,
        "descricao": "Consulta e emissão de certificados do CTF/APP para atividades "
                     "com produtos químicos.",
        "chaves": "IBAMA, CTF, cadastro técnico federal, ambiental, órgão regulador",
        "url": "https://www.gov.br/ibama/pt-br",
    },
    {
        "secao": "LINKS", "titulo": "Polícia Federal - Produtos químicos controlados",
        "codigo": None, "responsavel": "QUIMICO_RESPONSAVEL", "dias": 140,
        "descricao": "Serviços de licenciamento e mapas de controle de produtos "
                     "químicos fiscalizados pela PF.",
        "chaves": "polícia federal, controlado, licença, mapa, SIPROQUIM",
        "url": "https://www.gov.br/pf/pt-br/assuntos/produtos-quimicos",
    },
    {
        "secao": "LINKS", "titulo": "Exército Brasileiro - SisPCE", "codigo": None,
        "responsavel": "QUIMICO_RESPONSAVEL", "dias": 190,
        "descricao": "Sistema de produtos controlados pelo Exército: certificados, "
                     "autorizações e mapas.",
        "chaves": "exército, SisPCE, produto controlado, certificado de registro",
        "url": "https://www.gov.br/defesa/pt-br",
    },
]


def popular_biblioteca(sessao, usuarios):
    """Cria os itens de exemplo de Recursos e Documentos."""
    hoje = date.today()
    for item in BIBLIOTECA:
        responsavel = usuarios.get(item.get("responsavel", "SAUDE")) or usuarios.get("ADMIN")
        revisao = hoje - timedelta(days=item.get("dias", 30))
        proxima = None
        if item.get("proxima_meses"):
            proxima = somar_meses(revisao, item["proxima_meses"])
        e_link = "url" in item
        recurso = Recurso(
            secao=item["secao"],
            titulo=item["titulo"],
            codigo=item.get("codigo"),
            descricao=item.get("descricao"),
            palavras_chave=item.get("chaves"),
            tipo_midia="LINK" if e_link else "ARQUIVO",
            url=item.get("url"),
            versao_atual=1,
            data_revisao=revisao,
            proxima_revisao=proxima,
            responsavel_id=responsavel.id if responsavel else None,
            criado_em=datetime.combine(revisao, datetime.min.time()),
            atualizado_em=datetime.combine(revisao, datetime.min.time()),
            downloads=0,
        )
        sessao.add(recurso)
        sessao.flush()
        if e_link:
            continue

        if "arquivo_csv" in item:
            nome, cabecalho, linhas = item["arquivo_csv"]
            conteudo = _csv_exemplo(cabecalho, linhas)
            content_type = "text/csv"
        else:
            nome, titulo_pdf, corpo = item["arquivo"]
            conteudo = _pdf_simples(titulo_pdf, corpo)
            content_type = "application/pdf"

        # Versões anteriores (da mais antiga para a mais nova)
        historico = list(reversed(item.get("versoes", [])))
        versao = 0
        for nota, dias_atras in historico:
            versao += 1
            data_antiga = hoje - timedelta(days=dias_atras)
            sessao.add(
                RecursoArquivo(
                    recurso_id=recurso.id,
                    versao=versao,
                    nome_arquivo=nome.replace(".", f"_v{versao}.", 1),
                    content_type=content_type,
                    tamanho=len(conteudo),
                    conteudo=conteudo,
                    data_revisao=data_antiga,
                    notas=nota,
                    enviado_por_id=responsavel.id if responsavel else None,
                    enviado_em=datetime.combine(data_antiga, datetime.min.time()),
                )
            )
        versao += 1
        sessao.add(
            RecursoArquivo(
                recurso_id=recurso.id,
                versao=versao,
                nome_arquivo=nome,
                content_type=content_type,
                tamanho=len(conteudo),
                conteudo=conteudo,
                data_revisao=revisao,
                notas="Versão vigente." if versao == 1 else "Revisão periódica do documento.",
                enviado_por_id=responsavel.id if responsavel else None,
                enviado_em=datetime.combine(revisao, datetime.min.time()),
            )
        )
        recurso.versao_atual = versao
    sessao.flush()
    print(f"Biblioteca populada com {len(BIBLIOTECA)} itens.")


def limpar(sessao):
    for modelo in (Notificacao, LogAuditoria, RecursoArquivo, Recurso, Documento,
                   Aprovacao, ControleOrgao, ProdutoFabrica, ProdutoRisco,
                   Produto, Usuario):
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
            "SAUDE": "Sem agente com limite de exposição crítico. Monitoramento "
                     "ocupacional previsto para a equipe.",
            "SEGURANCA": "EPI compatível com o risco. Armazenagem e combate a "
                         "incêndio conferidos.",
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

            # Não há ordem entre as áreas; o Aprovador Final fecha depois delas.
            areas = ["MEIO_AMBIENTE", "SAUDE", "SEGURANCA", "QUIMICO_RESPONSAVEL"]
            etapas = areas + ["APROVADOR_FINAL"]
            if marcador == "reprovado":
                servicos.registrar_decisao(
                    s, produto, usuarios["MEIO_AMBIENTE"], "APROVADO",
                    pareceres["MEIO_AMBIENTE"], area="MEIO_AMBIENTE",
                )
                servicos.registrar_decisao(
                    s,
                    produto,
                    usuarios["SEGURANCA"],
                    "REPROVADO",
                    "Produto contém diclorometano (suspeita de carcinogenicidade). "
                    "Solicitar alternativa isenta de solventes clorados.",
                    area="SEGURANCA",
                )
            elif marcador == "descontinuado":
                for etapa in etapas:
                    servicos.registrar_decisao(
                        s, produto, usuarios[etapa], "APROVADO", pareceres[etapa],
                        area=etapa,
                    )
                servicos.descontinuar(
                    s,
                    produto,
                    usuarios["QUIMICO_RESPONSAVEL"],
                    "Substituído por produto de menor impacto ambiental (Antiferrum 15).",
                )
            else:
                # marcador = quantas etapas já decidiram (4 = áreas concluídas,
                # 5 = também aprovado pelo Aprovador Final).
                quantas = int(marcador)
                if quantas >= 4:
                    quantas = 5
                for etapa in etapas[:quantas]:
                    servicos.registrar_decisao(
                        s, produto, usuarios[etapa], "APROVADO", pareceres[etapa],
                        area=etapa,
                    )

        criados = servicos.sincronizar_aprovadores(s)
        if criados:
            print(f"Aprovadores por área vinculados: {criados}.")

        popular_biblioteca(s, usuarios)

        print("Base populada com sucesso.")
        print(f"Usuarios criados ({len(USUARIOS)}) - senha padrão: {SENHA_PADRAO}")
        for nome, email, papel, _ in USUARIOS:
            print(f"  {email:34s} {papel}")


if __name__ == "__main__":
    executar()
