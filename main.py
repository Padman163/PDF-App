from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
import shutil
import fitz
from pathlib import Path
from pdf_logic import split_a3_to_a4, verarbeite_pdf_ocr, verarbeite_einzelne_seite, speichere_finale_pdfs
from pydantic import BaseModel
from typing import List, Optional
import json


app = FastAPI(title="Noten-API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"], 
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
    pdf_url: str
    instrument: str
    seite: str
    geprueft: bool

class Region(BaseModel):
    x: float
    y: float
    width: float
    height: float

class MarkedDocument(BaseModel):
    filename: str
    first_instrument: Optional[Region] = None
    first_page_number: Optional[Region] = None
    second_instrument: Optional[Region] = None
    second_page_number: Optional[Region] = None

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
    data = [rule.model_dump() for rule in regeln if rule.erkannt.strip() and rule.ziel.strip()]
    RULES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "success", "regeln": data}

@app.post("/finalize/")
async def finalize_pdfs(pages: List[PageData]):
    seiten_daten = [page.model_dump() for page in pages]
    speichere_finale_pdfs(seiten_daten)
    return {"status": "success", "message": "Alle Dateien erfolgreich gespeichert!"}

@app.post("/upload/")
async def upload_and_process(files: List[UploadFile] = File(...)):
    dokumente = []

    for file in files:
        original_name = Path(file.filename or "upload.pdf").name
        upload_pfad = Path("uploads") / original_name
        with open(upload_pfad, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        ziel_name = f"{upload_pfad.stem}_a4.pdf"
        ziel_pfad = Path("Dateien") / ziel_name
        split_a3_to_a4(upload_pfad, ziel_pfad)
        with fitz.open(ziel_pfad) as doc:
            seiten_anzahl = len(doc)

        upload_pfad.unlink(missing_ok=True)
        dokumente.append({
            "filename": ziel_name,
            "original_name": original_name,
            "page_count": seiten_anzahl,
            "pdf_url": f"http://localhost:8000/pdfs/{ziel_name}"
        })

    return {"status": "success", "dokumente": dokumente}

@app.get("/preview/{filename}/{page_number}")
async def preview_page(filename: str, page_number: int):
    pdf_path = Path("Dateien") / Path(filename).name
    if page_number < 1 or not pdf_path.exists():
        return Response(status_code=404)

    with fitz.open(pdf_path) as doc:
        if page_number > len(doc):
            return Response(status_code=404)
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return Response(content=pixmap.tobytes("png"), media_type="image/png")

@app.post("/process/")
async def process_marked_documents(documents: List[MarkedDocument]):
    ergebnisse = []
    for dokument in documents:
        ziel_pfad = Path("Dateien") / Path(dokument.filename).name
        regionen = {
            "first_instrument": dokument.first_instrument.model_dump() if dokument.first_instrument else None,
            "first_page_number": dokument.first_page_number.model_dump() if dokument.first_page_number else None,
            "second_instrument": dokument.second_instrument.model_dump() if dokument.second_instrument else None,
            "second_page_number": dokument.second_page_number.model_dump() if dokument.second_page_number else None
        }
        ocr_daten = verarbeite_pdf_ocr(ziel_pfad, regionen, lade_instrument_regeln())
        for daten in ocr_daten:
            ergebnisse.append({
                "id": daten["seite_index"],
                "dateiname": dokument.filename,
                "pdf_url": f"http://localhost:8000/pdfs/{dokument.filename}#page={daten['seite_index']}",
                "instrument": daten["instrument"],
                "seite": daten["seite"],
                "profil": daten.get("profil", "second"),
                "geprueft": False
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