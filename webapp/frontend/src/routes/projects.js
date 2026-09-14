const express = require("express");
const api = require("../api");

const router = express.Router();

router.get("/", async (req, res, next) => {
  try {
    const { data: projects } = await api.get("/api/projects");
    res.render("index", { projects });
  } catch (err) {
    next(err);
  }
});

router.post("/projects", async (req, res, next) => {
  try {
    await api.post("/api/projects", { name: req.body.name, description: req.body.description || "" });
    res.redirect("/");
  } catch (err) {
    next(err);
  }
});

router.get("/projects/:projectId", async (req, res, next) => {
  try {
    const { projectId } = req.params;
    const [{ data: project }, { data: documents }, { data: runs }] = await Promise.all([
      api.get(`/api/projects/${projectId}`),
      api.get(`/api/projects/${projectId}/documents`),
      api.get(`/api/projects/${projectId}/runs`),
    ]);
    res.render("project", { project, documents, runs });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
