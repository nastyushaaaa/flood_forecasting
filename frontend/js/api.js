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
const REQUEST_TIMEOUT_MS = 15000;   // дольше ждать ответа нет смысла: пользователь решит, что страница зависла

/**
 * @typedef {Object} Thresholds  Пороги уровня воды на посту, см
 * @property {number} watch   порог готовности (критический)
 * @property {number} flood   выход воды на пойму
 * @property {number} danger  опасный уровень
 */

/**
 * @typedef {Object} Station
 * @property {string} id          код поста латиницей, например 'khabarovsk'
 * @property {string} name        название поста
 * @property {string} river       река
 * @property {string} okrug       федеральный округ
 * @property {number} lat         широта, градусы
 * @property {number} lon         долгота, градусы
 * @property {number|null} level  текущий уровень, см; null — нет данных
 * @property {Thresholds} thresholds
 * @property {string} measured_at дата измерения, ISO 8601
 */

/**
 * @typedef {Object} StationsResponse
 * @property {string} updated_at      время среза данных, ISO 8601
 * @property {string} next_update_at  время следующего обновления, ISO 8601
 * @property {Station[]} stations
 */

/**
 * @typedef {Object} ForecastPoint
 * @property {string} date        дата, ISO 8601
 * @property {number} [horizon]   заблаговременность, сут (только в краткосрочном прогнозе)
 * @property {number} level       прогноз уровня, см
 * @property {number} level_low   нижняя граница коридора, см
 * @property {number} level_high  верхняя граница коридора, см
 */

/**
 * @typedef {Object} Forecast  Краткосрочный прогноз поста
 * @property {string} station_id
 * @property {string} model           название модели
 * @property {string} model_note      пояснение к модели для подписи под графиком
 * @property {string} interval_label  подпись коридора, например «Коридор 80 %»
 * @property {string} today           дата выпуска прогноза
 * @property {{date: string, level: number}[]} history  фактические уровни, см
 * @property {ForecastPoint[]} forecast
 */

/**
 * @typedef {Object} Seasonal  Сезонный прогноз поста на год вперёд
 * @property {string} station_id
 * @property {string} model
 * @property {string} model_note
 * @property {string} today
 * @property {{date: string, level: number}[]} fact  уровни с начала года, см
 * @property {ForecastPoint[]} seasonal
 */

/**
 * Загружает JSON по адресу.
 * Если данных нет (ответ 404) — возвращает null, а не ошибку: например, прогноз пока считается не для всех постов.
 * @param {string} url
 * @returns {Promise<Object|null>}
 * @throws {Error} сервер не ответил за REQUEST_TIMEOUT_MS, ответил ошибкой или прислал не JSON
 */
async function fetchJson(url) {
  let response;
  try {
    response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  } catch (error) {
    if (error.name === 'TimeoutError') {
      throw new Error(`Сервер не ответил за ${REQUEST_TIMEOUT_MS / 1000} с (${url})`, { cause: error });
    }
    throw new Error(`Нет связи с сервером (${url})`, { cause: error });
  }
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Сервер ответил ${response.status} на запрос ${url}`);
  try {
    return await response.json();
  } catch (error) {
    throw new Error(`Сервер прислал некорректный JSON (${url})`, { cause: error });
  }
}

/**
 * Список постов с текущими уровнями и порогами.
 * @param {string} [at] дата и время проверки из фильтра («2026-08-01T10:30»)
 * @returns {Promise<StationsResponse|null>}
 */
function getStations(at) {
  if (USE_MOCK) return fetchJson('mock/stations.json');
  const query = at ? `?at=${encodeURIComponent(at)}` : '';
  return fetchJson(`${API_BASE}/stations${query}`);
}

/**
 * Краткосрочный прогноз поста: история + прогноз с коридором.
 * @param {string} stationId код поста, например 'khabarovsk'
 * @returns {Promise<Forecast|null>} null — прогноза для поста нет
 */
function getForecast(stationId) {
  if (USE_MOCK) return fetchJson(`mock/forecast_${stationId}.json`);
  return fetchJson(`${API_BASE}/forecast/${stationId}`);
}

/**
 * Сезонный прогноз на год вперёд.
 * @param {string} stationId код поста, например 'khabarovsk'
 * @returns {Promise<Seasonal|null>} null — прогноза для поста нет
 */
function getSeasonal(stationId) {
  if (USE_MOCK) return fetchJson(`mock/seasonal_${stationId}.json`);
  return fetchJson(`${API_BASE}/seasonal/${stationId}`);
}
