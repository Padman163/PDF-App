import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pathlib import Path

# WICHTIG: Passe diesen Pfad an, falls du Tesseract woanders installiert hast
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

import re

def extrahiere_instrument_und_seite(ocr_text):
    text = ocr_text.strip()
    
    # Fall 1: Explizite Seitenangaben (z.B. "S. 4", "Seite 12", "P. 3")
    # (?i) ignoriert Groß-/Kleinschreibung. \s* erlaubt Leerzeichen vor der Zahl.
    match = re.search(r'(?i)(?:s\.|seite|p\.|page)\s*(\d+)', text)
    if match:
        seite = match.group(1)
        # Entferne den gefundenen Teil aus dem Originaltext, um das Instrument übrig zu behalten
        instrument = text.replace(match.group(0), '').strip()
        # Säubere übrig gebliebene Bindestriche oder Kommas am Rand
        instrument = re.sub(r'^[\-\.,\s]+|[\-\.,\s]+$', '', instrument)
        return instrument, seite

    # Fall 2: Isolierte Zahl am Ende des Textes (z.B. "1. Klarinette in B  3")
    # Sucht nach Leerzeichen, optionalen Trennern (- oder /) und einer Zahl ganz am Ende ($)
    match = re.search(r'\s+[-/]?\s*(\d+)\s*$', text)
    if match:
        seite = match.group(1)
        instrument = text[:match.start()].strip()
        instrument = re.sub(r'^[\-\.,\s]+|[\-\.,\s]+$', '', instrument)
        return instrument, seite

    # Fall 3: Isolierte Zahl ganz am Anfang (z.B. "4   1. Klarinette in B")
    # Sucht nach einer Zahl am Zeilenanfang (^), gefolgt von Leerzeichen
    match = re.search(r'^\s*(\d+)\s+[-/]?\s*', text)
    if match:
        seite = match.group(1)
        instrument = text[match.end():].strip()
        instrument = re.sub(r'^[\-\.,\s]+|[\-\.,\s]+$', '', instrument)
        return instrument, seite

    # Fall 4: Keine Seitenzahl gefunden (Fallback für die Vue-Oberfläche)
    return text, ""

# --- Testfälle ---
if __name__ == "__main__":
    test_strings = [
        "S. 4 1. Klarinette in B",
        "1. Alto Saxophone  -  12",
        "3   Flöte",
        "Tenorhorn 1/2 Seite 5",
        "Schlechtes OCR ohne Zahl"
    ]
    
    for test in test_strings:
        inst, s = extrahiere_instrument_und_seite(test)
        print(f"Original: '{test}' -> Instrument: '{inst}', Seite: '{s}'")


def lese_kopfzeile(pdf_pfad):
    doc = fitz.open(pdf_pfad)
    
    for seiten_nummer, page in enumerate(doc):
        # 1. Definiere den Bereich: Nur die oberen 12% der Seite (die Kopfzeile)
        rect = page.rect
        kopf_bereich = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.height * 0.12)
        
        # 2. Rendere diesen Bereich als Bild. 
        # Matrix(3, 3) verdreifacht die Auflösung (ca. 300 DPI) für eine viel bessere OCR-Erkennung!
        zoom = fitz.Matrix(3, 3)
        pix = page.get_pixmap(matrix=zoom, clip=kopf_bereich)
        
        # 3. Konvertiere das Bild-Objekt in ein Format, das pytesseract versteht
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # 4. Führe die OCR-Erkennung aus
        # config='--psm 6' zwingt Tesseract, den Text als einen einzigen Block zu lesen.
        # Das hilft, wenn Seitenzahl (rechts) und Instrument (mittig) weit auseinander stehen.
        text = pytesseract.image_to_string(img, config='--psm 6')
        
        # Säubere den Text (entfernt überflüssige Zeilenumbrüche)
        sauberer_text = " ".join(text.split())
        
        # Neues Regex-Parsing
        instrument, seite = extrahiere_instrument_und_seite(sauberer_text)
        
        print(f"--- Seite {seiten_nummer + 1} ---")
        print(f"Erkanntes Instrument : {instrument}")
        print(f"Erkannte Seitenzahl  : {seite}\n")
        
    doc.close()

if __name__ == "__main__":
    ordner = Path("Dateien")
    # Sucht die erste geschnittene Datei im Ordner für den Test
    test_datei = next(ordner.glob("*_geschnitten.pdf"), None)
    
    if test_datei:
        print(f"Analysiere: {test_datei.name}")
        lese_kopfzeile(test_datei)
    else:
        print("Fehler: Lege zuerst eine geschnittene PDF in den Ordner 'Dateien'.")