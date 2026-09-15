# Taxonomy Pipeline — Webapp

Port ของ pipeline ใน `lab/` (chunk → embed → UMAP → `KDEWatershedClusterer` พร้อม bridge/boundary point → naming) ขึ้นเป็นระบบจริง ตามแนวคิดใน `docs/hierarchical-taxonomy-concept.md`

## Stack

- **backend/** — FastAPI (async) + SQLAlchemy — เลือกแทน Django เพราะเบากว่าและ throughput สูงกว่าใน workload ที่มี I/O รอ (DB, MinIO, Qdrant, LLM) เยอะ เก็บแค่ project/document/chunk (ingestion) ส่วนผลลัพธ์ pipeline run **ไม่เก็บใน Postgres ของ backend แล้ว** — trigger run ที่ `pipeline/` แล้วอ่านสถานะ/ผลลัพธ์กลับจาก MLflow ทั้งหมด
- **pipeline/** — service แยกต่างหาก เป็นตัว execute จริงของ embed → UMAP reduce → cluster (`KDEWatershedClusterer`) → naming ทั้งหมด (ย้ายออกจาก backend มาที่นี่) รับ trigger ผ่าน `POST /runs` จาก backend แบบ fire-and-forget (คืน mlflow run_id ทันที ไม่รอ pipeline จบ) แล้วรันเองใน background thread — log ทุก step ผ่าน mlflow tag `current_step` (ให้ backend poll เป็น progress) และ log ผลลัพธ์ (cluster/assignment/UMAP grid) เป็น artifact `.parquet` เข้า mlflow โดยตรง
- **Postgres** — เก็บ metadata: project, document, chunk เท่านั้น (chunk text ยังเป็นของ backend เก็บเอง — ผลลัพธ์ cluster ไม่อยู่ตรงนี้แล้ว)
- **MinIO** — เก็บไฟล์ PDF/txt ต้นฉบับ (S3-compatible) + เป็น artifact store ของ MLflow (parquet ผลลัพธ์ + ของเดิม)
- **Qdrant** — เก็บ embedding vector มิติสูง (bge-m3) ต่อ project ไว้ทำ semantic search — แยกจาก 2D UMAP coordinate โดยเจตนา (ดู `docs/` section 3: search ต้องใช้ vector มิติสูง ไม่ใช่ projection ที่ lossy) — upsert โดย `pipeline/` ตอนรัน, query โดย `backend/` ตอน search
- **frontend/** — Node.js + Express + EJS (server-rendered, ไม่มี build step) เรียก backend ผ่าน REST API
- **nginx** — reverse proxy หน้าเดียว (`/` → frontend, `/api/` → backend) เผื่อ scale-out backend หลาย replica ทีหลัง
- **mlflow/** — MLflow tracking server แยก service ต่างหาก (ไม่ embed ใน backend) — เป็น **source of truth ของผลการรัน pipeline ทั้งหมด** ไม่ใช่ auxiliary logging แบบเดิมอีกต่อไป: backend store = database `mlflow` บน Postgres instance เดียวกัน (คนละ database จาก app, สร้างผ่าน `postgres/init-mlflow-db.sql`), artifact store = MinIO bucket `${MLFLOW_BUCKET}` — experiment ต่อ project ชื่อ `project-{project_id}` ตั้ง `artifact_location` เป็น `s3://${MLFLOW_BUCKET}/projects/{project_id}/...` (key ด้วย project_id ตรง ๆ ทุก service คุยกันด้วย id นี้เหมือนกัน)

## รัน

```bash
cd webapp
docker compose up --build
```

เปิด `http://localhost` (nginx) — หรือ backend ตรง ๆ ที่ `:8000`, frontend ตรง ๆ ที่ `:3000`, MinIO console ที่ `:9001`, MLflow UI ที่ `:5001` — `pipeline/` ไม่ expose port ออกนอก docker network (backend เรียกผ่านชื่อ service `pipeline:8001` เท่านั้น)

**หมายเหตุ deploy ทับของเดิม**: `postgres/init-mlflow-db.sql` รันแค่ตอน postgres container สร้าง data dir ครั้งแรก ถ้าเคย `docker compose up` มาก่อนหน้านี้ (มี `postgres_data` volume อยู่แล้ว) ต้องสร้าง database `mlflow` เองด้วยมือ: `docker compose exec postgres psql -U ${POSTGRES_USER} -c "CREATE DATABASE mlflow;"`

ค่า default ใน `.env` ตั้งไว้ให้รันได้ทันทีโดยไม่ต้องมี API key ใด ๆ: `LLM_BACKEND=openai` แต่ `OPENAI_API_KEY` ว่าง → LLM health check ล้มเหลว → **fallback เป็น TF-IDF keyword ตั้งชื่อ cluster อัตโนมัติ** (ไม่ error) ถ้าต้องการชื่อ cluster จาก LLM จริง ใส่ `OPENAI_API_KEY` หรือสลับ `LLM_BACKEND=ollama` (ต้องมี ollama server ให้ backend เข้าถึงได้ตาม `OLLAMA_HOST`)

## GPU (embedding model)

`sentence-transformers` auto-detect CUDA ถ้ามี GPU ใน container/host — ถ้าเจอ error รูปแบบ `CUDA error: no kernel image is available for execution on the device` (GPU รุ่นเก่าเทียบ torch build ไม่ตรง) โค้ดจะ fallback เป็น CPU อัตโนมัติ (ดู `backend/app/services/embedding.py`) หรือ set `EMBED_DEVICE=cpu` ใน `.env` บังคับตรง ๆ

การรัน GPU ใน container ต้องใช้ NVIDIA Container Toolkit เพิ่ม `deploy.resources.reservations.devices` ใน `docker-compose.yml` service `backend` เอง (ไม่ได้ตั้งไว้ default เพราะขึ้นกับ driver/CUDA version ของเครื่องแต่ละเครื่อง — ดูปัญหาที่เคยเจอกับ TITAN Xp/Pascal ก่อนหน้านี้)

## Flow

1. สร้าง Project → นำเข้าข้อมูลด้วยวิธีใดวิธีหนึ่ง:
   - อัปโหลดเอกสาร (PDF/txt) → เก็บไฟล์ลง MinIO, สกัดข้อความทีละหน้า, chunk ด้วย `llama-index` `SentenceSplitter` (เก็บ `page_number` ต่อ chunk)
   - หรือส่ง `list[str]` ตรง ๆ ผ่าน `POST /api/projects/{id}/texts` (body `{"texts": [...], "source_name": "..."}`) — เช่นจาก script ที่โหลด CSV ด้วย pandas แล้ว `texts = df["content"].dropna().astype(str).tolist()` เข้า path chunking เดียวกัน (`page_number` = index ใน list ที่ส่งมา) มีฟอร์ม paste texts ในหน้า project ให้ทดสอบผ่านเว็บได้เลยโดยไม่ต้องเขียน script
2. กด "เริ่มรัน" → backend เรียก `POST /runs` ไปที่ `pipeline/` (fire-and-forget, ได้ mlflow run_id กลับมาทันที) → `pipeline/` สร้าง mlflow run แล้วรันจริงเองใน background thread ไล่ทีละ step (`current_step` tag บน mlflow run: `LOADING_CHUNKS` → `EMBEDDING` → `UPSERT_VECTORS` → `UMAP_SEARCH` → `CLUSTERING` → `NAMING` → `LOGGING_ARTIFACTS` → `DONE`/`FAILED`) — backend ไม่รันอะไรเองแล้ว มีหน้าที่ query สถานะ/ผลลัพธ์นี้กลับจาก mlflow (tag/param/metric/artifact) มาให้หน้า run โชว์ ซึ่ง poll ทุก 4 วิเหมือนเดิมจนกว่าจะเสร็จ
3. หน้า **Interactive Visualization (2D scatter)** — Plotly, filter cluster, detail panel (doc id/cluster name/text), search highlight
4. หน้า **Taxonomy (สารบัญ)** — แผนภาพต้นไม้ (Plotly Treemap, ตอนนี้ 1 ชั้น root→cluster) + citation list ต่อ cluster + cross-reference ของ bridge point — สลับไปมากับหน้า scatter ได้ผ่าน tab บนสุด (คนละ view จาก `PipelineRun` เดียวกัน ไม่ใช่คำนวณแยก)
5. หน้า search — ค้น semantic บน vector ใน Qdrant (ไม่ใช่พิกัด 2D)

## Non-goals ของ v1 นี้ (ยังไม่ทำ — ตัดสินใจแล้วว่ายังไม่จำเป็น)

- **Multi-level hierarchical taxonomy** (docs section 5, Option B multi-bandwidth sweep) — ยังไม่เคย prototype ใน `lab/` เลย ตาม roadmap ที่คุยกันไว้ (markdown → notebook → system) ควรไป prototype ใน notebook ก่อนค่อยพอร์ตเข้าระบบนี้ ตอนนี้เป็น **flat clustering ชั้นเดียว + bridge point** เท่านั้น ตรงกับสิ่งที่ validate แล้วใน `lab/`
- **Task queue จริง (Celery/RQ + Redis)** — v1 ใช้ `threading.Thread` ธรรมดารัน pipeline หลังบ้าน พอสำหรับ concurrent run จำนวนน้อย ถ้าโหลดสูงขึ้น (หลาย project รันพร้อมกันเยอะ) ควรย้ายไป task queue จริงที่คุมจำนวน worker/retry ได้
- **Auth/multi-user** — ไม่มีระบบ login แยกสิทธิ์ต่อ user ตอนนี้ (ทุกคนที่เข้าถึง URL ใช้ระบบร่วมกัน)
- **DB migration tool (Alembic)** — ใช้ `Base.metadata.create_all()` ตอน startup แทน ไม่มี migration history และ**ไม่แก้ schema ตารางที่มีอยู่แล้ว** (แค่สร้างตารางที่ยังไม่มี) ถ้าเคย `docker compose up` ไปแล้วครั้งหนึ่งบน DB ที่มีข้อมูลจริง แล้ว pull โค้ดใหม่ที่เพิ่ม column (เช่น `current_step`) ต้อง `ALTER TABLE` มือ หรือลบ volume `postgres_data` แล้วเริ่มใหม่ (ข้อมูลหาย) ถ้า schema เปลี่ยนบ่อยขึ้นควรสลับไป Alembic
- Use case อื่นใน `docs/hierarchical-taxonomy-concept.md` section 12 (gap analysis, conflict check, ฯลฯ) — ยังเป็น backlog ทั้งหมด

**หมายเหตุ migration จากของเดิม (backend เคยรัน pipeline เอง + เก็บผลใน Postgres)**: ถ้าเคย `docker compose up` มาก่อนตอน backend ยังเก็บผลลัพธ์ลง Postgres เอง จะมีตาราง `pipeline_runs`/`cluster_results`/`chunk_cluster_assignments`/`umap_grid_results` เหลืออยู่แบบไม่ใช้แล้ว (`Base.metadata.create_all()` ไม่ลบตารางเก่าให้) — ลบด้วยมือได้ถ้าต้องการเคลียร์ ไม่จำเป็นต้องลบก็รันต่อได้ปกติ (ไม่มีโค้ดฝั่งไหนอ้างอิงตารางพวกนี้อีกแล้ว)
