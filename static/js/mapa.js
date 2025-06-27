document.addEventListener("DOMContentLoaded", function () {
  // --- 1. ELEMENTOS DO DOM E VARIÁVEIS GLOBAIS ---
  const mapContainer = document.getElementById("map");
  const mapColumn = document.getElementById("map-column");
  const toggleMapBtn = document.getElementById("toggle-map-btn");
  const closeMapBtn = document.getElementById("close-map-btn");

  const bboxInput = document.getElementById("bbox-input");
  const filterForm = document.getElementById("filter-form");
  const addressInput = document.getElementById("address-input");
  const autocompleteList = document.getElementById("autocomplete-list");

  let markers = {};
  let debounceTimer;

  // --- 2. INICIALIZAÇÃO DO MAPA ---
  // O mapa inicia em São Paulo com zoom.
  const map = L.map(mapContainer).setView([-23.5505, -46.6333], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  const markersLayer = L.layerGroup().addTo(map);

  // --- 3. ÍCONES CUSTOMIZADOS ---
  const defaultIcon = new L.Icon.Default();
  const highlightIcon = new L.Icon({
    iconUrl:
      "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png",
    shadowUrl:
      "https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png",
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41],
  });

  // --- 4. FUNÇÃO DE APOIO ---
  function updateBboxInput() {
    const bounds = map.getBounds();
    bboxInput.value = `${bounds.getSouthWest().lat},${
      bounds.getSouthWest().lng
    },${bounds.getNorthEast().lat},${bounds.getNorthEast().lng}`;
  }

  // --- 5. CONTROLO DO MAPA POPUP (MOBILE) ---
  toggleMapBtn.addEventListener("click", () => {
    mapColumn.classList.add("visible");
    setTimeout(() => {
      map.invalidateSize();
    }, 10);
  });

  closeMapBtn.addEventListener("click", () => {
    mapColumn.classList.remove("visible");
  });

  // --- 6. LÓGICA DE AUTOCOMPLETE ---
  addressInput.addEventListener("input", function (e) {
    const query = e.target.value;
    autocompleteList.innerHTML = "";
    clearTimeout(debounceTimer);

    if (query.length < 3) return;

    debounceTimer = setTimeout(() => {
      fetch(`/api/geocode-autocomplete/?text=${encodeURIComponent(query)}`)
        .then((response) => response.json())
        .then((data) => {
          autocompleteList.innerHTML = "";
          if (data.error) {
            console.error("API Autocomplete Error:", data.error);
            return;
          }
          data.forEach((suggestion) => {
            const item = document.createElement("div");
            item.innerHTML = suggestion.text;
            item.addEventListener("click", function () {
              addressInput.value = suggestion.text;
              autocompleteList.innerHTML = "";
              if (suggestion.bbox) {
                const bounds = [
                  [suggestion.bbox[1], suggestion.bbox[0]],
                  [suggestion.bbox[3], suggestion.bbox[2]],
                ];
                map.fitBounds(bounds);
              }
            });
            autocompleteList.appendChild(item);
          });
        });
    }, 300);
  });

  document.addEventListener("click", (e) => {
    if (e.target !== addressInput) autocompleteList.innerHTML = "";
  });

  // --- 7. FUNÇÃO DE SINCRONIZAÇÃO DE MAPA E LISTA ---
  function syncMapAndList() {
    markersLayer.clearLayers();
    markers = {};
    const cards = document.querySelectorAll(".result-card");
    cards.forEach((card) => {
      const imovelId = card.dataset.imovelId;
      const lat = card.dataset.lat;
      const lng = card.dataset.lng;
      const title = card.dataset.title;

      if (lat && lng) {
        const latNum = parseFloat(lat.replace(",", "."));
        const lngNum = parseFloat(lng.replace(",", "."));
        const marker = L.marker([latNum, lngNum], { icon: defaultIcon });
        marker.bindPopup(`<b>${title}</b>`);
        marker.on("click", () => {
          const cardElement = document.querySelector(
            `a > .result-card[data-imovel-id="${imovelId}"]`
          );
          if (cardElement) {
            cardElement.scrollIntoView({ behavior: "smooth", block: "center" });
            cardElement.classList.add("highlight");
            setTimeout(() => cardElement.classList.remove("highlight"), 2000);

            if (mapColumn.classList.contains("visible")) {
              closeMapBtn.click();
            }
          }
        });
        markers[imovelId] = marker;
        markersLayer.addLayer(marker);
      }

      const linkElement = card.closest("a");
      if (linkElement) {
        linkElement.addEventListener("mouseover", () => {
          if (markers[imovelId])
            markers[imovelId].setIcon(highlightIcon).setZIndexOffset(1000);
        });
        linkElement.addEventListener("mouseout", () => {
          if (markers[imovelId])
            markers[imovelId].setIcon(defaultIcon).setZIndexOffset(0);
        });
      }
    });
  }

  // --- 8. EVENTOS PRINCIPAIS DO HTMX E MAPA ---

  // Interceta a requisição ANTES que ela seja enviada
  document.body.addEventListener("htmx:configRequest", function (evt) {
    if (evt.detail.elt.id === "filter-form") {
      updateBboxInput();
      addressInput.disabled = true;
    }
  });

  // Roda DEPOIS que a requisição termina
  document.body.addEventListener("htmx:afterRequest", function (evt) {
    if (evt.detail.elt.id === "filter-form") {
      addressInput.disabled = false;
    }
  });

  // Dispara a busca sempre que o mapa para de se mover
  map.on("moveend", () => {
    htmx.trigger("#filter-form", "submit");
  });

  // Sincroniza o mapa após o HTMX atualizar a lista
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (
      event.detail.target.id === "results-column" ||
      event.detail.target.id === "results-list"
    ) {
      syncMapAndList();
    }
  });

  // --- 9. EXECUÇÃO INICIAL (CORRIGIDA) ---

  // CORREÇÃO: Garante que o Bbox inicial seja o de São Paulo ANTES de qualquer busca.
  updateBboxInput();

  // Dispara a busca inicial assim que o mapa estiver pronto.
  map.whenReady(() => {
    htmx.trigger("#filter-form", "submit");
  });
});
