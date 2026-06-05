"""Utilidades de ingesta compartidas por los adapters Colombia / España / Terceros.

Las dos funciones centrales (`parse_es_number` y `normalizar_nif`) están fijadas por
el prompt y cubiertas por tests en `backend/tests/test_utils.py`. No cambiar su
contrato sin actualizar los tests.
"""
from __future__ import annotations

import re
import unicodedata

__all__ = [
    "parse_es_number",
    "normalizar_nif",
    "limpiar_concepto",
    "es_codigo_cuenta_es",
    "ACCOUNT_ES_RE",
]

# Código de cuenta DELSOL: 3 dígitos . 1 . 1 . 3 dígitos  ->  "700.0.0.101"
ACCOUNT_ES_RE = re.compile(r"^(\d{3}\.\d\.\d\.\d{3})\b\s*(.*)$")


def parse_es_number(v) -> float:
    """Convierte un importe a float, tolerando:

    - números nativos de Excel (int/float) -> tal cual
    - formato español en texto: '4.500.000,00' (punto miles, coma decimal)
    - signo negativo final estilo contable: '4.500.000,00-'
    - formato anglosajón ya numérico: '881768964.31'

    Devuelve 0.0 ante valores vacíos o no parseables.
    """
    if v is None:
        return 0.0
    if isinstance(v, bool):  # bool es subclase de int; evitar True->1.0 accidental
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    neg = s.endswith("-")
    s = s.rstrip("-").strip()

    # Heurística de separadores: si hay coma, asumimos formato español
    # (punto = miles, coma = decimal). Si no hay coma, el punto es decimal.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    # si no hay coma se deja el punto como decimal (formato anglosajón / nativo)

    try:
        f = float(s)
    except ValueError:
        return 0.0
    return -f if neg else f


def normalizar_nif(nif) -> str:
    """Normaliza NIF (España) / NIT (Colombia) a una clave de cruce estable.

    - Quita espacios y puntos.
    - Quita dígito de verificación tras guión ('-5', '-N').
    - Quita letra de control final de NIF español de persona física ('901207879S').
    - Conserva NIF español de empresa que EMPIEZA por letra ('B12550877').
    """
    if nif is None:
        return ""
    s = re.sub(r"[\s.]", "", str(nif).upper())
    s = re.sub(r"-[0-9A-Z]$", "", s)  # quitar dígito/letra de verificación tras guión
    s = re.sub(r"(?<=\d)[A-Z]$", "", s)  # letra final SOLO si va precedida de dígito
    return s.strip()


_ACCENTS = str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN")
_FECHA_PREFIJO_RE = re.compile(r"^\s*\d{1,2}\s*[/-]\s*\d{2,4}\s+")
_FRA_SUFIJO_RE = re.compile(r"\bS?\.?\s*FRA\.?\s*:?.*$", re.IGNORECASE)
_NO_ALNUM_RE = re.compile(r"[^A-Z0-9 ]+")
_MULTISPACE_RE = re.compile(r"\s+")


def limpiar_concepto(concepto) -> str:
    """Normaliza un texto de concepto ES para fuzzy-match contra nombre fiscal.

    Quita prefijo de fecha 'MM/YYYY', sufijo de factura 'S. FRA: XXXX',
    acentos, signos, y colapsa espacios. Devuelve mayúsculas.
    """
    if concepto is None:
        return ""
    s = str(concepto).upper().strip()
    s = _FECHA_PREFIJO_RE.sub("", s)
    s = _FRA_SUFIJO_RE.sub("", s)
    s = s.translate(_ACCENTS)
    # normaliza cualquier acento residual vía unicode
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = _NO_ALNUM_RE.sub(" ", s)
    s = _MULTISPACE_RE.sub(" ", s).strip()
    return s


def es_codigo_cuenta_es(texto) -> str | None:
    """Devuelve el código de cuenta ES si `texto` empieza por uno; si no, None."""
    if texto is None:
        return None
    m = ACCOUNT_ES_RE.match(str(texto).strip())
    return m.group(1) if m else None
