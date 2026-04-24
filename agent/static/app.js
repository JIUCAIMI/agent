const chatLog = document.getElementById("chat-log");
const queryForm = document.getElementById("query-form");
const queryInput = document.getElementById("query-input");
const sendBtn = document.getElementById("send-btn");
const dataFile = document.getElementById("data-file");
const rowCount = document.getElementById("row-count");
const fieldList = document.getElementById("field-list");
const aiStatus = document.getElementById("ai-status");
const aiModel = document.getElementById("ai-model");
const suggestionTemplate = document.getElementById("suggestion-template");

function scrollToBottom() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

function appendTextMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  article.appendChild(bubble);
  chatLog.appendChild(article);
  scrollToBottom();
  return article;
}

function createMetricCard(label, value) {
  const card = document.createElement("div");
  card.className = "metric-card";

  const labelNode = document.createElement("span");
  labelNode.className = "metric-label";
  labelNode.textContent = label;

  const valueNode = document.createElement("strong");
  valueNode.className = "metric-value";
  valueNode.textContent = value;

  card.append(labelNode, valueNode);
  return card;
}

function createTable(columns, rows) {
  const wrapper = document.createElement("div");
  wrapper.className = "table-wrap";

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");

  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headRow.appendChild(th);
  });

  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const td = document.createElement("td");
      const value = row[column];
      td.textContent = value === null || value === undefined ? "" : String(value);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  wrapper.appendChild(table);
  return wrapper;
}

function createSuggestions(items) {
  const wrapper = document.createElement("div");
  wrapper.className = "inline-suggestions";

  items.forEach((item) => {
    const node = suggestionTemplate.content.firstElementChild.cloneNode(true);
    node.textContent = item;
    node.addEventListener("click", async () => {
      queryInput.value = item;
      sendBtn.disabled = true;
      await sendQuery(item);
      queryInput.value = "";
      sendBtn.disabled = false;
      queryInput.focus();
    });
    wrapper.appendChild(node);
  });

  return wrapper;
}

function createChart(chartData) {
  if (!chartData || chartData.type !== "bar" || !chartData.labels?.length) {
    return null;
  }

  const section = document.createElement("section");
  section.className = "chart-card";

  const title = document.createElement("p");
  title.className = "chart-title";
  title.textContent = chartData.title || "结果图表";
  section.appendChild(title);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 640 260");
  svg.setAttribute("class", "chart-svg");

  const max = Math.max(...chartData.values, 1);
  const barWidth = 36;
  const gap = 14;
  const startX = 32;

  chartData.values.forEach((value, index) => {
    const height = Math.max((value / max) * 160, 4);
    const x = startX + index * (barWidth + gap);
    const y = 190 - height;

    const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bar.setAttribute("x", x);
    bar.setAttribute("y", y);
    bar.setAttribute("width", barWidth);
    bar.setAttribute("height", height);
    bar.setAttribute("rx", "10");
    bar.setAttribute("fill", "url(#barGradient)");
    svg.appendChild(bar);

    const valueLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    valueLabel.setAttribute("x", x + barWidth / 2);
    valueLabel.setAttribute("y", y - 8);
    valueLabel.setAttribute("text-anchor", "middle");
    valueLabel.setAttribute("class", "chart-value");
    valueLabel.textContent = String(value);
    svg.appendChild(valueLabel);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", x + barWidth / 2);
    label.setAttribute("y", "220");
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "chart-label");
    label.textContent = String(chartData.labels[index]).slice(0, 6);
    svg.appendChild(label);
  });

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <linearGradient id="barGradient" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#d77244"></stop>
      <stop offset="100%" stop-color="#924225"></stop>
    </linearGradient>
  `;
  svg.prepend(defs);
  section.appendChild(svg);
  return section;
}

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function exportCsv(columns, rows) {
  const lines = [columns.join(",")];
  rows.forEach((row) => {
    const line = columns
      .map((column) => {
        const raw = row[column] === null || row[column] === undefined ? "" : String(row[column]);
        return `"${raw.replaceAll('"', '""')}"`;
      })
      .join(",");
    lines.push(line);
  });
  downloadBlob("query-result.csv", "\ufeff" + lines.join("\n"), "text/csv;charset=utf-8");
}

function createActions(payload) {
  const actions = document.createElement("div");
  actions.className = "result-actions";
  const table = payload.presentation?.table;

  if (table?.columns?.length && table?.rows?.length) {
    const csvButton = document.createElement("button");
    csvButton.type = "button";
    csvButton.className = "action-btn";
    csvButton.textContent = "导出 CSV";
    csvButton.addEventListener("click", () => exportCsv(table.columns, table.rows));
    actions.appendChild(csvButton);
  }

  const jsonButton = document.createElement("button");
  jsonButton.type = "button";
  jsonButton.className = "action-btn";
  jsonButton.textContent = "导出 JSON";
  jsonButton.addEventListener("click", () => {
    downloadBlob("query-result.json", JSON.stringify(payload, null, 2), "application/json;charset=utf-8");
  });
  actions.appendChild(jsonButton);

  return actions;
}

function appendResultMessage(payload) {
  const presentation = payload.presentation || {};
  const article = document.createElement("article");
  article.className = "message assistant";

  const bubble = document.createElement("div");
  bubble.className = "bubble bubble-rich";

  const summary = document.createElement("p");
  summary.className = "summary";
  summary.textContent = presentation.summary || "查询已完成。";
  bubble.appendChild(summary);

  if (Array.isArray(presentation.cards) && presentation.cards.length) {
    const cardGrid = document.createElement("div");
    cardGrid.className = "metric-grid";
    presentation.cards.forEach((item) => {
      cardGrid.appendChild(createMetricCard(item.label, item.value));
    });
    bubble.appendChild(cardGrid);
  }

  const chart = createChart(presentation.chart);
  if (chart) {
    bubble.appendChild(chart);
  }

  if (presentation.table && presentation.table.columns?.length && presentation.table.rows?.length) {
    bubble.appendChild(createTable(presentation.table.columns, presentation.table.rows));
  }

  bubble.appendChild(createActions(payload));

  if (Array.isArray(presentation.suggestions) && presentation.suggestions.length) {
    const hint = document.createElement("p");
    hint.className = "suggestion-title";
    hint.textContent = "继续追问";
    bubble.appendChild(hint);
    bubble.appendChild(createSuggestions(presentation.suggestions));
  }

  const details = document.createElement("details");
  details.className = "debug-details";
  const debugSummary = document.createElement("summary");
  debugSummary.textContent = "查看原始返回";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(payload, null, 2);
  details.append(debugSummary, pre);
  bubble.appendChild(details);

  article.appendChild(bubble);
  chatLog.appendChild(article);
  scrollToBottom();
}

async function loadMeta() {
  const response = await fetch("/api/meta");
  const payload = await response.json();
  dataFile.textContent = payload.data_file;
  rowCount.textContent = payload.row_count;
  fieldList.textContent = payload.fields.join("、");
  aiStatus.textContent = payload.openai_enabled ? "已启用" : "未启用";
  aiModel.textContent = payload.openai_enabled ? payload.openai_model : "本地规则回退";
}

async function sendQuery(query) {
  appendTextMessage("user", query);
  const pending = appendTextMessage("assistant", "正在分析你的问题...");

  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    });
    const payload = await response.json();

    pending.remove();

    if (!response.ok) {
      appendTextMessage("assistant", payload.error || "请求失败。");
      return;
    }

    appendResultMessage(payload);
  } catch (error) {
    pending.remove();
    appendTextMessage("assistant", "网络请求失败，请检查服务是否正常。");
  }
}

queryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    return;
  }

  sendBtn.disabled = true;
  await sendQuery(query);
  queryInput.value = "";
  sendBtn.disabled = false;
  queryInput.focus();
});

document.querySelectorAll(".prompt-chip").forEach((button) => {
  button.addEventListener("click", async () => {
    const query = button.textContent.trim();
    queryInput.value = query;
    sendBtn.disabled = true;
    await sendQuery(query);
    queryInput.value = "";
    sendBtn.disabled = false;
    queryInput.focus();
  });
});

loadMeta();
