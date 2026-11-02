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
  forecastData: null,                // ответ getForecast(): факт и прогнозы всех моделей выбранного поста
  seasonalData: null,                // ответ getSeasonal()
  backtestData: null,                // проверка: последний прогноз моделей с погодой и что было на самом деле
  forecastKey: null,                 // выбранная модель краткосрочного прогноза; null — первая (основная)
  backtestKey: null,                 // выбранная модель в проверке
  seasonalKey: null,                 // выбранная модель сезонного прогноза
  forecast: null,                    // прогноз выбранной модели (нужен «Ближайшему риску» и бизнес-выводам)
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

    // При первой загрузке подставляем время среза в поле даты; выбрать можно только даты, на которые есть замеры
    if (!dateInput.value) dateInput.value = state.data.updated_at.slice(0, 16);
    if (state.data.available_from) dateInput.min = `${state.data.available_from}T00:00`;
    if (state.data.available_to) dateInput.max = `${state.data.available_to}T23:59`;
    document.getElementById('demo-badge').hidden = !isMockData();   // метка «сохранённый срез»
    // В сохранённых данных срез один: дату выбрать нельзя, пока не подключён бэкенд
    dateInput.disabled = isMockData();

    renderFilters();
    renderHeader();
    renderStations(true);
    await selectStation(state.selectedId, false);
  } catch (error) {
    console.error('Не удалось загрузить список постов:', error);
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
  // Сбор по расписанию пока не настроен (next_update_at = null): вместо него показываем дату самого свежего замера
  const latest = stations.map((s) => s.measured_at).filter(Boolean).sort().at(-1);
  document.getElementById('update-info').innerHTML =
    `Последний сбор: ${formatDate(updated_at)} ${formatTime(updated_at)} МСК<br>`
    + (next_update_at ? `Следующий: ${formatTime(next_update_at)} МСК` : `Самый свежий замер: ${formatDate(latest)}`);
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

  // Прогнозы независимы: если один не загрузился, остальные всё равно показываем
  const at = document.getElementById('filter-date').value;
  const [forecastResult, backtestResult, seasonalResult] = await Promise.allSettled(
    [getForecast(id, at), getBacktest(id), getSeasonal(id, at)]);
  // Пока ждали ответ, пользователь мог выбрать другой пост — тогда этот ответ уже не нужен
  if (state.selectedId !== id) return;

  state.forecastData = forecastResult.status === 'fulfilled' ? forecastResult.value : null;
  state.backtestData = backtestResult.status === 'fulfilled' ? backtestResult.value : null;
  state.seasonalData = seasonalResult.status === 'fulfilled' ? seasonalResult.value : null;
  if (forecastResult.status === 'fulfilled') renderForecast(station);
  else showForecastError(station, 'forecast', forecastResult.reason);
  if (backtestResult.status === 'rejected') {
    console.error(`Не загружена проверка прогноза для поста ${station.id}:`, backtestResult.reason);
  }
  renderBacktest(station);
  if (seasonalResult.status === 'fulfilled') renderSeasonal(station);
  else showForecastError(station, 'seasonal', seasonalResult.reason);
  renderRisk(station, state.forecast);
  updateBusiness();
}

// Прогноз не загрузился: вместо графика — сообщение об ошибке, подписи прошлого поста убираем.
// kind — 'forecast' (краткосрочный) или 'seasonal' (сезонный)
function showForecastError(station, kind, error) {
  const label = kind === 'forecast' ? 'краткосрочный' : 'сезонный';
  console.error(`Не загружен ${label} прогноз для поста ${station.id}:`, error);
  state[kind] = null;
  document.getElementById(`${kind}-sub`).textContent = '';
  document.getElementById(`${kind}-models`).innerHTML = '';
  document.getElementById(`${kind}-pending`).hidden = true;
  if (kind === 'forecast') {
    document.getElementById('forecast-kpis').innerHTML = '';
  } else {
    document.getElementById('seasonal-note').hidden = true;
  }
  showChartMessage(`${kind}-chart`, `Не удалось загрузить ${label} прогноз для поста «${station.name}»: ${error.message}`);
}

// Бизнес-выводы (js/business.js) по выбранной территории и прогнозу выбранного поста
function updateBusiness() {
  const station = state.data.stations.find((s) => s.id === state.selectedId);
  renderBusiness(stationsInArea(), areaLabel(), station, state.forecast, state.seasonal);
}

// ---------- Выбор модели ----------
// Модель с кодом key из ответа API; если её нет у этого поста — первая (основная). null — моделей нет.
function pickModel(data, key) {
  if (!data || data.models.length === 0) return null;
  return data.models.find((m) => m.key === key) || data.models[0];
}

// Кнопки моделей над графиком. Одна модель — кнопки не нужны.
function renderModelChips(elementId, models, selected) {
  document.getElementById(elementId).innerHTML = models.length > 1
    ? models.map((m) => chip(escapeHtml(m.model), m === selected, m.key)).join('')
    : '';
}

// Строка-пояснение над графиком: какие модели ещё обучаются на сервере (pending)
// или почему части моделей нет (note) — например, нет свежей погоды бассейна
function renderPending(elementId, pending, note = null) {
  const element = document.getElementById(elementId);
  const hasPending = pending && pending.length > 0;
  element.hidden = !hasPending && !note;
  element.textContent = hasPending
    ? `Ещё обучаются на сервере: ${pending.join(', ')}. Нажмите «Обновить данные» через пару минут.`
    : (note || '');
}

// Клик по кнопке модели. kind — 'forecast', 'backtest' или 'seasonal'. Выбор запоминаем: при смене поста
// остаётся та же модель, если она есть и у нового поста
function selectModel(kind, key) {
  const station = state.data.stations.find((s) => s.id === state.selectedId);
  if (kind === 'forecast') {
    state.forecastKey = key;
    renderForecast(station);
    renderRisk(station, state.forecast);
  } else if (kind === 'backtest') {
    state.backtestKey = key;
    renderBacktest(station);
    return;                          // бизнес-выводы считаются по прогнозу в будущее, проверка их не меняет
  } else {
    state.seasonalKey = key;
    renderSeasonal(station);
  }
  updateBusiness();
}

// ---------- Краткосрочный прогноз ----------
function renderForecast(station) {
  const data = state.forecastData;
  const kpis = document.getElementById('forecast-kpis');
  const fc = pickModel(data, state.forecastKey);
  state.forecast = fc;

  if (!data) {
    document.getElementById('forecast-sub').textContent = '';
    renderModelChips('forecast-models', [], null);
    renderPending('forecast-pending', []);
    kpis.innerHTML = '';
    // В тестовых данных прогноз есть только у Хабаровска — для остальных постов текст как в прототипе
    showChartMessage('forecast-chart', `По посту «${station.name}» нет замеров: прогноз пока не рассчитывается.`);
    return;
  }

  renderModelChips('forecast-models', data.models, fc);
  // Если моделей нет, причина — в подзаголовке; если есть, но не все, — строкой над графиком
  renderPending('forecast-pending', data.pending, fc ? data.note : null);
  document.getElementById('forecast-sub').textContent = fc
    ? `${fc.model}: ${fc.model_note}`
    : (data.note || 'Модели ещё обучаются, пока показан только факт.');
  document.getElementById('forecast-legend-model').hidden = !fc;
  document.getElementById('forecast-legend-band').hidden = !fc;
  document.getElementById('forecast-legend-others').hidden = data.models.length < 2;
  document.getElementById('forecast-legend-actual').hidden = data.actual.length === 0;
  if (fc) {
    document.getElementById('forecast-model-label').textContent = fc.model;
    document.getElementById('forecast-band-label').textContent = fc.interval_label;
  }
  drawForecastChart(data, fc, station.thresholds, FORECAST_KPI_HORIZONS);

  // Карточки «через N дней»: прогноз, коридор и статус по верхней границе коридора.
  // Если дата прогноза в прошлом, добавляем, сколько было на самом деле
  kpis.innerHTML = !fc ? '' : fc.forecast
    .filter((p) => FORECAST_KPI_HORIZONS.includes(p.horizon))
    .map((p) => {
      const upper = getStatus(p.level_high, station.thresholds);
      const actual = data.actual.find((a) => a.date === p.date);
      return kpiCard(
        `Через ${p.horizon} ${plural(p.horizon, 'день', 'дня', 'дней')} · ${formatDayMonth(p.date)}`,
        `${formatLevel(p.level)} см`,
        `${fc.interval_label}: ${formatLevel(p.level_low)}–${formatLevel(p.level_high)} см · верхняя граница: ${STATUSES[upper].short.toLowerCase()}`
          + (actual ? ` · было: ${formatLevel(actual.level)} см` : ''),
      );
    }).join('');
}

// ---------- Проверка: прогноз двухнедельной давности и что было ----------
// Прогноз всех моделей за 14 суток до последнего замера рядом с фактом за эти дни.
// Модели этих дней при обучении не видели, поэтому это честная проверка и сравнение моделей между собой
function renderBacktest(station) {
  const card = document.getElementById('backtest-card');
  const data = state.backtestData;
  const fc = pickModel(data, state.backtestKey);
  card.hidden = !fc;
  renderSkill(data, fc);
  if (!fc) return;

  renderModelChips('backtest-models', data.models, fc);
  document.getElementById('backtest-sub').textContent =
    `Прогноз от ${formatDate(data.today)}: как модели угадали следующие две недели. ${fc.model}: ${fc.model_note}`;
  document.getElementById('backtest-model-label').textContent = fc.model;
  document.getElementById('backtest-band-label').textContent = fc.interval_label;
  drawForecastChart(data, fc, station.thresholds, FORECAST_KPI_HORIZONS, 'backtest-chart');

  // Вывод текстом: насколько модель ошиблась через 1 / 7 / 14 суток
  const errors = fc.forecast
    .filter((p) => FORECAST_KPI_HORIZONS.includes(p.horizon))
    .map((p) => ({ point: p, actual: data.actual.find((a) => a.date === p.date) }))
    .filter((e) => e.actual)
    .map(({ point, actual }) => `через ${point.horizon} ${plural(point.horizon, 'сутки', 'суток', 'суток')} `
      + `прогноз ${formatLevel(point.level)} см, было ${formatLevel(actual.level)} см`);
  document.getElementById('backtest-note').textContent = errors.length
    ? `${fc.model}: ${errors.join('; ')}.`
    : 'Фактических замеров после даты прогноза пока нет.';
}

// ---------- Точность моделей ----------
// data — проверка (getBacktest), fc — выбранная в ней модель.
// Карточка видна, если хотя бы у двух моделей есть ошибки проверки — иначе сравнивать нечего
function renderSkill(data, fc) {
  const card = document.getElementById('skill-card');
  const models = data ? data.models.filter((m) => m.skill.length > 0) : [];
  card.hidden = models.length < 2 || !fc;
  if (card.hidden) return;

  document.getElementById('skill-model-label').textContent = fc.model;
  drawSkillChart(models, fc.key);

  // Вывод текстом для тех, кто графики не читает: ошибка выбранной модели на 1 и 14 сутки против инерционного
  const at = (m, h) => m.skill.find((p) => p.horizon === h);
  const lastHorizon = fc.skill.length ? fc.skill[fc.skill.length - 1].horizon : null;
  const naive = models.find((m) => m.key === 'naive');
  const note = document.getElementById('skill-note');
  if (!lastHorizon) {
    note.textContent = `Модель «${fc.model}» на проверке не оценивалась.`;
    return;
  }
  const own = `${fc.model} ошибается в среднем на ${formatLevel(at(fc, 1).mae)} см через сутки `
    + `и на ${formatLevel(at(fc, lastHorizon).mae)} см через ${lastHorizon} ${plural(lastHorizon, 'сутки', 'суток', 'суток')}`;
  note.textContent = naive && naive !== fc
    ? `${own}; инерционный прогноз — на ${formatLevel(at(naive, 1).mae)} и ${formatLevel(at(naive, lastHorizon).mae)} см.`
    : `${own}.`;
}

// ---------- Сезонный прогноз ----------
function renderSeasonal(station) {
  const data = state.seasonalData;
  const note = document.getElementById('seasonal-note');
  const seas = pickModel(data, state.seasonalKey);
  state.seasonal = seas;
  renderModelChips('seasonal-models', data ? data.models : [], seas);
  renderPending('seasonal-pending', data ? data.pending : []);

  if (!seas) {
    document.getElementById('seasonal-sub').textContent = '';
    note.hidden = true;
    showChartMessage('seasonal-chart', data
      ? 'Сезонные модели ещё обучаются на сервере.'
      : `Сезонный прогноз для поста «${station.name}» пока не рассчитывается.`);
    return;
  }

  document.getElementById('seasonal-sub').textContent = `${seas.model}: ${seas.model_note}`;
  document.getElementById('seasonal-model-label').textContent = seas.model;
  document.getElementById('seasonal-band-label').textContent = seas.interval_label;
  document.getElementById('seasonal-legend-others').hidden = data.models.length < 2;
  drawSeasonalChart(data, seas, station.thresholds);

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
  // Выше опасного порогов уже нет: firstCrossing ничего не найдёт, но писать «не превышаются» нельзя
  if (station.status === 'danger') {
    const last = fc.forecast[days - 1];
    textEl.textContent = `${station.name}: опасный уровень уже превышен`;
    noteEl.textContent = `на ${formatLevel(marginToDanger(station))} см; через ${days} ${plural(days, 'сутки', 'суток', 'суток')} `
      + `по прогнозу ${formatLevel(last.level)} см (${fc.model})`;
    return;
  }
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

  // Кнопки моделей над графиками: перерисовываем график, «Ближайший риск» и бизнес-выводы по выбранной модели
  document.getElementById('forecast-models').addEventListener('click', (event) => {
    const button = event.target.closest('.u-chip');
    if (button) selectModel('forecast', button.dataset.value);
  });
  document.getElementById('backtest-models').addEventListener('click', (event) => {
    const button = event.target.closest('.u-chip');
    if (button) selectModel('backtest', button.dataset.value);
  });
  document.getElementById('seasonal-models').addEventListener('click', (event) => {
    const button = event.target.closest('.u-chip');
    if (button) selectModel('seasonal', button.dataset.value);
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
