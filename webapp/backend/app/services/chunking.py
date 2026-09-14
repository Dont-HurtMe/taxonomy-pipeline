from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter


def chunk_pages(pages: list[str], chunk_size: int, chunk_overlap: int) -> list[tuple[str, int]]:
    """Split ข้อความแต่ละหน้าเป็น chunk ด้วย SentenceSplitter คืน (chunk_text, page_number) ต่อ chunk

    หน้าแยกกันตั้งแต่แรก (ไม่รวมเป็น doc เดียวก่อน split) กัน chunk คาบเกี่ยวข้ามหน้า
    ทำให้ page_number ต่อ chunk แม่นยำ — ใช้เป็น citation ตาม docs/hierarchical-taxonomy-concept.md section 10
    """
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    documents = [Document(text=text, id_=str(i)) for i, text in enumerate(pages) if text.strip()]
    if not documents:
        return []
    nodes = splitter.get_nodes_from_documents(documents)
    return [(node.get_content(), int(node.ref_doc_id)) for node in nodes]
