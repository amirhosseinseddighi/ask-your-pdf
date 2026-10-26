import os
from pathlib import Path
from typing import Annotated
import uuid
from fastapi import File, status ,APIRouter, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse
import structlog
from app.helpers import pdf_processing


TEMP_FILE_DIRECTORY = "/app/tmp/documents/"
CHUNK_SIZE = 1024 * 1024

os.makedirs(os.path.dirname(TEMP_FILE_DIRECTORY), exist_ok=True)


logger = structlog.get_logger()

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document_pdf(
    pdf_document: Annotated[UploadFile, File(description="PDF Document")],
    background_task: BackgroundTasks
):
    
    
    if pdf_document.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 
            detail="Only PDFs are allowed"
        )


    filename = f"{uuid.uuid4()}.pdf"
    dst_path = Path(TEMP_FILE_DIRECTORY) / filename

    try:
        total_length = 0
        with open(dst_path, "wb") as buffer:
            while chunk := await pdf_document.read(CHUNK_SIZE):
                buffer.write(chunk)
                total_length += len(chunk)
            buffer.close()

        background_task.add_task(pdf_processing.process_pdf_document, file_path=str(dst_path))
        
    except Exception as err:
        logger.error(f"error happend in document uploading process: {err}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,detail="Something went wrong. please try again")

    return {
        "message": "Document received successfully."
    }


    