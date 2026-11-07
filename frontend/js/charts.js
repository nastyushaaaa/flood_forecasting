// =====================================================================================
// ГРАФИКИ (библиотека Plotly.js, https://plotly.com/javascript/)
// Один и тот же приём на обоих графиках:
//   факт — сплошная тёмная линия, прогноз — пунктир, неопределённость — закрашенный коридор,
//   пороги поста — горизонтальные пунктиры с подписью справа, «сегодня» — вертикальная линия.
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

// Добавляет вертикальную линию «сегодня»
function addToday(layout, today) {
  layout.shapes.push({
    type: 'line', xref: 'x', x0: today, x1: today, yref: 'paper', y0: 0, y1: 1,
    line: { color: cssVar('--border-strong'), width: 1 },
  });
  layout.annotations.push({
    xref: 'x', x: today, xanchor: 'left', xshift: 4, yref: 'paper', y: 1, yanchor: 'top',
    text: 'сегодня', showarrow: false, font: { size: 11, color: cssVar('--ink') },
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

// ---------- Краткосрочный прогноз ----------
// fc — ответ getForecast(): history [{date, level}], forecast [{date, horizon, level, level_low, level_high}]
// markHorizons — горизонты (сутки), которые отмечаем кружками; это те же дни, что в карточках под графиком
function drawForecastChart(fc, thresholds, markHorizons) {
  const lastFact = fc.history[fc.history.length - 1];
  // Прогноз и коридор начинаем от последнего факта, чтобы линии шли без разрыва
  const start = { date: lastFact.date, level: lastFact.level, level_low: lastFact.level, level_high: lastFact.level };
  const points = [start, ...fc.forecast];
  const marked = fc.forecast.filter((p) => markHorizons.includes(p.horizon));

  const traces = [
    ...bandTraces(points, cssVar('--chart-band')),
    {
      name: 'Факт', x: fc.history.map((p) => p.date), y: fc.history.map((p) => p.level),
      mode: 'lines', line: { color: cssVar('--chart-fact'), width: 2 },
      hovertemplate: 'Факт: %{y:.0f} см<extra></extra>',
    },
    {
      name: 'Прогноз', x: points.map((p) => p.date), y: points.map((p) => p.level),
      customdata: points.map((p) => [p.level_low, p.level_high]),
      mode: 'lines', line: { color: cssVar('--chart-forecast'), width: 2, dash: 'dash' },
      hovertemplate: 'Прогноз: %{y:.0f} см (коридор %{customdata[0]:.0f}–%{customdata[1]:.0f})<extra></extra>',
    },
    {
      x: marked.map((p) => p.date), y: marked.map((p) => p.level), mode: 'markers', hoverinfo: 'skip',
      marker: { size: 8, color: cssVar('--surface'), line: { color: cssVar('--chart-forecast'), width: 2 } },
    },
  ];

  const layout = baseLayout();
  layout.xaxis.tickformat = '%d %b';
  layout.yaxis.range = yRange(points.map((p) => p.level_high).concat(fc.history.map((p) => p.level)), thresholds);
  addThresholds(layout, thresholds);
  addToday(layout, fc.today);

  drawPlot('forecast-chart', traces, layout);
}

// ---------- Сезонный прогноз ----------
// seas — ответ getSeasonal(): fact [{date, level}], seasonal [{date, level, level_low, level_high}]
function drawSeasonalChart(seas, thresholds) {
  const traces = [
    ...bandTraces(seas.seasonal, cssVar('--chart-seasonal-band')),
    {
      name: 'Факт', x: seas.fact.map((p) => p.date), y: seas.fact.map((p) => p.level),
      mode: 'lines', line: { color: cssVar('--chart-fact'), width: 2 },
      hovertemplate: 'Факт: %{y:.0f} см<extra></extra>',
    },
    {
      name: 'Ожидаемый ход', x: seas.seasonal.map((p) => p.date), y: seas.seasonal.map((p) => p.level),
      customdata: seas.seasonal.map((p) => [p.level_low, p.level_high]),
      mode: 'lines', line: { color: cssVar('--chart-seasonal'), width: 2 },
      hovertemplate: 'Ожидаемо: %{y:.0f} см (обычно %{customdata[0]:.0f}–%{customdata[1]:.0f})<extra></extra>',
    },
  ];

  const layout = baseLayout();
  layout.xaxis.tickformat = '%b %Y';
  layout.yaxis.range = yRange(
    seas.fact.map((p) => p.level).concat(seas.seasonal.map((p) => p.level_high), seas.seasonal.map((p) => p.level_low)),
    thresholds,
  );
  addThresholds(layout, thresholds);
  addToday(layout, seas.today);

  drawPlot('seasonal-chart', traces, layout);
}
