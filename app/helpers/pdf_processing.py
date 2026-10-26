from pathlib import Path
import structlog

logger = structlog.get_logger()


def process_pdf_document(file_path: str):
    document_path = Path(file_path)
    logger.info("Document received!!!")