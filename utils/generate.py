import fitz
import base64
from typing import List, Dict

FONT_REGULAR = str(Path(__file__).parent.parent / "fonts" / "calibri.ttf")
FONT_BOLD = str(Path(__file__).parent.parent / "fonts" / "calibrib.ttf")

# ---------------------------------------------------------------------------
# Template coordinate map  (template page = 743.7 x 1052.55 pts)
# ---------------------------------------------------------------------------
F = {
    'cliente':       (198.0,  87.5, 667.0, 102.5),
    'direccion':     (198.0, 116.0, 667.0, 131.0),
    'lugar':         (198.0, 144.5, 667.0, 160.0),
    'estacion':      (198.0, 173.5, 667.0, 188.5),
    'descripcion':   (198.0, 188.0, 667.0, 203.5),
    'tipo_muestra':  (198.0, 216.5, 252.0, 232.0),
    'clase':         (198.0, 245.5, 252.0, 261.0),
    'norte':         (255.0, 274.5, 323.0, 289.5),
    'zona':          (255.0, 289.0, 323.0, 304.0),
    'este':          (418.0, 274.5, 499.0, 289.5),
    'altitud':       (595.0, 274.5, 668.0, 289.5),
    'fecha_inicio':  (198.0, 317.5, 323.0, 332.5),
    'fecha_fin':     (198.0, 332.0, 323.0, 347.0),
    'hora_inicio':   (534.0, 317.5, 668.0, 332.5),
    'hora_fin':      (534.0, 332.0, 668.0, 347.0),
    'distrito':      ( 64.0, 390.0, 322.0, 405.5),
    'provincia':     (325.0, 390.0, 499.0, 405.5),
    'departamento':  (502.0, 390.0, 668.0, 405.5),
    'parametros':    ( 68.0, 436.0, 320.0, 491.5),
    'frec_muestreo': (326.0, 434.5, 498.0, 492.5),
    'frec_reporte':  (502.0, 434.5, 667.0, 492.5),
    'elaborado_por': (326.0, 876.0, 500.0, 890.0),
    'vb':            (326.0, 897.0, 500.0, 911.0),
}

BLACK = (0, 0, 0)

# ---------------------------------------------------------------------------
# Calibri font metrics (ascender=0.75, descender=-0.25).
# Baseline vertical offset from rect center = (asc + desc) / 2 × fontsize
#                                           = 0.25 × fontsize
# This produces perfect optical vertical centering.
# ---------------------------------------------------------------------------
_CAL_OFFSET = 0.25   # (0.75 + (-0.25)) / 2


def _center_text(page: fitz.Page,
                 rect: fitz.Rect,
                 text: str,
                 fontsize: float,
                 fontfile: str,
                 align: int = fitz.TEXT_ALIGN_CENTER) -> None:
    """
    Insert text with true vertical centering via insert_text.
    Horizontal position determined by `align`.
    """
    if not text:
        return

    # ── Vertical: baseline at optical center of rect ─────────────────────
    baseline_y = (rect.y0 + rect.y1) / 2 + _CAL_OFFSET * fontsize

    # ── Horizontal ────────────────────────────────────────────────────────
    if align == fitz.TEXT_ALIGN_CENTER:
        font_meas = fitz.Font(fontfile=fontfile)
        tw = font_meas.text_length(text, fontsize=fontsize)
        x  = rect.x0 + (rect.width - tw) / 2
        # clamp so text never exits the rect boundary
        x  = max(rect.x0 + 1.0, min(x, rect.x1 - 1.0))
    else:  # LEFT
        x = rect.x0 + 3.0

    page.insert_text(
        fitz.Point(x, baseline_y),
        text,
        fontname="calibri",
        fontfile=fontfile,
        fontsize=fontsize,
        color=BLACK,
    )


def _textbox(page: fitz.Page, key: str, text: str,
             fontsize: float = 9.5,
             align: int = fitz.TEXT_ALIGN_CENTER,
             bold: bool = False) -> None:
    """Insert a single-line field value with true vertical + horizontal centering."""
    _center_text(page, fitz.Rect(*F[key]), text, fontsize,
                 FONT_BOLD if bold else FONT_REGULAR, align)


def _params_text(params: List[str]) -> str:
    return ', '.join(params)


def _fit_params(page: fitz.Page, params: List[str]) -> None:
    """
    Insert parameters into the multi-line box, reducing font size
    until the text fits. insert_textbox is used here because we need
    automatic word-wrapping for multiple lines.
    """
    text = _params_text(params)
    rect = fitz.Rect(*F['parametros'])

    for fs in (9.0, 8.0, 7.5, 7.0, 6.5, 6.0):
        remaining = page.insert_textbox(
            rect, text,
            fontname="calibri",
            fontfile=FONT_REGULAR,
            fontsize=fs,
            align=fitz.TEXT_ALIGN_LEFT,
            color=BLACK,
        )
        if remaining >= 0:
            return

    # Fallback at minimum size
    page.insert_textbox(
        rect, text,
        fontname="calibri",
        fontfile=FONT_REGULAR,
        fontsize=6.0,
        align=fitz.TEXT_ALIGN_LEFT,
        color=BLACK,
    )


def _insert_image_centered(page: fitz.Page, cell: fitz.Rect,
                            img_bytes: bytes, padding: float = 10.0) -> None:
    """
    Insert image inside `cell` perfectly centered, maintaining aspect ratio.
    White space is left on non-constrained sides (never distorted).
    """
    try:
        tmp = fitz.open(stream=img_bytes, filetype="image")
        iw  = tmp[0].rect.width
        ih  = tmp[0].rect.height
        tmp.close()
    except Exception:
        return

    aw = cell.width  - 2 * padding
    ah = cell.height - 2 * padding
    if aw <= 0 or ah <= 0 or iw <= 0 or ih <= 0:
        return

    scale = min(aw / iw, ah / ih)
    fw = iw * scale
    fh = ih * scale

    ox = cell.x0 + padding + (aw - fw) / 2
    oy = cell.y0 + padding + (ah - fh) / 2

    page.insert_image(fitz.Rect(ox, oy, ox + fw, oy + fh),
                      stream=img_bytes, keep_proportion=False)


def _insert_photos_in_box(page: fitz.Page, photos: list) -> None:
    """
    Distribute up to 4 photos inside the large white box that already exists
    in the ficha template (x0=64, y0=508, x1=669, y1=861).

    Grid logic:
      1 photo  → full box
      2 photos → 2 columns, 1 row
      3 photos → 2 columns, 2 rows  (last photo centred)
      4 photos → 2×2 grid

    Each cell has a subtle gray border; the photo is perfectly centred
    inside it maintaining its original aspect ratio.
    """
    if not photos:
        return

    batch = photos[:4]
    n     = len(batch)

    # Exact template box boundaries (from drawing-path analysis)
    BOX  = fitz.Rect(64.0, 508.0, 669.0, 861.0)
    PAD  = 8.0     # inner padding from box wall
    GAP  = 8.0     # gap between cells
    BORDER = (0.75, 0.75, 0.75)

    # Usable area inside the box
    inner = fitz.Rect(BOX.x0 + PAD, BOX.y0 + PAD,
                      BOX.x1 - PAD, BOX.y1 - PAD)
    iw = inner.width
    ih = inner.height

    # Grid layout
    if n == 1:
        cols, rows = 1, 1
    elif n == 2:
        cols, rows = 2, 1
    else:
        cols, rows = 2, 2          # 3 or 4 photos → 2×2

    cell_w = (iw - GAP * (cols - 1)) / cols
    cell_h = (ih - GAP * (rows - 1)) / rows

    for i, b64_str in enumerate(batch):
        col = i % cols
        row = i // cols

        # Centre the lone third photo horizontally
        if n == 3 and i == 2:
            cx0 = inner.x0 + (iw - cell_w) / 2
        else:
            cx0 = inner.x0 + col * (cell_w + GAP)

        cy0  = inner.y0 + row * (cell_h + GAP)
        cell = fitz.Rect(cx0, cy0, cx0 + cell_w, cy0 + cell_h)

        # Draw cell border (white fill keeps box background clean)
        page.draw_rect(cell, fill=(1, 1, 1), color=BORDER, width=0.6)

        # Insert image perfectly centred inside cell
        try:
            img_bytes = base64.b64decode(b64_str)
            _insert_image_centered(page, cell, img_bytes, padding=6.0)
        except Exception:
            pass


def generate_fichas_pdf(samples: List[Dict], template_path: str, output_path: str) -> None:
    """
    Generate a multi-page PDF – one ficha técnica per page.
    Copies the official template as background and overlays values.
    """
    template_doc = fitz.open(template_path)
    output_doc   = fitz.open()

    for sample in samples:
        output_doc.insert_pdf(template_doc, from_page=0, to_page=0)
        page = output_doc[-1]

        _textbox(page, 'cliente',      sample.get('cliente', ''))
        _textbox(page, 'direccion',    sample.get('direccion', ''))
        _textbox(page, 'lugar',        sample.get('lugar_muestreo', ''))
        _textbox(page, 'estacion',     sample.get('estacion', ''))
        _textbox(page, 'descripcion',  sample.get('descripcion', ''))
        _textbox(page, 'tipo_muestra', sample.get('tipo_muestra', 'L'))
        _textbox(page, 'clase',        sample.get('clase', 'E'))

        _textbox(page, 'norte',   sample.get('utm_norte',   '-'))
        _textbox(page, 'zona',    sample.get('utm_zona',    '-'))
        _textbox(page, 'este',    sample.get('utm_este',    '-'))
        _textbox(page, 'altitud', sample.get('utm_altitud', '-'))

        _textbox(page, 'fecha_inicio', sample.get('fecha_inicio', '-'))
        _textbox(page, 'hora_inicio',  sample.get('hora_inicio',  '-'))
        _textbox(page, 'fecha_fin',    sample.get('fecha_fin',    '-'))
        _textbox(page, 'hora_fin',     sample.get('hora_fin',     '-'))

        _textbox(page, 'distrito',     sample.get('distrito',     ''))
        _textbox(page, 'provincia',    sample.get('provincia',    ''))
        _textbox(page, 'departamento', sample.get('departamento', ''))

        params = sample.get('parametros', [])
        _fit_params(page, params if isinstance(params, list) else [str(params)])

        _textbox(page, 'frec_muestreo', sample.get('frec_muestreo', '-'))
        _textbox(page, 'frec_reporte',  sample.get('frec_reporte',  '-'))

        _textbox(page, 'elaborado_por',
                 sample.get('elaborado_por', 'ÁREA DE OPERACIONES'))
        _textbox(page, 'vb',
                 sample.get('vb', 'PACIFIC CONTROL SAC'))

        # Photos go inside the large white box already in the template
        photos = sample.get('photos', [])
        if photos:
            _insert_photos_in_box(page, photos)

    output_doc.save(output_path, deflate=True)
    output_doc.close()
    template_doc.close()
