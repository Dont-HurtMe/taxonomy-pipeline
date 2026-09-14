const express = require("express");
const api = require("../api");

const router = express.Router();

router.post("/projects/:projectId/runs", async (req, res, next) => {
  try {
    const { projectId } = req.params;
    await api.post(`/api/projects/${projectId}/runs`, { llm_backend: req.body.llm_backend || null });
    res.redirect(`/projects/${projectId}`);
  } catch (err) {
    next(err);
  }
});

router.get("/projects/:projectId/runs/:runId", async (req, res, next) => {
  try {
    const { projectId, runId } = req.params;
    const { data: run } = await api.get(`/api/projects/${projectId}/runs/${runId}`);

    if (run.status !== "DONE") {
      return res.render("run", { project_id: projectId, run, results: null });
    }

    const { data: results } = await api.get(`/api/projects/${projectId}/runs/${runId}/results`);
    res.render("run", { project_id: projectId, run, results });
  } catch (err) {
    next(err);
  }
});

router.get("/projects/:projectId/runs/:runId/taxonomy", async (req, res, next) => {
  try {
    const { projectId, runId } = req.params;
    const { data: run } = await api.get(`/api/projects/${projectId}/runs/${runId}`);

    if (run.status !== "DONE") {
      return res.render("taxonomy", { project_id: projectId, run, results: null });
    }

    const { data: results } = await api.get(`/api/projects/${projectId}/runs/${runId}/results`);
    res.render("taxonomy", { project_id: projectId, run, results });
  } catch (err) {
    next(err);
  }
});

// polling endpoint สำหรับ auto-refresh หน้า run.ejs ระหว่างสถานะ PENDING/RUNNING
router.get("/api-proxy/projects/:projectId/runs/:runId/status", async (req, res, next) => {
  try {
    const { projectId, runId } = req.params;
    const { data } = await api.get(`/api/projects/${projectId}/runs/${runId}`);
    res.json(data);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
