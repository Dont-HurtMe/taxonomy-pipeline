# Taxonomy Pipeline — Webapp

Port ของ pipeline ใน `lab/` (chunk → embed → UMAP → `KDEWatershedClusterer` พร้อม bridge/boundary point → naming) ขึ้นเป็นระบบจริง ตามแนวคิดใน `docs/hierarchical-taxonomy-concept.md`

## Stack

- **backend/** — FastAPI (async) + SQLAlchemy — เลือกแทน Django เพราะเบากว่าและ throughput สูงกว่าใน workload ที่มี I/O รอ (DB, MinIO, Qdrant, LLM) เยอะ
- **Postgres** — เก็บ metadata: project, document, chunk, pipeline run, cluster result, chunk↔cluster assignment (รวม bridge point), UMAP grid search ranking
- **MinIO** — เก็บไฟล์ PDF/txt ต้นฉบับ (S3-compatible)
- **Qdrant** — เก็บ embedding vector มิติสูง (bge-m3) ต่อ project ไว้ทำ semantic search — แยกจาก 2D UMAP coordinate ที่อยู่ใน Postgres โดยเจตนา (ดู `docs/` section 3: search ต้องใช้ vector มิติสูง ไม่ใช่ projection ที่ lossy)
- **frontend/** — Node.js + Express + EJS (server-rendered, ไม่มี build step) เรียก backend ผ่าน REST API
- **nginx** — reverse proxy หน้าเดียว (`/` → frontend, `/api/` → backend) เผื่อ scale-out backend หลาย replica ทีหลัง

## รัน

```bash
cd webapp
docker compose up --build
```

เปิด `http://localhost` (nginx) — หรือ backend ตรง ๆ ที่ `:8000`, frontend ตรง ๆ ที่ `:3000`, MinIO console ที่ `:9001`

ค่า default ใน `.env` ตั้งไว้ให้รันได้ทันทีโดยไม่ต้องมี API key ใด ๆ: `LLM_BACKEND=openai` แต่ `OPENAI_API_KEY` ว่าง → LLM health check ล้มเหลว → **fallback เป็น TF-IDF keyword ตั้งชื่อ cluster อัตโนมัติ** (ไม่ error) ถ้าต้องการชื่อ cluster จาก LLM จริง ใส่ `OPENAI_API_KEY` หรือสลับ `LLM_BACKEND=ollama` (ต้องมี ollama server ให้ backend เข้าถึงได้ตาม `OLLAMA_HOST`)

## GPU (embedding model)

`sentence-transformers` auto-detect CUDA ถ้ามี GPU ใน container/host — ถ้าเจอ error รูปแบบ `CUDA error: no kernel image is available for execution on the device` (GPU รุ่นเก่าเทียบ torch build ไม่ตรง) โค้ดจะ fallback เป็น CPU อัตโนมัติ (ดู `backend/app/services/embedding.py`) หรือ set `EMBED_DEVICE=cpu` ใน `.env` บังคับตรง ๆ

การรัน GPU ใน container ต้องใช้ NVIDIA Container Toolkit เพิ่ม `deploy.resources.reservations.devices` ใน `docker-compose.yml` service `backend` เอง (ไม่ได้ตั้งไว้ default เพราะขึ้นกับ driver/CUDA version ของเครื่องแต่ละเครื่อง — ดูปัญหาที่เคยเจอกับ TITAN Xp/Pascal ก่อนหน้านี้)

## Flow

1. สร้าง Project → นำเข้าข้อมูลด้วยวิธีใดวิธีหนึ่ง:
   - อัปโหลดเอกสาร (PDF/txt) → เก็บไฟล์ลง MinIO, สกัดข้อความทีละหน้า, chunk ด้วย `llama-index` `SentenceSplitter` (เก็บ `page_number` ต่อ chunk)
   - หรือส่ง `list[str]` ตรง ๆ ผ่าน `POST /api/projects/{id}/texts` (body `{"texts": [...], "source_name": "..."}`) — เช่นจาก script ที่โหลด CSV ด้วย pandas แล้ว `texts = df["content"].dropna().astype(str).tolist()` เข้า path chunking เดียวกัน (`page_number` = index ใน list ที่ส่งมา) มีฟอร์ม paste texts ในหน้า project ให้ทดสอบผ่านเว็บได้เลยโดยไม่ต้องเขียน script
2. กด "เริ่มรัน" → สร้าง `PipelineRun` (status `PENDING`) → รันใน background thread แยกจาก HTTP request ไล่ทีละ step (`current_step`: `LOADING_CHUNKS` → `EMBEDDING` → `UPSERT_VECTORS` → `UMAP_SEARCH` → `CLUSTERING` → `NAMING` → `PERSISTING` → `DONE`/`FAILED`) — หน้า run poll สถานะนี้ auto-refresh ทุก 4 วิให้เห็น progress ระหว่างรอ
3. หน้า **Interactive Visualization (2D scatter)** — Plotly, filter cluster, detail panel (doc id/cluster name/text), search highlight
4. หน้า **Taxonomy (สารบัญ)** — แผนภาพต้นไม้ (Plotly Treemap, ตอนนี้ 1 ชั้น root→cluster) + citation list ต่อ cluster + cross-reference ของ bridge point — สลับไปมากับหน้า scatter ได้ผ่าน tab บนสุด (คนละ view จาก `PipelineRun` เดียวกัน ไม่ใช่คำนวณแยก)
5. หน้า search — ค้น semantic บน vector ใน Qdrant (ไม่ใช่พิกัด 2D)

## Non-goals ของ v1 นี้ (ยังไม่ทำ — ตัดสินใจแล้วว่ายังไม่จำเป็น)

- **Multi-level hierarchical taxonomy** (docs section 5, Option B multi-bandwidth sweep) — ยังไม่เคย prototype ใน `lab/` เลย ตาม roadmap ที่คุยกันไว้ (markdown → notebook → system) ควรไป prototype ใน notebook ก่อนค่อยพอร์ตเข้าระบบนี้ ตอนนี้เป็น **flat clustering ชั้นเดียว + bridge point** เท่านั้น ตรงกับสิ่งที่ validate แล้วใน `lab/`
- **Task queue จริง (Celery/RQ + Redis)** — v1 ใช้ `threading.Thread` ธรรมดารัน pipeline หลังบ้าน พอสำหรับ concurrent run จำนวนน้อย ถ้าโหลดสูงขึ้น (หลาย project รันพร้อมกันเยอะ) ควรย้ายไป task queue จริงที่คุมจำนวน worker/retry ได้
- **Auth/multi-user** — ไม่มีระบบ login แยกสิทธิ์ต่อ user ตอนนี้ (ทุกคนที่เข้าถึง URL ใช้ระบบร่วมกัน)
- **DB migration tool (Alembic)** — ใช้ `Base.metadata.create_all()` ตอน startup แทน ไม่มี migration history และ**ไม่แก้ schema ตารางที่มีอยู่แล้ว** (แค่สร้างตารางที่ยังไม่มี) ถ้าเคย `docker compose up` ไปแล้วครั้งหนึ่งบน DB ที่มีข้อมูลจริง แล้ว pull โค้ดใหม่ที่เพิ่ม column (เช่น `current_step`) ต้อง `ALTER TABLE` มือ หรือลบ volume `postgres_data` แล้วเริ่มใหม่ (ข้อมูลหาย) ถ้า schema เปลี่ยนบ่อยขึ้นควรสลับไป Alembic
- Use case อื่นใน `docs/hierarchical-taxonomy-concept.md` section 12 (gap analysis, conflict check, ฯลฯ) — ยังเป็น backlog ทั้งหมด
