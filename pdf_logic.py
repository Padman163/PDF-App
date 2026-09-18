import fitz
import pytesseract
from PIL import Image
from pathlib import Path
import re

INSTRUMENTE = {
    "double bass": "Kontrabass",
    "contrabass": "Kontrabass",
    # --- NEU: Zusammengesetzte Instrumente verhindern das Zerstückeln ---
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
    # -------------------------------------------------------------------
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

def split_a3_to_a4(input_path, output_path):
    doc = fitz.open(input_path)
    out_doc = fitz.open()

    for page in doc:
        rect = page.rect
        if rect.width > rect.height:
            mid = rect.width / 2
            out_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)
            out_doc[-1].set_cropbox(fitz.Rect(rect.x0, rect.y0, mid, rect.y1))

            out_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)
            out_doc[-1].set_cropbox(fitz.Rect(mid, rect.y0, rect.x1, rect.y1))
        else:
            out_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)

    out_doc.save(output_path)
    out_doc.close()
    doc.close()

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
    """Erkennt Titel, Instrument und Seitenzahl aus den Seitenrändern."""
    doc = fitz.open(pdf_pfad)
    ergebnisse = []

    for seiten_nummer, page in enumerate(doc):
        rect = page.rect
        if regionen:
            profil = "first" if seiten_nummer == 0 else "second"
            instrument_region = regionen.get(f"{profil}_instrument")
            if instrument_region:
                instrument_bereich = _region_rect(rect, instrument_region)
                instrument_text = _ocr_bereich(page, instrument_bereich, psm=7)
                instrument = erkenne_instrument(instrument_text, instrument_regeln)
            else:
                instrument = ""

            zahlen_bereich = regionen.get(f"{profil}_page_number")
            if seiten_nummer == 0 and not zahlen_bereich:
                seite = "1"
            elif zahlen_bereich:
                zahlen_text = _ocr_bereich(page, _region_rect(rect, zahlen_bereich), psm=7)
                seite = _einzelne_zahl(zahlen_text)
            else:
                seite = ""

            ergebnisse.append({
                "seite_index": seiten_nummer + 1,
                "instrument": instrument,
                "seite": seite,
                "profil": profil
            })
            continue

        obere_zone = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.height * 0.22)
        obere_mitte = fitz.Rect(rect.width * 0.35, rect.y0, rect.width * 0.65, rect.height * 0.18)
        untere_mitte = fitz.Rect(rect.width * 0.35, rect.height * 0.82, rect.width * 0.65, rect.y1)

        titel_text = _ocr_bereich(page, obere_zone, psm=6)
        seiten_text = _ocr_bereich(page, rect, psm=11)
        obere_zahl = _ocr_zahl(page, obere_mitte)
        untere_zahl = _ocr_zahl(page, untere_mitte)

        # Eine Seite mit sichtbarem Stücktitel ist immer die erste Seite.
        hat_titel = _enthaelt_stuecktitel(titel_text)
        if hat_titel:
            seite = "1"
        else:
            erkannte_seite = obere_zahl or untere_zahl or ""
            seite = "" if erkannte_seite == "1" else erkannte_seite

        instrument = erkenne_instrument(seiten_text, instrument_regeln)
        ergebnisse.append({
            "seite_index": seiten_nummer + 1,
            "instrument": instrument,
            "seite": seite
        })

    doc.close()
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
    
    # Toleranterer Abgleich: Bindestriche werden ignoriert, falls OCR "Bass-Clarinet" liest
    text_suche = bereinigter_text.casefold().replace("-", " ")
    
    gefundene_instrumente = []
    
    # 1. Benutzerdefinierte Regeln (aus instrument_rules.json)
    for regel in instrument_regeln or []:
        begriff = regel.get("erkannt", "").strip().casefold().replace("-", " ")
        ziel = regel.get("ziel", "").strip()
        
        if begriff and ziel:
            # NEU: Die Regex fängt jetzt auch Doppelstimmen wie "1/2" oder "1-2" ab!
            match = re.search(
                rf"(?<![a-zäöüß]){re.escape(begriff)}(?![a-zäöüß])\s*(?:[-:]?\s*(\d+(?:[/-]\d+)?))?",
                text_suche,
            )
            if match:
                nummer = f" {match.group(1)}" if match.group(1) else ""
                gefundene_instrumente.append((len(begriff) + 10000, f"{ziel}{nummer}"))

    # 2. Standard-Wörterbuch (Fallback)
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
        
    # Pickt den Treffer mit der höchsten Wertung (längstes Wort oder JSON-Regel)
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
    ziel_ordner.mkdir(exist_ok=True) # Erstellt den Ordner, falls er nicht existiert

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
        out_doc = fitz.open()

        for seite in pdf_seiten:
            daten = seite["daten"]
            with fitz.open(Path("Dateien") / seite["dateiname"]) as doc:
                out_doc.insert_pdf(doc, from_page=daten["id"] - 1, to_page=daten["id"] - 1)

        out_doc.save(ziel_pfad)
        out_doc.close()


def _seiten_sortierung(eintrag):
    seite = str(eintrag["daten"].get("seite", ""))
    match = re.search(r"\d+", seite)
    if match:
        return 0, int(match.group()), eintrag["reihenfolge"]
    # Eine Titelseite ohne eingetragene Seitenzahl gehört an den Anfang.
    return 0, 1, eintrag["reihenfolge"]
    
    # Optional: Das komplette A4-Sammeldokument am Ende löschen
    # quell_pfad.unlink(missing_ok=True)