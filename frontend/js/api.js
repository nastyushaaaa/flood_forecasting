// =====================================================================================
// ЗАГРУЗКА ДАННЫХ
// Весь обмен с сервером — только в этом файле. Остальной код вызывает getStations(),
// getForecast(), getBacktest(), getSeasonal() и не знает, откуда пришли данные.
//
// Сначала спрашиваем бэкенд (/api/...). Пока он эти данные не отдаёт, читаем готовые JSON из папки mock/
// (их создаёт frontend/tools/make_mock.py по моделям проекта) и показываем метку «сохранённый срез».
// Источник выбирается при каждой загрузке постов. Формат ответов описан в frontend/README.md, раздел «Контракт API».
// =====================================================================================

const API_BASE = '/api';
const MOCK_BASE = 'mock';
const REQUEST_TIMEOUT_MS = 15000;   // дольше ждать ответа нет смысла: пользователь решит, что страница зависла

let dataSource = 'api';             // 'api' — бэкенд, 'mock' — тестовые файлы из mock/

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
 * @property {number|null} level  уровень на дату среза, см; null — нет свежего замера
 * @property {Thresholds} thresholds
 * @property {string|null} measured_at дата последнего замера, ISO 8601; null — замеров нет
 */

/**
 * @typedef {Object} StationsResponse
 * @property {string} updated_at           время среза данных, ISO 8601
 * @property {string|null} next_update_at  время следующего обновления; null — не по расписанию
 * @property {string} [available_from]     первая дата, на которую есть замеры
 * @property {string} [available_to]       последняя дата, на которую есть замеры
 * @property {Station[]} stations
 */

/**
 * @typedef {Object} LevelPoint
 * @property {string} date   дата, ISO 8601
 * @property {number} level  уровень, см
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
 * @typedef {Object} SkillPoint  Ошибка модели на проверке 02.08.2025–01.08.2026
 * @property {number} horizon  заблаговременность, сут
 * @property {number} mae      средняя абсолютная ошибка, см
 * @property {number} rmse     среднеквадратичная ошибка, см
 */

/**
 * @typedef {Object} ModelForecast  Краткосрочный прогноз одной модели
 * @property {string} key             код модели, например 'pg_lstm'
 * @property {string} model           название модели
 * @property {string} model_note      пояснение к модели для подписи под графиком
 * @property {string} interval_label  подпись коридора, например «Коридор 80 %»
 * @property {ForecastPoint[]} forecast
 * @property {SkillPoint[]} skill     ошибки по горизонтам; пусто — модель не проверялась
 */

/**
 * @typedef {Object} Forecast  Краткосрочные прогнозы поста
 * @property {string} station_id
 * @property {string} today              дата выпуска прогноза
 * @property {LevelPoint[]} history      факт за 60 суток до даты прогноза
 * @property {LevelPoint[]} actual       факт после даты прогноза (если она в прошлом)
 * @property {ModelForecast[]} models    прогнозы моделей, первая — основная; пусто — прогноза нет
 * @property {string[]} pending          модели, которые ещё обучаются на сервере
 * @property {string|null} note          почему прогноза нет
 */

/**
 * @typedef {Object} ModelSeasonal  Сезонный прогноз одной модели
 * @property {string} key
 * @property {string} model
 * @property {string} model_note
 * @property {string} interval_label
 * @property {ForecastPoint[]} seasonal
 */

/**
 * @typedef {Object} Seasonal  Сезонные прогнозы поста на год вперёд
 * @property {string} station_id
 * @property {string} today
 * @property {LevelPoint[]} fact        уровни с начала года, см
 * @property {ModelSeasonal[]} models
 * @property {string[]} pending
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

// «?at=2026-08-01T10:30» или пустая строка
function atQuery(at) {
  return at ? `?at=${encodeURIComponent(at)}` : '';
}

/**
 * Показываются ли сейчас тестовые данные из mock/ вместо данных бэкенда.
 * @returns {boolean}
 */
function isMockData() {
  return dataSource === 'mock';
}

/**
 * Список постов с уровнями на дату и порогами.
 * Если бэкенд не отвечает или не отдаёт /api/stations, переключается на mock/ (см. isMockData).
 * @param {string} [at] дата и время проверки из фильтра («2026-08-01T10:30»)
 * @returns {Promise<StationsResponse|null>}
 */
async function getStations(at) {
  try {
    const data = await fetchJson(`${API_BASE}/stations${atQuery(at)}`);
    if (data) {
      dataSource = 'api';
      return data;
    }
    console.warn(`Бэкенд не отдаёт ${API_BASE}/stations: показываем тестовые данные из ${MOCK_BASE}/`);
  } catch (error) {
    console.warn(`Бэкенд недоступен, показываем тестовые данные из ${MOCK_BASE}/:`, error);
  }
  dataSource = 'mock';
  return fetchJson(`${MOCK_BASE}/stations.json`);
}

/**
 * Краткосрочные прогнозы поста: факт + прогнозы всех моделей с коридорами.
 * @param {string} stationId код поста, например 'khabarovsk'
 * @param {string} [at] дата прогноза из фильтра
 * @returns {Promise<Forecast|null>} null — по посту нет замеров
 */
function getForecast(stationId, at) {
  if (isMockData()) return fetchJson(`${MOCK_BASE}/forecast_${stationId}.json`);
  return fetchJson(`${API_BASE}/forecast/${stationId}${atQuery(at)}`);
}

/**
 * Проверка: прогноз всех моделей за 14 суток до последнего замера и что было на самом деле.
 * @param {string} stationId код поста, например 'khabarovsk'
 * @returns {Promise<Forecast|null>} null — проверки для поста нет
 */
function getBacktest(stationId) {
  if (isMockData()) return fetchJson(`${MOCK_BASE}/backtest_${stationId}.json`);
  return fetchJson(`${API_BASE}/backtest/${stationId}`);
}

/**
 * Сезонные прогнозы на год вперёд.
 * @param {string} stationId код поста, например 'khabarovsk'
 * @param {string} [at] дата прогноза из фильтра
 * @returns {Promise<Seasonal|null>} null — сезонного прогноза для поста нет
 */
function getSeasonal(stationId, at) {
  if (isMockData()) return fetchJson(`${MOCK_BASE}/seasonal_${stationId}.json`);
  return fetchJson(`${API_BASE}/seasonal/${stationId}${atQuery(at)}`);
}
