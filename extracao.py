"""Extração automática de dados da Ficha de Dados de Segurança (FDS).

Lê o texto do PDF localmente - o arquivo NÃO sai da rede interna - e procura
as informações nas seções previstas pela ABNT NBR 14725:

    Seção 1 - Identificação do produto e do fornecedor
    Seção 2 - Identificação de perigos (classificação GHS, frases H)
    Seção 3 - Composição e informações sobre os ingredientes (nº CAS)
    Seção 9 - Propriedades físicas e químicas (estado físico)
    Seção 14 - Informações sobre transporte (número ONU)

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

from models import CLASSES_RISCO, TIPOS_PRODUTO

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
    valor = re.sub(r"\s+", " ", valor).strip(" .:;-\t")
    return valor[:limite].strip()


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

_ROTULOS_FABRICANTE = [
    r"fabricante",
    r"empresa",
    r"fornecedor\s*/\s*fabricante",
    r"raz[ãa]o\s+social",
    r"nome\s+da\s+empresa",
]


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


_PADRAO_ONU = re.compile(r"\b(?:UN|ONU|N[º°.]?\s*ONU)\s*[:\-]?\s*(\d{4})\b", re.IGNORECASE)


def extrair_onu(texto: str) -> str:
    """Seção 14 primeiro; se não achar, procura em todo o documento."""
    for trecho in (_secao(texto, 14), texto):
        achado = _PADRAO_ONU.search(trecho or "")
        if achado:
            return f"UN{achado.group(1)}"
    return ""


# Data de revisão / versão da ficha
_PADROES_DATA = [
    re.compile(
        r"(?:data\s+d[ae]\s+(?:revis[ãa]o|emiss[ãa]o|elabora[çc][ãa]o)|"
        r"revis[ãa]o|revisado\s+em|vers[ãa]o\s+de)\s*[:\-]?\s*"
        r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:data\s+d[ae]\s+(?:revis[ãa]o|emiss[ãa]o)|revis[ãa]o)\s*[:\-]?\s*"
        r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})",
        re.IGNORECASE,
    ),
]


def extrair_data_revisao(texto: str) -> date | None:
    for i, padrao in enumerate(_PADROES_DATA):
        achado = padrao.search(texto)
        if not achado:
            continue
        a, b, c = (int(x) for x in achado.groups())
        try:
            if i == 0:
                ano = c if c > 99 else (2000 + c if c < 70 else 1900 + c)
                return date(ano, b, a)
            return date(a, b, c)
        except ValueError:
            continue
    return None


def extrair_tipo_produto(texto: str) -> str:
    """Chuta o tipo de produto pelas palavras do início da ficha."""
    trecho = texto[:3000].lower()
    pistas = {
        "Hidráulico": ["fluido hidr", "óleo hidr", "oleo hidr", "hidráulic"],
        "Emulsão": ["emuls", "solúvel de corte", "soluvel de corte"],
        "Lubrificante": ["lubrific", "graxa", "óleo de corte", "oleo de corte"],
        "Limpeza": ["desengraxa", "detergente", "limpeza", "sabão", "sabao"],
        "Solvente": ["solvente", "thinner", "diluente", "acetona", "álcool", "alcool"],
    }
    for tipo in TIPOS_PRODUTO:
        for pista in pistas.get(tipo, []):
            if pista in trecho:
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
    return trecho[: fim.start()] if fim else trecho[:6000]


# ---------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------

CAMPOS_AUTOMATICOS = (
    "nome_comercial",
    "fabricante",
    "numero_cas",
    "classificacao_ghs",
    "estado_fisico",
    "onu_numero",
    "tipo_produto",
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
    return {
        "nome_comercial": _valor_apos_rotulo(secao1, _ROTULOS_NOME),
        "fabricante": _valor_apos_rotulo(secao1, _ROTULOS_FABRICANTE),
        "numero_cas": extrair_cas(texto),
        "classificacao_ghs": "; ".join(riscos),
        "riscos": riscos,
        "estado_fisico": extrair_estado_fisico(texto),
        "onu_numero": extrair_onu(texto),
        "tipo_produto": extrair_tipo_produto(texto),
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
