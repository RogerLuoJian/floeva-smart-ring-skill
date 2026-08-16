(() => {
  "use strict";

  const svgNamespace = "http://www.w3.org/2000/svg";
  const canvas = document.getElementById("health-canvas");
  const loading = document.getElementById("loading-state");
  const errorState = document.getElementById("error-state");

  function text(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function rows(value) {
    if (!Array.isArray(value)) return [];
    return value
      .filter(item => item && typeof item === "object")
      .slice()
      .sort((left, right) => String(left.date || "").localeCompare(String(right.date || "")));
  }

  function latest(items) {
    return items.length ? items[items.length - 1] : {};
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function integer(value) {
    const parsed = number(value);
    return parsed === null ? "未记录" : Math.round(parsed).toLocaleString("zh-CN");
  }

  function dateLabel(value, long = false) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) return "日期未记录";
    const month = Number(match[2]);
    const day = Number(match[3]);
    return long ? `${match[1]} 年 ${month} 月 ${day} 日` : `${month}/${day}`;
  }

  function minutesLabel(value, compact = false) {
    const parsed = number(value);
    if (parsed === null) return "未记录";
    const total = Math.max(0, Math.round(parsed));
    const hours = Math.floor(total / 60);
    const minutes = total % 60;
    if (compact) return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
    if (!hours) return `${minutes} 分`;
    return `${hours} 小时 ${minutes} 分`;
  }

  function decimalHours(value) {
    const parsed = number(value);
    return parsed === null ? "—" : (parsed / 60).toFixed(1);
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function extent(values) {
    const valid = values.map(number).filter(value => value !== null);
    if (!valid.length) return [0, 1];
    const low = Math.min(...valid);
    const high = Math.max(...valid);
    return low === high ? [low - 1, high + 1] : [low, high];
  }

  function normalized(values, lowTarget = 0, highTarget = 1) {
    const [low, high] = extent(values);
    const span = high - low || 1;
    return values.map(value => {
      const parsed = number(value);
      if (parsed === null) return (lowTarget + highTarget) / 2;
      return lowTarget + ((parsed - low) / span) * (highTarget - lowTarget);
    });
  }

  function svgElement(name, attributes = {}, content = "") {
    const element = document.createElementNS(svgNamespace, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    if (content) element.textContent = content;
    return element;
  }

  function smoothPath(points) {
    if (!points.length) return "";
    if (points.length === 1) return `M ${points[0][0]} ${points[0][1]}`;
    let path = `M ${points[0][0]} ${points[0][1]}`;
    for (let index = 1; index < points.length - 1; index += 1) {
      const current = points[index];
      const next = points[index + 1];
      const middleX = (current[0] + next[0]) / 2;
      const middleY = (current[1] + next[1]) / 2;
      path += ` Q ${current[0]} ${current[1]} ${middleX} ${middleY}`;
    }
    const previous = points[points.length - 2];
    const last = points[points.length - 1];
    return `${path} Q ${previous[0]} ${previous[1]} ${last[0]} ${last[1]}`;
  }

  function linePoints(values, box) {
    const count = Math.max(1, values.length - 1);
    const normalizedValues = normalized(values, 0, 1);
    return normalizedValues.map((value, index) => [
      box.left + ((box.right - box.left) * index) / count,
      box.bottom - value * (box.bottom - box.top),
    ]);
  }

  function buildLandscape(stepRows, heartRows, sleepRows) {
    const grid = document.getElementById("terrain-grid");
    const ridges = document.getElementById("terrain-ridges");
    const signals = document.getElementById("terrain-signals");
    const labels = document.getElementById("terrain-labels");
    grid.replaceChildren();
    ridges.replaceChildren();
    signals.replaceChildren();
    labels.replaceChildren();

    for (let index = 0; index < 9; index += 1) {
      const y = 286 + index * 42;
      grid.appendChild(svgElement("path", {
        d: `M 70 ${y} C 310 ${y - 78}, 880 ${y - 22}, 1150 ${y + 34}`,
        fill: "none",
        stroke: "rgba(107,114,128,0.13)",
        "stroke-width": 1,
      }));
    }
    for (let index = 0; index < 12; index += 1) {
      const x = 80 + index * 98;
      grid.appendChild(svgElement("path", {
        d: `M ${x} 260 C ${x - 70} 420, ${x + 70} 560, ${x + 24} 660`,
        fill: "none",
        stroke: "rgba(107,114,128,0.1)",
        "stroke-width": 1,
      }));
    }

    const steps = stepRows.map(item => number(item.steps) || 0);
    const averageHeart = heartRows.map(item => number(item.avg_heart_rate) || 0);
    const sleepByDate = new Map(sleepRows.map(item => [item.date, number(item.total_minutes) || 0]));
    const dates = stepRows.length
      ? stepRows.map(item => item.date)
      : heartRows.map(item => item.date);
    const sleep = dates.map(date => sleepByDate.get(date) || 0);
    const source = steps.length ? steps : averageHeart.length ? averageHeart : [0, 0, 0];
    const box = { left: 120, right: 1080, top: 214, bottom: 478 };
    const mainPoints = linePoints(source, box);

    for (let layer = 6; layer >= 0; layer -= 1) {
      const offset = layer * 22;
      const shifted = mainPoints.map(([x, y]) => [x, y + offset]);
      const line = smoothPath(shifted);
      const area = `${line} L ${shifted[shifted.length - 1][0]} 642 L ${shifted[0][0]} 642 Z`;
      ridges.appendChild(svgElement("path", {
        d: area,
        fill: "url(#terrain-fill)",
        opacity: 0.15 + (6 - layer) * 0.055,
      }));
      ridges.appendChild(svgElement("path", {
        d: line,
        fill: "none",
        stroke: layer === 0 ? "url(#terrain-stroke)" : "rgba(124,58,237,0.18)",
        "stroke-width": layer === 0 ? 7 : 2,
        opacity: layer === 0 ? 0.78 : 0.45,
        filter: layer === 0 ? "url(#soft-glow)" : "none",
      }));
    }

    if (averageHeart.length > 1) {
      const heartPoints = linePoints(averageHeart, { left: 120, right: 1080, top: 294, bottom: 468 });
      signals.appendChild(svgElement("path", {
        d: smoothPath(heartPoints),
        fill: "none",
        stroke: "rgba(239,68,68,0.7)",
        "stroke-width": 3,
      }));
    }
    if (sleep.some(value => value > 0)) {
      const sleepPoints = linePoints(sleep, { left: 120, right: 1080, top: 340, bottom: 500 });
      signals.appendChild(svgElement("path", {
        d: smoothPath(sleepPoints),
        fill: "none",
        stroke: "rgba(99,102,241,0.65)",
        "stroke-width": 3,
        "stroke-dasharray": "8 9",
      }));
    }

    mainPoints.forEach(([x, y], index) => {
      signals.appendChild(svgElement("circle", {
        cx: x,
        cy: y,
        r: index === mainPoints.length - 1 ? 7 : 4,
        fill: index === mainPoints.length - 1 ? "#7c3aed" : "#ffffff",
        stroke: "#7c3aed",
        "stroke-width": 3,
      }));
      if (dates[index]) {
        labels.appendChild(svgElement("text", {
          x,
          y: 620,
          "text-anchor": index === 0 ? "start" : index === mainPoints.length - 1 ? "end" : "middle",
          fill: "#6b7280",
          "font-family": "Inter, sans-serif",
          "font-size": 16,
        }, dateLabel(dates[index])));
      }
    });
  }

  function buildStepsSpark(stepRows, baseline) {
    const svg = document.getElementById("steps-spark");
    svg.replaceChildren();
    if (!stepRows.length) {
      svg.appendChild(svgElement("text", { x: 0, y: 72 }, "暂无步数记录"));
      return;
    }
    const values = stepRows.map(item => number(item.steps) || 0);
    const withBaseline = number(baseline) === null ? values : [...values, number(baseline)];
    const [low, high] = extent(withBaseline);
    const span = high - low || 1;
    const points = values.map((value, index) => [
      14 + (492 * index) / Math.max(1, values.length - 1),
      102 - ((value - low) / span) * 76,
    ]);
    const path = smoothPath(points);
    const area = `${path} L ${points[points.length - 1][0]} 110 L ${points[0][0]} 110 Z`;
    const defs = svgElement("defs");
    const gradient = svgElement("linearGradient", { id: "steps-area", x1: 0, y1: 0, x2: 0, y2: 1 });
    gradient.appendChild(svgElement("stop", { offset: 0, "stop-color": "#10b981", "stop-opacity": 0.34 }));
    gradient.appendChild(svgElement("stop", { offset: 1, "stop-color": "#10b981", "stop-opacity": 0 }));
    defs.appendChild(gradient);
    svg.appendChild(defs);
    svg.appendChild(svgElement("path", { d: area, fill: "url(#steps-area)" }));
    svg.appendChild(svgElement("path", { d: path, fill: "none", stroke: "#10b981", "stroke-width": 4, "stroke-linecap": "round" }));
    points.forEach(([x, y], index) => {
      svg.appendChild(svgElement("circle", { cx: x, cy: y, r: index === points.length - 1 ? 5 : 3, fill: "#ffffff", stroke: "#10b981", "stroke-width": 3 }));
    });
    const last = stepRows[stepRows.length - 1];
    svg.appendChild(svgElement("text", { x: 506, y: 126, "text-anchor": "end" }, dateLabel(last.date)));
  }

  function buildHeartRange(heartRows) {
    const svg = document.getElementById("heart-range");
    svg.replaceChildren();
    if (!heartRows.length) {
      svg.appendChild(svgElement("text", { x: 0, y: 80 }, "暂无心率记录"));
      return;
    }
    const values = heartRows.flatMap(item => [number(item.min_heart_rate), number(item.max_heart_rate)]).filter(value => value !== null);
    const [low, high] = extent(values);
    const span = high - low || 1;
    const y = value => 118 - ((value - low) / span) * 86;
    const x = index => 22 + (476 * index) / Math.max(1, heartRows.length - 1);
    const averagePoints = [];
    heartRows.forEach((item, index) => {
      const minimum = number(item.min_heart_rate);
      const maximum = number(item.max_heart_rate);
      const average = number(item.avg_heart_rate);
      if (minimum === null || maximum === null || average === null) return;
      const currentX = x(index);
      svg.appendChild(svgElement("line", {
        x1: currentX,
        x2: currentX,
        y1: y(maximum),
        y2: y(minimum),
        stroke: "rgba(239,68,68,0.34)",
        "stroke-width": 7,
        "stroke-linecap": "round",
      }));
      averagePoints.push([currentX, y(average)]);
    });
    if (averagePoints.length) {
      svg.appendChild(svgElement("path", { d: smoothPath(averagePoints), fill: "none", stroke: "#ef4444", "stroke-width": 3 }));
      averagePoints.forEach(([cx, cy]) => svg.appendChild(svgElement("circle", { cx, cy, r: 4, fill: "#ffffff", stroke: "#ef4444", "stroke-width": 3 })));
    }
  }

  function renderSleep(latestSleep) {
    const deep = number(latestSleep.deep_sleep_minutes) || 0;
    const rem = number(latestSleep.rem_sleep_minutes) || 0;
    const light = number(latestSleep.light_sleep_minutes) || 0;
    const total = deep + rem + light;
    text("sleep-total", minutesLabel(total));
    text("deep-value", `${integer(deep)} 分`);
    text("rem-value", `${integer(rem)} 分`);
    text("light-value", `${integer(light)} 分`);
    document.getElementById("sleep-deep").style.width = total ? `${(deep / total) * 100}%` : "0%";
    document.getElementById("sleep-rem").style.width = total ? `${(rem / total) * 100}%` : "0%";
    document.getElementById("sleep-light").style.width = total ? `${(light / total) * 100}%` : "0%";
  }

  function reflection(data, latestStep, latestSleep, latestDaily, baseline, latestHeart) {
    const sleepMinutes = number(latestSleep.total_minutes);
    const personalNeedHours = number((baseline.sleep || {}).personal_sleep_need);
    const latestSamples = number(latestHeart.sample_count);
    if (latestSamples !== null && latestSamples < 18) {
      text("reflection-title", "今天的节律还在累积");
      text("reflection-copy", "目前的活动和心率只代表今天已经记录到的部分。晚一点同步后，再看会更完整。");
      return;
    }
    if (sleepMinutes !== null && personalNeedHours !== null && sleepMinutes < personalNeedHours * 60 * 0.7) {
      text("reflection-title", "这次睡眠记录偏短一些");
      text("reflection-copy", "如果这不是完整的一晚，可以先确认戒指是否持续佩戴并完成同步；身体的趋势需要连续记录来慢慢看清。");
      return;
    }
    if (latestStep.steps !== undefined && rows((data.steps_7d || {}).data).length >= 5) {
      text("reflection-title", "这周的活动节奏已经有迹可循");
      text("reflection-copy", "可以把每天的高低当作生活节奏的线索，不必追求每一天都完全一样。");
      return;
    }
    if (latestDaily.is_outlier === true) {
      text("reflection-title", "这一天和近期节奏有些不同");
      text("reflection-copy", "先把它当作一个值得留意的变化；结合接下来几天的记录，会比单独看一次更有意义。");
    }
  }

  function render(report) {
    const data = report.data || {};
    const stepRows = rows((data.steps_7d || {}).data);
    const heartRows = rows((data.heart_rate_7d || {}).data);
    const sleepRows = rows((data.last_sleep || {}).data);
    const dailyRows = rows((data.daily_summary || {}).data);
    const baseline = data.baseline && typeof data.baseline === "object" ? data.baseline : {};
    const latestStep = latest(stepRows);
    const latestHeart = latest(heartRows);
    const latestSleep = latest(sleepRows);
    const latestDaily = latest(dailyRows);
    const recovery = latestDaily.stress_recovery && typeof latestDaily.stress_recovery === "object" ? latestDaily.stress_recovery : {};
    const latestDates = [latestStep.date, latestHeart.date, latestSleep.date, latestDaily.date].filter(Boolean).sort();
    const latestDate = latestDates.length ? latestDates[latestDates.length - 1] : null;
    const firstDates = [stepRows[0]?.date, heartRows[0]?.date, sleepRows[0]?.date, dailyRows[0]?.date].filter(Boolean).sort();
    const firstDate = firstDates.length ? firstDates[0] : latestDate;
    const latestSleepMinutes = number(latestSleep.total_minutes);
    const latestHrv = number(recovery.avg_hrv);
    const latestRestingHeart = number(recovery.resting_hr);
    const latestSteps = number(latestStep.steps);

    text("region-label", report.region === "cn" ? "芙洛怡中国 · 本地报告" : "FLOEVA GLOBAL · LOCAL REPORT");
    text("date-range", firstDate && latestDate ? `${dateLabel(firstDate)} — ${dateLabel(latestDate)} · BODY RHYTHM` : "BODY RHYTHM");
    text("latest-date", latestDate ? dateLabel(latestDate, true) : "身体近况");
    text("coverage-label", `${stepRows.length}/7 天活动 · ${heartRows.length}/7 天心率`);
    text("coverage-mini", `${Math.max(stepRows.length, heartRows.length)} / 7 天`);
    text("hero-steps", latestSteps === null ? "—" : integer(latestSteps));
    text("hero-sleep", latestSleepMinutes === null ? "—" : minutesLabel(latestSleepMinutes, true));
    text("hero-hrv", latestHrv === null ? "—" : integer(latestHrv));
    text("primary-sleep", decimalHours(latestSleepMinutes));
    text("resting-heart-rate", integer(latestRestingHeart));
    text("latest-hrv", integer(latestHrv));
    text("latest-steps", integer(latestSteps));
    text("baseline-days", integer(baseline.days_of_data));

    const stepSummary = data.steps_7d && typeof data.steps_7d.summary === "object" ? data.steps_7d.summary : {};
    const stepAverage = number(stepSummary.avg_steps_per_day);
    text("steps-average", stepAverage === null ? "未记录" : `${integer(stepAverage)} 步`);
    const minimumHeart = number(latestHeart.min_heart_rate);
    const averageHeart = number(latestHeart.avg_heart_rate);
    const maximumHeart = number(latestHeart.max_heart_rate);
    text("heart-latest", [minimumHeart, averageHeart, maximumHeart].every(value => value !== null) ? `${minimumHeart}–${averageHeart}–${maximumHeart}` : "未记录");

    const today = new Date();
    const todayString = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    const sampleCount = number(latestHeart.sample_count);
    const partial = latestDate === todayString && (sampleCount === null || sampleCount < 18);
    text("data-status", partial ? "今日累积" : "已记录");
    if (partial) {
      text("hero-caption", "今天的活动与心率仍在累积；先把它看作身体正在写下的一页，而不是一天的最终结论。");
    } else if (Math.max(stepRows.length, heartRows.length) >= 5) {
      text("hero-caption", "最近几天的活动、心率与睡眠已经连成一段节律。高低变化是生活留下的形状，不是好坏标签。");
    }

    buildLandscape(stepRows, heartRows, sleepRows);
    buildStepsSpark(stepRows, (baseline.activity || {}).daily_steps_7d);
    buildHeartRange(heartRows);
    renderSleep(latestSleep);
    reflection(data, latestStep, latestSleep, latestDaily, baseline, latestHeart);

    const descriptionParts = [];
    if (stepRows.length) descriptionParts.push(`步数 ${stepRows.length}/7 天`);
    if (heartRows.length) descriptionParts.push(`心率 ${heartRows.length}/7 天`);
    if (sleepRows.length) descriptionParts.push(`睡眠 ${sleepRows.length} 条`);
    document.getElementById("landscape-desc").textContent = descriptionParts.length
      ? `近七天数据覆盖：${descriptionParts.join("，")}。`
      : "当前没有足够的健康数据可生成节律地形。";
  }

  async function start() {
    try {
      const response = await fetch("./report.json", { cache: "no-store", credentials: "same-origin" });
      if (!response.ok) throw new Error("report unavailable");
      const report = await response.json();
      if (!report || report.version !== 1 || !report.data || typeof report.data !== "object") {
        throw new Error("invalid report");
      }
      render(report);
      loading.hidden = true;
      canvas.hidden = false;
    } catch (error) {
      loading.hidden = true;
      errorState.hidden = false;
    }
  }

  start();
})();
