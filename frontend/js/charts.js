// =====================================================================================
// ГРАФИКИ (библиотека Plotly.js, https://plotly.com/javascript/)
// Один и тот же приём на графиках прогноза:
//   факт — сплошная тёмная линия, прогноз выбранной модели — цветная линия с закрашенным коридором,
//   прогнозы остальных моделей — тонкие серые линии, пороги поста — горизонтальные пунктиры
//   с подписью справа, дата прогноза — вертикальная линия.
// Цвета берём из tokens.css, поэтому графики сами подстраиваются под тему.
// =====================================================================================

// Значение CSS-переменной: cssVar('--chart-fact') -> '#24323c'
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Настройки Plotly: без панели инструментов, график тянется по ширине карточки, русские месяцы
const PLOT_CONFIG = { displayModeBar: false, responsive: true, locale: 'ru' };

// Цвет линии каждого порога. У «готовности» берём тёмно-жёлтый (-ink): светло-жёлтый не виден на белом.
const THRESHOLD_COLOR = { watch: '--status-watch-ink', flood: '--status-flood', danger: '--status-danger' };

// Общий вид осей и подсказок для всех графиков
function baseLayout() {
  return {
    margin: { l: 48, r: 96, t: 8, b: 32 },              // справа место под подписи порогов
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Golos Text, sans-serif', size: 11, color: cssVar('--ink-muted') },
    showlegend: false,                                   // легенда сделана в HTML над графиком
    hovermode: 'x unified',                              // одна подсказка на все линии в этот день
    hoverlabel: { bgcolor: cssVar('--surface'), bordercolor: cssVar('--border'), font: { color: cssVar('--ink') } },
    xaxis: { type: 'date', showgrid: false, linecolor: cssVar('--border'), fixedrange: true },
    yaxis: { gridcolor: cssVar('--chart-grid'), zeroline: false, fixedrange: true, ticksuffix: ' см' },
    shapes: [],
    annotations: [],
  };
}

// Добавляет в layout пороги поста: пунктирная линия + подпись «Пойма 470» справа от графика
function addThresholds(layout, thresholds) {
  ['watch', 'flood', 'danger'].forEach((key) => {
    const value = thresholds[key];
    layout.shapes.push({
      type: 'line', xref: 'paper', x0: 0, x1: 1, y0: value, y1: value,
      line: { color: cssVar(THRESHOLD_COLOR[key]), width: 1.25, dash: 'dot' },
    });
    layout.annotations.push({
      xref: 'paper', x: 1, xanchor: 'left', xshift: 6, y: value, yanchor: 'middle', showarrow: false,
      text: `${STATUSES[key].threshold} ${formatLevel(value)}`,
      font: { size: 11, color: cssVar('--ink') },
    });
  });
}

// Добавляет вертикальную линию «дата прогноза»: день последнего факта, от которого считается прогноз.
// Не «сегодня»: в сохранённых данных это может быть и прошлая дата
function addToday(layout, today) {
  layout.shapes.push({
    type: 'line', xref: 'x', x0: today, x1: today, yref: 'paper', y0: 0, y1: 1,
    line: { color: cssVar('--border-strong'), width: 1 },
  });
  layout.annotations.push({
    xref: 'x', x: today, xanchor: 'left', xshift: 4, yref: 'paper', y: 1, yanchor: 'top',
    text: 'дата прогноза', showarrow: false, font: { size: 11, color: cssVar('--ink') },
  });
}

// Диапазон оси Y: все значения + все пороги + небольшой запас, чтобы пороги всегда были видны
function yRange(values, thresholds) {
  const all = values.concat([thresholds.watch, thresholds.flood, thresholds.danger]);
  return [Math.min(...all) - 30, Math.max(...all) + 30];
}

// Две невидимые линии (нижняя и верхняя граница); fill: 'tonexty' закрашивает пространство между ними
function bandTraces(points, color) {
  const x = points.map((p) => p.date);
  return [
    { x, y: points.map((p) => p.level_low), mode: 'lines', line: { width: 0 }, hoverinfo: 'skip' },
    { x, y: points.map((p) => p.level_high), mode: 'lines', line: { width: 0 }, hoverinfo: 'skip',
      fill: 'tonexty', fillcolor: color },
  ];
}

// Вместо графика показывает текст (например, «прогноз для поста не рассчитывается»)
function showChartMessage(elementId, text) {
  const element = document.getElementById(elementId);
  Plotly.purge(element);
  element.innerHTML = `<div class="chart-empty">${escapeHtml(text)}</div>`;
}

// Рисует график, предварительно убрав сообщение-заглушку, если оно было
function drawPlot(elementId, traces, layout) {
  const element = document.getElementById(elementId);
  Plotly.purge(element);
  element.innerHTML = '';
  Plotly.newPlot(element, traces, layout, PLOT_CONFIG);
}

// Линия факта: сплошная тёмная
function factTrace(points) {
  return {
    name: 'Факт', x: points.map((p) => p.date), y: points.map((p) => p.level),
    mode: 'lines', line: { color: cssVar('--chart-fact'), width: 2 },
    hovertemplate: 'Факт: %{y:.0f} см<extra></extra>',
  };
}

// Прогнозы невыбранных моделей: тонкие серые линии без коридора. Цвет у всех один — выделена только выбранная
// модель, а названия остальных видны в подсказке при наведении.
function otherModelTraces(models, field, start) {
  return models.map((m) => {
    const points = start ? [start, ...m[field]] : m[field];
    return {
      name: m.model, x: points.map((p) => p.date), y: points.map((p) => p.level),
      mode: 'lines', line: { color: cssVar('--chart-other'), width: 1.25 },
      hovertemplate: `${escapeHtml(m.model)}: %{y:.0f} см<extra></extra>`,
    };
  });
}

// ---------- Краткосрочный прогноз ----------
// data — ответ getForecast(): history и actual [{date, level}], models [{key, model, forecast: [...]}]
// fc — выбранная модель из data.models (или null: тогда рисуем только факт)
// markHorizons — горизонты (сутки), которые отмечаем кружками; это те же дни, что в карточках под графиком
// elementId — где рисовать: 'forecast-chart' (прогноз) или 'backtest-chart' (проверка)
function drawForecastChart(data, fc, thresholds, markHorizons, elementId = 'forecast-chart') {
  const lastFact = data.history[data.history.length - 1];
  // Прогнозы и коридор начинаем от последнего факта, чтобы линии шли без разрыва
  const start = { date: lastFact.date, level: lastFact.level, level_low: lastFact.level, level_high: lastFact.level };
  const others = data.models.filter((m) => m !== fc);
  const points = fc ? [start, ...fc.forecast] : [];
  const marked = fc ? fc.forecast.filter((p) => markHorizons.includes(p.horizon)) : [];

  const traces = [
    ...(fc ? bandTraces(points, cssVar('--chart-band')) : []),
    ...otherModelTraces(others, 'forecast', start),
    factTrace(data.history),
  ];
  if (data.actual.length) {
    // Дата прогноза в прошлом: видно, что было на самом деле. Точки, а не сплошная линия, — чтобы не спутать
    // с фактом до прогноза, который модели знали
    traces.push({
      name: 'Факт после даты прогноза', x: [lastFact.date, ...data.actual.map((p) => p.date)],
      y: [lastFact.level, ...data.actual.map((p) => p.level)],
      mode: 'lines', line: { color: cssVar('--chart-fact'), width: 2, dash: 'dot' },
      hovertemplate: 'Было на самом деле: %{y:.0f} см<extra></extra>',
    });
  }
  if (fc) {
    traces.push({
      name: fc.model, x: points.map((p) => p.date), y: points.map((p) => p.level),
      customdata: points.map((p) => [p.level_low, p.level_high]),
      mode: 'lines', line: { color: cssVar('--chart-forecast'), width: 2.5, dash: 'dash' },
      hovertemplate: `${escapeHtml(fc.model)}: %{y:.0f} см (коридор %{customdata[0]:.0f}–%{customdata[1]:.0f})<extra></extra>`,
    }, {
      x: marked.map((p) => p.date), y: marked.map((p) => p.level), mode: 'markers', hoverinfo: 'skip',
      marker: { size: 8, color: cssVar('--surface'), line: { color: cssVar('--chart-forecast'), width: 2 } },
    });
  }

  const values = data.history.concat(data.actual).map((p) => p.level)
    .concat(points.map((p) => p.level_high), points.map((p) => p.level_low))
    .concat(...others.map((m) => m.forecast.map((p) => p.level)));
  const layout = baseLayout();
  layout.xaxis.tickformat = '%d %b';
  layout.yaxis.range = yRange(values, thresholds);
  addThresholds(layout, thresholds);
  addToday(layout, data.today);

  drawPlot(elementId, traces, layout);
}

// ---------- Сезонный прогноз ----------
// data — ответ getSeasonal(): fact [{date, level}], models [{key, model, seasonal: [...]}]
// seas — выбранная модель из data.models
function drawSeasonalChart(data, seas, thresholds) {
  const others = data.models.filter((m) => m !== seas);
  const traces = [
    ...bandTraces(seas.seasonal, cssVar('--chart-seasonal-band')),
    ...otherModelTraces(others, 'seasonal', null),
    factTrace(data.fact),
    {
      name: seas.model, x: seas.seasonal.map((p) => p.date), y: seas.seasonal.map((p) => p.level),
      customdata: seas.seasonal.map((p) => [p.level_low, p.level_high]),
      mode: 'lines', line: { color: cssVar('--chart-seasonal'), width: 2.5 },
      hovertemplate: `${escapeHtml(seas.model)}: %{y:.0f} см (коридор %{customdata[0]:.0f}–%{customdata[1]:.0f})<extra></extra>`,
    },
  ];

  const layout = baseLayout();
  layout.xaxis.tickformat = '%b %Y';
  layout.yaxis.range = yRange(
    data.fact.map((p) => p.level).concat(
      seas.seasonal.map((p) => p.level_high), seas.seasonal.map((p) => p.level_low),
      ...others.map((m) => m.seasonal.map((p) => p.level)),
    ),
    thresholds,
  );
  addThresholds(layout, thresholds);
  addToday(layout, data.today);

  drawPlot('seasonal-chart', traces, layout);
}

// ---------- Точность моделей ----------
// models — модели с ошибками проверки (skill: [{horizon, mae}]), selectedKey — выбранная на графике прогноза.
// Выбранная модель — бирюзовая и подписана справа, инерционный прогноз — серый пунктир (точка отсчёта),
// остальные — тонкие серые линии.
function drawSkillChart(models, selectedKey) {
  const ordered = [...models.filter((m) => m.key !== selectedKey), ...models.filter((m) => m.key === selectedKey)];
  const traces = ordered.map((m) => {
    const selected = m.key === selectedKey;
    const color = cssVar(selected ? '--chart-forecast' : '--chart-other');
    return {
      name: m.model, x: m.skill.map((p) => p.horizon), y: m.skill.map((p) => p.mae),
      mode: selected ? 'lines+markers' : 'lines',
      line: { color, width: selected ? 2.5 : 1.25, dash: m.key === 'naive' ? 'dot' : 'solid' },
      marker: { size: 8, color: cssVar('--surface'), line: { color, width: 2 } },
      hovertemplate: `${escapeHtml(m.model)}: %{y:.0f} см<extra></extra>`,
    };
  });

  const layout = baseLayout();
  layout.xaxis = { type: 'linear', dtick: 1, range: [0.6, 14.4], showgrid: false, linecolor: cssVar('--border'), fixedrange: true,
    title: { text: 'Через сколько суток', font: { size: 11 } } };
  layout.yaxis.rangemode = 'tozero';
  layout.margin.b = 44;
  layout.hovermode = 'x unified';
  // Подписи справа у последней точки: выбранная модель и инерционный прогноз
  ordered.filter((m) => m.key === selectedKey || m.key === 'naive').forEach((m) => {
    const last = m.skill[m.skill.length - 1];
    layout.annotations.push({
      x: last.horizon, y: last.mae, xanchor: 'left', xshift: 8, showarrow: false,
      text: m.key === 'naive' ? 'Инерционный' : escapeHtml(m.model),
      font: { size: 11, color: cssVar(m.key === selectedKey ? '--ink' : '--ink-muted') },
    });
  });

  drawPlot('skill-chart', traces, layout);
}
