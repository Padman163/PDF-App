import fitz
import pytesseract
from PIL import Image
from pathlib import Path
import re

INSTRUMENTE = {
    "double bass": "Kontrabass",
    "contrabass": "Kontrabass",
    "bass clarinet": "Bassklarinette",
    "alto clarinet": "Altklarinette",
    "alto saxophone": "Altsaxophon",
    "tenor saxophone": "Tenorsaxophon",
    "baritone saxophone": "Baritonsaxophon",
    "bass trombone": "Bassposaune",
    "flugelhorn": "Flügelhorn",
    "euphonium": "Euphonium",
    "cornet": "Kornett",
    "tuba": "Tuba",
    "bassoon": "Fagott",
    "saxophone": "Saxophon",
    "percussion": "Schlagwerk",
    "drums": "Schlagzeug",
    "trumpet": "Trompete",
    "trombone": "Posaune",
    "clarinet": "Klarinette",
    "violin": "Violine",
    "cello": "Violoncello",
    "flute": "Flöte",
    "piccolo": "Piccolo",
    "oboe": "Oboe",
    "horn": "Horn",
    "piano": "Klavier",
    "organ": "Orgel",
    "guitar": "Gitarre",
    "voice": "Gesang",
    "soprano": "Sopran",
    "alto": "Alt",
    "tenor": "Tenor",
    "bass": "Bass",
    "kontrabass": "Kontrabass",
    "schlagzeug": "Schlagzeug",
    "trompete": "Trompete",
    "posaune": "Posaune",
    "klarinette": "Klarinette",
    "violine": "Violine",
    "violoncello": "Violoncello",
    "flöte": "Flöte",
    "klavier": "Klavier",
    "gitarre": "Gitarre",
}

# WICHTIG: Pfad zu Tesseract anpassen, falls abweichend!
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def split_a3_to_a4(input_path, output_path, rotation=0, split_ratio=0.5, enabled=True, target_format="a4"):
    """
    1. Berechnet die Drehung im Uhrzeigersinn und überträgt sie exakt (ohne 180°-Invertierung)
       in ein normalisiertes Zwischen-PDF.
    2. Schneidet das normalisierte Dokument vertikal an der Schieberegler-Position.
    3. Passt die Hälften aufrecht und unverzerrt in DIN A4 ein.
    """
    split_ratio = max(0.1, min(0.9, float(split_ratio)))
    rotation = int(rotation) % 360

    # DIN A4 Standardmaße in PDF-Punkten (210 x 297 mm = 595.28 x 841.89 pt)
    A4_W = 595.28
    A4_H = 841.89

    # --- SCHRITT 1: Drehung sicher einbrennen ---
    with fitz.open(input_path) as src_doc:
        temp_doc = fitz.open()

        for page in src_doc:
            # Gesamtdrehung im Uhrzeigersinn (wie in der Browser-Vorschau)
            total_rot = (page.rotation + rotation) % 360

            # Quellseite neutralisieren
            page.set_rotation(0)
            raw_w = page.rect.width
            raw_h = page.rect.height

            # Bei 90° / 270° Drehung tauschen Breite und Höhe
            if total_rot in (90, 270):
                vis_w, vis_h = raw_h, raw_w
            else:
                vis_w, vis_h = raw_w, raw_h

            temp_page = temp_doc.new_page(width=vis_w, height=vis_h)

            # KORREKTUR: PyMuPDF show_pdf_page dreht gegen den Uhrzeigersinn.
            # (360 - total_rot) % 360 kehrt das um, damit es exakt wie in der Vorschau aufrecht liegt:
            show_rot = (360 - total_rot) % 360

            temp_page.show_pdf_page(
                temp_page.rect,
                src_doc,
                page.number,
                rotate=show_rot
            )

        temp_bytes = temp_doc.tobytes()
        temp_doc.close()

    # --- SCHRITT 2: Aufrecht stehendes Dokument schneiden ---
    with fitz.open("pdf", temp_bytes) as norm_doc, fitz.open() as out_doc:
        for page in norm_doc:
            rect = page.rect  # x0=0, y0=0, width=vis_w, height=vis_h, rotation=0

            if enabled:
                split_x = rect.width * split_ratio
                rect_left = fitz.Rect(0, 0, split_x, rect.height)
                rect_right = fitz.Rect(split_x, 0, rect.width, rect.height)

                # Links = Seite 1, Rechts = Seite 2
                for clip_rect in (rect_left, rect_right):
                    if target_format in ("a4", "a4_portrait"):
                        target_w, target_h = A4_W, A4_H
                    elif target_format == "a4_landscape":
                        target_w, target_h = A4_H, A4_W
                    else:
                        target_w, target_h = clip_rect.width, clip_rect.height

                    target_page = out_doc.new_page(width=target_w, height=target_h)

                    if target_format == "original":
                        target_page.show_pdf_page(target_page.rect, norm_doc, page.number, clip=clip_rect)
                    else:
                        target_page.show_pdf_page(target_page.rect, norm_doc, page.number, clip=clip_rect, keep_proportion=True)

            else:
                # Kein Schnitt: Seite ungeschnitten übernehmen
                if target_format in ("a4", "a4_portrait"):
                    target_w, target_h = (A4_H, A4_W) if rect.width > rect.height else (A4_W, A4_H)
                elif target_format == "a4_landscape":
                    target_w, target_h = A4_H, A4_W
                else:
                    target_w, target_h = rect.width, rect.height

                target_page = out_doc.new_page(width=target_w, height=target_h)
                if target_format == "original":
                    target_page.show_pdf_page(target_page.rect, norm_doc, page.number)
                else:
                    target_page.show_pdf_page(target_page.rect, norm_doc, page.number, keep_proportion=True)

        out_doc.save(output_path)

def extrahiere_instrument_und_seite(ocr_text):
    text = ocr_text.strip()
    match = re.search(r'(?i)(?:s\.|seite|p\.|page)\s*(\d+)', text)
    if match:
        seite = match.group(1)
        instrument = re.sub(r'^[\-\.,\s]+|[\-\.,\s]+$', '', text.replace(match.group(0), '').strip())
        return instrument, seite

    match = re.search(r'\s+[-/]?\s*(\d+)\s*$', text)
    if match:
        seite = match.group(1)
        instrument = re.sub(r'^[\-\.,\s]+|[\-\.,\s]+$', '', text[:match.start()].strip())
        return instrument, seite

    match = re.search(r'^\s*(\d+)\s+[-/]?\s*', text)
    if match:
        seite = match.group(1)
        instrument = re.sub(r'^[\-\.,\s]+|[\-\.,\s]+$', '', text[match.end():].strip())
        return instrument, seite

    return text, ""


def verarbeite_pdf_ocr(pdf_pfad, regionen=None, instrument_regeln=None):
    """
    Erkennt Titel, Instrument und Seitenzahl aus den Seitenrändern.
    Variante 1 bei 3 Referenzseiten:
    - Seite 1 -> 'first'
    - Gerade Seiten (2, 4, 6, ...) -> 'second'
    - Ungerade Folgeseiten (3, 5, 7, ...) -> 'third' (Fallback auf 'second', falls 'third' nicht markiert wurde)
    """
    ergebnisse = []

    with fitz.open(pdf_pfad) as doc:
        for seiten_nummer, page in enumerate(doc):
            rect = page.rect
            seiten_nr_1basiert = seiten_nummer + 1

            if regionen:
                if seiten_nr_1basiert == 1:
                    profil = "first"
                elif seiten_nr_1basiert % 2 == 0:
                    profil = "second"
                else:
                    profil = "third"

                # Falls auf der 3. Referenzseite nichts markiert wurde, auf 2. Referenzseite zurückfallen
                instrument_region = regionen.get(f"{profil}_instrument")
                if not instrument_region and profil == "third":
                    instrument_region = regionen.get("second_instrument")

                if instrument_region:
                    instrument_bereich = _region_rect(rect, instrument_region)
                    instrument_text = _ocr_bereich(page, instrument_bereich, psm=7)
                    instrument = erkenne_instrument(instrument_text, instrument_regeln)
                else:
                    instrument = ""

                zahlen_bereich = regionen.get(f"{profil}_page_number")
                if not zahlen_bereich and profil == "third":
                    zahlen_bereich = regionen.get("second_page_number")

                if seiten_nr_1basiert == 1 and not zahlen_bereich:
                    seite = "1"
                elif zahlen_bereich:
                    zahlen_text = _ocr_bereich(page, _region_rect(rect, zahlen_bereich), psm=7)
                    seite = _einzelne_zahl(zahlen_text)
                else:
                    seite = ""

                ergebnisse.append({
                    "seite_index": seiten_nr_1basiert,
                    "instrument": instrument,
                    "seite": seite,
                    "profil": profil
                })
                continue

            obere_zone = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.22)
            obere_mitte = fitz.Rect(rect.x0 + rect.width * 0.35, rect.y0, rect.x0 + rect.width * 0.65, rect.y0 + rect.height * 0.18)
            untere_mitte = fitz.Rect(rect.x0 + rect.width * 0.35, rect.y0 + rect.height * 0.82, rect.x0 + rect.width * 0.65, rect.y1)

            titel_text = _ocr_bereich(page, obere_zone, psm=6)
            seiten_text = _ocr_bereich(page, rect, psm=11)
            obere_zahl = _ocr_zahl(page, obere_mitte)
            untere_zahl = _ocr_zahl(page, untere_mitte)

            hat_titel = _enthaelt_stuecktitel(titel_text)
            if hat_titel:
                seite = "1"
            else:
                erkannte_seite = obere_zahl or untere_zahl or ""
                seite = "" if erkannte_seite == "1" else erkannte_seite

            instrument = erkenne_instrument(seiten_text, instrument_regeln)
            ergebnisse.append({
                "seite_index": seiten_nr_1basiert,
                "instrument": instrument,
                "seite": seite
            })

    return ergebnisse


def verarbeite_einzelne_seite(pdf_pfad, seiten_index, instrument_region=None, page_region=None, instrument_regeln=None):
    with fitz.open(pdf_pfad) as doc:
        page = doc[seiten_index - 1]
        rect = page.rect
        instrument = ""
        if instrument_region:
            text = _ocr_bereich(page, _region_rect(rect, instrument_region), psm=7)
            instrument = erkenne_instrument(text, instrument_regeln)

        if page_region:
            text = _ocr_bereich(page, _region_rect(rect, page_region), psm=7)
            seite = _einzelne_zahl(text)
        else:
            seite = "1" if seiten_index == 1 else ""

        return {"instrument": instrument, "seite": seite}


def _region_rect(page_rect, region):
    return fitz.Rect(
        page_rect.x0 + page_rect.width * region["x"],
        page_rect.y0 + page_rect.height * region["y"],
        page_rect.x0 + page_rect.width * (region["x"] + region["width"]),
        page_rect.y0 + page_rect.height * (region["y"] + region["height"]),
    )


def erkenne_instrument(text, instrument_regeln=None):
    """Gibt ausschließlich den erkannten Instrumentnamen auf Deutsch zurück."""
    bereinigter_text = " ".join(text.split()).strip()
    text_suche = bereinigter_text.casefold().replace("-", " ")
    gefundene_instrumente = []

    for regel in instrument_regeln or []:
        begriff = regel.get("erkannt", "").strip().casefold().replace("-", " ")
        ziel = regel.get("ziel", "").strip()

        if begriff and ziel:
            match = re.search(
                rf"(?<![a-zäöüß]){re.escape(begriff)}(?![a-zäöüß])\s*(?:[-:]?\s*(\d+(?:[/-]\d+)?))?",
                text_suche,
            )
            if match:
                nummer = f" {match.group(1)}" if match.group(1) else ""
                gefundene_instrumente.append((len(begriff) + 10000, f"{ziel}{nummer}"))

    for begriff, uebersetzung in INSTRUMENTE.items():
        begriff_suche = begriff.casefold().replace("-", " ")
        match = re.search(
            rf"(?<![a-zäöüß]){re.escape(begriff_suche)}(?![a-zäöüß])\s*(?:[-:]?\s*(\d+(?:[/-]\d+)?))?",
            text_suche,
        )
        if match:
            nummer = f" {match.group(1)}" if match.group(1) else ""
            gefundene_instrumente.append((len(begriff_suche), f"{uebersetzung}{nummer}"))

    if not gefundene_instrumente:
        return bereinigter_text

    return max(gefundene_instrumente)[1]


def _ocr_bereich(page, bereich, psm=6):
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=bereich)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return " ".join(pytesseract.image_to_string(img, config=f"--psm {psm}").split())


def _ocr_zahl(page, bereich):
    text = _ocr_bereich(page, bereich, psm=7)
    return _einzelne_zahl(text)


def _einzelne_zahl(text):
    text = text.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5"})).strip()
    if re.search(r"[A-Za-zÄÖÜäöüß]", text):
        return ""

    match = re.fullmatch(r"[^\d]*(\d{1,3})[^\d]*", text)
    return match.group(1) if match else ""


def _enthaelt_stuecktitel(text):
    woerter = re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", text)
    return len(woerter) >= 2


def speichere_finale_pdfs(seiten_daten):
    ziel_ordner = Path("Dateien") / "Fertig"
    ziel_ordner.mkdir(parents=True, exist_ok=True)

    pdf_gruppen = {}
    for reihenfolge, daten in enumerate(seiten_daten):
        dateiname = daten["pdf_url"].split("/pdfs/")[1].split("#")[0]
        instrument = re.sub(r'[\\/*?:"<>|]', '_', daten["instrument"]).strip() or "Unbenannt"
        schluessel = instrument.casefold()
        pdf_gruppen.setdefault(schluessel, {"instrument": instrument, "seiten": []})["seiten"].append({
            "daten": daten,
            "dateiname": dateiname,
            "reihenfolge": reihenfolge
        })

    for gruppe in pdf_gruppen.values():
        pdf_seiten = sorted(gruppe["seiten"], key=_seiten_sortierung)
        ziel_pfad = ziel_ordner / f"{gruppe['instrument']}.pdf"

        with fitz.open() as out_doc:
            for seite in pdf_seiten:
                daten = seite["daten"]
                with fitz.open(Path("Dateien") / seite["dateiname"]) as doc:
                    out_doc.insert_pdf(doc, from_page=daten["id"] - 1, to_page=daten["id"] - 1)

            out_doc.save(ziel_pfad)


def _seiten_sortierung(eintrag):
    seite = str(eintrag["daten"].get("seite", ""))
    match = re.search(r"\d+", seite)
    if match:
        return 0, int(match.group()), eintrag["reihenfolge"]
    return 0, 1, eintrag["reihenfolge"]