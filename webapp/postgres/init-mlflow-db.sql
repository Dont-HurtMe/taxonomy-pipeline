-- รันครั้งเดียวตอน postgres container สร้างครั้งแรก (data dir ว่าง) — DB แยกจาก app database
-- เก็บ MLflow backend store (experiments/runs/metrics/params) ไว้คนละ database ไม่ปนตารางกับ app
CREATE DATABASE mlflow;
