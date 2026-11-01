// =====================================================================================
// БИЗНЕС-ВЫВОДЫ ДЛЯ БАНКА
// Переводим уровни воды и прогноз на язык банка: какой уровень риска, что сделать
// с отделениями и кредитным портфелем, сколько можно потерять и что можно заработать.
// Данные на входе: посты выбранной территории (фильтры «округ» и «река») и прогнозы
// выбранного поста. Тексты рекомендаций лежат в ACTIONS, их можно править, не трогая расчёты.
// =====================================================================================

// Уровень риска для банка. status — какой цвет и значок статуса поста взять для бейджа
const RISK_LEVELS = {
  low:      { label: 'Низкий',      status: 'normal', headline: 'Паводковой угрозы для объектов банка нет.' },
  moderate: { label: 'Умеренный',   status: 'watch',  headline: 'Угрозы пока нет, но вода близко к порогам: пора готовиться.' },
  high:     { label: 'Высокий',     status: 'flood',  headline: 'Вероятен выход воды на пойму: объекты банка в низинах под угрозой.' },
  critical: { label: 'Критический', status: 'danger', headline: 'Опасный уровень воды: возможен ущерб имуществу банка и залогам.' },
};

const ACTIONS = {
  // Главное действие: одна фраза для руководства
  main: {
    low:      'плановый мониторинг, дополнительных мер не нужно.',
    moderate: 'предупредить региональный офис и проверить план непрерывности бизнеса.',
    high:     'подготовить отделения в пойме к закрытию и проверить страховку залогов в зоне подтопления.',
    critical: 'запустить план непрерывности бизнеса в регионе и начать работу с пострадавшими клиентами.',
  },
  // Операционный риск: отделения, банкоматы, сотрудники
  operations: {
    low: [
      'Сверить список отделений и банкоматов, которые стоят в пойме реки.',
      'Проверить, что план непрерывности бизнеса для региона актуален.',
    ],
    moderate: [
      'Предупредить региональный офис и службу безопасности о возможном паводке.',
      'Проверить резервное отделение и каналы связи на случай закрытия офисов в пойме.',
      'Следить за прогнозом ежедневно, назначить ответственного.',
    ],
    high: [
      'Сократить запас наличных в банкоматах и кассах в зоне подтопления, перенести инкассацию.',
      'Подготовить перевод сотрудников из отделений в пойме в соседние офисы или на удалённую работу.',
      'Поднять технику и документы с первых этажей, проверить резервное копирование.',
      'Подготовить сообщение клиентам о том, какие отделения будут работать.',
    ],
    critical: [
      'Запустить план непрерывности бизнеса: закрыть отделения в зоне подтопления, отключить банкоматы.',
      'Отправить клиентам SMS и push-уведомления о закрытых и работающих отделениях.',
      'Обеспечить безопасность сотрудников: эвакуация по плану МЧС.',
      'Фиксировать ущерб имуществу банка для страховой компании.',
    ],
  },
  // Кредитный риск: заёмщики и залоги
  credit: {
    low: [
      'Стандартный мониторинг портфеля.',
      'По новым кредитам под залог недвижимости в пойме требовать страхование от наводнения.',
    ],
    moderate: [
      'Выгрузить список залогов и заёмщиков с адресами в пойме реки.',
      'Проверить, что залоги в зоне застрахованы от наводнения и полисы действуют.',
      'Выделить заёмщиков, чей бизнес зависит от реки: сельское хозяйство, логистика, речной транспорт.',
    ],
    high: [
      'Выдавать кредиты под залог в зоне подтопления только со страховкой от наводнения.',
      'Связаться с крупными заёмщиками в зоне: есть ли у них план на случай паводка.',
      'Оценить возможные потери (раздел ниже) и при необходимости учесть их в резервах.',
    ],
    critical: [
      'Приостановить выдачу новых кредитов под залог в зоне подтопления до спада воды.',
      'Подготовиться к обращениям пострадавших за кредитными каникулами и реструктуризацией.',
      'После спада воды осмотреть и переоценить залоги.',
      'Досоздать резервы на возможные потери по заёмщикам в зоне бедствия.',
    ],
  },
  // Возможности: до паводка — продавать защиту, во время и после — поддерживать клиентов
  opportunities: {
    before: [
      'Предложить клиентам в пойме страхование имущества от наводнения до начала паводка: это комиссионный доход и защита залогов.',
      'Учитывать паводковый риск в цене кредитов и при выборе мест для новых отделений и банкоматов.',
      'Использовать данные мониторинга в отчётности о климатических рисках (рекомендации Банка России).',
    ],
    during: [
      'Запустить кредиты на восстановление жилья и бизнеса после паводка.',
      'Предложить пострадавшим клиентам отсрочку платежей: это удерживает клиентов и снижает просрочку.',
      'Быстрая помощь клиентам в беде укрепляет репутацию банка в регионе.',
    ],
  },
};

// Порог существенности для калькулятора: ожидаемые потери больше этой доли портфеля — повод действовать
const MATERIALITY = 0.01;

// Последние данные — калькулятор пересчитывает по ним при вводе в форму
let businessContext = null;

// ---------- Вероятности по коридору прогноза ----------
// Функция нормального распределения Φ(x) (приближение Абрамовица и Стиган, точность ~1e-7)
function normalCdf(x) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp(-x * x / 2);
  const tail = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - tail : tail;
}

// Вероятность, что уровень в этот день превысит порог.
// Коридор 80 % считаем интервалом от 10 до 90 %: верхняя граница = медиана + 1,28σ.
function pointExceedance(point, threshold) {
  const sigma = (point.level_high - point.level) / 1.2816;
  if (sigma <= 0) return point.level >= threshold ? 1 : 0;
  return 1 - normalCdf((threshold - point.level) / sigma);
}

// Вероятность превысить порог хотя бы в один из дней (берём самый опасный день).
// Если уровень уже выше порога — 1.
function exceedance(station, points, threshold) {
  if (station.level !== null && station.level >= threshold) return 1;
  return Math.max(0, ...points.map((p) => pointExceedance(p, threshold)));
}

// ---------- Оценка риска ----------
// area — посты территории, station — выбранный пост, fc и seas — его прогнозы (могут быть null)
function assessRisk(area, station, fc, seas) {
  const count = (st) => area.filter((s) => s.status === st).length;
  // Прогноз учитываем, только если выбранный пост относится к территории
  const useForecast = area.includes(station);
  const t = station ? station.thresholds : null;
  // Без прогноза вероятность известна, только если порог уже превышен (тогда она равна 1)
  const already = (threshold) => (station.level !== null && station.level >= threshold ? 1 : null);
  const p = {
    flood14:   useForecast ? (fc ? exceedance(station, fc.forecast, t.flood) : already(t.flood)) : null,
    danger14:  useForecast ? (fc ? exceedance(station, fc.forecast, t.danger) : already(t.danger)) : null,
    floodYear: useForecast ? (seas ? exceedance(station, seas.seasonal, t.flood) : already(t.flood)) : null,
  };
  // Год включает ближайшие 14 суток, поэтому вероятность за год не меньше, чем за 14 суток
  // (сезонная модель пока не знает, что вода в этом году выше нормы)
  if (p.floodYear !== null && p.flood14 !== null) p.floodYear = Math.max(p.floodYear, p.flood14);

  let level = 'low';
  if (count('watch') || p.flood14 >= 0.1 || p.floodYear >= 0.2) level = 'moderate';
  if (count('flood') || p.flood14 >= 0.5 || p.danger14 >= 0.2) level = 'high';
  if (count('danger') || p.danger14 >= 0.5) level = 'critical';

  return { level, count, p, useForecast };
}

// ---------- Отрисовка ----------
function bulletList(items) {
  return `<ul class="biz-list">${items.map((text) => `<li>${text}</li>`).join('')}</ul>`;
}

function renderBusiness(area, areaText, station, fc, seas) {
  const summary = document.getElementById('biz-summary');
  document.getElementById('biz-area').textContent = areaText;

  if (area.length === 0 || !station) {
    businessContext = null;
    document.getElementById('biz-level').innerHTML = '';
    summary.innerHTML = '<p class="muted">Нет постов под выбранные фильтры: выберите округ или реку.</p>';
    ['biz-operations', 'biz-credit', 'biz-opportunities'].forEach((id) => { document.getElementById(id).innerHTML = ''; });
    renderLoss();
    return;
  }

  const risk = assessRisk(area, station, fc, seas);
  const level = RISK_LEVELS[risk.level];
  businessContext = { station, fc, risk };

  document.getElementById('biz-level').innerHTML =
    `<span class="u-badge u-badge--${level.status}">${glyph(level.status)}Риск: ${level.label.toLowerCase()}</span>`;

  // --- Сводка для руководства ---
  const facts = [];
  const statusText = STATUS_ORDER
    .filter((st) => st !== 'nodata' && risk.count(st) > 0)
    .map((st) => `${risk.count(st)} — ${STATUSES[st].label.toLowerCase()}`).join(', ');
  facts.push(`<b>Территория:</b> ${escapeHtml(areaText)}, ${area.length} ${plural(area.length, 'пост', 'поста', 'постов')}: ${statusText || 'данных нет'}.`);

  if (risk.useForecast && fc) {
    facts.push(`<b>Прогноз по посту ${escapeHtml(station.name)}</b> (${escapeHtml(fc.model)}, ${fc.forecast.length} сут.): `
      + `выход на пойму — ${formatPercent(risk.p.flood14)}, опасный уровень — ${formatPercent(risk.p.danger14)}.`);
    const crossing = firstCrossing(station, fc.forecast);
    if (crossing) {
      const { key, point } = crossing;
      facts.push(`<b>Запас времени:</b> ${STATUSES[key].label.toLowerCase()} возможен через ${point.horizon} `
        + `${plural(point.horizon, 'день', 'дня', 'дней')} (${formatDate(point.date)}). Столько времени есть на подготовку.`);
    }
  } else if (risk.useForecast) {
    facts.push(`Для поста ${escapeHtml(station.name)} краткосрочный прогноз не рассчитывается, вывод сделан по текущим уровням.`);
  }
  if (risk.useForecast && seas) {
    facts.push(`<b>На год вперёд:</b> вероятность выхода на пойму — ${formatPercent(risk.p.floodYear)} (по сезонному и краткосрочному прогнозам).`);
  }
  const nodata = area.filter((s) => s.status === 'nodata');
  if (nodata.length) {
    facts.push(`Нет данных: ${nodata.map((s) => escapeHtml(s.name)).join(', ')}. Риск там не оценён.`);
  }

  summary.innerHTML = `
    <p class="body-strong">${level.headline}</p>
    ${bulletList(facts)}
    <p class="u-callout${risk.level === 'critical' ? ' u-callout--danger' : ''}"><span><b>Главное действие:</b> ${ACTIONS.main[risk.level]}</span></p>`;

  // --- Рекомендации ---
  document.getElementById('biz-operations').innerHTML = bulletList(ACTIONS.operations[risk.level]);
  document.getElementById('biz-credit').innerHTML = bulletList(ACTIONS.credit[risk.level]);
  const phase = risk.level === 'high' || risk.level === 'critical' ? 'during' : 'before';
  document.getElementById('biz-opportunities').innerHTML = bulletList(ACTIONS.opportunities[phase]);

  renderLoss();
}

// ---------- Калькулятор потерь ----------
// Подпись под суммой: откуда взялась вероятность
function probabilityNote(p, kind) {
  if (p === null) return `${kind} прогноза нет`;
  if (p === 1) return 'вода уже выше поймы';
  return `вероятность выхода на пойму ${formatPercent(p)}`;
}

// Ожидаемые потери = кредиты под залог в зоне × вероятность выхода на пойму × доля ущерба
function renderLoss() {
  const result = document.getElementById('loss-result');
  const form = document.getElementById('loss-form');
  const exposure = Math.max(0, Number(form.exposure.value) || 0);
  const damage = Math.min(100, Math.max(0, Number(form.damage.value) || 0)) / 100;

  if (!businessContext || !businessContext.risk.useForecast) {
    result.innerHTML = '<p class="caption muted">Выберите пост на карте или в таблице, чтобы оценить потери.</p>';
    return;
  }
  const { station, risk } = businessContext;
  const loss = (p) => (p === null ? null : exposure * p * damage);
  const lossText = (p) => (p === null ? '—' : formatMillions(loss(p)));
  const worst = exposure * damage;

  const cards = [
    kpiCard('Ожидаемые потери · 14 суток', lossText(risk.p.flood14), probabilityNote(risk.p.flood14, 'краткосрочного')),
    kpiCard('Ожидаемые потери · год', lossText(risk.p.floodYear), probabilityNote(risk.p.floodYear, 'сезонного')),
    kpiCard('Худший сценарий', formatMillions(worst), 'вода выше поймы во всей зоне', risk.level === 'critical'),
  ].join('');

  // Вывод: сравниваем самые большие ожидаемые потери с порогом существенности
  const maxP = Math.max(risk.p.flood14 ?? 0, risk.p.floodYear ?? 0);
  const share = maxP * damage;
  const verdict = risk.p.flood14 === null && risk.p.floodYear === null
    ? `Для поста ${escapeHtml(station.name)} нет прогноза, поэтому ожидаемые потери посчитать нельзя. Выберите пост с прогнозом, например Хабаровск.`
    : exposure === 0
    ? 'Введите сумму кредитов под залог в зоне подтопления.'
    : share >= MATERIALITY
      ? `<b>Потери существенные:</b> до ${formatMillions(loss(maxP))}, это ${formatPercent(share)} портфеля в зоне (порог — ${formatPercent(MATERIALITY)}). Стоит проверить страховое покрытие залогов и учесть риск в резервах.`
      : `<b>Потери несущественные:</b> до ${formatMillions(loss(maxP))}, меньше ${formatPercent(MATERIALITY)} портфеля в зоне. Достаточно мониторинга.`;

  result.innerHTML = `
    <div class="kpi-row kpi-row--3">${cards}</div>
    <p class="u-callout biz-verdict"><span>${verdict}</span></p>
    <p class="caption muted">Вероятность взята из коридора прогноза поста ${escapeHtml(station.name)}.
      Расчёт ориентировочный: он помогает понять, где действовать в первую очередь, но не заменяет расчёт резервов.</p>`;
}

function initBusiness() {
  const form = document.getElementById('loss-form');
  form.addEventListener('input', renderLoss);
  form.addEventListener('submit', (event) => event.preventDefault());   // Enter в поле не перезагружает страницу
}
