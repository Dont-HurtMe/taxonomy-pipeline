(function () {
  const results = window.__RESULTS__;
  if (!results) return;

  const nameByCluster = {};
  results.clusters.forEach(function (c) {
    nameByCluster[c.cluster_id] = c.name;
  });

  const byCluster = {};
  results.assignments.forEach(function (a) {
    const key = a.cluster_id;
    if (!byCluster[key]) byCluster[key] = [];
    byCluster[key].push(a);
  });

  const palette = [
    "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#ea580c", "#4f46e5",
  ];

  function clusterLabel(cid) {
    if (cid === -2) return "bridge point";
    if (cid === -1) return "noise";
    return cid + ": " + (nameByCluster[cid] || cid);
  }

  const clusterIds = Object.keys(byCluster).map(Number).sort(function (a, b) { return a - b; });

  const traces = [];
  const traceMeta = []; // {clusterId, label, color, baseSize, isNoise, points}

  clusterIds.forEach(function (cid, idx) {
    const points = byCluster[cid];
    const isBridge = cid === -2;
    const isNoise = cid === -1;
    const baseColor = isBridge ? "#111827" : isNoise ? "#d1d5db" : palette[idx % palette.length];
    const baseSize = isBridge ? 9 : isNoise ? 6 : 7;
    const baseOpacity = isNoise ? 0.5 : 0.85;
    const label = clusterLabel(cid);

    traces.push({
      x: points.map(function (p) { return p.x; }),
      y: points.map(function (p) { return p.y; }),
      text: points.map(function (p) { return p.text.slice(0, 120); }),
      customdata: points,
      mode: "markers",
      type: "scattergl",
      name: label,
      hoverinfo: "text",
      marker: {
        symbol: isBridge ? "diamond-open" : "circle",
        size: points.map(function () { return baseSize; }),
        color: points.map(function () { return baseColor; }),
        opacity: points.map(function () { return baseOpacity; }),
        line: isBridge ? { width: 1.5, color: baseColor } : { width: 0 },
      },
    });

    traceMeta.push({ clusterId: cid, label: label, color: baseColor, baseSize: baseSize, baseOpacity: baseOpacity, points: points });
  });

  Plotly.newPlot(
    "scatter",
    traces,
    { margin: { t: 10 }, hovermode: "closest", showlegend: false }
  );

  const gd = document.getElementById("scatter");

  gd.on("plotly_click", function (data) {
    if (!data.points.length) return;
    renderDetail(data.points[0].customdata);
  });

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function renderDetail(point) {
    const bridgeLine = point.bridge_between
      ? '<div class="detail-field"><span class="label"># bridge_between</span><div class="value">' +
        point.bridge_between.join(", ") + "</div></div>"
      : "";
    document.getElementById("pointDetail").innerHTML =
      '<div class="detail-field"><span class="label"># doc id</span><div class="value">' +
      point.document_id + (point.page_number != null ? " (หน้า " + point.page_number + ")" : "") + "</div></div>" +
      '<div class="detail-field"><span class="label"># cluster name</span><div class="value">' +
      clusterLabel(point.cluster_id) + "</div></div>" +
      '<div class="detail-field"><span class="label"># text</span><div class="value">' +
      escapeHtml(point.text) + "</div></div>" +
      bridgeLine +
      '<div class="muted">คลิกไปยังเอกสารต้นฉบับ (หน้า/chunk) — ยังไม่เปิดใช้งาน (แผนถัดไป)</div>';
  }

  // --- filter panel: เปิด/ปิดทีละ cluster ---
  const filterList = document.getElementById("filterList");
  traceMeta.forEach(function (meta, idx) {
    const label = document.createElement("label");
    label.innerHTML =
      '<input type="checkbox" checked data-idx="' + idx + '" />' +
      '<span class="filter-swatch" style="background:' + meta.color + '"></span>' +
      "<span>" + escapeHtml(meta.label) + " (" + meta.points.length + ")</span>";
    filterList.appendChild(label);
  });

  filterList.addEventListener("change", function (e) {
    if (!e.target.matches('input[type="checkbox"]')) return;
    const idx = Number(e.target.dataset.idx);
    Plotly.restyle("scatter", { visible: e.target.checked }, [idx]);
  });

  function setAllFilters(checked) {
    filterList.querySelectorAll('input[type="checkbox"]').forEach(function (b) { b.checked = checked; });
    Plotly.restyle("scatter", { visible: checked }, traceMeta.map(function (_, i) { return i; }));
  }
  document.getElementById("filterAll").addEventListener("click", function (e) { e.preventDefault(); setAllFilters(true); });
  document.getElementById("filterNone").addEventListener("click", function (e) { e.preventDefault(); setAllFilters(false); });

  // --- search: highlight จุดที่ text ตรงกับคำค้น (ไม่ filter ออก แค่เน้น/หรี่) ---
  const searchInput = document.getElementById("mapSearch");
  let searchTimer = null;
  searchInput.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applySearch, 150);
  });

  function applySearch() {
    const q = searchInput.value.trim().toLowerCase();
    traceMeta.forEach(function (meta, idx) {
      let sizes, opacities;
      if (!q) {
        sizes = meta.points.map(function () { return meta.baseSize; });
        opacities = meta.points.map(function () { return meta.baseOpacity; });
      } else {
        sizes = meta.points.map(function (p) {
          return p.text.toLowerCase().indexOf(q) !== -1 ? meta.baseSize + 6 : meta.baseSize;
        });
        opacities = meta.points.map(function (p) {
          return p.text.toLowerCase().indexOf(q) !== -1 ? 1 : 0.08;
        });
      }
      Plotly.restyle("scatter", { "marker.size": [sizes], "marker.opacity": [opacities] }, [idx]);
    });
  }
})();
