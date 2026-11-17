"""Extração automática de dados da Ficha de Dados de Segurança (FDS).

Lê o texto do PDF localmente - o arquivo NÃO sai da rede interna - e procura
as informações nas seções previstas pela ABNT NBR 14725:

    Seção 1  - Identificação: nome, fabricante e usos recomendados
    Seção 2  - Perigos: classificação GHS, frases H, inflamabilidade
    Seção 3  - Composição: número CAS
    Seção 9  - Propriedades: estado físico e ponto de fulgor
    Seção 11 - Toxicologia: carcinogenicidade
    Seção 14 - Transporte: número ONU

Na prática cada fabricante monta a ficha de um jeito - tabela de duas
colunas, seções numeradas "SEÇÃO 9:" ou "9 -", rótulo com e sem dois-pontos,
e a extração do PDF ainda parte palavras no meio ("r evisão", "202 4"). Por
isso a leitura é feita sobre o texto achatado, delimitando cada valor pelo
rótulo seguinte, com vários caminhos alternativos por campo.

O resultado é sempre uma SUGESTÃO: o solicitante confere e corrige na tela
antes de enviar. Campo não encontrado volta vazio para preenchimento manual.

Para plugar uma extração por IA no futuro, basta implementar uma função com a
mesma assinatura de `extrair` e chamá-la em `extrair_de_pdf` quando o modo
local não encontrar o suficiente.
"""

from __future__ import annotations

import io
import re
from datetime import date

from models import CLASSES_RISCO, TIPOS_PRODUTO, sem_acento

# ---------------------------------------------------------------------
# Leitura do PDF
# ---------------------------------------------------------------------

MAX_PAGINAS = 12  # a Seção 3 raramente passa da página 4; 12 é folga


def texto_do_pdf(conteudo: bytes) -> str:
    """Devolve o texto do PDF. String vazia quando não há texto extraível."""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return ""
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        partes = []
        for pagina in leitor.pages[:MAX_PAGINAS]:
            try:
                partes.append(pagina.extract_text() or "")
            except Exception:
                continue
        return "\n".join(partes)
    except Exception:
        return ""


def _limpar(valor: str | None, limite: int = 180) -> str:
    if not valor:
        return ""
    valor = re.sub(r"\s+", " ", valor).strip(" .:;-–—()\t")
    return valor[:limite].strip()


# ---------------------------------------------------------------------
# Leitura por rótulo em fichas de duas colunas
# ---------------------------------------------------------------------
# A maioria das FDS brasileiras é uma tabela de duas colunas: o rótulo à
# esquerda, o valor à direita. Ao extrair o texto do PDF, o rótulo quebra em
# várias linhas ("Classificação da\nsubstância ou mistura:  Corrosivo..."),
# o que quebra qualquer busca linha a linha. A saída é achatar o documento
# num texto só e delimitar o valor pelo rótulo seguinte.

def _plano(texto: str) -> str:
    """Texto do PDF em uma linha só, com espaços normalizados."""
    return re.sub(r"\s+", " ", texto or "")


# Rótulos que costumam vir logo depois de um valor: servem de "pare aqui".
_TERMINADORES = [
    r"Outras?\s+maneiras?", r"Usos?\s+recomendados?", r"Detalhes?\s+do\s+fornecedor",
    r"Endere[çc]o", r"Telefones?", r"E-?mail", r"N[úu]mero\s+do\s+telefone",
    r"Raz[ãa]o\s+social", r"CNPJ", r"Site\b",
    r"Sistema\s+de\s+classifica", r"Elementos?\s+de\s+rotulagem", r"Pictogramas?",
    r"Palavras?\s+de\s+advert", r"Frases?\s+de\s+(?:perigo|precau)",
    r"Outros\s+perigos", r"Classifica[çc][ãa]o\s+d[ao]s?\s+(?:subst|mistura|perigo)",
    r"Estado\s+f[íi]sico", r"\bCor\s*:", r"\bOdor\b", r"\bpH\b",
    r"Ponto\s+de\s+(?:fus[ãa]o|ebuli|fulgor)", r"Inflamabilidade",
    r"Limites?\s+(?:inferior|superior|de)", r"Temperaturas?\s+de",
    r"Viscosidade", r"Solubilidade", r"Press[ãa]o\s+de\s+vapor",
    r"Coeficiente\s+de\s+parti", r"Densidades?\b", r"Caracter[íi]sticas?\s+de\s+part",
    r"Outras\s+informa", r"Toxicidade", r"Corros[ãa]o\s*/", r"Sensibiliza[çc][ãa]o",
    r"Mutagenicidade", r"Carcinogenicidade", r"Les[õo]es\s+oculares",
    r"Perigo\s+por\s+aspira", r"Nome\s+apropriado", r"Classe\s+ou\s+subclasse",
    r"Grupo\s+de\s+embalagem", r"N[úu]mero\s+de\s+risco", r"Perigo\s+ao\s+Meio",
    r"P[áa]gina\s*:", r"Em\s+conformidade\s+com", r"Vers[ãa]o\s*:",
    r"Nome\s+d[ao]\s+(?:empresa|mistura|produto|fabricante|fornecedor)",
    r"Taxa\s+de\s+evapora", r"Aspecto\b", r"Apar[êe]ncia\b", r"Forma\s+do\s+produto",
    r"C[óo]digo\s+do\s+produto", r"Limiar\s+de\s+odor", r"Tamanho\s+das\s+part",
    r"Revis[ãa]o\s*:", r"Data\s+d[ae]\b", r"Principais\s+usos?",
    # começo de um endereço (o nome da empresa termina ali)
    r"\b(?:Av(?:enida)?|Rua|Rod(?:ovia)?\.?|Estrada|Pra[çc]a|Alameda|Travessa|Km|CEP)\b",
]


# Cabeçalho da próxima seção ("9 - PROPRIEDADES FÍSICAS E QUÍMICAS"). Vai
# separado porque só vale em CAIXA ALTA - com IGNORECASE ele casaria com
# qualquer "1. Sistema de classificação" e cortaria o valor no meio.
_TERMINADOR_SECAO = re.compile(r"\d{1,2}\s*[-–.]\s*[A-ZÀ-Ú][A-ZÀ-Ú\s\-]{5,}")


def _valor_rotulado(plano: str, rotulos: list[str], limite: int = 300,
                    exigir_dois_pontos: bool = True,
                    terminadores: list[str] | None = None) -> str:
    """Valor que vem depois de um rótulo, até o próximo rótulo conhecido.

    Algumas fichas escrevem o rótulo sem dois-pontos, com o valor na linha
    de baixo ("Detalhes do fornecedor / Fabricante / Empresa X Ltda"). Nesse
    caso a busca é repetida com `exigir_dois_pontos=False`.
    """
    pontuacao = r"\s*:\s*" if exigir_dois_pontos else r"\s*:?\s*"
    for rotulo in rotulos:
        achado = re.search(rf"{rotulo}{pontuacao}", plano, re.IGNORECASE)
        if not achado:
            continue
        resto = plano[achado.end():]
        corte = min(len(resto), limite * 3)
        for terminador in (terminadores or _TERMINADORES):
            fim = re.search(terminador, resto, re.IGNORECASE)
            if fim and 0 < fim.start() < corte:
                corte = fim.start()
        secao = _TERMINADOR_SECAO.search(resto)
        if secao and 0 < secao.start() < corte:
            corte = secao.start()
        valor = _limpar(resto[:corte], limite)
        if len(valor) >= 2 and not valor.lower().startswith(("ver ", "consulte", "vide")):
            return valor
    return ""


def _sem_informacao(valor: str) -> bool:
    """True para 'Não disponível', 'N/A', '-' e afins."""
    v = (valor or "").strip().lower().strip(" .")
    return (not v) or v in {"-", "--", "n/a", "n.a", "n/d", "n.d", "na", "nd"} or v.startswith(
        ("não disponível", "nao disponivel", "não aplicável", "nao aplicavel",
         "não determinado", "nao determinado", "não informado", "nao informado",
         "sem informa", "não estabelecid", "nao estabelecid")
    )


# ---------------------------------------------------------------------
# Campos individuais
# ---------------------------------------------------------------------

# "Nome do produto: XPTO 220" / "Nome comercial ..... XPTO 220"
_ROTULOS_NOME = [
    r"nome\s+comercial",
    r"nome\s+do\s+produto",
    r"identifica[çc][ãa]o\s+do\s+produto",
    r"nome\s+do\s+material",
    r"produto",
]

# No texto achatado o rótulo pode estar partido em várias linhas
# ("Identificação do\nproduto:\nCoagulante...") - depende da versão do pypdf.
_ROTULOS_NOME_PLANO = [
    r"nome\s+d[ao]\s+mistura\s*\(\s*nome\s+comercial\s*\)",
    r"nome\s+comercial",
    r"nome\s+d[ao]\s+produto",
    r"identifica[çc][ãa]o\s+d[ao]\s+produto",
    r"nome\s+d[ao]\s+(?:mistura|material|subst[âa]ncia)",
]

_ROTULOS_FABRICANTE = [
    r"fabricante",
    r"empresa",
    r"fornecedor\s*/\s*fabricante",
    r"raz[ãa]o\s+social",
    r"nome\s+da\s+empresa",
]

# Na NBR 14725 a empresa aparece como "Detalhes do fornecedor" - e o valor
# quase sempre quebra em várias linhas, junto com endereço e telefone.
_ROTULOS_EMPRESA = [
    r"detalhes?\s+d[oa]\s+(?:fornecedor|fabricante|empresa)",
    r"identifica[çc][ãa]o\s+d[ao]\s+(?:empresa|fornecedor|fabricante)",
    r"nome\s+d[ao]\s+(?:empresa|fornecedor|fabricante)",
    r"raz[ãa]o\s+social",
    r"fabricante",
    r"fornecedor",
    r"empresa",
]

_ROTULOS_USO = [
    r"usos?\s+recomendados?\s+do\s+produto\s+qu[íi]mico\s+e\s+restri[çc][õo]es\s+de\s+uso",
    r"usos?\s+recomendados?[^:]{0,60}",
    r"uso\s+(?:previsto|indicado)[^:]{0,40}",
    r"aplica[çc][ãa]o\s+do\s+produto",
]

_ROTULOS_CLASSIFICACAO = [
    r"classifica[çc][ãa]o\s+d[ao]\s+subst[âa]ncia\s+ou\s+mistura",
    r"classifica[çc][ãa]o\s+de\s+perigos?(?:\s+d[oa]\s+(?:produto|mistura))?",
    r"classifica[çc][ãa]o\s+GHS",
    r"classifica[çc][ãa]o\s+d[oa]\s+(?:produto|mistura)",
]

_ROTULOS_FULGOR = [r"ponto\s+de\s+fulgor", r"flash\s*point"]
_ROTULOS_INFLAMABILIDADE = [r"inflamabilidade"]
_ROTULOS_CARCINO = [r"carcinogenicidade", r"carcinogenicidade\s*/\s*mutagenicidade"]


def _valor_apos_rotulo(texto: str, rotulos: list[str], limite: int = 180) -> str:
    """Procura 'rótulo: valor' na mesma linha ou na linha seguinte."""
    for rotulo in rotulos:
        padrao = re.compile(
            rf"{rotulo}\s*[:\-–]?\s*(?:\.{{2,}}\s*)?(.+)", re.IGNORECASE
        )
        for linha in texto.splitlines():
            achado = padrao.search(linha)
            if not achado:
                continue
            valor = _limpar(achado.group(1), limite)
            # descarta rótulo sem valor e ruído de sumário
            if len(valor) >= 2 and not valor.lower().startswith(("ver ", "consulte")):
                return valor
    return ""


# CAS: 2 a 7 dígitos, hífen, 2 dígitos, hífen, 1 dígito
_PADRAO_CAS = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")

# Substâncias que aparecem na FDS mas não identificam o produto
_CAS_IGNORAR = {"7732-18-5"}  # água


def extrair_cas(texto: str) -> str:
    """Devolve o CAS mais provável do produto.

    Em mistura há vários CAS; usamos o de maior ocorrência que não seja água,
    porque o componente principal costuma ser citado mais vezes.
    """
    achados = [c for c in _PADRAO_CAS.findall(texto) if c not in _CAS_IGNORAR]
    if not achados:
        return ""
    contagem: dict[str, int] = {}
    for cas in achados:
        contagem[cas] = contagem.get(cas, 0) + 1
    # empate: mantém a ordem de aparição no documento
    return max(contagem, key=lambda c: (contagem[c], -achados.index(c)))


def _digito_cas_confere(numero: str) -> bool:
    """Confere o dígito verificador do CAS.

    O último dígito é a soma dos demais, cada um multiplicado pela sua
    posição contada da direita, módulo 10. Serve para descartar número de
    telefone, código de norma e data que caem no mesmo formato.
    """
    corpo, _, verificador = numero.rpartition("-")
    digitos = corpo.replace("-", "")
    if not digitos.isdigit() or not verificador.isdigit():
        return False
    soma = sum(int(d) * (i + 1) for i, d in enumerate(reversed(digitos)))
    return soma % 10 == int(verificador)


def extrair_numeros_cas(texto: str) -> list[str]:
    """Todos os números CAS da FDS, na ordem em que aparecem.

    A FDS traz um CAS por substância da composição (seção 3), e a mistura
    costuma ter vários. A água entra na lista aqui - diferente de
    `extrair_cas()`, que procura o componente principal e por isso a
    descarta.

    Só entram números cujo dígito verificador confere, senão qualquer
    "11-22-3" solto no documento viraria um CAS.
    """
    vistos: list[str] = []
    for numero in _PADRAO_CAS.findall(texto):
        if numero not in vistos and _digito_cas_confere(numero):
            vistos.append(numero)
    return vistos


# Frases de perigo (GHS) mapeadas para as classes de risco do sistema.
_FRASES_H = {
    "Inflamável": [r"\bH2(?:0[0-9]|1[0-9]|2[0-6])\b", r"inflam[áa]ve", r"combust[íi]ve"],
    "Corrosivo": [r"\bH31[45]\b", r"\bH318\b", r"\bH290\b", r"corrosiv", r"queimadura severa"],
    "Tóxico": [r"\bH3(?:0[0-9]|1[0-2]|3[0-1])\b", r"\bH37[01]\b", r"\bt[óo]xic"],
    "Perigoso ao Meio Ambiente": [
        r"\bH4(?:00|10|11|12|13|20)\b", r"perigoso ao (?:meio )?ambiente",
        r"ambiente aqu[áa]tic",
    ],
    "Comburente": [r"\bH2(?:70|71|72)\b", r"comburente", r"oxidante"],
    "Irritante": [r"\bH31[567]\b", r"\bH319\b", r"\bH335\b", r"irritaç[ãa]o", r"irritante"],
    "Nocivo": [r"\bH30[2358]\b", r"\bH33[23]\b", r"nociv"],
    "Gás sob pressão": [r"\bH28[0-4]\b", r"g[áa]s sob press[ãa]o"],
}


def _classes_em(trecho: str) -> list[str]:
    encontradas = []
    for classe in CLASSES_RISCO:
        for padrao in _FRASES_H.get(classe, []):
            if re.search(padrao, trecho, re.IGNORECASE):
                encontradas.append(classe)
                break
    return encontradas


def extrair_classes_risco(texto: str) -> list[str]:
    """Classes de risco do produto.

    Procura primeiro na Seção 2 (identificação de perigos), que é onde a norma
    manda declarar. Se nada aparecer ali - acontece quando a numeração das
    seções não segue o padrão, ou quando a ficha usa outro layout - varre o
    documento todo em vez de devolver vazio.
    """
    secao2 = _secao(texto, 2)
    return _classes_em(secao2) or _classes_em(texto)


_ESTADOS = {
    "Líquido": [r"\bl[íi]quido\b"],
    "Sólido": [r"\bs[óo]lido\b", r"\bp[óo]\b", r"gr[âa]nulo"],
    "Gás": [r"\bg[áa]s\b", r"gasoso"],
    "Pasta / Gel": [r"\bpasta\b", r"\bgel\b", r"pastoso"],
    "Aerossol": [r"aeross"],
}


def _estado_em(trecho: str) -> str:
    for estado, padroes in _ESTADOS.items():
        for padrao in padroes:
            if re.search(padrao, trecho, re.IGNORECASE):
                return estado
    return ""


def extrair_estado_fisico(texto: str) -> str:
    """Seção 9 primeiro; se não achar, procura em todo o documento."""
    return _estado_em(_secao(texto, 9)) or _estado_em(texto)


_PADRAO_ONU = re.compile(
    r"\b(?:UN|ONU|N[º°.]?\s*ONU)\s*(?:\([^)]{1,15}\))?\s*[:\-]?\s*(\d{4})\b",
    re.IGNORECASE,
)


def extrair_onu(texto: str) -> str:
    """Seção 14 primeiro; se não achar, procura em todo o documento."""
    for trecho in (_secao(texto, 14), texto):
        achado = _PADRAO_ONU.search(trecho or "")
        if achado:
            return f"UN{achado.group(1)}"
    return ""


# Data de revisão / versão da ficha
# ---------------------------------------------------------------------
# A data aparece de todo jeito: "Data: 03/07/2025", "Data de emissão:
# 27/05/2025", "Data da última revisão: 21/12/2024". Pior: a extração do PDF
# às vezes parte palavras e números ("r evisão", "202 4"), então os padrões
# toleram espaços perdidos e, no fim, há uma varredura do cabeçalho.

_DIA_MES_ANO = r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2}(?:\s?\d)?(?:\s?\d)?)"
_ANO_MES_DIA = r"(\d{4})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})"

_ROTULO_DATA = (
    r"(?:data\s+d[ae]?\s*(?:[úu]ltima\s+)?(?:r\s?e\s?v\s?i\s?s[ãa]o|emiss[ãa]o|"
    r"elabora[çc][ãa]o|atualiza[çc][ãa]o)|r\s?e\s?v\s?i\s?s[ãa]o|revisado\s+em|"
    r"vers[ãa]o\s+de|\bdata)\s*[:\-]?\s*(?:n[º°]?\s*\d+\s*)?"
)


def _para_data(a: str, b: str, c: str, ano_primeiro: bool = False) -> date | None:
    """Monta a data tolerando espaços perdidos dentro dos números."""
    try:
        a, b, c = (int(x.replace(" ", "")) for x in (a, b, c))
    except ValueError:
        return None
    if ano_primeiro:
        ano, mes, dia = a, b, c
    else:
        dia, mes, ano = a, b, c
        if ano < 100:
            ano = 2000 + ano if ano < 70 else 1900 + ano
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def extrair_data_revisao(texto: str) -> date | None:
    """Data de revisão/emissão da ficha."""
    plano = _plano(texto)
    hoje = date.today()

    for padrao, ano_primeiro in (
        (rf"{_ROTULO_DATA}{_DIA_MES_ANO}", False),
        (rf"{_ROTULO_DATA}{_ANO_MES_DIA}", True),
    ):
        for achado in re.finditer(padrao, plano, re.IGNORECASE):
            data = _para_data(*achado.groups(), ano_primeiro=ano_primeiro)
            if data and 1990 <= data.year and data <= hoje:
                return data

    # Último recurso: a primeira data plausível do cabeçalho da ficha.
    for padrao, ano_primeiro in ((_DIA_MES_ANO, False), (_ANO_MES_DIA, True)):
        for achado in re.finditer(padrao, plano[:2500]):
            data = _para_data(*achado.groups(), ano_primeiro=ano_primeiro)
            if data and 1990 <= data.year and data <= hoje:
                return data
    return None


# ---------------------------------------------------------------------
# Inflamável, cancerígeno e ponto de fulgor (exigências da Tenaris)
# ---------------------------------------------------------------------

# Frases H de inflamabilidade e a redação por extenso equivalente.
_SINAIS_INFLAMAVEL = [
    r"\bH2(?:2[0-6]|28|4[12]|50|51|52)\b",
    r"(?:l[íi]quido|s[óo]lido|g[áa]s|aeross[óo]l)\w*\s+(?:e\s+vapor\w*\s+)?"
    r"(?:extremamente\s+|altamente\s+)?inflam[áa]ve",
    r"inflam[áa]ve\w*\s*[,\-–]?\s*(?:categoria|cat\.?)\s*[1-4]",
    r"pirof[óo]ric",
]


def extrair_nome_comercial(texto: str) -> str:
    """Nome comercial do produto (Seção 1 ou cabeçalho da primeira página)."""
    plano = _plano("\n".join(filter(None, [texto[:4000], _secao(texto, 1)])))
    valor = _valor_rotulado(plano, _ROTULOS_NOME_PLANO, limite=120)
    if valor and not _sem_informacao(valor):
        return valor
    # último recurso: a busca linha a linha, que atende fichas fora do padrão
    return _valor_apos_rotulo(
        "\n".join(filter(None, [texto[:3000], _secao(texto, 1)])), _ROTULOS_NOME
    )


def extrair_fabricante(texto: str) -> str:
    """Empresa responsável pelo produto (Seção 1)."""
    plano = _plano("\n".join(filter(None, [texto[:4000], _secao(texto, 1)])))
    for exigir in (True, False):
        valor = _valor_rotulado(plano, _ROTULOS_EMPRESA, limite=120,
                                exigir_dois_pontos=exigir)
        # "Detalhes do fornecedor / Fabricante / Empresa X" deixa o rótulo colado
        valor = re.sub(
            r"^(?:fabricante|fornecedor|empresa|raz[ãa]o\s+social)\b\s*:?\s*",
            "", valor, flags=re.IGNORECASE,
        ).strip()
        if valor and not _sem_informacao(valor):
            return valor
    return ""


def extrair_uso_recomendado(texto: str) -> str:
    """Usos recomendados pelo fabricante (Seção 1) - sugestão de finalidade."""
    plano = _plano("\n".join(filter(None, [texto[:4000], _secao(texto, 1)])))
    for exigir in (True, False):
        valor = _valor_rotulado(plano, _ROTULOS_USO, limite=300,
                                exigir_dois_pontos=exigir)
        # numeração de subseção ("1.4.") gruda no fim do valor
        valor = re.sub(r"\s*\d+(?:\.\d+)*\.?\s*$", "", valor).strip()
        if valor and not _sem_informacao(valor) and not valor.lower().startswith("nenhuma"):
            return valor
    return ""


# A classificação é uma lista ("Corrosivo - Cat. 1; Lesões oculares - Cat. 1"),
# então ela só termina no próximo assunto de verdade - não em cada palavra que
# por acaso também é nome de campo em outra seção.
_FIM_CLASSIFICACAO = [
    r"Sistema\s+de\s+classifica", r"Elementos?\s+d[oe]\s+r[óo]tulo",
    r"Elementos?\s+de\s+rotulagem", r"Pictogramas?", r"Palavras?\s+de\s+advert",
    r"Frases?\s+de\s+(?:perigo|precau)", r"Outros\s+perigos",
    r"Ades[ãa]o\s+ao\s+Sistema", r"Ado[çc][ãa]o\s+do\s+Sistema",
    r"P[áa]gina\s*:",
]


def extrair_classificacao_ghs(texto: str) -> str:
    """Classificação de perigo como a ficha declara (Seção 2)."""
    for trecho in (_secao(texto, 2), texto[:12000]):
        if not trecho:
            continue
        plano = _plano(trecho)
        for exigir in (True, False):
            valor = _valor_rotulado(
                plano, _ROTULOS_CLASSIFICACAO, limite=255,
                exigir_dois_pontos=exigir, terminadores=_FIM_CLASSIFICACAO,
            )
            # "Classificação de acordo com GHS BR (ABNT NBR 14725: 2023)" é
            # cabeçalho, não classificação: pula o que está entre parênteses.
            valor = re.sub(
                r"^(?:classifica[çc][ãa]o\s+)?(?:de\s+)?acordo\s+com[^)]{0,90}\)\s*",
                "", valor, flags=re.IGNORECASE,
            ).strip(" :-")
            # o corte no rótulo seguinte às vezes deixa uma preposição solta
            valor = re.sub(
                r"\s+(?:pel[oa]s?|por|de|do|da|dos|das|e|com|no|na|em|conforme)$",
                "", valor, flags=re.IGNORECASE,
            ).strip(" :;,-")
            if len(valor) >= 4 and not _sem_informacao(valor):
                return _cortar(valor, 255)
    return ""


def _cortar(valor: str, limite: int) -> str:
    """Corta no último separador antes do limite, para não partir palavra."""
    if len(valor) <= limite:
        return valor
    pedaco = valor[:limite]
    quebra = max(pedaco.rfind(";"), pedaco.rfind(","))
    return (pedaco[:quebra] if quebra > limite // 2 else pedaco).strip(" ;,-")


def extrair_ponto_fulgor(texto: str) -> str:
    """Ponto de fulgor, como a ficha declara (Seção 9)."""
    plano = _plano(_secao(texto, 9) or texto)
    return _valor_rotulado(plano, _ROTULOS_FULGOR, limite=60)


def _fulgor_em_celsius(valor: str) -> float | None:
    """Converte '13 °C', '>93 C', '55,5 ºC' num número. None quando não há."""
    achado = re.search(r"(-?\d{1,3}(?:[.,]\d+)?)\s*°?\s*[cC]\b", valor or "")
    if not achado:
        return None
    try:
        return float(achado.group(1).replace(",", "."))
    except ValueError:
        return None


def extrair_inflamavel(texto: str) -> str:
    """'SIM', 'NAO' ou '' quando a ficha não permite concluir."""
    plano = _plano(texto)
    secao2 = _plano(_secao(texto, 2))
    fulgor = _fulgor_em_celsius(extrair_ponto_fulgor(texto))

    for padrao in _SINAIS_INFLAMAVEL:
        if re.search(padrao, secao2 or plano, re.IGNORECASE):
            return "SIM"
    # Um ponto de fulgor medido até 93 °C caracteriza líquido inflamável (GHS).
    if fulgor is not None and fulgor <= 93:
        return "SIM"

    # Sem sinal de inflamabilidade: só concluímos "Não" quando a ficha
    # realmente declarou a classificação de perigos.
    classificacao = _valor_rotulado(plano, _ROTULOS_CLASSIFICACAO, limite=400)
    inflamabilidade = _valor_rotulado(
        _plano(_secao(texto, 9) or texto), _ROTULOS_INFLAMABILIDADE, limite=120
    )
    sem_perigo_de_fogo = re.search(
        r"n[ãa]o\s+(?:é\s+esperado\s+que\s+o\s+produto\s+)?(?:apresent\w*|possui\w*|oferec\w*)"
        r"[^.]{0,60}(?:perigo\s+de\s+)?inc[êe]ndio",
        plano,
        re.IGNORECASE,
    )
    if classificacao or sem_perigo_de_fogo or inflamabilidade:
        return "NAO"
    return ""


_SINAIS_CANCERIGENO = [
    r"\bH35[01]\b",
    r"pode\s+(?:provocar|causar)\s+c[âa]ncer",
    r"suspeito\s+de\s+(?:provocar|causar)\s+c[âa]ncer",
    r"carcinogenicidade\s*[-–:]?\s*categoria\s*(?:1|2)",
]

_NEGATIVAS = (
    r"n[ãa]o\s+é\s+esperado", r"n[ãa]o\s+(?:é\s+)?classificad", r"n[ãa]o\s+apresenta",
    r"n[ãa]o\s+atende\s+aos\s+crit[ée]rios", r"n[ãa]o\s+h[áa]\s+(?:dados|evid)",
    r"n[ãa]o\s+cancer[íi]gen", r"n[ãa]o\s+carcinog",
)


def extrair_cancerigeno(texto: str) -> str:
    """'SIM', 'NAO' ou '' - a Seção 11 é quem responde."""
    plano = _plano(texto)
    for padrao in _SINAIS_CANCERIGENO:
        if re.search(padrao, plano, re.IGNORECASE):
            return "SIM"

    campo = _valor_rotulado(
        _plano(_secao(texto, 11) or texto), _ROTULOS_CARCINO, limite=300
    )
    if campo and not _sem_informacao(campo):
        if any(re.search(p, campo, re.IGNORECASE) for p in _NEGATIVAS):
            return "NAO"
    return ""


# ---------------------------------------------------------------------
# Categoria química (lista do sistema)
# ---------------------------------------------------------------------

_PISTAS_CATEGORIA = {
    "Ácido": ["ácido", "acido", "acid "],
    "Base / Álcali": ["hidróxido", "hidroxido", "soda cáustica", "soda caustica",
                      "alcalin", "álcali", "alcali", "amônia", "amonia"],
    "Solvente": ["solvente", "thinner", "diluente", "acetona", "xileno", "tolueno",
                 "álcool", "alcool", "isopropanol"],
    "Tinta / Revestimento": ["tinta", "verniz", "primer", "esmalte", "revestimento",
                             "pintura", "demarca", "sinalizaç"],
    "Óleo / Lubrificante": ["lubrific", "graxa", "óleo", "oleo", "fluido hidr"],
    "Gás": ["gás comprimido", "gas comprimido", "acetileno", "oxigênio", "oxigenio",
            "nitrogênio", "nitrogenio", "argônio", "argonio"],
    "Detergente / Limpeza": ["detergente", "desengraxa", "sabão", "sabao",
                             "limpador", "limpeza"],
    "Reagente de laboratório": ["reagente", "p.a.", "grau analítico", "grau analitico",
                                "titulaç", "padrão analítico"],
    "Aditivo de processo": ["coagulante", "floculante", "biocida", "inibidor",
                            "antiespumante", "aditivo", "tratamento de água",
                            "tratamento de agua", "dispersante"],
    "Outros": ["raticida", "rodenticida", "inseticida", "fungicida", "herbicida",
               "praguicida", "controle de roedores", "controle de pragas"],
}


def extrair_categoria(nome: str = "", uso: str = "", texto: str = "") -> str:
    """Categoria química provável.

    Olha o nome do produto e o uso recomendado - não o documento inteiro,
    onde a lista de ingredientes cheia de "ácido" confundiria tudo.
    """
    trecho = _plano(f"{nome} {uso} {texto[:400]}").lower()
    for categoria, pistas in _PISTAS_CATEGORIA.items():
        for pista in pistas:
            if pista in trecho:
                return categoria
    return ""


def extrair_tipo_produto(nome: str = "", uso: str = "", texto: str = "") -> str:
    """Tipo de produto provável, pelo nome e pelo uso recomendado."""
    trecho = sem_acento(_plano(f"{nome} {uso} {texto[:1500]}")).lower()
    # Só pistas inequívocas; a limpeza de áreas comuns x industrial não dá
    # para decidir pelo texto, então fica para o solicitante escolher.
    # A ordem importa: o primeiro tipo com pista no texto vence.
    pistas = {
        "Tratamento de água e efluentes": [
            "tratamento de agua", "tratamento de efluente", "coagulante",
            "floculante", "biocida", "antiincrustante",
        ],
        "Tintas e revestimentos": ["tinta", "verniz", "revestimento", "primer", "esmalte"],
        "Adesivos e selantes": ["adesivo", "selante", "silicone", "cola "],
        "Produtos para soldagem": ["soldagem", "eletrodo", "solda "],
        "Gases industriais e analíticos": [
            "gas comprimido", "gases industriais", "oxigenio", "nitrogenio",
            "argonio", "acetileno",
        ],
        "Produtos para construção civil": ["cimento", "argamassa", "concreto", "rejunte"],
        "Combustíveis e derivados": [
            "combustivel", "gasolina", "diesel", "querosene", "etanol",
        ],
        # "desengraxa" contém "graxa": precisa vir antes dos lubrificantes.
        "Produtos de limpeza - áreas industrial": ["desengraxa"],
        "Graxa e oleos Lubrificantes": [
            "lubrific", "graxa", "oleo de corte", "oleo hidr", "fluido hidr",
            "hidraulic", "emuls", "soluvel de corte",
        ],
        "Solventes e diluentes": [
            "solvente", "thinner", "diluente", "acetona", "alcool",
        ],
    }
    for tipo, termos in pistas.items():
        if tipo not in TIPOS_PRODUTO:
            continue
        if any(termo in trecho for termo in termos):
            return tipo
    return ""


# ---------------------------------------------------------------------
# Seções da FDS
# ---------------------------------------------------------------------

def _secao(texto: str, numero: int) -> str:
    """Recorta o trecho de uma seção numerada da FDS."""
    inicio = re.search(
        rf"(?:^|\n)\s*(?:SE[ÇC][ÃA]O\s*)?{numero}\s*[.\-:)]\s*\S", texto, re.IGNORECASE
    )
    if not inicio:
        return ""
    fim = re.search(
        rf"(?:^|\n)\s*(?:SE[ÇC][ÃA]O\s*)?{numero + 1}\s*[.\-:)]\s*\S",
        texto[inicio.end():],
        re.IGNORECASE,
    )
    trecho = texto[inicio.start():]
    trecho = trecho[: fim.start()] if fim else trecho[:6000]
    # Em várias fichas os cabeçalhos saem fora de ordem na extração do PDF e
    # o recorte vira só o título. Seção de verdade não tem 200 caracteres.
    return trecho if len(trecho) >= 200 else ""


# ---------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------

CAMPOS_AUTOMATICOS = (
    "nome_comercial",
    "fabricante",
    "numero_cas",
    "categoria",
    "tipo_produto",
    "estado_fisico",
    "aplicacao",
    "classificacao_ghs",
    "onu_numero",
    "inflamavel",
    "cancerigeno",
    "ponto_fulgor",
    "riscos",
    "data_revisao_fds",
)


def extrair(texto: str) -> dict:
    """Extrai o que der do texto da FDS. Campos ausentes voltam vazios."""
    # A identificação pode estar na Seção 1 OU no cabeçalho da primeira página,
    # em tabela, antes de qualquer numeração de seção. Procuramos nos dois.
    secao1 = "\n".join(filter(None, [texto[:3000], _secao(texto, 1)]))
    riscos = extrair_classes_risco(texto)
    data = extrair_data_revisao(texto)

    nome = extrair_nome_comercial(texto)
    uso = extrair_uso_recomendado(texto)
    fulgor = extrair_ponto_fulgor(texto)

    categoria = extrair_categoria(nome, uso, texto)
    # Sem pista clara, o tipo volta vazio para a pessoa escolher na lista.
    tipo = extrair_tipo_produto(nome, uso, texto)

    return {
        "nome_comercial": nome,
        "fabricante": extrair_fabricante(texto) or _valor_apos_rotulo(
            secao1, _ROTULOS_FABRICANTE
        ),
        "numero_cas": extrair_cas(texto),
        "categoria": categoria,
        "tipo_produto": tipo,
        "estado_fisico": extrair_estado_fisico(texto),
        "aplicacao": uso,
        "classificacao_ghs": extrair_classificacao_ghs(texto) or "; ".join(riscos),
        "riscos": riscos,
        "onu_numero": extrair_onu(texto),
        "inflamavel": extrair_inflamavel(texto),
        "cancerigeno": extrair_cancerigeno(texto),
        # "Não disponível" não é resposta: melhor deixar em branco para a pessoa.
        "ponto_fulgor": "" if _sem_informacao(fulgor) else fulgor,
        "data_revisao_fds": data.isoformat() if data else "",
    }


def extrair_de_pdf(conteudo: bytes) -> tuple[dict, list[str], str | None]:
    """Lê o PDF e extrai os dados.

    Devolve (dados, campos_preenchidos, aviso). `aviso` vem preenchido quando
    o documento não permite leitura automática - o formulário segue utilizável,
    só inteiramente manual.
    """
    texto = texto_do_pdf(conteudo)
    if not texto.strip():
        return (
            {c: "" for c in CAMPOS_AUTOMATICOS},
            [],
            "Não foi possível ler texto deste PDF. Provavelmente é um documento "
            "escaneado (imagem). Preencha os campos manualmente e, se possível, "
            "peça ao fabricante a FDS em PDF digital.",
        )
    dados = extrair(texto)
    preenchidos = [c for c in CAMPOS_AUTOMATICOS if dados.get(c)]
    aviso = None
    if len(preenchidos) <= 1:
        aviso = (
            "A leitura automática encontrou pouca informação nesta ficha. "
            "Confira e complete os campos manualmente."
        )
    return dados, preenchidos, aviso
