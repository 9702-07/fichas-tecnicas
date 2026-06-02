# -*- coding: utf-8 -*-
"""
Agrupación de parámetros para la ficha técnica.

Porta la lógica de `resolver_grupos` del proyecto "Plan de muestreo"
(familias_parametros.json + mapeo_parametros.json) y le añade:

  1. Una capa de NORMALIZACIÓN de nombres, para que los parámetros tal como
     vienen en el CDC (con acentos, mayúsculas/minúsculas, sufijos y hasta
     artefactos de OCR como "C obalto" / "Níqu el") casen con las claves del
     mapeo.
  2. Un FORMATO LIMPIO de salida (Tipo Título, sin asteriscos de acreditación).

Regla de oro (igual que el plan de muestreo): un grupo combinado solo se usa
si TODOS sus miembros están presentes; si no, cada token cae a su grupo
individual. Las entradas marcadas "SKIP" se descartan. Los parámetros que no
están en ningún mapeo se conservan tal cual (no se pierde nada).
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_DIR = Path(__file__).resolve().parent
_MAPEO_PATH = _DIR / "mapeo_parametros.json"
_FAMILIAS_PATH = _DIR / "familias_parametros.json"

# ---------------------------------------------------------------------------
# Orden canónico de los grupos (de generar_plan.py · ORDEN_GRUPOS)
# ---------------------------------------------------------------------------
ORDEN_GRUPOS = [
    "COLIF.FECALES*/TOTALES* - E.COLI* - BACT.HETEROTROFAS* - VIRUS",
    "COLIFORMES FECALES*-TOTALES*",
    "COLIF.FECALES*/TOTALES* - E.COLI* - BACT.HETEROTROFAS*",
    "COLIF.TOTALES / FECALES - E.COLI",
    "COLIF.FECALES*/TOTALES* - BACT.HETEROTROFAS*",
    "COLIFORMES TOTALES* - BACT.HETEROTROFAS*",
    "ESCHERICHIA COLI*",
    "BACTERIAS HETEROTROFAS*",
    "ORGANISMOS DE VIDA LIBRE (O.V.L)",
    "HUEVOS Y LARVAS HELMINTOS",
    "FORMAS PARASITARIAS",
    "PSEUDOMONAS AERUGINOSA",
    "Recuento de microorganismos aerobios mesófilos",
    "Recuento de mohos y levaduras",
    "ENUMERACIÓN DE BACTERIAS ANAEROBIAS SULFITO REDUCTORES",
    "ESTREPTOCOCOS FECALES",
    "ENUMERACION DE ENTEROCOCOS",
    "COLOR - OLOR - SABOR",
    "PH* - T° - CONDUCTIVIDAD - TURBIDEZ - CLORO LIBRE - O.D (Campo)",
    "PH* - TEMPERATURA* - CONDUCTIVIDAD - CLORO LIBRE",
    "PH* - CONDUCTIVIDAD* - CLORO LIBRE",
    "PH* - TEMPERATURA* - CONDUCTIVIDAD",
    "PH* - TEMPERATURA* - CLORO LIBRE (Campo)",
    "PH* - TEMPERATURA*",
    "PH* - CONDUCTIVIDAD*",
    "PH* - CLORO LIBRE",
    "PH*",
    "TEMPERATURA* (Campo)",
    "TEMPERATURA",
    "CONDUCTIVIDAD*",
    "TURBIEDAD*",
    "CLORO LIBRE",
    "OXIGENO DIUELTO (O.D)",
    "SOLIDOS TOTALES DISUELTOS (TDS)*",
    "SOLIDOS SUSPENDIDOS TOTALES (TSS)*",
    "SOLIDOS TOTALES (ST)*",
    "SOLIDOS SEDIMENTABLES (SS)*",
    "DEMANDA BIOQUIMICA DE OXIGENO (DBO5)*",
    "DEMANDA QUIMICA DE OXIGENO (DQO)*",
    "CLORUROS - SULFATOS* - FLUOR",
    "CLORUROS* - SULFATOS*",
    "CLORUROS*",
    "SULFATOS*",
    "FLUOR",
    "CLORITO - CLORATO - NITRATOS - NITRITOS - BROMATOS",
    "CLORITO - CLORATO Y BROMATOS",
    "CLORITO - CLORATO ",
    "NITRATOS - NITRITOS",
    "NITRATOS",
    "NITRITOS",
    "NITROGENO AMONIACAL*",
    "NITROGENO ORGANICO Kjeldahl",
    "NITROGENO TOTAL",
    "FOSFORO TOTAL",
    "FOSFATOS",
    "FLUORUROS ",
    "ALCALINIDAD*",
    "SULFUROS*",
    "AMONIACO",
    "AMONIO (NITROGENO AMONIACAL)",
    "SILICE, SILICATO",
    "POTASIO - SODIO",
    "CALCIO - MAGNESIO - POTASIO - SODIO",
    "METALES TOTALES AA* e ICP-OES - DUREZA TOTAL",
    "METALES TOTALES AA* e ICP-OES",
    "DUREZA TOTAL",
    "DUREZA CALCICA",
    "CIANURO TOTAL",
    "CN- TOTAL* (CIANURO TOTAL)",
    "CROMO HEXAVALENTE*",
    "MERCURIO",
    "ACEITES Y GRASAS*",
    "Hidrocarburos totales (TPH; F2; F3)",
    "PCBs",
    "MCPA",
    "MICROSISTINA - LR",
    "Detergentes SAAM",
    "ORGANICOS - INORGANICOS",
]

# ---------------------------------------------------------------------------
# Etiquetas limpias (grupo canónico → nombre legible Tipo Título, sin *)
# Solo se curan los grupos frecuentes; el resto cae al titlecase automático.
# ---------------------------------------------------------------------------
CLEAN_LABELS = {
    "COLIF.FECALES*/TOTALES* - E.COLI* - BACT.HETEROTROFAS* - VIRUS":
        "Coliformes Totales y Fecales - E. Coli - Bacterias Heterótrofas - Virus",
    "COLIF.FECALES*/TOTALES* - E.COLI* - BACT.HETEROTROFAS*":
        "Coliformes Totales y Fecales - E. Coli - Bacterias Heterótrofas",
    "COLIF.FECALES*/TOTALES* - BACT.HETEROTROFAS*":
        "Coliformes Totales y Fecales - Bacterias Heterótrofas",
    "COLIF.TOTALES / FECALES - E.COLI":
        "Coliformes Totales y Fecales - E. Coli",
    "COLIFORMES FECALES*-TOTALES*":
        "Coliformes Totales y Fecales",
    "COLIFORMES TOTALES* - BACT.HETEROTROFAS*":
        "Coliformes Totales - Bacterias Heterótrofas",
    "ESCHERICHIA COLI*": "Escherichia Coli",
    "BACTERIAS HETEROTROFAS*": "Bacterias Heterótrofas",
    "ORGANISMOS DE VIDA LIBRE (O.V.L)": "Organismos de Vida Libre (O.V.L.)",
    "HUEVOS Y LARVAS HELMINTOS": "Huevos y Larvas de Helmintos",
    "FORMAS PARASITARIAS": "Formas Parasitarias",
    "PSEUDOMONAS AERUGINOSA": "Pseudomonas Aeruginosa",
    "ESTREPTOCOCOS FECALES": "Estreptococos Fecales",
    "ENUMERACION DE ENTEROCOCOS": "Enumeración de Enterococos",
    "COLOR - OLOR - SABOR": "Color - Olor - Sabor",
    "PH* - T° - CONDUCTIVIDAD - TURBIDEZ - CLORO LIBRE - O.D (Campo)":
        "pH - Temperatura - Conductividad - Turbidez - Cloro Libre - O.D. (Campo)",
    "PH* - TEMPERATURA* - CONDUCTIVIDAD - CLORO LIBRE":
        "pH - Temperatura - Conductividad - Cloro Libre",
    "PH* - CONDUCTIVIDAD* - CLORO LIBRE": "pH - Conductividad - Cloro Libre",
    "PH* - TEMPERATURA* - CONDUCTIVIDAD": "pH - Temperatura - Conductividad",
    "PH* - TEMPERATURA* - CLORO LIBRE (Campo)": "pH - Temperatura - Cloro Libre (Campo)",
    "PH* - TEMPERATURA*": "pH - Temperatura",
    "PH* - CONDUCTIVIDAD*": "pH - Conductividad",
    "PH* - CLORO LIBRE": "pH - Cloro Libre",
    "PH*": "pH",
    "TEMPERATURA* (Campo)": "Temperatura (Campo)",
    "TEMPERATURA": "Temperatura",
    "CONDUCTIVIDAD*": "Conductividad",
    "TURBIEDAD*": "Turbidez",
    "CLORO LIBRE": "Cloro Libre",
    "OXIGENO DIUELTO (O.D)": "Oxígeno Disuelto (O.D.)",
    "SOLIDOS TOTALES DISUELTOS (TDS)*": "Sólidos Totales Disueltos (TDS)",
    "SOLIDOS SUSPENDIDOS TOTALES (TSS)*": "Sólidos Suspendidos Totales (TSS)",
    "SOLIDOS TOTALES (ST)*": "Sólidos Totales (ST)",
    "SOLIDOS SEDIMENTABLES (SS)*": "Sólidos Sedimentables (SS)",
    "DEMANDA BIOQUIMICA DE OXIGENO (DBO5)*": "Demanda Bioquímica de Oxígeno (DBO5)",
    "DEMANDA QUIMICA DE OXIGENO (DQO)*": "Demanda Química de Oxígeno (DQO)",
    "CLORUROS - SULFATOS* - FLUOR": "Cloruros - Sulfatos - Flúor",
    "CLORUROS* - SULFATOS*": "Cloruros - Sulfatos",
    "CLORUROS*": "Cloruros",
    "SULFATOS*": "Sulfatos",
    "FLUOR": "Flúor",
    "CLORITO - CLORATO - NITRATOS - NITRITOS - BROMATOS":
        "Clorito - Clorato - Nitratos - Nitritos - Bromatos",
    "CLORITO - CLORATO Y BROMATOS": "Clorito - Clorato y Bromatos",
    "CLORITO - CLORATO ": "Clorito - Clorato",
    "NITRATOS - NITRITOS": "Nitratos - Nitritos",
    "NITRATOS": "Nitratos",
    "NITRITOS": "Nitritos",
    "NITROGENO AMONIACAL*": "Nitrógeno Amoniacal",
    "NITROGENO ORGANICO Kjeldahl": "Nitrógeno Orgánico Kjeldahl",
    "NITROGENO TOTAL": "Nitrógeno Total",
    "FOSFORO TOTAL": "Fósforo Total",
    "FOSFATOS": "Fosfatos",
    "FLUORUROS ": "Fluoruros",
    "ALCALINIDAD*": "Alcalinidad",
    "SULFUROS*": "Sulfuros",
    "AMONIACO": "Amoníaco",
    "AMONIO (NITROGENO AMONIACAL)": "Amonio (Nitrógeno Amoniacal)",
    "SILICE, SILICATO": "Sílice / Silicato",
    "POTASIO - SODIO": "Potasio - Sodio",
    "CALCIO - MAGNESIO - POTASIO - SODIO": "Calcio - Magnesio - Potasio - Sodio",
    "METALES TOTALES AA* e ICP-OES - DUREZA TOTAL": "METALES TOTALES AA* e ICP-OES - DUREZA TOTAL",
    "METALES TOTALES AA* e ICP-OES": "METALES TOTALES AA* e ICP-OES",
    "DUREZA TOTAL": "Dureza Total",
    "DUREZA CALCICA": "Dureza Cálcica",
    "CIANURO TOTAL": "Cianuro Total",
    "CN- TOTAL* (CIANURO TOTAL)": "Cianuro Total",
    "CROMO HEXAVALENTE*": "Cromo Hexavalente",
    "MERCURIO": "Mercurio",
    "ACEITES Y GRASAS*": "Aceites y Grasas",
    "Hidrocarburos totales (TPH; F2; F3)": "Hidrocarburos Totales (TPH; F2; F3)",
    "PCBs": "PCBs",
    "MCPA": "MCPA",
    "MICROSISTINA - LR": "Microcistina-LR",
    "Detergentes SAAM": "Detergentes (SAAM)",
    "ORGANICOS - INORGANICOS": "Orgánicos - Inorgánicos",
}

# ---------------------------------------------------------------------------
# Normalización para emparejar nombres
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    """Quita acentos, signos y espacios; deja solo A-Z0-9 en mayúsculas.
    Absorbe variantes de extracción: 'C obalto'→'COBALTO', 'Níqu el'→'NIQUEL',
    'Cianuro total'/'CIANURO TOTAL'→'CIANUROTOTAL'.
    """
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


# ---------------------------------------------------------------------------
# Carga de datos + índices normalizados (una sola vez)
# ---------------------------------------------------------------------------
with open(_MAPEO_PATH, encoding="utf-8") as _f:
    _MAPEO: Dict[str, str] = json.load(_f)
with open(_FAMILIAS_PATH, encoding="utf-8") as _f:
    _FAMILIAS: List[dict] = json.load(_f)["familias"]
# Snapshot COMPLETO de la hoja PARAMETROS del Excel (todas las agrupaciones,
# nombres exactos, en el orden del Excel). Alimenta el desplegable del catálogo.
with open(_DIR / "catalogo_excel.json", encoding="utf-8") as _f:
    _CATALOGO_EXCEL: List[str] = json.load(_f)

# mapeo directo: norm(parametro) → grupo
_MAPEO_NORM: Dict[str, str] = {_norm(k): g for k, g in _MAPEO.items()}

# Reglas adicionales específicas del CDC de Fichas. El CDC desglosa el conteo
# parasitológico por taxón/especie (p. ej. "Nemátodos - Ascaris sp."), mientras
# que las cotizaciones del plan lo listan como una sola línea ("Numeración de
# Huevos y Larvas de Helmintos"). Nemátodos, céstodos, tremátodos y
# acantocéfalos son helmintos → se pliegan en el mismo grupo.
_EXTRA_MAPEO = {
    "Nematodos": "HUEVOS Y LARVAS HELMINTOS",
    "Cestodos": "HUEVOS Y LARVAS HELMINTOS",
    "Trematodos": "HUEVOS Y LARVAS HELMINTOS",
    "Acantocefalos": "HUEVOS Y LARVAS HELMINTOS",
    "Larvas de Helmintos": "HUEVOS Y LARVAS HELMINTOS",
    "Huevos de Helmintos": "HUEVOS Y LARVAS HELMINTOS",
}
for _ek, _eg in _EXTRA_MAPEO.items():
    _MAPEO_NORM.setdefault(_norm(_ek), _eg)

# Override (pedido del cliente): cuando hay metales, se agrupan en
# "METALES TOTALES AA* e ICP-OES" SIN incluir la dureza total. Todo lo que el
# mapeo enviaba al grupo combinado pasa al de metales solos, y la dureza total
# se reporta como su propio grupo "DUREZA TOTAL".
_GRUPO_METALES_CON_DUREZA = "METALES TOTALES AA* e ICP-OES - DUREZA TOTAL"
_GRUPO_METALES = "METALES TOTALES AA* e ICP-OES"
for _nk, _g in list(_MAPEO_NORM.items()):
    if _g == _GRUPO_METALES_CON_DUREZA:
        _MAPEO_NORM[_nk] = _GRUPO_METALES
# La dureza total NO va con los metales: grupo propio.
_MAPEO_NORM[_norm("Dureza total")] = "DUREZA TOTAL"

# Umbral de metales: 1 metal → se muestra su nombre individual; 2 o más →
# se agrupan en "METALES TOTALES AA* e ICP-OES". _METAL_DISPLAY guarda el
# nombre de presentación de cada metal (norm → nombre limpio del mapeo).
_UMBRAL_METALES = 2
_DUREZA_NORM = _norm("Dureza total")
_METAL_DISPLAY: Dict[str, str] = {}
for _mk, _mg in _MAPEO.items():
    if _mg in (_GRUPO_METALES_CON_DUREZA, _GRUPO_METALES):
        _mnk = _norm(_mk)
        if _mnk == _DUREZA_NORM:
            continue
        _METAL_DISPLAY[_mnk] = _mk.strip()

# familias: por cada familia, lista de (norm(parametro), token)
_FAM_NORM: List[List[Tuple[str, str]]] = [
    [(_norm(k), tok) for k, tok in fam["individual_a_token"].items()]
    for fam in _FAMILIAS
]

_MIN_PREFIX = 4  # longitud mínima de clave para permitir match por prefijo


def _match_in_pairs(npar: str, pairs: List[Tuple[str, str]]) -> Optional[str]:
    """Devuelve el valor asociado: match exacto y, si no, prefijo más largo."""
    for nk, val in pairs:
        if nk == npar:
            return val
    best: Optional[str] = None
    best_len = 0
    for nk, val in pairs:
        if len(nk) >= _MIN_PREFIX and npar.startswith(nk) and len(nk) > best_len:
            best, best_len = val, len(nk)
    return best


def _match_mapeo(npar: str) -> Optional[str]:
    return _match_in_pairs(npar, list(_MAPEO_NORM.items()))


def _clean_label(grupo: str) -> str:
    """Devuelve el nombre del grupo EXACTO como el Excel/macros (solo normaliza
    los espacios). El cliente pidió que el desplegable Y la agrupación automática
    coincidan 1:1 con su sistema, por eso se conservan tal cual (MAYÚSCULAS, *).
    (CLEAN_LABELS quedó en desuso al pasar a 'nombres exactos del Excel'.)"""
    return re.sub(r"\s+", " ", str(grupo)).strip()


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------
def agrupar_parametros(nombres: List[str]) -> List[str]:
    """
    Agrupa la lista de parámetros del CDC según familias + mapeo, y devuelve
    los nombres de grupo ya en formato limpio y ordenados canónicamente.
    """
    nombres = [n for n in (str(s).strip() for s in (nombres or [])) if n]
    norm_list: List[Tuple[str, str]] = [(n, _norm(n)) for n in nombres]

    grupos: Set[str] = set()
    procesados: Set[str] = set()      # nombres originales ya consumidos por familia
    raw_extra: List[str] = []         # parámetros sin mapeo (se conservan)
    metales: List[Tuple[str, str]] = []   # (orig, npar) de cada metal detectado

    # ── 1. Familias con cobertura greedy por subconjunto ────────────────────
    for fi, fam in enumerate(_FAMILIAS):
        pairs = _FAM_NORM[fi]
        tokens_a_grupo: Dict[str, str] = fam["tokens_a_grupo"]

        tokens_presentes: Set[str] = set()
        param_token: Dict[str, str] = {}
        for orig, npar in norm_list:
            tok = _match_in_pairs(npar, pairs)
            if tok:
                tokens_presentes.add(tok)
                param_token[orig] = tok
        if not tokens_presentes:
            continue

        combos = [(frozenset(k.split("|")), g) for k, g in tokens_a_grupo.items()]
        combos.sort(key=lambda x: len(x[0]), reverse=True)

        restante = set(tokens_presentes)
        cubiertos: Set[str] = set()
        while restante:
            elegido = None
            for kset, grupo in combos:
                if kset.issubset(restante):     # solo si TODOS están presentes
                    elegido = (kset, grupo)
                    break
            if elegido is None:
                break
            kset, grupo = elegido
            grupos.add(grupo)
            cubiertos |= kset
            restante -= kset

        for orig, tok in param_token.items():
            if tok in cubiertos:
                procesados.add(orig)

    # ── 2. Resto: mapeo directo ─────────────────────────────────────────────
    for orig, npar in norm_list:
        if orig in procesados:
            continue
        g = _match_mapeo(npar)
        if g is None:
            if orig not in raw_extra:
                raw_extra.append(orig)         # sin mapeo → se conserva tal cual
        elif g == _GRUPO_METALES:
            metales.append((orig, npar))        # se decide por umbral más abajo
        elif g != "SKIP":
            grupos.add(g)

    # ── 2b. Umbral de metales: 1 → nombre individual; 2+ → "Metales Totales" ─
    metales_individuales: List[str] = []
    if metales:
        if len(metales) >= _UMBRAL_METALES:
            grupos.add(_GRUPO_METALES)
        else:
            for _orig, _npar in metales:
                disp = _METAL_DISPLAY.get(_npar, _orig)
                if disp not in metales_individuales:
                    metales_individuales.append(disp)

    # ── 3. Ordenar canónicamente + formato limpio ───────────────────────────
    ordenados: List[str] = [g for g in ORDEN_GRUPOS if g in grupos]
    for g in grupos:
        if g not in ordenados:
            ordenados.append(g)

    salida: List[str] = []
    vistos: Set[str] = set()
    for g in ordenados:
        etiqueta = _clean_label(g)
        if etiqueta not in vistos:
            vistos.add(etiqueta)
            salida.append(etiqueta)
    # metales individuales (cuando hay un solo metal)
    for m in metales_individuales:
        if m not in vistos:
            vistos.add(m)
            salida.append(m)
    # parámetros sin mapeo al final (tal cual)
    for r in raw_extra:
        if r not in vistos:
            vistos.add(r)
            salida.append(r)

    return salida


# ---------------------------------------------------------------------------
# Catálogo de grupos para el desplegable "agregar parámetro" (categorizado)
# ---------------------------------------------------------------------------
_CATEGORIAS: List[Tuple[str, List[str]]] = [
    ("Microbiológicos", [
        "COLIF.FECALES*/TOTALES* - E.COLI* - BACT.HETEROTROFAS* - VIRUS",
        "COLIF.FECALES*/TOTALES* - E.COLI* - BACT.HETEROTROFAS*",
        "COLIFORMES FECALES*-TOTALES*",
        "COLIF.TOTALES / FECALES - E.COLI",
        "COLIF.FECALES*/TOTALES* - BACT.HETEROTROFAS*",
        "COLIFORMES TOTALES* - BACT.HETEROTROFAS*",
        "ESCHERICHIA COLI*",
        "BACTERIAS HETEROTROFAS*",
        "ORGANISMOS DE VIDA LIBRE (O.V.L)",
        "HUEVOS Y LARVAS HELMINTOS",
        "FORMAS PARASITARIAS",
        "PSEUDOMONAS AERUGINOSA",
        "Recuento de microorganismos aerobios mesófilos",
        "Recuento de mohos y levaduras",
        "ENUMERACIÓN DE BACTERIAS ANAEROBIAS SULFITO REDUCTORES",
        "ESTREPTOCOCOS FECALES",
        "ENUMERACION DE ENTEROCOCOS",
    ]),
    ("Físico-químicos de campo", [
        "PH* - T° - CONDUCTIVIDAD - TURBIDEZ - CLORO LIBRE - O.D (Campo)",
        "PH* - TEMPERATURA* - CONDUCTIVIDAD - CLORO LIBRE",
        "PH* - CONDUCTIVIDAD* - CLORO LIBRE",
        "PH* - TEMPERATURA* - CONDUCTIVIDAD",
        "PH* - TEMPERATURA*",
        "PH* - CONDUCTIVIDAD*",
        "PH* - CLORO LIBRE",
        "PH*",
        "TEMPERATURA* (Campo)",
        "TEMPERATURA",
        "CONDUCTIVIDAD*",
        "TURBIEDAD*",
        "CLORO LIBRE",
        "OXIGENO DIUELTO (O.D)",
    ]),
    ("Físico-químicos", [
        "COLOR - OLOR - SABOR",
        "SOLIDOS TOTALES DISUELTOS (TDS)*",
        "SOLIDOS SUSPENDIDOS TOTALES (TSS)*",
        "SOLIDOS TOTALES (ST)*",
        "SOLIDOS SEDIMENTABLES (SS)*",
        "DEMANDA BIOQUIMICA DE OXIGENO (DBO5)*",
        "DEMANDA QUIMICA DE OXIGENO (DQO)*",
    ]),
    ("Iones y nutrientes", [
        "CLORUROS - SULFATOS* - FLUOR",
        "CLORUROS* - SULFATOS*",
        "CLORUROS*",
        "SULFATOS*",
        "FLUOR",
        "CLORITO - CLORATO - NITRATOS - NITRITOS - BROMATOS",
        "NITRATOS - NITRITOS",
        "NITROGENO AMONIACAL*",
        "NITROGENO ORGANICO Kjeldahl",
        "NITROGENO TOTAL",
        "FOSFORO TOTAL",
        "FOSFATOS",
        "FLUORUROS ",
        "ALCALINIDAD*",
        "SULFUROS*",
        "AMONIACO",
        "SILICE, SILICATO",
        "POTASIO - SODIO",
        "CALCIO - MAGNESIO - POTASIO - SODIO",
    ]),
    ("Metales", [
        "METALES TOTALES AA* e ICP-OES - DUREZA TOTAL",
        "METALES TOTALES AA* e ICP-OES",
        "DUREZA TOTAL",
        "DUREZA CALCICA",
        "CIANURO TOTAL",
        "CROMO HEXAVALENTE*",
        "MERCURIO",
    ]),
    ("Orgánicos", [
        "ACEITES Y GRASAS*",
        "Hidrocarburos totales (TPH; F2; F3)",
        "PCBs",
        "MCPA",
        "MICROSISTINA - LR",
        "Detergentes SAAM",
        "ORGANICOS - INORGANICOS",
    ]),
]


# Orden de las categorías en el desplegable
_ORDEN_CATEGORIAS = [
    "Microbiológicos",
    "Físico-químicos e iones",
    "Metales",
    "Orgánicos",
    "Aire",
    "Ruido",
]

# Palabras clave (sobre el nombre normalizado) para clasificar cada agrupación.
_KW_MIC = ("COLIF", "ECOLI", "ESCHERICHIA", "HETEROTROFAS", "SALMONELLA", "VIBRIO",
           "CLOSTRIDIUM", "ENTEROCOCOS", "PSEUDOMONAS", "ESTREPTOCOCOS", "HELMINTOS",
           "PARASITARIAS", "ORGANISMOSDEVIDA", "VIRUS", "MOHOS", "LEVADURAS",
           "ANAEROBIAS", "AEROBIOSMESOFILOS", "ENDOTOXINA")
_KW_MET = ("METALES", "DUREZA", "MERCURIO", "CROMO", "CIANURO", "CNTOTAL", "CNWAD",
           "CNL", "BORO", "POTASIO", "SODIO", "CALCIO", "MAGNESIO")
_KW_ORG = ("ACEITES", "HIDROCARBUR", "TPH", "HTP", "PCB", "COV", "HAP", "BETX",
           "FENOL", "PESTICIDA", "FTALATO", "FORMALDEHIDO", "MCPA", "MICROSISTINA",
           "DETERGENTES", "ORGANICOS", "CARBONOORGANICO", "PARACUAT", "METAMIDOFOS",
           "ALDICARB", "TIOCIANATO", "ESTERES", "CLORAMINA")


def _categoria_de(nombre: str) -> str:
    raw = nombre.strip().upper()
    n = _norm(nombre)
    if raw.startswith("AI-") or "PM10" in n or "PM25" in n:
        return "Aire"
    if "RUIDO" in n:
        return "Ruido"
    if any(k in n for k in _KW_MIC):
        return "Microbiológicos"
    if any(k in n for k in _KW_MET):
        return "Metales"
    if any(k in n for k in _KW_ORG):
        return "Orgánicos"
    return "Físico-químicos e iones"


def catalogo_grupos() -> List[Dict[str, object]]:
    """
    Catálogo COMPLETO para el desplegable: TODAS las agrupaciones de la hoja
    PARAMETROS del Excel, con sus nombres EXACTOS, clasificadas por categoría
    (conservando el orden del Excel dentro de cada una).
    """
    cats: Dict[str, List[str]] = {c: [] for c in _ORDEN_CATEGORIAS}
    vistos: Set[str] = set()
    for nombre in _CATALOGO_EXCEL:
        nombre = re.sub(r"\s+", " ", str(nombre)).strip()
        if not nombre or nombre in vistos:
            continue
        vistos.add(nombre)
        cats[_categoria_de(nombre)].append(nombre)
    return [{"categoria": c, "grupos": cats[c]} for c in _ORDEN_CATEGORIAS if cats[c]]
