import fitz  # PyMuPDF
from pathlib import Path


def split_a3_to_a4(input_path, output_path):
    with fitz.open(input_path) as doc, fitz.open() as out_doc:
        for page in doc:
            rect = page.rect

            if rect.width > rect.height:
                mid = rect.x0 + (rect.width / 2)
                rect_left = fitz.Rect(rect.x0, rect.y0, mid, rect.y1)
                rect_right = fitz.Rect(mid, rect.y0, rect.x1, rect.y1)

                # Linke Hälfte als saubere A4-Seite anlegen
                page_left = out_doc.new_page(width=rect_left.width, height=rect_left.height)
                page_left.show_pdf_page(page_left.rect, doc, page.number, clip=rect_left)

                # Rechte Hälfte als saubere A4-Seite anlegen
                page_right = out_doc.new_page(width=rect_right.width, height=rect_right.height)
                page_right.show_pdf_page(page_right.rect, doc, page.number, clip=rect_right)
            else:
                out_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)

        out_doc.save(output_path)


if __name__ == "__main__":
    ordner = Path("Dateien")

    if not ordner.exists():
        print(f"Fehler: Der Ordner '{ordner.absolute()}' existiert nicht.")
    else:
        pdf_dateien = [f for f in ordner.glob("*.pdf") if "_geschnitten" not in f.name]

        if not pdf_dateien:
            print(f"Keine ungeschnittenen PDFs im Ordner '{ordner}' gefunden.")

        for pdf_pfad in pdf_dateien:
            neuer_name = f"{pdf_pfad.stem}_geschnitten.pdf"
            ziel_pfad = ordner / neuer_name

            print(f"Schneide zu: {pdf_pfad.name} ...")
            split_a3_to_a4(pdf_pfad, ziel_pfad)

            # Originaldatei sicher löschen
            pdf_pfad.unlink()
            print(f"Original gelöscht: {pdf_pfad.name}")

        print("Fertig! Alle Dateien wurden verarbeitet und die Originale entfernt.")