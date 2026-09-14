const express = require("express");
const multer = require("multer");
const FormData = require("form-data");
const api = require("../api");

const router = express.Router();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 100 * 1024 * 1024 } });

router.post("/projects/:projectId/documents", upload.single("file"), async (req, res, next) => {
  try {
    const { projectId } = req.params;
    if (!req.file) {
      return res.redirect(`/projects/${projectId}`);
    }
    const form = new FormData();
    form.append("file", req.file.buffer, {
      filename: req.file.originalname,
      contentType: req.file.mimetype,
    });
    await api.post(`/api/projects/${projectId}/documents`, form, {
      headers: form.getHeaders(),
      maxBodyLength: Infinity,
      maxContentLength: Infinity,
    });
    res.redirect(`/projects/${projectId}`);
  } catch (err) {
    next(err);
  }
});

// usecase 1: paste texts ตรง ๆ (ทดสอบผ่านหน้าเว็บโดยไม่ต้องเขียน script เรียก /api/projects/:id/texts เอง)
router.post("/projects/:projectId/texts", async (req, res, next) => {
  try {
    const { projectId } = req.params;
    const texts = (req.body.texts || "")
      .split("\n")
      .map((t) => t.trim())
      .filter(Boolean);
    if (texts.length === 0) {
      return res.redirect(`/projects/${projectId}`);
    }
    await api.post(`/api/projects/${projectId}/texts`, { texts, source_name: req.body.source_name || "" });
    res.redirect(`/projects/${projectId}`);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
