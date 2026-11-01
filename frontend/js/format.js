// =====================================================================================
// ФОРМАТИРОВАНИЕ ЧИСЕЛ И ДАТ
// Как в дизайн-проекте: «1 384» (пробел между разрядами), «−74» (настоящий минус),
// даты «01.08.2026». Даты из API приходят строками «2026-08-01» или «2026-08-01T10:30:00+03:00».
// =====================================================================================

const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

// 1384 -> «1 384», -74 -> «−74», null -> «—»
function formatLevel(value) {
  if (value === null || value === undefined) return '—';
  return numberFormat.format(value).replace('-', '−');
}

// Число со знаком: 34 -> «+34», -74 -> «−74»
function formatSigned(value) {
  if (value === null || value === undefined) return '—';
  return (value > 0 ? '+' : '') + formatLevel(value);
}

const moneyFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

// 1234.56 -> «1 234,6 млн ₽»
function formatMillions(value) {
  return `${moneyFormat.format(value)} млн ₽`;
}

// Доля в проценты: 0.873 -> «87 %». Крайние значения не округляем до 0 и 100, чтобы не врать:
// 0.003 -> «<1 %», 0.996 -> «>99 %»
function formatPercent(share) {
  if (share > 0 && share < 0.01) return '<1 %';
  if (share > 0.99 && share < 1) return '>99 %';
  return `${Math.round(share * 100)} %`;
}

// «2026-08-01» -> «01.08.2026»
function formatDate(isoDate) {
  const [year, month, day] = isoDate.slice(0, 10).split('-');
  return `${day}.${month}.${year}`;
}

// «2026-08-01» -> «01.08» (для коротких подписей)
function formatDayMonth(isoDate) {
  return formatDate(isoDate).slice(0, 5);
}

// «2026-08-01T10:30:00+03:00» -> «10:30». Время берём из строки как есть: сервер отдаёт московское.
function formatTime(isoDateTime) {
  return isoDateTime.slice(11, 16);
}

// Склонение: plural(7, 'день', 'дня', 'дней') -> «дней»
function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

// Защита от «поломки» разметки: текст из данных вставляем в HTML только через эту функцию
function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
