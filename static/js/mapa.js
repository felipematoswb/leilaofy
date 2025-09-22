// static/js/mapa.js

// Configura o HTMX para enviar o CSRF token do Django em todas as requisições POST
htmx.on("htmx:configRequest", function (evt) {
  const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]');
  if (csrfToken && evt.detail.verb !== "get") {
    // Adiciona o token apenas para requisições não-GET
    evt.detail.headers["X-CSRFToken"] = csrfToken.value;
  }
});

document.addEventListener("DOMContentLoaded", function () {
  const configElement = document.getElementById("map-config");
  if (!configElement) {
    console.error("Elemento de configuração #map-config não encontrado.");
    return;
  }
  const config = JSON.parse(configElement.textContent);

  // --- SETUP INICIAL E ÍCONES ---
  const saoPauloCoords = [-23.5505, -46.6333];
  const map = L.map("map", { maxZoom: 19, minZoom: 4 }).setView(
    saoPauloCoords,
    11
  );

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  const defaultIcon = new L.Icon({
    iconUrl:
      "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowUrl:
      "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
    shadowSize: [41, 41],
  });

  const highlightIcon = new L.Icon({
    iconUrl:
      "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowUrl:
      "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
    shadowSize: [41, 41],
  });

  // --- SELEÇÃO DE ELEMENTOS DO DOM ---
  const form = document.getElementById("filter-form");
  const bboxInput = document.getElementById("bbox-input");
  const loadingIndicator = document.getElementById("loading");
  const addressInput = document.getElementById("address-input");
  const autocompleteList = document.getElementById("autocomplete-list");
  const comarcaInput = document.getElementById("comarca-input");
  const resultsContainer = document.getElementById("results-list");

  // --- CAMADA DE MARCADORES E ESTADO ---
  let markers = L.featureGroup().addTo(map);
  let markerRegistry = {};
  let fetchController = null;
  let debounceTimeout = null;
  let autocompleteDebounceTimeout = null;

  // --- FUNÇÕES AUXILIARES ---
  function removerAcentos(texto) {
    if (!texto) return "";
    return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  // --- LÓGICA DE AUTOCOMPLETE ---
  async function handleAddressInput() {
    const query = addressInput.value;
    if (query.length < 3) {
      autocompleteList.innerHTML = "";
      if (comarcaInput.value) {
        comarcaInput.value = "";
        debouncedFetch();
      }
      return;
    }
    try {
      const response = await fetch(
        `/api/geocode-autocomplete/?text=${encodeURIComponent(query)}`
      );
      const suggestions = await response.json();
      autocompleteList.innerHTML = "";
      suggestions.forEach((suggestion) => {
        const item = document.createElement("div");
        item.textContent = suggestion.text;
        item.dataset.text = suggestion.text;
        if (suggestion.bbox) item.dataset.bbox = suggestion.bbox.join(",");
        item.dataset.city = suggestion.city || "";
        item.dataset.stateCode = suggestion.state_code || "";
        item.addEventListener("click", (e) => {
          const clickedItem = e.currentTarget;
          const city = clickedItem.dataset.city;
          const stateCode = clickedItem.dataset.stateCode;
          addressInput.value = clickedItem.dataset.text;
          autocompleteList.innerHTML = "";
          if (city && stateCode) {
            const cidadeSemAcento = removerAcentos(city);
            const comarca = `${cidadeSemAcento.toUpperCase()}-${stateCode.toUpperCase()}`;
            comarcaInput.value = comarca;
          } else {
            comarcaInput.value = "";
          }
          if (clickedItem.dataset.bbox) {
            const bbox = clickedItem.dataset.bbox.split(",").map(Number);
            map.flyToBounds([
              [bbox[1], bbox[0]],
              [bbox[3], bbox[2]],
            ]);
          } else {
            fetchAndUpdate();
          }
        });
        autocompleteList.appendChild(item);
      });
    } catch (error) {
      console.error("Autocomplete error:", error);
    }
  }

  // --- FUNÇÃO PRINCIPAL DE BUSCA (O MAESTRO) ---
  async function fetchAndUpdate() {
    loadingIndicator.style.display = "block";
    if (fetchController) fetchController.abort();
    fetchController = new AbortController();
    const signal = fetchController.signal;

    const bounds = map.getBounds();
    bboxInput.value = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;

    const formData = new FormData(form);
    const params = new URLSearchParams(formData);
    const queryString = params.toString();

    try {
      const response = await fetch(`${config.geojsonUrl}?${queryString}`, {
        signal,
      });
      if (!response.ok)
        throw new Error("Network response was not ok for GeoJSON");
      const geojsonData = await response.json();

      markers.clearLayers();
      markerRegistry = {};

      const geoJsonLayer = L.geoJSON(geojsonData, {
        pointToLayer: function (feature, latlng) {
          return L.marker(latlng, { icon: defaultIcon });
        },
        onEachFeature: function (feature, layer) {
          const props = feature.properties;
          const imovelId = props.id;
          markerRegistry[imovelId] = layer;
          const detailUrl = props.detail_url || `/imovel/${imovelId}/`;
          const popupContent = `
                        <h5>${props.title}</h5>
                        <b>Preço:</b> R$ ${
                          props.price
                            ? props.price.toLocaleString("pt-BR")
                            : "N/A"
                        }<br>
                        <a href="${detailUrl}" target="_blank">Ver detalhes</a>
                    `;
          layer.bindPopup(popupContent);
        },
      });

      markers.addLayer(geoJsonLayer);

      htmx.trigger(form, "updateSidebar");
    } catch (error) {
      if (error.name !== "AbortError") console.error("Fetch error:", error);
    } finally {
      htmx.on("htmx:afterRequest", () => {
        loadingIndicator.style.display = "none";
      });
      if (document.querySelector(".htmx-request") === null)
        loadingIndicator.style.display = "none";
    }
  }

  // --- FUNÇÃO DE DEBOUNCE ---
  function debouncedFetch() {
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(fetchAndUpdate, 500);
  }

  // --- EVENT LISTENERS ---
  map.on("moveend", debouncedFetch);
  form.addEventListener("change", debouncedFetch);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    debouncedFetch();
  });

  addressInput.addEventListener("input", () => {
    clearTimeout(autocompleteDebounceTimeout);
    autocompleteDebounceTimeout = setTimeout(handleAddressInput, 300);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".autocomplete-container")) {
      autocompleteList.innerHTML = "";
    }
  });

  resultsContainer.addEventListener("mouseover", (e) => {
    const card = e.target.closest(".result-card");
    if (!card) return;
    const imovelId = card.dataset.imovelId;
    const marker = markerRegistry[imovelId];
    if (marker) {
      marker.setIcon(highlightIcon);
    }
  });

  resultsContainer.addEventListener("mouseout", (e) => {
    const card = e.target.closest(".result-card");
    if (!card) return;
    const imovelId = card.dataset.imovelId;
    const marker = markerRegistry[imovelId];
    if (marker) {
      marker.setIcon(defaultIcon);
    }
  });

  // --- CARGA INICIAL ---
  // Antes: map.whenReady(fetchAndUpdate);
  // Agora: dispara a primeira busca manualmente
  fetchAndUpdate();
});
