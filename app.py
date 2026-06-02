from flask import Flask, render_template, request, jsonify, send_file
from pathlib import Path
import uuid
import os

from utils.extract import extract_cdc_data, _merge_duplicate_stations
from utils.generate import generate_fichas_pdf

app = Flask(__name__)
app.secret_key = 'pacific-control-fichas-2026'

BASE_DIR    = Path(__file__).parent
UPLOAD_DIR  = Path("/tmp/uploads")
OUTPUT_DIR  = Path("/tmp/output")
TEMPLATE_PDF = BASE_DIR / 'Modelo ficha tecnica.pdf'

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/preview')
def preview():
    return render_template('preview.html')


@app.route('/process', methods=['POST'])
def process():
    if 'cdc_file' not in request.files:
        return jsonify({'error': 'No se adjuntó la Cadena de Custodia'}), 400

    cdc_file = request.files['cdc_file']
    if not cdc_file.filename:
        return jsonify({'error': 'Archivo vacío'}), 400

    session_id = uuid.uuid4().hex[:8]
    cdc_path = UPLOAD_DIR / f'cdc_{session_id}.pdf'
    cdc_file.save(cdc_path)

    try:
        data = extract_cdc_data(str(cdc_path))
    except Exception as e:
        return jsonify({'error': f'Error al procesar el PDF: {e}'}), 500
    finally:
        try:
            cdc_path.unlink(missing_ok=True)
        except Exception:
            pass

    return jsonify({'data': data})


@app.route('/generate', methods=['POST'])
def generate():
    body = request.get_json(force=True)
    samples = body.get('samples', [])

    if not samples:
        return jsonify({'error': 'No hay fichas que generar'}), 400

    # ── Final consolidation pass (catches any duplicates from any source) ──
    before = len(samples)
    samples = _merge_duplicate_stations(samples)
    after  = len(samples)

    output_id   = uuid.uuid4().hex[:8]
    output_path = OUTPUT_DIR / f'fichas_{output_id}.pdf'

    try:
        generate_fichas_pdf(samples, str(TEMPLATE_PDF), str(output_path))
    except Exception as e:
        return jsonify({'error': f'Error al generar el PDF: {e}'}), 500

    return jsonify({'download_id': output_id, 'merged': before - after, 'count': after})


@app.route('/debug_extract', methods=['POST'])
def debug_extract():
    """Diagnostic endpoint – returns raw extraction data without merging."""
    if 'cdc_file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['cdc_file']
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        import pdfplumber, re
        def _clean(t):
            return re.sub(r'\s+', ' ', str(t or '').replace('\n', ' ')).strip()
        def _is_lab(c):
            return bool(c and re.match(r'^\d{4}-\d{7}', str(c).strip()))
        rows_debug = []
        with pdfplumber.open(tmp.name) as pdf:
            for pn, page in enumerate(pdf.pages):
                for tn, tbl in enumerate(page.extract_tables()):
                    for rn, row in enumerate(tbl):
                        cells = [_clean(c) for c in row]
                        if _is_lab(cells[0] if cells else None):
                            rows_debug.append({
                                'page': pn+1, 'table': tn, 'row': rn,
                                'col0': cells[0] if len(cells)>0 else '',
                                'col1': cells[1] if len(cells)>1 else '',
                                'ncols': len(cells),
                            })
        return jsonify({'sample_rows': rows_debug})
    finally:
        os.unlink(tmp.name)


@app.route('/download/<download_id>')
def download(download_id):
    if not download_id.isalnum():
        return 'Not found', 404
    path = OUTPUT_DIR / f'fichas_{download_id}.pdf'
    if not path.exists():
        return 'Not found', 404
    return send_file(str(path), as_attachment=True,
                     download_name='Fichas_Tecnicas_Muestreo.pdf')


if __name__ == '__main__':
    print("=== Fichas Técnicas – Pacific Control SAC ===")
    print(f"Plantilla: {TEMPLATE_PDF}")
    print("Abriendo en: http://127.0.0.1:5000")
    app.run(debug=False, port=5000)
