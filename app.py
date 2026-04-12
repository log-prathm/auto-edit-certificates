from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
import shutil
from pathlib import Path
import subprocess
from pydantic import BaseModel

app = FastAPI()

class FileName(BaseModel):
    fileName: str

@app.get("/")
def home():
    return FileResponse("frontend/index.html")

@app.post("/textUpload")
async def textUpload(file: UploadFile = File(...)):
    save_path = Path(file.filename)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": f"{file.filename} uploaded successfully", "status":"ok"}

@app.post("/generateCertificates")
async def generateCertificates(req: FileName):
    process = subprocess.run(
        [
            "python", "main.py",
            "--template", "certificate.jpeg",
            "--names", req.fileName,
            "--outdir", "output",
            "--y", "410",
            "--box-h", "120",
            "--font", "C:/Windows/Fonts/BRUSHSCI.TTF",
            "--font-size", "48",
        ],
        capture_output=True,
        text=True
    )



    return {
    "message": "Certificate generated successfully" if process.returncode == 0 else "Error generating certificates",
    "stdout": process.stdout,
    "stderr": process.stderr,
    "returncode": process.returncode
}