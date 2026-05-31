"""
PDF document loader using pdfplumber (better Thai font support than PyMuPDF).
Falls back to PyMuPDF if pdfplumber fails.
"""
import logging
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class RawDocument:
    filename: str
    source: str
    page_count: int
    pages: List[dict]


def clean_thai_text(text: str) -> str:
    """Clean common OCR/encoding artifacts in Thai PDF text."""
    if not text:
        return text

    # Remove null bytes and control characters
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Remove replacement characters
    text = text.replace('\ufffd', '')
    text = text.replace('\u200b', '')

    # Fix Thai sara am split ONLY for specific known words
    # "ส านักงาน" → "สำนักงาน", "ทำ" patterns
    # Be specific to avoid converting "การ" → "กำร"
    specific_fixes = [
        ('ส านักงาน', 'สำนักงาน'),
        ('ส านัก', 'สำนัก'),
        ('ทำ', 'ทำ'),  # keep
        ('ดำ', 'ดำ'),  # keep
        ('นำ', 'นำ'),  # keep
        ('จำ', 'จำ'),  # keep
        ('ยำ', 'ยำ'),  # keep
        ('ล้ำ', 'ล้ำ'),  # keep
        ('ก าหนด', 'กำหนด'),
        ('ก าลัง', 'กำลัง'),
        ('ก ากับ', 'กำกับ'),
        ('ร าไร', 'รำไร'),
        ('ลำ', 'ลำ'),
        ('ดำเนิน', 'ดำเนิน'),
        ('จำนวน', 'จำนวน'),
        ('จำกัด', 'จำกัด'),
        ('ทำการ', 'ทำการ'),
        ('ทำธุรกรรม', 'ทำธุรกรรม'),
        ('ผ าน', 'ผ่าน'),
        ('ชำระ', 'ชำระ'),
        ('ชำ', 'ชำ'),
        ('ระ', 'ระ'),
    ]
    for old, new in specific_fixes:
        text = text.replace(old, new)

    # Fix "ด้า" → "การ" (font encoding artifact in Thai legal PDFs)
    text = text.replace('ด้า', 'การ')

    # Fix amlo_guideline.pdf font issue: า encoded as ำ
    # This PDF uses a font where sara a (า) is mapped to sara am (ำ)
    # causing "การ"→"กำร", "รายงาน"→"รำยงำน", etc.
    sara_a_fixes = [
        ('รำยงำน', 'รายงาน'),
        ('รำยงำ', 'รายงา'),
        ('กำรท', 'การท'),
        ('กำรร', 'การร'),
        ('กำรก', 'การก'),
        ('กำรด', 'การด'),
        ('กำรต', 'การต'),
        ('กำรป', 'การป'),
        ('กำรส', 'การส'),
        ('กำรฟ', 'การฟ'),
        ('กำรพ', 'การพ'),
        ('กำรน', 'การน'),
        ('กำรม', 'การม'),
        ('กำรว', 'การว'),
        ('กำรห', 'การห'),
        ('กำรล', 'การล'),
        ('กำรช', 'การช'),
        ('กำรค', 'การค'),
        ('กำรบ', 'การบ'),
        ('กำรย', 'การย'),
        ('กำรข', 'การข'),
        ('กำรอ', 'การอ'),
        ('กำรเ', 'การเ'),
        ('กำรแ', 'การแ'),
        ('กำรใ', 'การใ'),
        ('กำรไ', 'การไ'),
        ('กำรจ', 'การจ'),
        ('กำรฉ', 'การฉ'),
        ('กำรถ', 'การถ'),
        ('กำรท', 'การท'),
        ('งำน', 'งาน'),
        ('ทรำบ', 'ทราบ'),
        ('ควำม', 'ความ'),
        ('สำมำรถ', 'สามารถ'),
        ('สำมำร', 'สามาร'),
        ('ทำงำน', 'ทำงาน'),
        ('กรณีที่ไม่สำมำรถ', 'กรณีที่ไม่สามารถ'),
        ('ไม่สำมำรถ', 'ไม่สามารถ'),
        ('ข้อเท็จจรงิ', 'ข้อเท็จจริง'),
        ('เพอื่', 'เพื่อ'),
    ]
    for wrong, correct in sara_a_fixes:
        text = text.replace(wrong, correct)

    # Remove Thai legal footnote markers e.g. "๑", "๒", "๑๒๓" standalone
    # that appear as superscript numbers injected mid-paragraph
    text = re.sub(r'(?<=[^\n])\s*[๑๒๓๔๕๖๗๘๙๐]{1,3}\s*(?=[ก-๙A-Za-z])', ' ', text)

    # Remove lines that are only footnote numbers or short markers
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are only Thai numerals or very short markers
        if re.fullmatch(r'[๑๒๓๔๕๖๗๘๙๐\s\*]+', stripped) and len(stripped) < 5:
            continue
        cleaned.append(line)
    text = '\n'.join(cleaned)

    # Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


class PDFLoader:
    def load(self, path: str, source: str = "unknown") -> RawDocument:
        """Load PDF with pdfplumber for better Thai text extraction."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        # Try pdfplumber first (better Thai support)
        try:
            return self._load_pdfplumber(path, source)
        except Exception as e:
            logger.warning(f"pdfplumber failed for {path.name}: {e}, falling back to PyMuPDF")
            return self._load_pymupdf(path, source)

    def _load_pdfplumber(self, path: Path, source: str) -> RawDocument:
        import pdfplumber

        pages = []
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text(
                    x_tolerance=2,
                    y_tolerance=2,
                    layout=True,
                    x_density=7.25,
                    y_density=13,
                ) or ""
                text = clean_thai_text(text)
                if not text:
                    logger.warning(f"Empty page {page_num} in {path.name}")
                    continue
                pages.append({"page_num": page_num, "text": text})

        logger.info(f"Loaded {path.name} via pdfplumber: {len(pages)} pages")
        return RawDocument(
            filename=path.name,
            source=source,
            page_count=page_count,
            pages=pages,
        )

    def _load_pymupdf(self, path: Path, source: str) -> RawDocument:
        import fitz
        doc = fitz.open(str(path))
        pages = []
        for page_num, page in enumerate(doc, start=1):
            text = clean_thai_text(page.get_text("text"))
            if not text:
                continue
            pages.append({"page_num": page_num, "text": text})

        logger.info(f"Loaded {path.name} via PyMuPDF: {len(pages)} pages")
        return RawDocument(
            filename=path.name,
            source=source,
            page_count=doc.page_count,
            pages=pages,
        )