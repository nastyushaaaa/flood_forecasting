// =====================================================================================
// СТАТУСЫ ГИДРОПОСТА
// У каждого поста три порога (см): watch — критический уровень (готовность),
// flood — выход воды на пойму, danger — опасный уровень.
// Статус = самый высокий порог, который уровень уже достиг.
// =====================================================================================

// Порядок важен: от самого опасного к «нет данных». Так сортируем таблицу и рисуем списки.
const STATUS_ORDER = ['danger', 'flood', 'watch', 'normal', 'nodata'];

const STATUSES = {
  danger: { label: 'Опасный уровень',     short: 'Опасный',         threshold: 'Опасн.' },
  flood:  { label: 'Выход на пойму',      short: 'Выход на пойму',  threshold: 'Пойма' },
  watch:  { label: 'Критический уровень', short: 'Критический',     threshold: 'Готовн.' },
  normal: { label: 'Норма',               short: 'Норма' },
  nodata: { label: 'Нет данных',          short: 'Нет данных' },
};

// Определяет статус по уровню и порогам поста
function getStatus(level, thresholds) {
  if (level === null || level === undefined) return 'nodata';
  if (level >= thresholds.danger) return 'danger';
  if (level >= thresholds.flood) return 'flood';
  if (level >= thresholds.watch) return 'watch';
  return 'normal';
}

// Первый день прогноза, когда верхняя граница коридора дойдёт до следующего порога
// (выше текущего статуса поста). Возвращает { key: 'flood', point } или null.
function firstCrossing(station, forecast) {
  const levels = ['watch', 'flood', 'danger'];
  const higher = levels.slice(levels.indexOf(station.status) + 1);   // пороги выше текущего статуса
  for (const key of higher) {
    const point = forecast.find((p) => p.level_high >= station.thresholds[key]);
    if (point) return { key, point };
  }
  return null;
}

// SVG-значок статуса. Форма своя у каждого статуса — различим даже при дальтонизме и на ч/б печати:
// норма — круг, критический — треугольник, пойма — ромб, опасный — квадрат, нет данных — кольцо.
// Цвет задаётся CSS-классом g-<статус> (см. style.css), поэтому значок сам меняется в тёмной теме.
const GLYPH_SHAPES = {
  normal: '<circle class="g-normal" cx="6" cy="6" r="5"/>',
  watch:  '<polygon class="g-watch" points="6,1 11.5,10.5 0.5,10.5"/>',
  flood:  '<polygon class="g-flood" points="6,0.5 11.5,6 6,11.5 0.5,6"/>',
  danger: '<rect class="g-danger" x="1" y="1" width="10" height="10" rx="2"/>',
  nodata: '<circle class="g-nodata" cx="6" cy="6" r="4"/>',
};

function glyph(status) {
  return `<svg class="glyph" viewBox="0 0 12 12" aria-hidden="true">${GLYPH_SHAPES[status]}</svg>`;
}

// Бейдж «значок + подпись» на мягком фоне (для таблицы и списка распределения)
function badge(status) {
  return `<span class="u-badge u-badge--${status}">${glyph(status)}${STATUSES[status].label}</span>`;
}
