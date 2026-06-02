import re
import pdfplumber
import logging
import os
from typing import Dict, List, Tuple, Optional

# ---------------------------------------------------------------------------
# Debug log  (C:\Fichas tecnicas\extract_debug.log)
# Only our own 'extract' logger is DEBUG; everything else stays at WARNING
# so pdfplumber/pdfminer internals don't flood the file.
# ---------------------------------------------------------------------------
_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'extract_debug.log')
logging.basicConfig(
    filename=_LOG_PATH,
    filemode='w',           # overwrite each run – keep the file small
    level=logging.WARNING,  # suppress all third-party library logs
    format='%(asctime)s %(levelname)s %(message)s',
    encoding='utf-8',
)
log = logging.getLogger('extract')

# ---------------------------------------------------------------------------
# Matrix type → (tipo_muestra, clase)
# ---------------------------------------------------------------------------
MATRIX_MAP = {
    'AR': ('L', 'E'),   # Agua Residual  → Líquido / Efluente
    'AN': ('A', 'R'),   # Agua Natural   → Acuoso  / Receptor
    'AC': ('L', 'R'),   # Agua Consumo   → Líquido / Receptor
    'AS': ('L', 'R'),   # Agua Salina    → Líquido / Receptor
    'AP': ('L', 'E'),   # Agua Proceso   → Líquido / Efluente
}

# ---------------------------------------------------------------------------
# Parameter grouping
# ---------------------------------------------------------------------------
METALS = {
    'aluminio', 'arsenico', 'arsénico', 'cadmio', 'cobre',
    'cromo hexavalente', 'cromo total', 'manganeso',
    'mercurio', 'niquel', 'níquel', 'plomo', 'zinc',
}

PARAM_CANONICAL = [
    ('DBO5',               ['demanda bioqu']),
    ('DQO',                    ['demanda qu']),
    ('SST',                    ['s\xf3lidos', 'solidos', 'tss']),
    ('Aceites y Grasas',       ['aceites']),
    ('Nitr\xf3geno Amoniacal', ['nitr\xf3geno', 'nitrogeno']),
    ('Sulfatos',               ['sulfatos']),
    ('Cianuro Total',          ['cianuro']),
    ('pH',                     ['ph']),
    ('Temperatura',            ['temperatura']),
]


def group_parameters(raw_list: List[str]) -> List[str]:
    """Abbreviate and group parameters so they fit in the ficha box."""
    result: List[str] = []
    has_metals = False

    for param in raw_list:
        p = param.lower().strip()
        if not p:
            continue

        # Check metals first
        if any(m in p for m in METALS):
            has_metals = True
            continue

        # Map to canonical name
        matched = False
        for canon, keywords in PARAM_CANONICAL:
            if any(kw in p for kw in keywords):
                if canon not in result:
                    result.append(canon)
                matched = True
                break

        if not matched:
            clean = param.strip()
            if clean and clean not in result:
                result.append(clean)

    # Insert Metales right after Aceites y Grasas (or at end)
    if has_metals:
        if 'Aceites y Grasas' in result:
            idx = result.index('Aceites y Grasas') + 1
            result.insert(idx, 'Metales')
        else:
            result.append('Metales')

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(text: Optional[str]) -> str:
    if not text:
        return ''
    return re.sub(r'\s+', ' ', str(text).replace('\n', ' ')).strip()


def _parse_pto(raw: str) -> Tuple[str, str, str]:
    """
    'P-1 / F1 - 39 / INVERSION ES TAMARA SAC'
    → estacion='P-01', cod_pto='F1-39', descripcion='F1-39 INVERSION ES TAMARA SAC'

    Returns a 3-tuple: (estacion, cod_pto, descripcion)
    - estacion  : normalised station code, e.g. 'P-01'
    - cod_pto   : compact point code stripped of spaces, e.g. 'F1-39'
                  This is the MOST STABLE identifier – used as merge key.
    - descripcion: cod_pto + company name for display purposes
    """
    cleaned = _clean(raw)
    parts = re.split(r'\s*/\s*', cleaned)

    # ── Station ──────────────────────────────────────────────────────────────
    st_match = re.search(r'[Pp]-?\s*(\d+)', parts[0]) if parts else None
    estacion = f"P-{int(st_match.group(1)):02d}" if st_match else parts[0].strip()

    # ── Code vs. descriptive name ───────────────────────────────────────────
    # Two CdC formats exist:
    #   (a) coded     : 'P-01 / F1 - 39 / INVERSION ES TAMARA SAC'
    #                   parts[1] is a short point code → strip spaces → 'F1-39'
    #   (b) descriptive: 'P-04 / Punto de Maquina de Sala'
    #                   parts[1] is a human-readable name → keep spaces intact
    #
    # A point code matches: 1-3 letters, optional digits, hyphen, digits
    # (e.g. 'F1-39', 'I1 - 03', 'I-11', 'D1-3', 'I1-09.10'). Anything else
    # (multi-word names) is treated as a description and left readable.
    _CODE_RE = r'^[A-Za-z]{1,3}\d{0,2}\s*-\s*\d+(?:\.\d+)?$'

    if len(parts) >= 2:
        second  = parts[1].strip()
        company = ' '.join(p.strip() for p in parts[2:]).strip()

        if re.match(_CODE_RE, second):
            # Coded point: compact code is the stable merge identifier
            cod_pto = re.sub(r'\s+', '', second)        # 'F1 - 39' → 'F1-39'
            descripcion = f"{cod_pto} {company}".strip() if company else cod_pto
        else:
            # Descriptive point: no code; keep the name readable (spaces intact).
            # Merge falls back to the normalised description key (Level 2).
            cod_pto = ''
            descripcion = f"{second} {company}".strip() if company else second
    else:
        cod_pto = ''
        descripcion = cleaned

    return estacion, cod_pto, descripcion


def _parse_params(raw: str) -> List[str]:
    """Split comma-separated parameters from CdC cell."""
    cleaned = _clean(raw)
    items = [p.strip() for p in cleaned.split(',')]
    return [i for i in items if i]


def _extract_e(cell: str) -> str:
    m = re.search(r'[Ee]:\s*0*(\d+)', cell)
    return m.group(1) if m else ''


def _extract_n(cell: str) -> str:
    m = re.search(r'[Nn]:\s*(\d+)', cell)
    return m.group(1) if m else ''


def _extract_zona(cell: str) -> str:
    m = re.match(r'^(\d{1,2}[A-Za-z])$', cell.strip())
    return m.group(1).upper() if m else ''


def deduce_location(lugar: str, direccion: str) -> Tuple[str, str, str]:
    """
    Try to infer Distrito/Provincia/Departamento.
    The address format used in Peru is often '... - DISTRICT'.
    """
    distrito = ''
    for text in (lugar, direccion):
        if ' - ' in text:
            candidate = text.split(' - ')[-1].strip().upper()
            if candidate and len(candidate) > 2:
                distrito = candidate
                break
    return distrito, 'LIMA', 'LIMA'


# ---------------------------------------------------------------------------
# Merge key normalisation
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    """Keep only alphanumeric chars, uppercase.
    'F1 - 39' → 'F139'  |  'I1 - 03' → 'I103'
    Removes all whitespace, hyphens, dots and punctuation so that any
    PDF-extraction variant of the same code produces an identical key.
    """
    return re.sub(r'[^A-Z0-9]', '', str(s).upper())


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------
def _is_lab_code(cell: Optional[str]) -> bool:
    return bool(cell and re.match(r'^\d{4}-\d{7}', str(cell).strip()))


def extract_cdc_data(pdf_path: str) -> Dict:
    """
    Parse a Cadena de Custodia PDF and return structured data.
    """
    log.info('=== extract_cdc_data: %s ===', pdf_path)

    result = {
        'cliente': '', 'direccion': '', 'lugar_muestreo': '',
        'fecha_muestreo': '', 'cma': '',
        'samples': []
    }

    all_rows: List[List] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                all_rows.extend(table)

    # ---- Header extraction ------------------------------------------------
    for row in all_rows:
        cells = [_clean(c) for c in row]
        row_text = ' '.join(c for c in cells if c)

        if not result['cliente'] and ('Razón Social' in row_text or 'Razon Social' in row_text):
            for i_c, c in enumerate(cells):
                if c and ('Razón Social' in c or 'Razon Social' in c):
                    for j in range(i_c + 1, len(cells)):
                        v = cells[j]
                        if v and len(v) > 3 and 'Razón' not in v and 'Razon' not in v:
                            result['cliente'] = v
                            break
                    break

        if not result['direccion'] and ('Dirección' in row_text or 'Direccion' in row_text):
            for i_c, c in enumerate(cells):
                if c and ('Dirección' in c or 'Direccion' in c):
                    for j in range(i_c + 1, len(cells)):
                        v = cells[j]
                        if v and len(v) > 3 and 'Direcci' not in v:
                            result['direccion'] = v
                            break
                    break

        if not result['lugar_muestreo'] and 'Lugar de Muestreo' in row_text:
            for i_c, c in enumerate(cells):
                if c and 'Lugar de Muestreo' in c:
                    for j in range(i_c + 1, len(cells)):
                        v = cells[j]
                        if v and len(v) > 3 and 'Lugar' not in v:
                            result['lugar_muestreo'] = v
                            break
                    break

        if not result['fecha_muestreo']:
            for c in cells:
                m = re.search(r'(\d{4}-\d{2}-\d{2})', c)
                if m:
                    result['fecha_muestreo'] = m.group(1)
                    break

        if not result['cma']:
            m = re.search(r'(\d{4}-\d{4})', row_text)
            if m:
                result['cma'] = m.group(1)

    # ---- Sample rows extraction --------------------------------------------
    i = 0
    last_pto_raw = ''   # carry-forward: reuse when PDF has merged/empty station cell

    while i < len(all_rows):
        row = all_rows[i]
        cells = [_clean(c) for c in row]

        if not _is_lab_code(cells[0] if cells else None):
            i += 1
            continue

        next_cells = [_clean(c) for c in all_rows[i + 1]] if i + 1 < len(all_rows) else []

        cod_lab = cells[0]

        # Station cell: if empty (PDF merged/spanned cell) reuse the previous row's value.
        # This is the most common cause of "same point on different rows not being merged".
        pto_raw = cells[1] if len(cells) > 1 else ''
        if pto_raw.strip():
            last_pto_raw = pto_raw   # remember for next row
        else:
            pto_raw = last_pto_raw   # inherit from previous sample row

        # Hora: first cell matching HH:MM
        hora = ''
        for c in cells[2:10]:
            if re.match(r'^\d{1,2}:\d{2}$', c):
                hora = c
                break

        # Tipo de matriz: AR-4, AN-1, etc.
        tipo_matriz = ''
        for c in cells:
            if re.match(r'^(AR|AN|AC|AS|AP)-\d+$', c):
                tipo_matriz = c
                break

        # UTM – search all cells of both rows
        utm_e = utm_n = utm_zona = ''
        for c in cells + next_cells:
            if not utm_e:   utm_e    = _extract_e(c)
            if not utm_n:   utm_n    = _extract_n(c)
            if not utm_zona: utm_zona = _extract_zona(c)

        # Análisis: longest cell containing commas
        analisis_raw = ''
        for c in cells:
            if ',' in c and len(c) > len(analisis_raw):
                analisis_raw = c

        # Parse / group
        estacion, cod_pto, descripcion = _parse_pto(pto_raw)
        params_raw    = _parse_params(analisis_raw)
        params_grouped = group_parameters(params_raw)

        log.debug(
            'SAMPLE cod_lab=%s  pto_raw=%r  estacion=%r  cod_pto=%r  '
            'descripcion=%r  norm_key=(%r, %r)  params=%s',
            cod_lab, pto_raw, estacion, cod_pto, descripcion,
            _norm(estacion), _norm(cod_pto) if cod_pto else _norm(descripcion),
            params_grouped,
        )

        # Tipo de muestra / Clase from matrix type
        matrix_key = tipo_matriz[:2] if tipo_matriz else 'AR'
        tipo_muestra, clase = MATRIX_MAP.get(matrix_key, ('L', 'E'))

        # Format fecha (YYYY-MM-DD → DD/MM/YYYY)
        fecha = result['fecha_muestreo']
        if re.match(r'\d{4}-\d{2}-\d{2}', fecha):
            y, mo, d = fecha.split('-')
            fecha = f"{d}/{mo}/{y}"

        # Deduce location
        distrito, provincia, departamento = deduce_location(
            result['lugar_muestreo'], result['direccion']
        )

        result['samples'].append({
            'cod_lab':        cod_lab,
            'cod_pto':        cod_pto,
            'cliente':        result['cliente'],
            'direccion':      result['direccion'],
            'lugar_muestreo': result['lugar_muestreo'],
            'estacion':       estacion,
            'descripcion':    descripcion,
            'tipo_muestra':   tipo_muestra,
            'clase':          clase,
            'utm_norte':     utm_n or '-',
            'utm_este':      utm_e or '-',
            'utm_altitud':   '-',
            'utm_zona':      utm_zona or '18L',
            'fecha_inicio':  fecha,
            'hora_inicio':   hora or '-',
            'fecha_fin':     '-',
            'hora_fin':      '-',
            'distrito':      distrito,
            'provincia':     provincia,
            'departamento':  departamento,
            'parametros':    params_grouped,
            'frec_muestreo': '-',
            'frec_reporte':  '-',
            'elaborado_por': 'ÁREA DE OPERACIONES',
            'vb':            'PACIFIC CONTROL SAC',
        })

        i += 1

    log.info('Before merge: %d samples', len(result['samples']))
    result['samples'] = _merge_duplicate_stations(result['samples'])
    log.info('After  merge: %d samples', len(result['samples']))

    return result


def _merge_duplicate_stations(samples: List[Dict]) -> List[Dict]:
    """
    Collapse ALL rows that represent the same physical sampling point into one
    ficha, regardless of how the PDF split them.

    Strategy (three levels, applied in order):

      Level 1 – compact code key  (most reliable)
        key = (_norm(estacion), _norm(cod_pto))
        cod_pto is the slash-delimited point code ('F1-39', 'I1-03').
        Because it is short and stripped of whitespace it survives all
        PDF extraction artefacts ('F1 - 39' → 'F139').

      Level 2 – description key  (fallback when no slash code exists)
        key = (_norm(estacion), _norm(descripcion))
        Full description normalised to alphanumeric-only.

      Level 3 – station-only key  (last resort when description is also empty)
        key = (_norm(estacion),)
        Merges into any existing entry for the same station number.
        Handles rows where pdfplumber returned an empty station cell that
        carry-forward also could not recover.

    _norm() strips everything except letters/digits and uppercases, so
    'NATURSA SAC-BAZAN', 'NATURSA SAC - BAZAN', 'NATURSA  SAC  BAZAN'
    all produce the same key.
    """
    seen: dict = {}     # key  → index in `merged`
    est_seen: dict = {} # _norm(estacion) → index in `merged` (for level-3 fallback)
    merged: List[Dict] = []

    def _add_params(target: Dict, source: Dict) -> None:
        existing = target.get('parametros') or []
        for p in (source.get('parametros') or []):
            if p and p not in existing:
                existing.append(p)
        target['parametros'] = existing

    for s in samples:
        est  = _norm(s.get('estacion',    ''))
        code = _norm(s.get('cod_pto',     ''))
        desc = _norm(s.get('descripcion', ''))

        # ── Level 1: compact code ────────────────────────────────────────────
        if code:
            key = (est, code)
            if key in seen:
                _add_params(merged[seen[key]], s)
                log.debug('MERGE L1 key=%s → merged', key)
                continue
            seen[key] = len(merged)
            if est and est not in est_seen:
                est_seen[est] = len(merged)
            merged.append(dict(s))
            log.debug('MERGE L1 key=%s → new[%d]', key, len(merged)-1)
            continue

        # ── Level 2: full description ────────────────────────────────────────
        if desc:
            key = (est, desc)
            if key in seen:
                _add_params(merged[seen[key]], s)
                log.debug('MERGE L2 key=%s → merged', key)
                continue
            seen[key] = len(merged)
            if est and est not in est_seen:
                est_seen[est] = len(merged)
            merged.append(dict(s))
            log.debug('MERGE L2 key=%s → new[%d]', key, len(merged)-1)
            continue

        # ── Level 3: station number only (empty description) ─────────────────
        if est and est in est_seen:
            _add_params(merged[est_seen[est]], s)
            log.debug('MERGE L3 est=%s → merged into existing', est)
            continue

        # Completely unknown – keep as new entry
        if est:
            est_seen[est] = len(merged)
        merged.append(dict(s))
        log.debug('MERGE L3 est=%s → new[%d] (no code/desc)', est, len(merged)-1)

    return merged
