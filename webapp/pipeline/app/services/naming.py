import random

import dspy
from pythainlp.corpus import thai_stopwords
from pythainlp.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer

from app.config import settings

_THAI_STOPWORDS = thai_stopwords()


def _thai_tokenizer(text: str) -> list[str]:
    """sklearn default token_pattern (\\w+) แตกคำไทยผิด เพราะสระ/วรรณยุกต์เป็น combining mark
    ไม่ match \\w แยกคำกลางคำ (เช่น 'ระดับน้ำ' -> 'ระด', 'บน', 'ำ') ต้องใช้ตัวตัดคำไทยจริงแทน
    """
    tokens = word_tokenize(text, engine="newmm")
    return [t for t in tokens if t.strip() and len(t) > 1 and t not in _THAI_STOPWORDS and not t.isdigit()]


class TopicLabeler(dspy.Signature):
    """วิเคราะห์ข้อความตัวอย่างและตั้งชื่อหมวดหมู่ของปัญหา/ภัยพิบัติที่เกิดขึ้น เป็นภาษาไทยแบบสั้น กระชับ สื่อความหมายถึงภาพรวมของข้อความทั้งหมด"""

    samples = dspy.InputField(desc="รายการข้อความตัวอย่างที่อยู่ในกลุ่มเดียวกัน")
    taxonomy_name = dspy.OutputField(desc="ชื่อหมวดหมู่สั้น กระชับ เป็นภาษาไทย")


def _configure_llm(llm_backend: str) -> None:
    if llm_backend == "ollama":
        lm = dspy.LM(f"ollama_chat/{settings.ollama_model}", api_base=settings.ollama_host, api_key="")
    else:
        lm = dspy.LM(settings.dspy_model, api_key=settings.openai_api_key or None)
    dspy.configure(lm=lm)


def _llm_available() -> bool:
    try:
        dspy.Predict(TopicLabeler)(samples="- ทดสอบระบบ")
        return True
    except Exception:
        return False


def _keyword_cluster_names(texts_by_cluster: dict[int, list[str]], top_n: int = 3) -> dict[int, str]:
    """Fallback ตั้งชื่อ cluster ด้วย TF-IDF keyword (ไม่พึ่ง LLM) — ดู docs/hierarchical-taxonomy-concept.md"""
    cluster_ids = sorted(texts_by_cluster.keys())
    corpus = [" ".join(texts_by_cluster[cid]) for cid in cluster_ids]

    try:
        vectorizer = TfidfVectorizer(max_features=2000, tokenizer=_thai_tokenizer, token_pattern=None)
        tfidf = vectorizer.fit_transform(corpus)
        terms = vectorizer.get_feature_names_out()
    except ValueError:
        return {cid: f"cluster_{cid}" for cid in cluster_ids}

    names: dict[int, str] = {}
    for row_idx, cid in enumerate(cluster_ids):
        row = tfidf[row_idx].toarray().flatten()
        top_idx = row.argsort()[::-1][:top_n]
        top_terms = [terms[i] for i in top_idx if row[i] > 0]
        names[cid] = "-".join(top_terms) if top_terms else f"cluster_{cid}"
    return names


def name_clusters(
    texts: list[str],
    labels,
    llm_backend: str | None = None,
    sample_size: int = 15,
) -> dict[int, str]:
    """คืน {cluster_id: name} เฉพาะ cluster จริง (label >= 0) — ไม่ตั้งชื่อ noise(-1)/bridge(-2)
    bridge point เป็น cross-reference ไม่ใช่หัวข้อของตัวเอง (docs section 10-11)
    """
    llm_backend = llm_backend or settings.llm_backend
    cluster_ids = sorted({int(c) for c in labels if c >= 0})
    texts_by_cluster = {cid: [t for t, lbl in zip(texts, labels) if lbl == cid] for cid in cluster_ids}
    keyword_fallback = _keyword_cluster_names(texts_by_cluster)

    if not cluster_ids:
        return {}

    try:
        _configure_llm(llm_backend)
        llm_ok = _llm_available()
    except Exception:
        llm_ok = False

    if not llm_ok:
        return keyword_fallback

    predictor = dspy.Predict(TopicLabeler)
    names: dict[int, str] = {}
    rng = random.Random(42)

    for cid in cluster_ids:
        cluster_texts = texts_by_cluster[cid]
        sample = rng.sample(cluster_texts, k=min(len(cluster_texts), sample_size))
        samples_str = "\n".join(f"- {t}" for t in sample)
        try:
            pred = predictor(samples=samples_str)
            names[cid] = pred.taxonomy_name.strip(' "\'')
        except Exception:
            names[cid] = keyword_fallback.get(cid, f"cluster_{cid}")

    return names
