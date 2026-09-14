const axios = require("axios");

const api = axios.create({
  baseURL: process.env.BACKEND_URL || "http://backend:8000",
  timeout: 15000,
});

module.exports = api;
