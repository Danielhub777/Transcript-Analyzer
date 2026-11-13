from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from starlette.concurrency import run_in_threadpool

from packages.analytics.compare_transcripts import compare_transcripts
from packages.analytics.read_transcripts import analyze_text


app = FastAPI()


class TranscriptRequest(BaseModel):
    text: str


class ComparisonRequest(BaseModel):
    previous_text: str
    current_text: str


def read_pdf_text(contents: bytes, filename: str) -> str:
    try:
        reader = PdfReader(BytesIO(contents))

        if reader.is_encrypted:
            raise HTTPException(
                status_code=400,
                detail=f"{filename}: Upload an unlocked PDF.",
            )

        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            lines = [line.split() for line in text.splitlines() if line.strip()]
            if lines and sum(len(line) == 1 for line in lines) > len(lines) / 2:
                text = page.extract_text(extraction_mode="layout") or text
            pages.append(text)
        return "\n\n".join(pages)
    except (PdfReadError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail=f"{filename}: Could not read the PDF.",
        ) from error


async def read_transcript_upload(upload: UploadFile) -> str:
    filename = upload.filename or "transcript"
    extension = Path(filename).suffix.lower()

    if extension not in {".txt", ".pdf"}:
        raise HTTPException(
            status_code=400,
            detail=f"{filename}: Upload a .txt or .pdf transcript.",
        )

    contents = await upload.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail=f"{filename}: The uploaded file is empty.",
        )

    if extension == ".pdf":
        text = await run_in_threadpool(read_pdf_text, contents, filename)
    else:
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(
                status_code=400,
                detail=f"{filename}: Save the text file using UTF-8 encoding.",
            ) from error

    if not text.strip():
        detail = (
            "No selectable text found. Run OCR if this is a scanned PDF."
            if extension == ".pdf"
            else "The transcript contains no text."
        )
        raise HTTPException(status_code=400, detail=f"{filename}: {detail}")

    return text


@app.get("/")
def home():
    return {"message": "EarningsScope backend is running"}


@app.post("/analyze")
def analyze_transcript(transcript: TranscriptRequest):
    try:
        return analyze_text(transcript.text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/analyze-file")
async def analyze_file(file: UploadFile = File(...)):
    text = await read_transcript_upload(file)

    try:
        result = await run_in_threadpool(analyze_text, text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"source_file": file.filename, **result}


@app.post("/compare")
def compare_calls(request: ComparisonRequest):
    try:
        return compare_transcripts(request.previous_text, request.current_text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/compare-files")
async def compare_files(
    previous_file: UploadFile = File(...),
    current_file: UploadFile = File(...),
    management_speakers: str = Form(""),
):
    previous_text = await read_transcript_upload(previous_file)
    current_text = await read_transcript_upload(current_file)

    selected_speakers = None
    if management_speakers.strip():
        selected_speakers = [
            name.strip()
            for name in management_speakers.split(",")
            if name.strip()
        ]

    try:
        result = await run_in_threadpool(
            compare_transcripts,
            previous_text,
            current_text,
            management_speakers=selected_speakers,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "previous_file": previous_file.filename,
        "current_file": current_file.filename,
        **result,
    }
