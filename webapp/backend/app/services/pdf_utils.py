import io

from pypdf import PdfReader


def extract_pages(data: bytes, content_type: str) -> list[str]:
    """คืน list ของข้อความต่อหน้า — .txt ถือเป็น 1 หน้า, .pdf แยกข้อความทีละหน้าจริง

    เก็บ page boundary ไว้ตั้งแต่ขั้นนี้ เพื่อให้ chunk ที่ตามมา trace กลับไปยังเลขหน้าได้ (citation)
    """
    if content_type == "application/pdf" or content_type == "":
        try:
            reader = PdfReader(io.BytesIO(data))
            return [page.extract_text() or "" for page in reader.pages]
        except Exception:
            pass
    return [data.decode("utf-8", errors="ignore")]
