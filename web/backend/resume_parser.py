"""
Server-side Resume Parser for PDF and DOCX documents.
Extracts clean, searchable plain text from uploaded resume files.
"""
import io
import re
from pathlib import Path
from typing import Tuple
from pypdf import PdfReader
import docx
from web.backend.config import PROFILE_RESUMES_DIR, UPLOADS_DIR


class ResumeParser:
    """
    Handles file saving and text extraction for PDF and DOCX files.
    """

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Removes excessive whitespace and unprintable characters."""
        # Replace non-breaking spaces and unusual whitespace
        t = re.sub(r"[\xa0\u200b\u200e\ufeff]", " ", text)
        # Normalize multiple newlines and spaces
        t = re.sub(r"\r\n|\r", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        t = re.sub(r"[ \t]+", " ", t)
        return t.strip()

    @classmethod
    def ocr_pdf(cls, file_bytes: bytes) -> str:
        """
        Performs OCR on scanned or image-based PDF pages when text extraction yields no digital characters.
        """
        ocr_pages = []

        # Strategy A: High-fidelity page rendering via pypdfium2
        try:
            import pypdfium2 as pdfium
            import pytesseract
            pdf = pdfium.PdfDocument(file_bytes)
            for page in pdf:
                pil_image = page.render(scale=2).to_pil()
                page_text = pytesseract.image_to_string(pil_image)
                if page_text.strip():
                    ocr_pages.append(page_text)
            if ocr_pages:
                return "\n\n".join(ocr_pages)
        except Exception:
            pass

        # Strategy B: Extract embedded images via pypdf
        try:
            import pytesseract
            from PIL import Image
            reader = PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                for img in getattr(page, "images", []):
                    pil_img = Image.open(io.BytesIO(img.data))
                    txt = pytesseract.image_to_string(pil_img)
                    if txt.strip():
                        ocr_pages.append(txt)
            if ocr_pages:
                return "\n\n".join(ocr_pages)
        except Exception:
            pass

        # Strategy C: pdf2image
        try:
            from pdf2image import convert_from_bytes
            import pytesseract
            images = convert_from_bytes(file_bytes)
            for img in images:
                txt = pytesseract.image_to_string(img)
                if txt.strip():
                    ocr_pages.append(txt)
            if ocr_pages:
                return "\n\n".join(ocr_pages)
        except Exception:
            pass

        return ""

    @classmethod
    def extract_from_pdf(cls, file_bytes: bytes) -> str:
        """Extracts text from PDF bytes using pypdf, falling back to OCR if scanned or image-based."""
        text = ""
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_text = []
            for page in reader.pages:
                extracted = page.extract_text() or ""
                if extracted.strip():
                    pages_text.append(extracted)
            text = cls.clean_text("\n\n".join(pages_text))
        except Exception:
            pass

        # If digital extraction yielded meaningful text (>= 50 chars), return it
        if len(text.strip()) >= 50:
            return text

        # Fallback: Scanned or image-only PDF (e.g. Canva / graphic designer / photo PDFs)
        ocr_text = cls.ocr_pdf(file_bytes)
        if ocr_text.strip():
            return cls.clean_text(ocr_text)

        return text

    @classmethod
    def extract_from_image(cls, file_bytes: bytes) -> str:
        """Extracts text from image resume files (PNG, JPG, WEBP, etc.) via OCR."""
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(img)
            return cls.clean_text(text)
        except Exception as e:
            raise ValueError(f"Could not perform OCR on image resume: {e}")

    @classmethod
    def extract_from_docx(cls, file_bytes: bytes) -> str:
        """Extracts text from DOCX bytes using python-docx."""
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    paragraphs.append(" | ".join(row_text))
        return cls.clean_text("\n".join(paragraphs))

    @classmethod
    def process_upload(cls, filename: str, file_bytes: bytes, session_id: str = "default") -> Tuple[str, str]:
        """
        Saves candidate resume to profile_resumes directory isolated by session_id
        and returns (saved_file_path, extracted_text).
        Supports: PDF (digital & scanned), DOCX, DOC, PNG, JPG, JPEG, WEBP, BMP, TIFF, TXT, RTF, MD.
        """
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            text = cls.extract_from_pdf(file_bytes)
        elif ext in [".docx", ".doc"]:
            text = cls.extract_from_docx(file_bytes)
        elif ext in [".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"]:
            text = cls.extract_from_image(file_bytes)
        elif ext in [".txt", ".md", ".rtf"]:
            try:
                raw = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raw = file_bytes.decode("latin-1", errors="replace")
            text = cls.clean_text(raw)
        else:
            raise ValueError(
                f"Unsupported resume file format: '{ext}'. "
                f"Supported formats: PDF (digital or scanned), Word (DOCX, DOC), Images (PNG, JPG, WEBP), and TXT."
            )

        safe_name = re.sub(r"[^\w\.-]", "_", filename)
        clean_sess = re.sub(r"[^a-zA-Z0-9_\-]", "", str(session_id))[:64] or "default"
        target_dir = PROFILE_RESUMES_DIR / clean_sess
        target_dir.mkdir(parents=True, exist_ok=True)
        save_path = target_dir / safe_name
        save_path.write_bytes(file_bytes)

        # Mirror to uploads directory for legacy compatibility
        try:
            uploads_sess_dir = UPLOADS_DIR / clean_sess
            uploads_sess_dir.mkdir(parents=True, exist_ok=True)
            (uploads_sess_dir / safe_name).write_bytes(file_bytes)
        except Exception:
            pass

        return str(save_path.resolve()), text

    @classmethod
    def extract_contact_info(cls, text: str) -> dict:
        """Extracts contact details from resume text with OCR error tolerance."""
        # Handle emails split across line breaks e.g. foo@gmail\ncom
        clean_text_for_contact = re.sub(r"(@[\w\.-]+)\s*[\r\n\s]+\s*([a-zA-Z]{2,6})\b", r"\1.\2", text)
        email_match = re.search(r"[\w\.\-\+]+@[\w\.-]+\.[a-zA-Z]{2,}", clean_text_for_contact)
        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}", text)
        linkedin_match = re.search(r"https?://(?:www[\.-]?)?(?:linkedin|inkedin)\.com/in/[\w\-]+", text, re.IGNORECASE)
        linkedin_url = ""
        if linkedin_match:
            linkedin_url = re.sub(r"https?://(?:www[\.-]?)?(?:linkedin|inkedin)\.com", "https://www.linkedin.com", linkedin_match.group(0))

        first_line = text.strip().split("\n")[0].strip() if text.strip() else ""
        name = first_line if len(first_line) < 40 and not any(c in first_line for c in "@:/") else "Candidate"

        return {
            "name": name,
            "email": email_match.group(0) if email_match else "",
            "phone": phone_match.group(0).strip() if phone_match else "",
            "linkedin_url": linkedin_url,
        }
