const express = require("express");
const api = require("../api");

const router = express.Router();

router.get("/projects/:projectId/search", async (req, res, next) => {
  try {
    const { projectId } = req.params;
    const q = req.query.q || "";
    let results = null;
    if (q) {
      const { data } = await api.get(`/api/projects/${projectId}/search`, { params: { q, top_k: 10 } });
      results = data;
    }
    const { data: project } = await api.get(`/api/projects/${projectId}`);
    res.render("search", { project, query: q, results });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
