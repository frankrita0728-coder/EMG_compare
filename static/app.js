const delsysListEl = document.getElementById("delsys-list");
const txtListEl = document.getElementById("txt-list");
const suggestListEl = document.getElementById("suggest-list");
const statusEl = document.getElementById("status");
const pathsEl = document.getElementById("paths");

const TXT_COLORS = [
  "#3dd68c", "#a0e85c", "#5ef0c8", "#80d4ff", "#c8f070",
  "#48e0a0", "#90f0b0", "#68d8e0", "#b0f080", "#58e8d0",
];

const state = {
  delsysFiles: [],
  txtFiles: [],
  selectedDelsys: null,
  selectedTxt: new Set(),
  suggestions: [],
  results: {
    waveform: { delsys: false, txt: false, overlay: false },
    contractions: { delsys: false, txt: false },
    features: { delsys: false, txt: false, delta: false },
  },
};

const PLOT_LAYOUT = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#e7efe9" },
  margin: { t: 40, r: 20, b: 50, l: 55 },
  legend: { orientation: "h", y: 1.12 },
  xaxis: { title: "Time (s)", gridcolor: "#24322b", zerolinecolor: "#314239" },
  yaxis: { title: "Normalized", gridcolor: "#24322b", zerolinecolor: "#314239" },
};

const SOURCE_COLOR = {
  delsys: "#5ec8ff",
  txt: "#3dd68c",
};

function currentNormMethod() {
  return document.getElementById("norm-method").value || "zscore";
}

function plotLayout(extra = {}) {
  const method = currentNormMethod();
  const yTitle =
    method === "none" ? "Original" :
    method === "maxabs" ? "Norm (maxabs)" :
    "Norm (zscore)";
  return {
    ...PLOT_LAYOUT,
    yaxis: { ...PLOT_LAYOUT.yaxis, title: yTitle },
    ...extra,
  };
}

function setStatus(message) {
  statusEl.textContent = message;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function updateBadges() {
  const waveDone =
    state.results.waveform.delsys ||
    state.results.waveform.txt ||
    state.results.waveform.overlay;
  const contrDone = state.results.contractions.delsys || state.results.contractions.txt;
  const featDone =
    state.results.features.delsys ||
    state.results.features.txt ||
    state.results.features.delta;

  document.getElementById("badge-waveform").hidden = !waveDone;
  document.getElementById("badge-contractions").hidden = !contrDone;
  document.getElementById("badge-features").hidden = !featDone;
}

async function api(url, options) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "請求失敗");
  }
  return data;
}

function renderDelsysList() {
  const files = state.delsysFiles;
  if (!files.length) {
    delsysListEl.innerHTML = `<div class="empty">尚無檔案</div>`;
    return;
  }
  delsysListEl.innerHTML = files
    .map((file) => {
      const active = file.name === state.selectedDelsys ? "active" : "";
      return `
        <button class="file-item ${active}" type="button" data-source="delsys" data-name="${escapeHtml(file.name)}">
          <span class="file-name">${escapeHtml(file.name)}</span>
        </button>
      `;
    })
    .join("");
}

function renderTxtList() {
  const files = state.txtFiles;
  if (!files.length) {
    txtListEl.innerHTML = `<div class="empty">尚無檔案</div>`;
    return;
  }
  txtListEl.innerHTML = files
    .map((file) => {
      const active = state.selectedTxt.has(file.name) ? "active" : "";
      return `
        <button class="file-item ${active}" type="button" data-source="txt" data-name="${escapeHtml(file.name)}">
          <span class="file-name">${escapeHtml(file.name)}</span>
        </button>
      `;
    })
    .join("");
}

function txtSelectionLabel() {
  const count = state.selectedTxt.size;
  if (count === 0) return "未選";
  if (count === 1) return [...state.selectedTxt][0];
  return `${count} 個 TXT`;
}

function renderSuggestions(items) {
  if (!items.length) {
    suggestListEl.innerHTML = `<div class="empty">尚無建議，請先選檔或放入更多資料</div>`;
    return;
  }

  suggestListEl.innerHTML = items
    .map((item) => {
      if (item.delsys && item.txt) {
        return `
          <button class="suggest-item" type="button"
            data-delsys="${escapeHtml(item.delsys)}"
            data-txt="${escapeHtml(item.txt)}">
            <span class="file-name">${escapeHtml(item.delsys)}</span>
            <span class="file-name">↔ ${escapeHtml(item.txt)}</span>
            <span class="suggest-meta">分數 ${item.score} · ${escapeHtml(item.reason || "")}</span>
          </button>
        `;
      }

      const isForDelsys = item.selected_source === "delsys";
      const delsys = isForDelsys ? item.selected_name : item.name;
      const txt = isForDelsys ? item.name : item.selected_name;
      return `
        <button class="suggest-item" type="button"
          data-delsys="${escapeHtml(delsys)}"
          data-txt="${escapeHtml(txt)}">
          <span class="file-name">${escapeHtml(item.name)}</span>
          <span class="suggest-meta">分數 ${item.score} · ${escapeHtml(item.reason || "")}</span>
        </button>
      `;
    })
    .join("");
}

async function refreshSuggestions() {
  const params = new URLSearchParams();
  if (state.selectedDelsys && state.selectedTxt.size === 0) {
    params.set("source", "delsys");
    params.set("filename", state.selectedDelsys);
  } else if (state.selectedTxt.size > 0 && !state.selectedDelsys) {
    params.set("source", "txt");
    params.set("filename", [...state.selectedTxt][0]);
  }

  const query = params.toString() ? `?${params.toString()}` : "";
  const data = await api(`/api/suggest${query}`);
  state.suggestions = data.suggestions || [];
  renderSuggestions(state.suggestions);
}

async function loadFiles() {
  setStatus("載入檔案清單...");
  const data = await api("/api/files");
  state.delsysFiles = data.delsys || [];
  state.txtFiles = data.txt || [];
  renderDelsysList();
  renderTxtList();
  pathsEl.textContent = `Delsys: ${data.paths.delsys} ｜ TXT: ${data.paths.txt}`;
  await refreshSuggestions();
  setStatus(`Delsys ${state.delsysFiles.length} 個 · TXT ${state.txtFiles.length} 個`);
}

async function selectPair(delsysName, txtName) {
  state.selectedDelsys = delsysName;
  state.selectedTxt.clear();
  state.selectedTxt.add(txtName);
  renderDelsysList();
  renderTxtList();
  setStatus(`已配對：${delsysName} ↔ ${txtName}`);
  await refreshSuggestions();
}

function requireDelsys() {
  if (!state.selectedDelsys) throw new Error("請先選擇 Delsys 檔案");
  return state.selectedDelsys;
}

function requireTxt() {
  if (state.selectedTxt.size === 0) throw new Error("請先選擇至少一個 TXT 檔案");
  return [...state.selectedTxt];
}

function requirePair() {
  requireDelsys();
  requireTxt();
}

function shapesFromContractions(contractions, color) {
  return (contractions || []).map((c) => ({
    type: "rect",
    xref: "x",
    yref: "paper",
    x0: c.start,
    x1: c.end,
    y0: 0,
    y1: 1,
    fillcolor: color,
    line: { width: 0 },
    layer: "below",
  }));
}

function renderContractionTable(container, contractions, label) {
  if (!contractions || !contractions.length) {
    container.innerHTML += `<div class="empty">${escapeHtml(label || "")}: 未偵測到收縮區間</div>`;
    return;
  }
  container.innerHTML += `
    ${label ? `<div class="table-label">${escapeHtml(label)}</div>` : ""}
    <table>
      <thead>
        <tr><th>#</th><th>開始(s)</th><th>結束(s)</th><th>時長(s)</th><th>Peak RMS</th></tr>
      </thead>
      <tbody>
        ${contractions
          .map(
            (c) => `
          <tr>
            <td>${c.index}</td>
            <td>${c.start}</td>
            <td>${c.end}</td>
            <td>${c.duration}</td>
            <td>${c.peak_rms}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function featureColumns(method) {
  if (method === "ttri") {
    return [
      { key: "duration", label: "時長" },
      { key: "aemg", label: "AEMG" },
      { key: "iemg", label: "iEMG" },
      { key: "rms", label: "RMS" },
      { key: "mdf", label: "MDF" },
      { key: "mpf", label: "MPF" },
      { key: "peak_rms", label: "Peak RMS" },
    ];
  }
  return [
    { key: "duration", label: "時長" },
    { key: "iemg", label: "iEMG" },
    { key: "rms", label: "RMS" },
    { key: "mdf", label: "MDF" },
    { key: "mpf", label: "MPF" },
    { key: "peak_rms", label: "Peak RMS" },
  ];
}

function currentContractionMethod(which) {
  const id = which === "f" ? "contraction-method-f" : "contraction-method-c";
  return document.getElementById(id).value || "rms_peak";
}

function currentFeatureMethod() {
  return document.getElementById("feature-method-f").value || "spectral";
}

function renderSingleFeatureTable(container, rows, label, method) {
  if (!rows || !rows.length) {
    container.innerHTML += `<div class="empty">${escapeHtml(label || "")}: 無可計算特徵</div>`;
    return;
  }
  const cols = featureColumns(method || rows[0].method || "spectral");
  container.innerHTML += `
    ${label ? `<div class="table-label">${escapeHtml(label)}</div>` : ""}
    <table>
      <thead>
        <tr>
          <th>#</th>${cols.map((c) => `<th>${c.label}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (r) => `
          <tr>
            <td>${r.index}</td>
            ${cols.map((c) => `<td>${r[c.key] ?? "-"}</td>`).join("")}
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function deltaClass(value) {
  if (value == null) return "";
  if (value > 0) return "delta-pos";
  if (value < 0) return "delta-neg";
  return "";
}

function renderDeltaTable(data) {
  const noteEl = document.getElementById("features-note");
  const tableEl = document.getElementById("features-table");
  noteEl.classList.remove("empty-slot");
  noteEl.textContent = data.note || "";

  if (!data.pairs || !data.pairs.length) {
    tableEl.innerHTML = `<div class="empty">沒有可比較的特徵</div>`;
    return;
  }

  const cols = featureColumns(data.feature_method || "spectral");
  tableEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>來源</th>
          ${cols.map((c) => `<th>${c.label}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${data.pairs
          .map((pair) => {
            const d = pair.delsys;
            const t = pair.txt;
            const delta = pair.delta || {};
            return `
              <tr>
                <td rowspan="3">${pair.index}</td>
                <td>Delsys</td>
                ${cols.map((c) => `<td>${d ? d[c.key] : "-"}</td>`).join("")}
              </tr>
              <tr>
                <td>TXT</td>
                ${cols.map((c) => `<td>${t ? t[c.key] : "-"}</td>`).join("")}
              </tr>
              <tr>
                <td>Δ (D-T)</td>
                ${cols
                  .map(
                    (c) =>
                      `<td class="${deltaClass(delta[c.key])}">${delta[c.key] ?? "-"}</td>`
                  )
                  .join("")}
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

/* ── Waveform ── */

async function runWaveformSingle(source) {
  if (source === "delsys") {
    const filename = requireDelsys();
    setStatus("執行 Delsys 波形...");
    const method = document.getElementById("norm-method").value;
    const data = await api("/api/analyze/waveform", {
      method: "POST",
      body: JSON.stringify({ source: "delsys", filename, norm_method: method }),
    });

    await Plotly.newPlot(
      "chart-wave-delsys",
      [{
        x: data.trace.times,
        y: data.trace.values,
        type: "scattergl",
        mode: "lines",
        name: "Delsys",
        line: { color: SOURCE_COLOR.delsys, width: 1.2 },
      }],
      { ...plotLayout(), title: data.trace.filename, height: 280, margin: { t: 48, r: 16, b: 40, l: 48 } },
      { responsive: true }
    );
    const meta = document.getElementById("meta-wave-delsys");
    meta.classList.remove("empty-slot");
    meta.textContent = [
      data.trace.filename,
      `${data.trace.sample_rate} Hz`,
      `${data.trace.point_count} pts`,
      data.norm_method,
      data.trace.start_label ? `start ${data.trace.start_label}` : null,
    ].filter(Boolean).join(" · ");
    state.results.waveform.delsys = true;
    updateBadges();
    setStatus("Delsys 波形完成");
  } else {
    const txtFiles = requireTxt();
    setStatus(`執行 TXT 波形（${txtFiles.length} 個）...`);
    const method = document.getElementById("norm-method").value;

    const traces = [];
    const metas = [];
    for (let i = 0; i < txtFiles.length; i++) {
      const data = await api("/api/analyze/waveform", {
        method: "POST",
        body: JSON.stringify({ source: "txt", filename: txtFiles[i], norm_method: method }),
      });
      traces.push({
        x: data.trace.times,
        y: data.trace.values,
        type: "scattergl",
        mode: "lines",
        name: `TXT · ${data.trace.filename}`,
        line: { color: TXT_COLORS[i % TXT_COLORS.length], width: 1.2 },
      });
      metas.push(
        [
          data.trace.filename,
          `${data.trace.sample_rate} Hz`,
          `${data.trace.point_count} pts`,
          data.trace.start_label ? `start ${data.trace.start_label}` : null,
        ].filter(Boolean).join(", ")
      );
    }

    await Plotly.newPlot(
      "chart-wave-txt",
      traces,
      { ...plotLayout(), title: `TXT 波形（${txtFiles.length} 個）`, height: 280, margin: { t: 48, r: 16, b: 40, l: 48 } },
      { responsive: true }
    );
    const meta = document.getElementById("meta-wave-txt");
    meta.classList.remove("empty-slot");
    meta.textContent = metas.join("｜");
    state.results.waveform.txt = true;
    updateBadges();
    setStatus(`TXT 波形完成（${txtFiles.length} 個）`);
  }
}

async function runWaveformBoth() {
  requirePair();
  setStatus("兩邊波形疊圖中...");
  const method = document.getElementById("norm-method").value;
  const alignByStart = document.getElementById("align-by-start").checked;
  const txtFiles = [...state.selectedTxt];

  const data = await api("/api/compare/waveform", {
    method: "POST",
    body: JSON.stringify({
      delsys: state.selectedDelsys,
      txt_list: txtFiles,
      norm_method: method,
      align_by_start: alignByStart,
    }),
  });

  // Support both single-compare and multi-overlay response shapes.
  const delsys = data.delsys;
  const txtList = data.txt_list || (data.txt ? [data.txt] : []);
  const overlay = data.overlay || [delsys, ...txtList];

  await Plotly.newPlot(
    "chart-wave-delsys",
    [{
      x: delsys.times,
      y: delsys.values,
      type: "scattergl",
      mode: "lines",
      name: "Delsys",
      line: { color: SOURCE_COLOR.delsys, width: 1.3 },
    }],
    { ...plotLayout(), title: delsys.filename, height: 280, margin: { t: 48, r: 16, b: 40, l: 48 } },
    { responsive: true }
  );
  const metaD = document.getElementById("meta-wave-delsys");
  metaD.classList.remove("empty-slot");
  metaD.textContent = [
    delsys.filename,
    `${delsys.sample_rate} Hz`,
    `${delsys.point_count} pts`,
    delsys.start_label ? `start ${delsys.start_label}` : null,
  ].filter(Boolean).join(" · ");

  const txtTraces = txtList.map((item, i) => ({
    x: item.times,
    y: item.values,
    type: "scattergl",
    mode: "lines",
    name: `TXT · ${item.filename}`,
    line: { color: TXT_COLORS[i % TXT_COLORS.length], width: 1.3 },
  }));
  await Plotly.newPlot(
    "chart-wave-txt",
    txtTraces,
    { ...plotLayout(), title: `TXT（${txtList.length} 個）`, height: 280, margin: { t: 48, r: 16, b: 40, l: 48 } },
    { responsive: true }
  );
  const metaT = document.getElementById("meta-wave-txt");
  metaT.classList.remove("empty-slot");
  metaT.textContent = txtList
    .map((item) => {
      const start = item.start_label ? `, start ${item.start_label}` : "";
      return `${item.filename} (${item.sample_rate} Hz${start})`;
    })
    .join("｜");

  const overlayTraces = overlay.map((item, i) => {
    const isDelsys = item.source === "delsys";
    const color = isDelsys
      ? SOURCE_COLOR.delsys
      : TXT_COLORS[Math.max(0, i - 1) % TXT_COLORS.length];
    const offset =
      item.time_offset != null ? ` [${item.time_offset >= 0 ? "+" : ""}${item.time_offset}s]` : "";
    return {
      x: item.times,
      y: item.values,
      type: "scattergl",
      mode: "lines",
      name: `${isDelsys ? "Delsys" : "TXT"} · ${item.filename}${offset}`,
      line: { color, width: 1.3 },
    };
  });

  const alignTitle = data.align && data.align.aligned ? "· 已起始對齊" : "";
  await Plotly.newPlot(
    "chart-waveform",
    overlayTraces,
    {
      ...plotLayout(),
      title: `波形疊圖（${method}）${alignTitle} · Delsys + ${txtList.length} TXT`,
    },
    { responsive: true, displayModeBar: true }
  );

  const note = document.getElementById("waveform-note");
  note.classList.remove("empty-slot");
  note.textContent = data.note || "";

  state.results.waveform.delsys = true;
  state.results.waveform.txt = true;
  state.results.waveform.overlay = true;
  updateBadges();
  setStatus(
    data.align && data.align.aligned
      ? `波形疊圖完成（已依起始時間對齊）`
      : `波形疊圖完成（1 Delsys + ${txtList.length} TXT）`
  );
}

/* ── Contractions ── */

async function renderContractionSide(source, result, color) {
  const chartId = source === "delsys" ? "chart-delsys-c" : "chart-txt-c";

  await Plotly.newPlot(
    chartId,
    [{
      x: result.times,
      y: result.values,
      type: "scattergl",
      mode: "lines",
      name: result.filename || source,
      line: { color: color || SOURCE_COLOR[source], width: 1.2 },
    }],
    {
      ...PLOT_LAYOUT,
      title: result.filename,
      shapes: shapesFromContractions(result.contractions, color ? color.replace(")", ",0.18)").replace("rgb", "rgba") : "rgba(61,214,140,0.18)"),
      height: 280,
      margin: { t: 48, r: 16, b: 40, l: 48 },
    },
    { responsive: true }
  );
}

async function runContractionsSingle(source) {
  const contractionMethod = currentContractionMethod("c");
  if (source === "delsys") {
    const filename = requireDelsys();
    setStatus(`偵測 Delsys 收縮區間（${contractionMethod}）...`);
    const expected = Number(document.getElementById("expected-count-c").value || 3);
    const data = await api("/api/analyze/contractions", {
      method: "POST",
      body: JSON.stringify({
        source: "delsys",
        filename,
        expected_count: expected,
        contraction_method: contractionMethod,
      }),
    });

    await Plotly.newPlot(
      "chart-delsys-c",
      [{
        x: data.result.times,
        y: data.result.values,
        type: "scattergl",
        mode: "lines",
        name: "Delsys",
        line: { color: SOURCE_COLOR.delsys, width: 1.2 },
      }],
      {
        ...PLOT_LAYOUT,
        title: `${data.result.filename} · ${contractionMethod}`,
        shapes: shapesFromContractions(data.result.contractions, "rgba(94,200,255,0.18)"),
        height: 280,
        margin: { t: 48, r: 16, b: 40, l: 48 },
      },
      { responsive: true }
    );
    const tableEl = document.getElementById("table-delsys-c");
    tableEl.innerHTML = "";
    renderContractionTable(tableEl, data.result.contractions);
    state.results.contractions.delsys = true;
    updateBadges();
    setStatus(`Delsys 收縮區間完成（${data.result.contractions.length} 段）`);
  } else {
    const txtFiles = requireTxt();
    setStatus(`偵測 TXT 收縮區間（${txtFiles.length} 個 · ${contractionMethod}）...`);
    const expected = Number(document.getElementById("expected-count-c").value || 3);

    const traces = [];
    const allShapes = [];
    const tableEl = document.getElementById("table-txt-c");
    tableEl.innerHTML = "";

    for (let i = 0; i < txtFiles.length; i++) {
      const data = await api("/api/analyze/contractions", {
        method: "POST",
        body: JSON.stringify({
          source: "txt",
          filename: txtFiles[i],
          expected_count: expected,
          contraction_method: contractionMethod,
        }),
      });
      const color = TXT_COLORS[i % TXT_COLORS.length];
      traces.push({
        x: data.result.times,
        y: data.result.values,
        type: "scattergl",
        mode: "lines",
        name: data.result.filename,
        line: { color, width: 1.2 },
      });
      const shapeColor = color.replace("#", "");
      const r = parseInt(shapeColor.substring(0, 2), 16);
      const g = parseInt(shapeColor.substring(2, 4), 16);
      const b = parseInt(shapeColor.substring(4, 6), 16);
      allShapes.push(...shapesFromContractions(data.result.contractions, `rgba(${r},${g},${b},0.18)`));
      renderContractionTable(tableEl, data.result.contractions, data.result.filename);
    }

    await Plotly.newPlot(
      "chart-txt-c",
      traces,
      {
        ...PLOT_LAYOUT,
        title: `TXT 收縮區間（${txtFiles.length} 個 · ${contractionMethod}）`,
        shapes: allShapes,
        height: 280,
        margin: { t: 48, r: 16, b: 40, l: 48 },
      },
      { responsive: true }
    );
    state.results.contractions.txt = true;
    updateBadges();
    setStatus(`TXT 收縮區間完成（${txtFiles.length} 個）`);
  }
}

async function runContractionsBoth() {
  requirePair();
  setStatus("兩邊收縮區間偵測中...");
  await runContractionsSingle("delsys");
  await runContractionsSingle("txt");
  state.results.contractions.delsys = true;
  state.results.contractions.txt = true;
  updateBadges();
  setStatus("兩邊收縮區間完成");
}

/* ── Features ── */

async function runFeaturesSingle(source) {
  const contractionMethod = currentContractionMethod("f");
  const featureMethod = currentFeatureMethod();
  if (source === "delsys") {
    const filename = requireDelsys();
    setStatus(`計算 Delsys 特徵（${featureMethod}）...`);
    const expected = Number(document.getElementById("expected-count-f").value || 3);
    const data = await api("/api/analyze/features", {
      method: "POST",
      body: JSON.stringify({
        source: "delsys",
        filename,
        expected_count: expected,
        contraction_method: contractionMethod,
        feature_method: featureMethod,
      }),
    });
    const tableEl = document.getElementById("table-feat-delsys");
    tableEl.innerHTML = "";
    renderSingleFeatureTable(tableEl, data.result.features, null, featureMethod);
    state.results.features.delsys = true;
    updateBadges();
    setStatus(`Delsys 特徵完成（${data.result.count} 段）`);
  } else {
    const txtFiles = requireTxt();
    setStatus(`計算 TXT 特徵（${txtFiles.length} 個 · ${featureMethod}）...`);
    const expected = Number(document.getElementById("expected-count-f").value || 3);

    const tableEl = document.getElementById("table-feat-txt");
    tableEl.innerHTML = "";
    for (const filename of txtFiles) {
      const data = await api("/api/analyze/features", {
        method: "POST",
        body: JSON.stringify({
          source: "txt",
          filename,
          expected_count: expected,
          contraction_method: contractionMethod,
          feature_method: featureMethod,
        }),
      });
      renderSingleFeatureTable(tableEl, data.result.features, data.result.filename, featureMethod);
    }
    state.results.features.txt = true;
    updateBadges();
    setStatus(`TXT 特徵完成（${txtFiles.length} 個）`);
  }
}

async function runFeaturesBoth() {
  requirePair();
  setStatus("兩邊特徵計算中...");
  const expected = Number(document.getElementById("expected-count-f").value || 3);
  const contractionMethod = currentContractionMethod("f");
  const featureMethod = currentFeatureMethod();
  const txtFiles = [...state.selectedTxt];

  const data = await api("/api/compare/features", {
    method: "POST",
    body: JSON.stringify({
      delsys: state.selectedDelsys,
      txt: txtFiles[0],
      expected_count: expected,
      contraction_method: contractionMethod,
      feature_method: featureMethod,
    }),
  });

  const delsysTableEl = document.getElementById("table-feat-delsys");
  delsysTableEl.innerHTML = "";
  renderSingleFeatureTable(delsysTableEl, data.delsys.features, null, featureMethod);

  const txtTableEl = document.getElementById("table-feat-txt");
  txtTableEl.innerHTML = "";
  renderSingleFeatureTable(txtTableEl, data.txt.features, txtFiles[0], featureMethod);

  for (let i = 1; i < txtFiles.length; i++) {
    const extra = await api("/api/analyze/features", {
      method: "POST",
      body: JSON.stringify({
        source: "txt",
        filename: txtFiles[i],
        expected_count: expected,
        contraction_method: contractionMethod,
        feature_method: featureMethod,
      }),
    });
    renderSingleFeatureTable(txtTableEl, extra.result.features, extra.result.filename, featureMethod);
  }

  renderDeltaTable(data);

  state.results.features.delsys = true;
  state.results.features.txt = true;
  state.results.features.delta = true;
  updateBadges();
  setStatus(`特徵比對完成（Delsys vs ${txtFiles.length} TXT，Δ 以第一個 TXT 計算）`);
}

/* ── Tabs ── */

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el === tab));
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === `panel-${name}`);
      });
      requestAnimationFrame(() => {
        document.querySelectorAll(`#panel-${name} .js-plotly-plot`).forEach((el) => {
          try { Plotly.Plots.resize(el); } catch (_) { /* ignore */ }
        });
      });
    });
  });
}

/* ── Events ── */

function setupEvents() {
  document.getElementById("refresh-btn").addEventListener("click", () => {
    loadFiles().catch((err) => setStatus(err.message));
  });

  delsysListEl.addEventListener("click", (event) => {
    const btn = event.target.closest(".file-item");
    if (!btn) return;
    state.selectedDelsys = btn.dataset.name;
    renderDelsysList();
    setStatus(`已選 Delsys：${state.selectedDelsys}`);
    refreshSuggestions().catch((err) => setStatus(err.message));
  });

  txtListEl.addEventListener("click", (event) => {
    const btn = event.target.closest(".file-item");
    if (!btn) return;
    const name = btn.dataset.name;
    if (state.selectedTxt.has(name)) {
      state.selectedTxt.delete(name);
    } else {
      state.selectedTxt.add(name);
    }
    renderTxtList();
    setStatus(`已選 TXT：${txtSelectionLabel()}`);
    refreshSuggestions().catch((err) => setStatus(err.message));
  });

  suggestListEl.addEventListener("click", (event) => {
    const btn = event.target.closest(".suggest-item");
    if (!btn) return;
    selectPair(btn.dataset.delsys, btn.dataset.txt).catch((err) => setStatus(err.message));
  });

  document.getElementById("run-wave-delsys").addEventListener("click", () => {
    runWaveformSingle("delsys").catch((err) => setStatus(err.message));
  });
  document.getElementById("run-wave-txt").addEventListener("click", () => {
    runWaveformSingle("txt").catch((err) => setStatus(err.message));
  });
  document.getElementById("run-wave-both").addEventListener("click", () => {
    runWaveformBoth().catch((err) => setStatus(err.message));
  });

  document.getElementById("run-contr-delsys").addEventListener("click", () => {
    runContractionsSingle("delsys").catch((err) => setStatus(err.message));
  });
  document.getElementById("run-contr-txt").addEventListener("click", () => {
    runContractionsSingle("txt").catch((err) => setStatus(err.message));
  });
  document.getElementById("run-contr-both").addEventListener("click", () => {
    runContractionsBoth().catch((err) => setStatus(err.message));
  });

  document.getElementById("run-feat-delsys").addEventListener("click", () => {
    runFeaturesSingle("delsys").catch((err) => setStatus(err.message));
  });
  document.getElementById("run-feat-txt").addEventListener("click", () => {
    runFeaturesSingle("txt").catch((err) => setStatus(err.message));
  });
  document.getElementById("run-feat-both").addEventListener("click", () => {
    runFeaturesBoth().catch((err) => setStatus(err.message));
  });
}

setupTabs();
setupEvents();
loadFiles().catch((err) => setStatus(err.message));
