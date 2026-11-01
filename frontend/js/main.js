// =====================================================================================
// СБОРКА СТРАНИЦЫ
// Порядок работы:
//   1) ставим тему из адреса страницы (?theme=dark, ?brand=sber);
//   2) загружаем посты (getStations) и рисуем фильтры, плашки, KPI, карту, таблицу;
//   3) загружаем прогнозы выбранного поста и рисуем графики.
// Всё, что выбрал пользователь, хранится в объекте state. Любое действие меняет state
// и вызывает перерисовку нужных блоков (функции render...).
// =====================================================================================

const DEFAULT_STATION = 'khabarovsk';       // пост, прогноз которого открыт при загрузке
const FORECAST_KPI_HORIZONS = [1, 7, 14];   // через сколько суток показываем карточки под графиком
const BRANDS = ['sber', 'alfa', 'vtb', 'gpb', 'rshb', 'sovcom'];   // темы банков из tokens.css

// Фильтры: Set выбранных значений. Пустой Set = «Все» (фильтр не применяется).
// Так один клик по чипу сразу оставляет нужную реку или округ, не нужно выключать остальные.
const state = {
  data: null,                        // ответ getStations(): { updated_at, next_update_at, stations }
  okrugs: new Set(),                 // выбранные округа
  rivers: new Set(),                 // выбранные реки
  statuses: new Set(),               // выбранные статусы
  selectedId: DEFAULT_STATION,       // пост, чей прогноз показан
  forecast: null,                    // прогнозы выбранного поста (нужны блоку бизнес-выводов)
  seasonal: null,
};

const WARNING_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">
  <path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4"/><path d="M12 17v.5"/></svg>`;
const INFO_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">
  <circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.5v.5"/></svg>`;

// ---------- Тема ----------
// Возвращает true для тёмной темы (карте нужна тёмная подложка)
function applyThemeFromUrl() {
  const params = new URLSearchParams(location.search);
  const isDark = params.get('theme') === 'dark';
  if (isDark) document.documentElement.dataset.theme = 'dark';
  if (BRANDS.includes(params.get('brand'))) document.documentElement.dataset.brand = params.get('brand');
  return isDark;
}

// ---------- Отбор постов ----------
// Проходит ли значение фильтр: пустой набор = «Все»
function matches(set, value) {
  return set.size === 0 || set.has(value);
}

// Посты выбранных округов и рек. По ним считаем KPI, распределение и бизнес-выводы:
// фильтр по статусу к счётчикам не применяем, иначе они теряют смысл.
function stationsInArea() {
  return state.data.stations.filter((s) => matches(state.okrugs, s.okrug) && matches(state.rivers, s.river));
}

// Посты после всех фильтров — для карты, таблицы и выгрузки в Excel
function visibleStations() {
  return stationsInArea().filter((s) => matches(state.statuses, s.status));
}

// Подпись выбранной территории: «ДФО · р. Амур», «все округа»
function areaLabel() {
  const okrugs = state.okrugs.size ? [...state.okrugs].join(', ') : 'все округа';
  return state.rivers.size ? `${okrugs} · р. ${[...state.rivers].join(', ')}` : okrugs;
}

// Запас до опасного уровня, см: «+34» — порог уже превышен, «−74» — до порога ещё 74 см
function marginToDanger(station) {
  return station.level === null ? null : station.level - station.thresholds.danger;
}

// Сортировка как в макете: сначала самые опасные статусы, внутри статуса — кто ближе к порогу
function sortBySeverity(stations) {
  return [...stations].sort((a, b) =>
    STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status)
    || (marginToDanger(b) ?? -Infinity) - (marginToDanger(a) ?? -Infinity));
}

// ---------- Загрузка данных ----------
async function loadAll() {
  const button = document.getElementById('btn-refresh');
  const dateInput = document.getElementById('filter-date');
  button.disabled = true;
  try {
    state.data = await getStations(dateInput.value);

    // Статус считаем один раз и запоминаем прямо в объекте поста
    state.data.stations.forEach((s) => { s.status = getStatus(s.level, s.thresholds); });

    // При первой загрузке подставляем время среза в поле даты
    if (!dateInput.value) dateInput.value = state.data.updated_at.slice(0, 16);

    renderFilters();
    renderHeader();
    renderStations(true);
    await selectStation(state.selectedId, false);
  } catch (error) {
    console.error(error);
    document.getElementById('snapshot-info').textContent = `Не удалось загрузить данные: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

// ---------- Боковая панель: фильтры ----------
// Чип = кнопка-переключатель. aria-pressed хранит состояние (его же использует CSS для подсветки).
// Чип «Все» имеет пустое значение data-value="".
function chip(content, pressed, value) {
  return `<button type="button" class="u-chip" aria-pressed="${pressed}" data-value="${escapeHtml(value)}">${content}</button>`;
}

// Группа чипов: «Все» + по чипу на каждое значение
function chipGroup(allLabel, values, selected, content = escapeHtml) {
  return chip(allLabel, selected.size === 0, '')
    + values.map((v) => chip(content(v), selected.has(v), v)).join('');
}

// Реки, которые есть в выбранных округах (список рек зависит от фильтра округов)
function riversInOkrugs() {
  const stations = state.data.stations.filter((s) => matches(state.okrugs, s.okrug));
  return [...new Set(stations.map((s) => s.river))];
}

function renderFilters() {
  // Если выбранная река пропала из списка (сменили округ) — убираем её из фильтра
  const rivers = riversInOkrugs();
  state.rivers.forEach((r) => { if (!rivers.includes(r)) state.rivers.delete(r); });

  const okrugs = [...new Set(state.data.stations.map((s) => s.okrug))];
  document.getElementById('filter-okrug').innerHTML = chipGroup('Все', okrugs, state.okrugs);
  document.getElementById('filter-river').innerHTML = chipGroup('Все реки', rivers, state.rivers);
  document.getElementById('filter-status').innerHTML =
    chipGroup('Все статусы', STATUS_ORDER, state.statuses, (st) => glyph(st) + STATUSES[st].label);
}

// Клик по чипу: «Все» сбрасывает фильтр, остальные чипы включаются и выключаются.
// Если выбрали все значения по одному — это то же самое, что «Все».
function toggleFilter(set, value, allValues) {
  if (value === '') set.clear();
  else if (set.has(value)) set.delete(value);
  else set.add(value);
  if (set.size === allValues.length) set.clear();
}

// Если выбранный пост скрыт фильтрами — открываем прогноз самого опасного из показанных,
// иначе прогноз и бизнес-выводы будут про пост, которого нет на карте и в таблице
function keepSelectionVisible() {
  const visible = visibleStations();
  if (visible.length === 0 || visible.some((s) => s.id === state.selectedId)) return false;
  selectStation(sortBySeverity(visible)[0].id, false);
  return true;
}

// ---------- Шапка ----------
function renderHeader() {
  const { updated_at, next_update_at, stations } = state.data;
  const active = stations.filter((s) => s.status !== 'nodata').length;
  document.getElementById('snapshot-info').textContent =
    `Срез на ${formatDate(updated_at)} ${formatTime(updated_at)} МСК · ${active} ${plural(active, 'активный пост', 'активных поста', 'активных постов')}`;
  document.getElementById('update-info').innerHTML =
    `Последний сбор: ${formatDate(updated_at)} ${formatTime(updated_at)} МСК<br>Следующий: ${formatTime(next_update_at)} МСК`;
}

// ---------- Все блоки, которые зависят от фильтров ----------
// fitView — подогнать масштаб карты под показанные посты
function renderStations(fitView) {
  renderAlerts();
  renderKpis();
  renderDistribution();
  renderTable();
  renderMap(visibleStations(), state.selectedId, (id) => selectStation(id, true), fitView);
}

// Красная плашка на каждый пост с опасным уровнем
function renderAlerts() {
  const dangerous = stationsInArea().filter((s) => s.status === 'danger');
  document.getElementById('alerts').innerHTML = dangerous.map((s) => `
    <div class="u-callout u-callout--danger" role="alert">
      ${WARNING_ICON}
      <span><b>${escapeHtml(s.name)}, р. ${escapeHtml(s.river)}: опасный уровень.</b>
      Превышение порога на ${formatLevel(marginToDanger(s))} см.
      Рекомендуется активировать план непрерывности для объектов в зоне.</span>
    </div>`).join('');
}

// Одна KPI-карточка: подпись, крупное число, пояснение
function kpiCard(label, value, note, isAlert = false) {
  return `
    <div class="u-kpi${isAlert ? ' u-kpi--alert' : ''}">
      <div class="u-kpi__label overline muted">${label}</div>
      <div class="u-kpi__value">${value}</div>
      <div class="caption muted">${note}</div>
    </div>`;
}

function renderKpis() {
  const list = stationsInArea();
  const withStatus = (st) => list.filter((s) => s.status === st);
  const names = (stations) => stations.map((s) => escapeHtml(s.name)).join(', ') || '—';

  const normal = withStatus('normal'), watch = withStatus('watch');
  const flood = withStatus('flood'), danger = withStatus('danger'), nodata = withStatus('nodata');
  const percent = list.length ? Math.round(normal.length / list.length * 100) : 0;
  const dangerNote = danger
    .map((s) => `${escapeHtml(s.name)}, ${formatSigned(marginToDanger(s))} см к порогу`).join('; ') || '—';

  document.getElementById('kpi-row').innerHTML = [
    kpiCard('Всего постов', list.length,
      `обновлено ${formatTime(state.data.updated_at)} МСК` + (nodata.length ? ` · без данных: ${nodata.length}` : '')),
    kpiCard(glyph('normal') + 'Норма', normal.length, `${percent} %`),
    kpiCard(glyph('watch') + 'Критический', watch.length, names(watch)),
    kpiCard(glyph('flood') + 'Выход на пойму', flood.length, names(flood)),
    kpiCard(glyph('danger') + 'Опасный', danger.length, dangerNote, danger.length > 0),
  ].join('');
}

// Полоса-распределение (доля каждого статуса) и список «статус — количество»
function renderDistribution() {
  const list = stationsInArea();
  const count = (st) => list.filter((s) => s.status === st).length;

  // ширина сегмента пропорциональна числу постов: flex-grow = количество
  document.getElementById('dist-bar').innerHTML = ['normal', 'watch', 'flood', 'danger', 'nodata']
    .filter((st) => count(st) > 0)
    .map((st) => `<span class="${st}" style="flex-grow:${count(st)}" title="${STATUSES[st].label}: ${count(st)}"></span>`)
    .join('');

  document.getElementById('dist-list').innerHTML = STATUS_ORDER
    .filter((st) => count(st) > 0)
    .map((st) => `<li>${badge(st)}<span class="num">${count(st)}</span></li>`).join('');

  document.getElementById('dist-sub').textContent =
    `${list.length} ${plural(list.length, 'пост', 'поста', 'постов')} · ${areaLabel()}`;
}

// ---------- Таблица ----------
function renderTable() {
  const rows = sortBySeverity(visibleStations()).map((s) => `
    <tr tabindex="0" data-id="${s.id}" class="${s.id === state.selectedId ? 'is-selected' : ''}">
      <td><div class="body-strong">${escapeHtml(s.name)}</div><div class="caption muted">р. ${escapeHtml(s.river)}</div></td>
      <td>${escapeHtml(s.okrug)}</td>
      <td>${badge(s.status)}</td>
      <td class="num">${formatLevel(s.level)}</td>
      <td class="num">${formatSigned(marginToDanger(s))}</td>
      <td class="caption muted">${formatDate(s.measured_at)}</td>
    </tr>`);

  document.getElementById('stations-body').innerHTML = rows.join('')
    || '<tr><td colspan="6" class="muted">Нет постов под выбранные фильтры</td></tr>';
}

// ---------- Выбор поста: заголовок, графики прогноза ----------
async function selectStation(id, scrollToForecast) {
  state.selectedId = id;
  renderTable();                                                        // подсветить строку
  renderMap(visibleStations(), id, (sid) => selectStation(sid, true), false);   // и маркер

  const station = state.data.stations.find((s) => s.id === id);
  if (!station) return;                                                 // такого поста нет в данных
  document.getElementById('forecast-title').textContent =
    `Прогноз уровня воды · ${station.name}, р. ${station.river}`;
  if (scrollToForecast) document.getElementById('forecast-card').scrollIntoView({ behavior: 'smooth' });

  let forecast, seasonal;
  try {
    [forecast, seasonal] = await Promise.all([getForecast(id), getSeasonal(id)]);
  } catch (error) {
    console.error(error);
    if (state.selectedId === id) showForecastError(station, error);
    return;
  }
  // Пока ждали ответ, пользователь мог выбрать другой пост — тогда этот ответ уже не нужен
  if (state.selectedId !== id) return;

  state.forecast = forecast;
  state.seasonal = seasonal;
  renderForecast(station, forecast);
  renderSeasonal(station, seasonal);
  renderRisk(station, forecast);
  updateBusiness();
}

// Прогноз не загрузился: вместо графиков — сообщение об ошибке, данные прошлого поста убираем
function showForecastError(station, error) {
  state.forecast = null;
  state.seasonal = null;
  document.getElementById('forecast-sub').textContent = '';
  document.getElementById('forecast-kpis').innerHTML = '';
  document.getElementById('seasonal-sub').textContent = '';
  document.getElementById('seasonal-note').hidden = true;
  const text = `Не удалось загрузить прогноз для поста «${station.name}»: ${error.message}`;
  showChartMessage('forecast-chart', text);
  showChartMessage('seasonal-chart', text);
  renderRisk(station, null);
  updateBusiness();
}

// Бизнес-выводы (js/business.js) по выбранной территории и прогнозу выбранного поста
function updateBusiness() {
  const station = state.data.stations.find((s) => s.id === state.selectedId);
  renderBusiness(stationsInArea(), areaLabel(), station, state.forecast, state.seasonal);
}

function renderForecast(station, fc) {
  const kpis = document.getElementById('forecast-kpis');
  if (!fc) {
    document.getElementById('forecast-sub').textContent = '';
    kpis.innerHTML = '';
    showChartMessage('forecast-chart', `Краткосрочный прогноз для поста «${station.name}» пока не рассчитывается.`);
    return;
  }

  document.getElementById('forecast-sub').textContent = `${fc.model}: ${fc.model_note}`;
  document.getElementById('forecast-band-label').textContent = fc.interval_label;
  drawForecastChart(fc, station.thresholds, FORECAST_KPI_HORIZONS);

  // Карточки «через N дней»: прогноз, коридор и статус по верхней границе коридора
  kpis.innerHTML = fc.forecast
    .filter((p) => FORECAST_KPI_HORIZONS.includes(p.horizon))
    .map((p) => {
      const upper = getStatus(p.level_high, station.thresholds);
      return kpiCard(
        `Через ${p.horizon} ${plural(p.horizon, 'день', 'дня', 'дней')} · ${formatDayMonth(p.date)}`,
        `${formatLevel(p.level)} см`,
        `${fc.interval_label}: ${formatLevel(p.level_low)}–${formatLevel(p.level_high)} см · верхняя граница: ${STATUSES[upper].short.toLowerCase()}`,
      );
    }).join('');
}

function renderSeasonal(station, seas) {
  const note = document.getElementById('seasonal-note');
  if (!seas) {
    document.getElementById('seasonal-sub').textContent = '';
    note.hidden = true;
    showChartMessage('seasonal-chart', `Сезонный прогноз для поста «${station.name}» пока не рассчитывается.`);
    return;
  }

  document.getElementById('seasonal-sub').textContent = `${seas.model}: ${seas.model_note}`;
  drawSeasonalChart(seas, station.thresholds);

  // Вывод под графиком: дойдёт ли ожидаемый пик до поймы
  const peak = seas.seasonal.reduce((max, p) => (p.level > max.level ? p : max));
  const t = station.thresholds;
  const text = peak.level >= t.flood
    ? `<b>Ожидается выход на пойму.</b> Пик сезонного прогноза: около ${formatLevel(peak.level)} см к ${formatDate(peak.date)}.`
    : `Выход на пойму в ближайший год не ожидается. Пик сезонного прогноза: около ${formatLevel(peak.level)} см к ${formatDate(peak.date)}, `
      + (peak.level >= t.watch ? 'выше порога готовности.' : 'ниже порога готовности.');
  note.className = peak.level >= t.flood ? 'u-callout u-callout--danger' : 'u-callout';
  note.innerHTML = `${INFO_ICON}<span>${text}</span>`;
  note.hidden = false;
}

// ---------- «Ближайший риск» ----------
// Берём прогноз выбранного поста и ищем первый день, когда верхняя граница коридора
// дойдёт до следующего порога (выше текущего статуса поста).
function renderRisk(station, fc) {
  const textEl = document.getElementById('risk-text');
  const noteEl = document.getElementById('risk-note');
  if (!fc) {
    textEl.textContent = `${station.name}: прогноз не рассчитывается`;
    noteEl.textContent = 'выберите пост с прогнозом на карте или в таблице';
    return;
  }

  const crossing = firstCrossing(station, fc.forecast);
  if (crossing) {
    const { key, point } = crossing;
    textEl.textContent = `${station.name}: ${STATUSES[key].label.toLowerCase()} через ${point.horizon} ${plural(point.horizon, 'день', 'дня', 'дней')}`;
    noteEl.textContent = `${formatDate(point.date)}, по верхней границе коридора (${fc.interval_label.toLowerCase()})`;
    return;
  }
  const days = fc.forecast.length;
  textEl.textContent = `${station.name}: пороги не превышаются`;
  noteEl.textContent = `в ближайшие ${days} ${plural(days, 'сутки', 'суток', 'суток')}, по верхней границе коридора`;
}

// ---------- Выгрузка таблицы ----------
// Формат CSV открывается в Excel. Когда бэкенд научится отдавать .xlsx — заменить на ссылку на API.
function csvCell(value) {
  const text = String(value ?? '');
  return /[;"\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function exportCsv() {
  if (!state.data) return;
  const header = ['Пост', 'Река', 'Округ', 'Статус', 'Уровень, см', 'До опасного, см',
    'Порог готовности, см', 'Порог поймы, см', 'Опасный порог, см', 'Дата замера'];
  const rows = sortBySeverity(visibleStations()).map((s) => [
    s.name, s.river, s.okrug, STATUSES[s.status].label, s.level, marginToDanger(s),
    s.thresholds.watch, s.thresholds.flood, s.thresholds.danger, formatDate(s.measured_at),
  ]);
  // Excel в русской локали ждёт разделитель «;» и метку кодировки UTF-8 (BOM) в начале файла
  const csv = '﻿' + [header, ...rows].map((row) => row.map(csvCell).join(';')).join('\r\n');

  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  link.download = `uroven_${state.data.updated_at.slice(0, 10)}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

// ---------- Запуск ----------
function init() {
  initMap(applyThemeFromUrl());
  renderMapLegend();
  document.getElementById('demo-badge').hidden = !USE_MOCK;   // метка «демонстрационные данные»

  // Клики по чипам ловим на контейнере: чипы перерисовываются, а обработчик остаётся один.
  // allValues — все значения фильтра (нужны, чтобы понять, что выбрано «всё»)
  const filters = [
    ['filter-okrug', state.okrugs, () => new Set(state.data.stations.map((s) => s.okrug))],
    ['filter-river', state.rivers, () => riversInOkrugs()],
    ['filter-status', state.statuses, () => STATUS_ORDER],
  ];
  filters.forEach(([elementId, set, allValues]) => {
    document.getElementById(elementId).addEventListener('click', (event) => {
      const button = event.target.closest('.u-chip');
      if (!button || !state.data) return;
      toggleFilter(set, button.dataset.value, [...allValues()]);
      renderFilters();
      renderStations(true);
      if (!keepSelectionVisible()) updateBusiness();   // при смене поста выводы обновит selectStation
    });
  });

  initBusiness();

  // Строка таблицы: клик мышью или Enter/пробел с клавиатуры
  const tbody = document.getElementById('stations-body');
  tbody.addEventListener('click', (event) => {
    const row = event.target.closest('tr[data-id]');
    if (row) selectStation(row.dataset.id, true);
  });
  tbody.addEventListener('keydown', (event) => {
    const row = event.target.closest('tr[data-id]');
    if (row && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      selectStation(row.dataset.id, true);
    }
  });

  document.getElementById('btn-refresh').addEventListener('click', loadAll);
  document.querySelectorAll('.js-export').forEach((button) => button.addEventListener('click', exportCsv));

  loadAll();
}

init();
