from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
import shutil
import fitz
from pathlib import Path
from pdf_logic import (
    split_a3_to_a4,
    verarbeite_pdf_ocr,
    verarbeite_einzelne_seite,
    speichere_finale_pdfs,
)
from pydantic import BaseModel
from typing import List, Optional
import json


app = FastAPI(title="Noten-API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path("Dateien").mkdir(exist_ok=True)
Path("uploads").mkdir(exist_ok=True)
app.mount("/pdfs", StaticFiles(directory="Dateien"), name="pdfs")
RULES_PATH = Path("instrument_rules.json")


class PageData(BaseModel):
    id: int
    dateiname: Optional[str] = None
    pdf_url: str
    instrument: str
    seite: str
    profil: Optional[str] = None
    geprueft: bool


class Region(BaseModel):
    x: float
    y: float
    width: float
    height: float


class SplitDocumentRequest(BaseModel):
    original_name: str
    rotation: int = 0
    split_ratio: float = 0.5
    enabled: bool = True
    target_format: str = "a4"  # Neu: "a4", "a4_landscape" oder "original"


class MarkedDocument(BaseModel):
    filename: str
    first_instrument: Optional[Region] = None
    first_page_number: Optional[Region] = None
    second_instrument: Optional[Region] = None
    second_page_number: Optional[Region] = None
    third_instrument: Optional[Region] = None
    third_page_number: Optional[Region] = None


class PageReprocessRequest(BaseModel):
    filename: str
    page_index: int
    instrument: Optional[Region] = None
    page_number: Optional[Region] = None


class InstrumentRule(BaseModel):
    erkannt: str
    ziel: str


def lade_instrument_regeln():
    if not RULES_PATH.exists():
        return []
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


@app.get("/instrument-rules/")
async def get_instrument_rules():
    return {"regeln": lade_instrument_regeln()}


@app.put("/instrument-rules/")
async def save_instrument_rules(regeln: List[InstrumentRule]):
    data = [
        rule.model_dump()
        for rule in regeln
        if rule.erkannt.strip() and rule.ziel.strip()
    ]
    RULES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"status": "success", "regeln": data}


# SCHRITT 1: PDFs hochladen und für die Schnitt-Vorschau bereitstellen
@app.post("/upload/")
async def upload_files(files: List[UploadFile] = File(...)):
    dokumente = []

    for file in files:
        original_name = Path(file.filename or "upload.pdf").name
        upload_pfad = Path("uploads") / original_name
        with open(upload_pfad, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with fitz.open(upload_pfad) as doc:
            raw_page_count = len(doc)

        dokumente.append({
            "original_name": original_name,
            "raw_page_count": raw_page_count,
            "rotation": 0,
            "split_ratio": 0.5,
            "enabled": True,
            "target_format": "a4",  # Standard: DIN A4 Hochformat
        })

    return {"status": "success", "dokumente": dokumente}


# Vorschaubild für Schritt 1 (ungeschnittene PDF inkl. Drehung als PNG)
@app.get("/preview-upload/{filename}/{page_number}")
async def preview_upload_page(filename: str, page_number: int, rotation: int = 0):
    pdf_path = Path("uploads") / Path(filename).name
    if page_number < 1 or not pdf_path.exists():
        return Response(status_code=404)

    with fitz.open(pdf_path) as doc:
        if page_number > len(doc):
            return Response(status_code=404)
        page = doc[page_number - 1]
        if rotation != 0:
            page.set_rotation((page.rotation + rotation) % 360)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return Response(content=pixmap.tobytes("png"), media_type="image/png")


# SCHRITT 2: Schnitt & Drehung ausführen und A4-PDFs erzeugen
@app.post("/split/")
async def split_documents(items: List[SplitDocumentRequest]):
    dokumente = []

    for item in items:
        original_name = Path(item.original_name).name
        upload_pfad = Path("uploads") / original_name
        if not upload_pfad.exists():
            continue

        ziel_name = f"{upload_pfad.stem}_a4.pdf"
        ziel_pfad = Path("Dateien") / ziel_name

        split_a3_to_a4(
            upload_pfad,
            ziel_pfad,
            rotation=item.rotation,
            split_ratio=item.split_ratio,
            enabled=item.enabled,
            target_format=item.target_format,
        )

        with fitz.open(ziel_pfad) as doc:
            seiten_anzahl = len(doc)

        dokumente.append({
            "filename": ziel_name,
            "original_name": original_name,
            "page_count": seiten_anzahl,
            "pdf_url": f"http://127.0.0.1:8000/pdfs/{ziel_name}",
        })

    return {"status": "success", "dokumente": dokumente}


# Vorschaubild für Schritt 2: 'def' statt 'async def' verhindert das Blockieren
@app.get("/preview/{filename}/{page_number}")
def preview_page(filename: str, page_number: int):
    pdf_path = Path("Dateien") / Path(filename).name
    if page_number < 1 or not pdf_path.exists():
        return Response(status_code=404)

    with fitz.open(pdf_path) as doc:
        if page_number > len(doc):
            return Response(status_code=404)
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return Response(content=pixmap.tobytes("png"), media_type="image/png")


# SCHRITT 3: OCR mit allen 3 Referenzseiten ausführen
@app.post("/process/")
async def process_marked_documents(documents: List[MarkedDocument]):
    ergebnisse = []
    for dokument in documents:
        ziel_pfad = Path("Dateien") / Path(dokument.filename).name
        regionen = {
            "first_instrument": dokument.first_instrument.model_dump() if dokument.first_instrument else None,
            "first_page_number": dokument.first_page_number.model_dump() if dokument.first_page_number else None,
            "second_instrument": dokument.second_instrument.model_dump() if dokument.second_instrument else None,
            "second_page_number": dokument.second_page_number.model_dump() if dokument.second_page_number else None,
            "third_instrument": dokument.third_instrument.model_dump() if dokument.third_instrument else None,
            "third_page_number": dokument.third_page_number.model_dump() if dokument.third_page_number else None,
        }
        ocr_daten = verarbeite_pdf_ocr(ziel_pfad, regionen, lade_instrument_regeln())
        for daten in ocr_daten:
            ergebnisse.append({
                "id": daten["seite_index"],
                "dateiname": dokument.filename,
                "pdf_url": f"http://127.0.0.1:8000/pdfs/{dokument.filename}#page={daten['seite_index']}",
                "instrument": daten["instrument"],
                "seite": daten["seite"],
                "profil": daten.get("profil", "second"),
                "geprueft": False,
            })

    return {"status": "success", "seiten": ergebnisse}


@app.post("/process-page/")
async def process_page(request: PageReprocessRequest):
    pdf_path = Path("Dateien") / Path(request.filename).name
    daten = verarbeite_einzelne_seite(
        pdf_path,
        request.page_index,
        request.instrument.model_dump() if request.instrument else None,
        request.page_number.model_dump() if request.page_number else None,
        lade_instrument_regeln(),
    )
    return {"instrument": daten["instrument"], "seite": daten["seite"]}


@app.post("/finalize/")
async def finalize_pdfs(pages: List[PageData]):
    seiten_daten = [page.model_dump() for page in pages]
    speichere_finale_pdfs(seiten_daten)

    # Temporäre Upload-Dateien nach dem finalen Speichern aufräumen
    for temp_file in Path("uploads").glob("*.pdf"):
        temp_file.unlink(missing_ok=True)

    return {"status": "success", "message": "Alle Dateien erfolgreich gespeichert!"}