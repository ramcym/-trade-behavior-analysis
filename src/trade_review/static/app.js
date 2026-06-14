let state = null;
let currentView = "dashboard";
let selectedTradeId = null;
let reviewScrollTop = 0;

const app = document.getElementById("app");

async function loadData() {
  const response = await fetch("/api/data");
  state = await response.json();
  if (!selectedTradeId && trades().length) selectedTradeId = trades()[0].trade_id;
  render();
}

function trades() {
  return state?.diagnosis?.trades || [];
}

function fmtMoney(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${Number(value || 0).toFixed(2)}`;
}

function fmtPct(value) {
  const pct = Number(value || 0) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function cls(value) {
  return Number(value) >= 0 ? "good" : "bad";
}

function render() {
  document.querySelectorAll(".nav").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === currentView);
  });
  if (!state) return;
  if (currentView === "dashboard") renderDashboard();
  if (currentView === "review") renderReview();
  if (currentView === "winsLosses") renderWinsLosses();
  if (currentView === "emotion") renderEmotion();
  if (currentView === "progress") renderProgress();
}

function renderDashboard() {
  const d = state.diagnosis;
  const s = d.summary;
  const sim = d.simulations;
  const risk = d.risk_model;
  app.innerHTML = `
    <div class="card"><strong>??????</strong>${state.source?.trades_path || "-"}</div>
    <div class="grid kpis">
      ${kpi("实际盈亏", fmtMoney(s.pnl), cls(s.pnl))}
      ${kpi("交易笔数", s.count, "")}
      ${kpi("胜率", `${s.win_rate}%`, "")}
      ${kpi("剔除模式外", fmtMoney(sim.without_system_out_pnl), cls(sim.without_system_out_pnl))}
      ${kpi("-3%止损模拟", fmtMoney(sim.strict_stop_3pct_pnl), cls(sim.strict_stop_3pct_pnl))}
    </div>
    <h2>核心结论</h2>
    <div class="card">${d.conclusions.map((item) => `<p>${item}</p>`).join("")}</div>
    <h2>凯利仓位策略</h2>
    <div class="card">
      <p>${risk.formula}</p>
      <table>
        <thead><tr><th>状态</th><th>样本</th><th>胜率</th><th>盈亏比</th><th>单笔期望</th><th>Raw Kelly</th><th>半凯利</th><th>建议仓位</th></tr></thead>
        <tbody>${risk.profiles.map((p) => `
          <tr>
            <td>${p.name}</td><td>${p.sample_size}</td><td>${p.win_rate}%</td><td>${p.payoff_ratio ?? "-"}</td>
            <td>${p.expectancy}</td><td>${p.raw_kelly_pct}%</td><td>${p.half_kelly_pct}%</td>
            <td><strong>${p.recommended_position_pct}%</strong><div class="muted">${p.reason}</div></td>
          </tr>`).join("")}</tbody>
      </table>
    </div>
    <h2>模式分组</h2>
    <table>
      <thead><tr><th>分组</th><th>笔数</th><th>盈亏</th><th>胜率</th><th>盈亏比</th><th>单笔期望</th><th>严重亏损</th></tr></thead>
      <tbody>
        ${groupRow("系统内", d.groups.system_in)}
        ${groupRow("部分符合", d.groups.partial)}
        ${groupRow("系统外", d.groups.system_out)}
        ${groupRow("未标注", d.groups.unannotated)}
      </tbody>
    </table>
    <h2>修正模拟</h2>
    <div class="grid kpis">
      ${kpi("连续盈利后半仓", fmtMoney(sim.half_size_after_three_wins_pnl), cls(sim.half_size_after_three_wins_pnl))}
      ${kpi("模式外降至2成", fmtMoney(sim.system_out_20pct_size_pnl), cls(sim.system_out_20pct_size_pnl))}
      ${kpi("禁止午后情绪单", fmtMoney(sim.no_afternoon_emotion_pnl), cls(sim.no_afternoon_emotion_pnl))}
    </div>
  `;
}

function kpi(label, value, klass) {
  return `<div class="card"><div class="muted">${label}</div><div class="kpi-value ${klass}">${value}</div></div>`;
}

function groupRow(label, g) {
  return `<tr>
    <td>${label}</td><td>${g.count}</td><td class="${cls(g.pnl)}">${fmtMoney(g.pnl)}</td>
    <td>${g.win_rate}%</td><td>${g.payoff_ratio ?? "-"}</td><td>${g.expectancy}</td><td>${g.severe_loss_count}</td>
  </tr>`;
}

function renderReview(filter = null) {
  const list = filter || trades();
  const selected = trades().find((trade) => trade.trade_id === selectedTradeId) || list[0];
  if (!selected) {
    app.innerHTML = `<div class="card">没有闭合交易。</div>`;
    return;
  }
  selectedTradeId = selected.trade_id;
  app.innerHTML = `
    <div class="split">
      <div class="trade-list">${list.map(tradeItem).join("")}</div>
      <div class="card">${annotationForm(selected)}</div>
    </div>
  `;
  bindTradeList();
  bindForm(selected);
  restoreReviewScroll();
}

function tradeItem(t) {
  return `<div class="trade-item ${t.trade_id === selectedTradeId ? "active" : ""}" data-id="${t.trade_id}">
    <strong>${t.code} ${t.name}</strong>
    <div class="${cls(t.pnl)}">${fmtMoney(t.pnl)} / ${fmtPct(t.return_pct)}</div>
    <div class="muted">${t.buy_time.slice(5, 16)} → ${t.sell_time.slice(5, 16)} · ${t.rank_tag || "普通"}</div>
    <div>${t.system_fit} · ${t.quality_label}</div>
  </div>`;
}

function annotationForm(t) {
  return `
    <h2>${t.code} ${t.name}</h2>
    <p>${t.buy_time} 买入，${t.sell_time} 卖出，结果 <span class="${cls(t.pnl)}">${fmtMoney(t.pnl)} / ${fmtPct(t.return_pct)}</span></p>
    <div class="form-grid">
      ${selectField("system_fit", "是否符合交易模式", t.system_fit)}
      ${selectField("plan_follow", "是否按计划执行", t.plan_follow)}
      ${selectField("emotion_state", "开仓情绪", t.emotion_state)}
      ${selectField("buy_quality", "买点质量", t.buy_quality)}
      ${selectField("position_quality", "仓位质量", t.position_quality)}
      ${selectField("stop_execution", "止损执行", t.stop_execution)}
    </div>
    <h3>情绪来源</h3>
    <div class="chips">${state.choices.emotion_sources.map((item) => `<button class="chip ${t.emotion_sources.includes(item) ? "active" : ""}" data-source="${item}">${item}</button>`).join("")}</div>
    <label class="notes">备注<textarea id="notes">${t.notes || ""}</textarea></label>
    <div class="card">
      <strong>知行合一分：</strong>${t.plan_follow_score ?? "未评分"}
      <div class="bar"><span style="width:${Math.max(0, Math.min(100, t.plan_follow_score || 0))}%"></span></div>
    </div>
    <button id="saveAnnotation">保存标注</button>
  `;
}

function selectField(key, label, value) {
  return `<label>${label}<select id="${key}">
    ${state.choices[key].map((item) => `<option ${item === value ? "selected" : ""}>${item}</option>`).join("")}
  </select></label>`;
}

function bindTradeList() {
  const list = document.querySelector(".trade-list");
  if (list) {
    list.addEventListener("scroll", () => {
      reviewScrollTop = list.scrollTop;
    });
  }
  document.querySelectorAll(".trade-item").forEach((item) => {
    item.addEventListener("click", () => {
      selectedTradeId = item.dataset.id;
      renderReview();
    });
  });
}

function restoreReviewScroll() {
  const list = document.querySelector(".trade-list");
  const active = document.querySelector(".trade-item.active");
  if (!list) return;
  list.scrollTop = reviewScrollTop;
  if (active) {
    const activeTop = active.offsetTop;
    const activeBottom = activeTop + active.offsetHeight;
    if (activeTop < list.scrollTop || activeBottom > list.scrollTop + list.clientHeight) {
      active.scrollIntoView({ block: "nearest" });
      reviewScrollTop = list.scrollTop;
    }
  }
}

function bindForm(t) {
  const sources = new Set(t.emotion_sources || []);
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", (event) => {
      event.preventDefault();
      const value = chip.dataset.source;
      if (sources.has(value)) sources.delete(value);
      else sources.add(value);
      chip.classList.toggle("active");
    });
  });
  document.getElementById("saveAnnotation").addEventListener("click", async () => {
    const list = document.querySelector(".trade-list");
    if (list) reviewScrollTop = list.scrollTop;
    const payload = {
      trade_id: t.trade_id,
      system_fit: value("system_fit"),
      plan_follow: value("plan_follow"),
      emotion_state: value("emotion_state"),
      emotion_sources: [...sources],
      buy_quality: value("buy_quality"),
      position_quality: value("position_quality"),
      stop_execution: value("stop_execution"),
      notes: document.getElementById("notes").value,
    };
    await fetch("/api/annotation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadData();
  });
}

function value(id) {
  return document.getElementById(id).value;
}

function renderWinsLosses() {
  const key = trades().filter((t) => t.rank_tag.includes("大肉") || t.rank_tag.includes("大亏"));
  app.innerHTML = `
    <h2>关键交易</h2>
    <table>
      <thead><tr><th>标签</th><th>交易</th><th>买入</th><th>盈亏</th><th>标注</th><th>质量</th></tr></thead>
      <tbody>${key.map((t) => `<tr>
        <td>${t.rank_tag}</td><td>${t.code} ${t.name}</td><td>${t.buy_time}</td>
        <td class="${cls(t.pnl)}">${fmtMoney(t.pnl)} / ${fmtPct(t.return_pct)}</td><td>${t.system_fit}</td><td>${t.quality_label}</td>
      </tr>`).join("")}</tbody>
    </table>
  `;
}

function renderEmotion() {
  const e = state.diagnosis.emotion;
  app.innerHTML = `
    <h2>情绪周期</h2>
    <table>
      <thead><tr><th>状态</th><th>笔数</th><th>盈亏</th><th>胜率</th><th>严重亏损</th></tr></thead>
      <tbody>${Object.entries(e).map(([name, s]) => `<tr><td>${name}</td><td>${s.count}</td><td class="${cls(s.pnl)}">${fmtMoney(s.pnl)}</td><td>${s.win_rate}%</td><td>${s.severe_loss_count}</td></tr>`).join("")}</tbody>
    </table>
  `;
}

function renderProgress() {
  const daily = state.diagnosis.progress;
  const weekly = state.diagnosis.weekly_progress || [];
  app.innerHTML = `
    <h2>??????</h2>
    <div class="card">${lineChart(daily, "date")}</div>
    <table>
      <thead><tr><th>??</th><th>??</th><th>????</th><th>?????</th><th>?????</th><th>??</th></tr></thead>
      <tbody>${daily.map((item) => `<tr><td>${item.date}</td><td class="${cls(item.pnl)}">${fmtMoney(item.pnl)}</td><td>${item.alignment_score ?? "???"}</td><td>${item.system_in_ratio}%</td><td>${item.emotion_trade_count}</td><td>${item.severe_loss_count}</td></tr>`).join("")}</tbody>
    </table>
    <h2>??????</h2>
    <div class="card">${lineChart(weekly, "week")}</div>
    <table>
      <thead><tr><th>?</th><th>??</th><th>??</th><th>????</th><th>?????</th><th>?????</th><th>??</th></tr></thead>
      <tbody>${weekly.map((item) => `<tr><td>${item.week}</td><td>${item.trade_count}</td><td class="${cls(item.pnl)}">${fmtMoney(item.pnl)}</td><td>${item.alignment_score ?? "???"}</td><td>${item.system_in_ratio}%</td><td>${item.emotion_trade_count}</td><td>${item.severe_loss_count}</td></tr>`).join("")}</tbody>
    </table>
  `;
}

function lineChart(items, labelKey) {
  const points = items
    .map((item, index) => ({ ...item, index, score: item.alignment_score }))
    .filter((item) => item.score !== null && item.score !== undefined);
  if (!points.length) {
    return `<p>????????????????????${labelKey === "week" ? "?" : "?"}??????????</p>`;
  }
  const width = 820;
  const height = 260;
  const left = 46;
  const right = 18;
  const top = 18;
  const bottom = 42;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const maxIndex = Math.max(points.length - 1, 1);
  const xy = points.map((point, idx) => {
    const x = left + (idx / maxIndex) * plotW;
    const y = top + (1 - point.score / 100) * plotH;
    return { ...point, x, y };
  });
  const path = xy.map((point, idx) => `${idx === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const labels = xy.map((point) => {
    const label = String(point[labelKey]).replace(/^2026-/, "");
    return `<text x="${point.x}" y="${height - 14}" text-anchor="middle" font-size="11" fill="#647084">${label}</text>`;
  }).join("");
  const dots = xy.map((point) => `
    <circle class="score-point" cx="${point.x}" cy="${point.y}" r="4">
      <title>${point[labelKey]} ???? ${point.score}??? ${fmtMoney(point.pnl)}</title>
    </circle>`).join("");
  return `
    <svg class="line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="????????">
      <line class="axis" x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}"></line>
      <line class="axis" x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}"></line>
      ${[0, 25, 50, 75, 100].map((tick) => {
        const y = top + (1 - tick / 100) * plotH;
        return `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width - right}" y2="${y}"></line><text x="10" y="${y + 4}" font-size="11" fill="#647084">${tick}</text>`;
      }).join("")}
      <path class="score-line" d="${path}"></path>
      ${dots}
      ${labels}
    </svg>`;
}

document.querySelectorAll(".nav").forEach((button) => {
  button.addEventListener("click", () => {
    currentView = button.dataset.view;
    render();
  });
});

document.getElementById("exportReport").addEventListener("click", async () => {
  const response = await fetch("/api/report");
  const data = await response.json();
  alert(`报告已生成：${data.path}`);
});


document.getElementById("importFile").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const response = await fetch("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, content_base64: btoa(binary) }),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    alert(`?????${data.error || response.statusText}`);
    return;
  }
  state = data;
  selectedTradeId = null;
  reviewScrollTop = 0;
  currentView = "dashboard";
  render();
  event.target.value = "";
});

loadData();
