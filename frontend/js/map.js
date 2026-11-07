// =====================================================================================
// КАРТА ГИДРОПОСТОВ (библиотека Leaflet, https://leafletjs.com)
// Подложка — спокойная серая карта Esri (светлая или тёмная под тему), сверху маркеры постов:
// белое кольцо + значок статуса. Клик по маркеру вызывает onSelect(id поста).
// =====================================================================================

let map = null;            // объект карты Leaflet (создаём один раз)
let markersLayer = null;   // слой с маркерами: очищаем и рисуем заново при каждом обновлении

function initMap(isDark) {
  map = L.map('map', { zoomControl: true, scrollWheelZoom: false });  // колесо мыши крутит страницу, а не карту

  // Серая подложка Esri: работает без ключа. CARTO теперь требует API-ключ и без него
  // вместо карты рисует надпись «API KEY REQUIRED»
  const style = isDark ? 'World_Dark_Gray_Base' : 'World_Light_Gray_Base';
  L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/${style}/MapServer/tile/{z}/{y}/{x}`, {
    attribution: '&copy; Esri, HERE, Garmin, &copy; OpenStreetMap',
    maxZoom: 12,
  }).addTo(map);

  markersLayer = L.layerGroup().addTo(map);
  // Подписи постов — под маркерами (у Leaflet по умолчанию наоборот): при плотной карте
  // подпись соседнего поста не должна закрывать маркер от клика
  map.getPane('tooltipPane').style.zIndex = 550;
  map.setView([55, 100], 3);   // вид по умолчанию — вся Россия
}

// stations — посты после фильтров; у каждого уже посчитан station.status (см. main.js)
// fitView — true, если нужно заново подогнать масштаб (после смены фильтров);
//           при выборе поста масштаб не трогаем, чтобы карта не «прыгала».
function renderMap(stations, selectedId, onSelect, fitView) {
  markersLayer.clearLayers();

  stations.forEach((station) => {
    const selected = station.id === selectedId ? ' is-selected' : '';
    const icon = L.divIcon({
      className: 'map-marker' + selected,
      iconSize: [20, 20],
      // кольцо радиусом 8.5 и значок статуса 12×12 в центре
      html: `<svg width="20" height="20" viewBox="0 0 20 20">
               <circle class="ring" cx="10" cy="10" r="8.5"/>
               <svg x="4" y="4" width="12" height="12" viewBox="0 0 12 12">${GLYPH_SHAPES[station.status]}</svg>
             </svg>`,
    });

    const marker = L.marker([station.lat, station.lon], {
      icon,
      keyboard: true,                                   // маркер можно выбрать Tab + Enter
      title: `${station.name}: ${STATUSES[station.status].label}`,
    })
      // interactive: подпись тоже кликается (по умолчанию Leaflet пропускает клики сквозь неё)
      .bindTooltip(escapeHtml(station.name), { permanent: true, direction: 'right', offset: [10, 0], className: 'map-label', interactive: true })
      .on('click', () => onSelect(station.id))
      .addTo(markersLayer);
    marker.getTooltip().on('click', () => onSelect(station.id));
  });

  // Подгоняем масштаб так, чтобы все показанные посты поместились
  if (fitView && stations.length > 0) {
    map.invalidateSize();   // карта заново меряет свой размер: к этому моменту шрифты и вёрстка уже загрузились
    const bounds = L.latLngBounds(stations.map((s) => [s.lat, s.lon]));
    // справа отступ больше — там подписи постов
    map.fitBounds(bounds, { paddingTopLeft: [30, 30], paddingBottomRight: [90, 30], maxZoom: 7 });
  }
}

// Рисует легенду под картой: значок + подпись для каждого статуса
function renderMapLegend() {
  document.getElementById('map-legend').innerHTML = ['normal', 'watch', 'flood', 'danger', 'nodata']
    .map((status) => `<span>${glyph(status)}${STATUSES[status].label}</span>`)
    .join('');
}
