require("dotenv").config();
const express = require("express");
const path = require("path");

const projectsRouter = require("./routes/projects");
const documentsRouter = require("./routes/documents");
const runsRouter = require("./routes/runs");
const searchRouter = require("./routes/search");

const app = express();

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));
app.use(express.static(path.join(__dirname, "public")));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

app.use("/", projectsRouter);
app.use("/", documentsRouter);
app.use("/", runsRouter);
app.use("/", searchRouter);

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).render("error", { message: err.message });
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`frontend listening on :${port}`);
});
