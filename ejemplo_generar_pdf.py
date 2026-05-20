from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from xhtml2pdf import pisa


PDF_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>{{ titulo }}</title>
  <style>
    @page {
      size: A4;
      margin: 1cm;
      @frame footer_frame {
        -pdf-frame-content: footer_content;
        bottom: 0cm;
        margin-left: 1cm;
        margin-right: 1cm;
        height: 1cm;
      }
    }

    body {
      font-family: Helvetica, Arial, sans-serif;
      font-size: 10pt;
      color: #333;
    }

    h1 {
      font-size: 16pt;
      margin: 0 0 4px 0;
      color: #059669;
    }

    .meta {
      font-size: 9pt;
      color: #666;
      margin-bottom: 12px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th {
      background-color: #f3f4f6;
      border-bottom: 2px solid #e5e7eb;
      padding: 4px;
      text-align: left;
      font-weight: bold;
      font-size: 8pt;
      color: #374151;
    }

    td {
      border-bottom: 1px solid #e5e7eb;
      padding: 4px;
      font-size: 8pt;
      vertical-align: top;
      word-wrap: break-word;
      overflow: hidden;
    }

    .text-right { text-align: right; }
    .total-row td {
      font-weight: bold;
      background-color: #f9fafb;
      border-top: 2px solid #e5e7eb;
    }
  </style>
</head>
<body>
  <h1>{{ titulo }}</h1>
  <div class="meta"><strong>Generado:</strong> {{ generado_el }}</div>

  <table>
    <colgroup>
      <col width="60%"/>
      <col width="20%"/>
      <col width="20%"/>
    </colgroup>
    <thead>
      <tr>
        <th>Detalle</th>
        <th class="text-right">Cantidad</th>
        <th class="text-right">Total</th>
      </tr>
    </thead>
    <tbody>
      {% for it in items %}
      <tr>
        <td>{{ it.detalle }}</td>
        <td class="text-right">{{ it.cantidad }}</td>
        <td class="text-right">Gs. {{ "{:,.0f}".format(it.total).replace(",", ".") }}</td>
      </tr>
      {% endfor %}
    </tbody>
    <tfoot>
      <tr class="total-row">
        <td class="text-right" colspan="2">Total</td>
        <td class="text-right">Gs. {{ "{:,.0f}".format(total_general).replace(",", ".") }}</td>
      </tr>
    </tfoot>
  </table>
</body>
<div id="footer_content" style="text-align: right; font-size: 9pt; color: #666;">
  Página <pdf:pagenumber /> de <pdf:pagecount />
</div>
</html>
"""


@dataclass(frozen=True)
class ItemPDF:
    detalle: str
    cantidad: int
    total: int


def generar_pdf_bytes(html: str) -> bytes:
    pdf_buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=pdf_buffer, encoding="UTF-8")
    if status.err:
        raise RuntimeError("Error al generar el PDF con xhtml2pdf/pisa")
    return pdf_buffer.getvalue()


def generar_pdf_response(html: str, filename: str, inline: bool = True):
    from flask import make_response

    pdf_bytes = generar_pdf_bytes(html)
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    disposition = "inline" if inline else "attachment"
    response.headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response


def _render_html_example(items: list[ItemPDF]) -> str:
    from jinja2 import Template

    template = Template(PDF_TEMPLATE)
    total_general = sum(int(it.total or 0) for it in items)
    return template.render(
        titulo="Ejemplo de PDF (xhtml2pdf)",
        generado_el=datetime.now().strftime("%d/%m/%Y %H:%M"),
        items=items,
        total_general=total_general,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="ejemplo.pdf")
    args = parser.parse_args()

    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()

    items = [
        ItemPDF(detalle="Servicio técnico - diagnóstico", cantidad=1, total=50000),
        ItemPDF(detalle="Repuesto: batería", cantidad=1, total=120000),
        ItemPDF(detalle="Mano de obra", cantidad=1, total=80000),
    ]
    html = _render_html_example(items)
    out_path.write_bytes(generar_pdf_bytes(html))
    print(f"OK: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
