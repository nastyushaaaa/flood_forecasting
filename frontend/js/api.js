// =====================================================================================
// ЗАГРУЗКА ДАННЫХ
// Весь обмен с сервером — только в этом файле. Остальной код вызывает getStations(),
// getForecast(), getSeasonal() и не знает, откуда пришли данные.
//
// Пока бэкенд не отдаёт эти данные, USE_MOCK = true: читаем готовые JSON из папки mock/
// (их создаёт frontend/tools/make_mock.py). Когда эндпоинты появятся — ставим false.
// Формат ответов описан в frontend/README.md, раздел «Контракт API».
// =====================================================================================

const USE_MOCK = true;
const API_BASE = '/api';

// Загружает JSON по адресу. Если данных нет (ответ 404) — возвращает null, а не ошибку:
// например, прогноз пока считается не для всех постов.
async function fetchJson(url) {
  const response = await fetch(url);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Сервер ответил ${response.status} на запрос ${url}`);
  return response.json();
}

// Список постов с текущими уровнями и порогами.
// at — дата и время проверки из фильтра («2026-08-01T10:30»), можно не передавать.
function getStations(at) {
  if (USE_MOCK) return fetchJson('mock/stations.json');
  const query = at ? `?at=${encodeURIComponent(at)}` : '';
  return fetchJson(`${API_BASE}/stations${query}`);
}

// Краткосрочный прогноз поста: история + прогноз с коридором. null — прогноза для поста нет.
function getForecast(stationId) {
  if (USE_MOCK) return fetchJson(`mock/forecast_${stationId}.json`);
  return fetchJson(`${API_BASE}/forecast/${stationId}`);
}

// Сезонный прогноз на год вперёд. null — прогноза для поста нет.
function getSeasonal(stationId) {
  if (USE_MOCK) return fetchJson(`mock/seasonal_${stationId}.json`);
  return fetchJson(`${API_BASE}/seasonal/${stationId}`);
}
