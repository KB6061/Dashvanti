window.dashvantiSilverCarIcon=()=>({url:'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"64\" height=\"80\" viewBox=\"0 0 64 80\"><defs><linearGradient id=\"s\" x2=\"0\" y2=\"1\"><stop stop-color=\"#fff\"/><stop offset=\".3\" stop-color=\"#dce1e5\"/><stop offset=\".55\" stop-color=\"#fff\"/><stop offset=\"1\" stop-color=\"#727c85\"/></linearGradient><linearGradient id=\"g\" x2=\"0\" y2=\"1\"><stop stop-color=\"#56606a\"/><stop offset=\"1\" stop-color=\"#10151a\"/></linearGradient><radialGradient id=\"h\"><stop stop-opacity=\".4\"/><stop offset=\"1\" stop-opacity=\"0\"/></radialGradient></defs><path d=\"M32 2a12 12 0 0 0-12 12c0 9 12 24 12 24s12-15 12-24A12 12 0 0 0 32 2Z\" fill=\"#e53935\" stroke=\"#fff\" stroke-width=\"1.5\"/><circle cx=\"32\" cy=\"14\" r=\"4\" fill=\"#fff\"/><ellipse cx=\"32\" cy=\"66\" rx=\"31\" ry=\"12\" fill=\"url(#h)\"/><g fill=\"#171b20\"><rect x=\"13\" y=\"46\" width=\"11\" height=\"7\" rx=\"2\"/><rect x=\"40\" y=\"46\" width=\"11\" height=\"7\" rx=\"2\"/><rect x=\"13\" y=\"69\" width=\"11\" height=\"7\" rx=\"2\"/><rect x=\"40\" y=\"69\" width=\"11\" height=\"7\" rx=\"2\"/></g><path d=\"M8 51Q32 45 56 51Q62 54 62 61Q62 69 56 71Q32 76 8 71Q2 69 2 61Q2 54 8 51Z\" fill=\"url(#s)\" stroke=\"#6d767e\"/><path d=\"M22 52L17 55V67L22 70L26 65V57Z M42 52L48 55V67L42 70L38 65V57Z\" fill=\"url(#g)\"/><path d=\"M26 54H37L39 57V65L37 69H26L24 65V57Z\" fill=\"url(#s)\" stroke=\"#a3abb2\"/><path d=\"M23 50H40M23 72H40\" stroke=\"#fff\" stroke-width=\"2\"/><path d=\"M6 54V59M6 64V68\" stroke=\"#fffbdc\" stroke-width=\"3\"/><path d=\"M58 54V58M58 65V69\" stroke=\"#bd2828\" stroke-width=\"2\"/><path d=\"M29 49V46M35 73V76\" stroke=\"#adb5bd\" stroke-width=\"3\"/></svg>"),scaledSize:new google.maps.Size(48,60),anchor:new google.maps.Point(24,46)});
(() => {
  const mapElements = [...document.querySelectorAll('[data-google-map]')];
  if (!mapElements.length && !document.querySelector('[data-address-autocomplete]')) return;

  const apiKey = document.body.dataset.googleMapsKey || '';
  const setStatus = (element, message) => {
    const status = element.parentElement?.querySelector('[data-map-status]');
    if (status) status.textContent = message;
  };
  if (!apiKey) {
    mapElements.forEach((element) => setStatus(element, 'Map configuration unavailable'));
    return;
  }

  const mapsReady = new Promise((resolve, reject) => {
    if (window.google?.maps) {
      resolve(window.google.maps);
      return;
    }
    const callback = `dashvantiMapsReady${Date.now()}`;
    window[callback] = () => {
      resolve(window.google.maps);
      delete window[callback];
    };
    const script = document.createElement('script');
    const params = new URLSearchParams({key: apiKey, v: 'weekly', loading: 'async', libraries: 'places', callback});
    script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
    script.async = true;
    script.onerror = () => reject(new Error('Google Maps failed to load'));
    document.head.appendChild(script);
  });

  const states = new WeakMap();
  const geocodeCache = new Map();
  const geocodeAddress = (geocoder, address) => {
    const normalized = address.trim().toLowerCase();
    if (!geocodeCache.has(normalized)) {
      geocodeCache.set(normalized, new Promise((resolve, reject) => {
        geocoder.geocode({address}, async (results, status) => {
          if (status === 'OK' && results?.[0]) {resolve(results[0].geometry.location);return;}
          try {
            const {Place}=await google.maps.importLibrary('places');
            const {places}=await Place.searchByText({textQuery:address,fields:['location'],maxResultCount:1});
            if(!places?.[0]?.location)throw new Error('Restaurant location unavailable');
            resolve(places[0].location);
          }catch(error){geocodeCache.delete(normalized);reject(error);}
        });
      }));
    }
    return geocodeCache.get(normalized);
  };
  const markerData = (element) => {
    const rows = [];
    const scriptId = element.dataset.mapMarkersId;
    if (scriptId) {
      try {
        rows.push(...JSON.parse(document.getElementById(scriptId)?.textContent || '[]'));
      } catch (_) {
      }
    }
    if (element.dataset.mapAddress) {
      rows.push({id: 'primary', name: element.dataset.mapTitle || 'Location', address: element.dataset.mapAddress});
    }
    return rows.filter((row) => row.address || (
      window.dashvantiValidCoordinates(row)
    ));
  };
  const addMarker = (state, item, position) => {
    const labels = {driver: 'D', restaurant: 'R', destination: 'H'};
    const marker = new google.maps.Marker({
      map: state.map,
      position,
      title: item.name || item.address || 'Location',
      icon: item.type === 'driver' ? (document.querySelector('[data-order-alerts]')?.dataset.orderAlerts!=='driver' ? window.dashvantiSilverCarIcon() : {url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"64\" height=\"80\" viewBox=\"0 0 64 80\"><defs><linearGradient id=\"body\"><stop stop-color=\"#730d16\"/><stop offset=\".22\" stop-color=\"#ff6570\"/><stop offset=\".48\" stop-color=\"#ffb0b5\"/><stop offset=\".73\" stop-color=\"#c81e32\"/><stop offset=\"1\" stop-color=\"#680b17\"/></linearGradient><linearGradient id=\"glass\" x2=\".6\" y2=\"1\"><stop stop-color=\"#9ed8f0\"/><stop offset=\".4\" stop-color=\"#29495f\"/><stop offset=\"1\" stop-color=\"#101e30\"/></linearGradient><radialGradient id=\"shadow\"><stop stop-opacity=\".5\"/><stop offset=\"1\" stop-opacity=\"0\"/></radialGradient></defs><ellipse cx=\"34\" cy=\"43\" rx=\"27\" ry=\"37\" fill=\"url(#shadow)\"/><g fill=\"#151b24\"><rect x=\"12\" y=\"17\" width=\"8\" height=\"15\" rx=\"3\"/><rect x=\"44\" y=\"17\" width=\"8\" height=\"15\" rx=\"3\"/><rect x=\"12\" y=\"51\" width=\"8\" height=\"16\" rx=\"3\"/><rect x=\"44\" y=\"51\" width=\"8\" height=\"16\" rx=\"3\"/></g><path d=\"M20 7Q32 2 44 7Q49 11 49 24L48 64Q47 73 40 75H24Q17 73 16 64L15 24Q15 11 20 7Z\" fill=\"url(#body)\" stroke=\"#344454\" stroke-width=\"1.2\"/><path d=\"M21 11Q32 7 43 11L44 23Q32 19 20 23Z\" fill=\"#ff7882\" opacity=\".75\"/><path d=\"M20 26Q32 21 44 26L41 39H23Z\" fill=\"url(#glass)\" stroke=\"#526475\"/><path d=\"M24 40H40L42 54H22Z\" fill=\"url(#body)\" stroke=\"#9e1725\"/><path d=\"M22 56H42L44 65Q32 69 20 65Z\" fill=\"url(#glass)\" stroke=\"#526475\"/><path d=\"M18 30L21 40V52L18 57ZM46 30L43 40V52L46 57Z\" fill=\"#243e51\"/><path d=\"M22 27L40 25L25 36Z\" fill=\"#fff\" opacity=\".23\"/><g fill=\"#c9d6e0\" stroke=\"#405365\"><path d=\"M16 29L10 31V35L16 34Z\"/><path d=\"M48 29L54 31V35L48 34Z\"/></g><path d=\"M19 12L25 10M39 10L45 12\" stroke=\"#fffde0\" stroke-width=\"3.5\" stroke-linecap=\"round\"/><path d=\"M19 68L25 70M39 70L45 68\" stroke=\"#e53838\" stroke-width=\"3\" stroke-linecap=\"round\"/><path d=\"M25 7H39M24 73H40\" stroke=\"#273747\" stroke-width=\"2\"/><path d=\"M18 39V51M46 39V51\" stroke=\"#fff\" stroke-opacity=\".75\"/></svg>"), scaledSize: new google.maps.Size(48,60), anchor: new google.maps.Point(24,30)}) : undefined,
      label: item.type !== 'driver' && item.type && labels[item.type] ? {text: labels[item.type], color: '#ffffff', fontWeight: '800'} : undefined,
    });
    if (state.element.dataset.mapShowName === 'true' && item.name) {
      new google.maps.Marker({
        map: state.map, position, clickable: false,
        icon: {path: google.maps.SymbolPath.CIRCLE, scale: 0, labelOrigin: new google.maps.Point(0, 18)},
        label: {text: item.name, color: '#9b4312', fontSize: '14px', fontWeight: '700', className: 'restaurant-map-name'}
      });
    }
    const key = String(item.id ?? item.address);
    const entry = {marker, item, position};
    state.markers.set(key, entry);
    if (item.address) state.addresses.set(item.address.trim().toLowerCase(), entry);
    state.bounds.extend(position);
    const latitude = typeof position.lat === 'function' ? position.lat() : Number(position.lat);
    const longitude = typeof position.lng === 'function' ? position.lng() : Number(position.lng);
    document.dispatchEvent(new CustomEvent('dashvanti:map-marker-ready', {detail: {
      mapId: state.element.id,
      item,
      latitude,
      longitude,
    }}));
    marker.addListener('click', () => {
      const content = document.createElement('div');
      const title = document.createElement('strong');
      const address = document.createElement('div');
      title.textContent = item.name || 'Location';
      address.textContent = item.address || (
        Number.isFinite(Number(item.latitude))
          ? Number(item.latitude).toFixed(5) + ', ' + Number(item.longitude).toFixed(5)
          : 'Live location'
      );
      content.append(title, address);
      state.info.setContent(content);
      state.info.open({map: state.map, anchor: marker});
      document.dispatchEvent(new CustomEvent('dashvanti:map-marker-selected', {detail: {mapId: state.element.id, item}}));
    });
    return marker;
  };
  const updateDriverPosition = (state, location) => {
    if (!window.dashvantiValidCoordinates(location)) return;
    const target = {lat:Number(location.latitude), lng:Number(location.longitude)};
    let entry = state.markers.get('driver-self');
    if (!entry) {
      addMarker(state, {id:'driver-self', type:'driver', name:'Your live location'}, target);
      state.map.setCenter(target);
      state.map.setZoom(16);
      return;
    }
    cancelAnimationFrame(state.driverFrame);
    const previous = entry.marker.getPosition();
    const start = {lat:previous.lat(), lng:previous.lng()};
    const began = performance.now();
    const animate = now => {
      const fraction = Math.min(1,(now-began)/650);
      entry.marker.setPosition({lat:start.lat+(target.lat-start.lat)*fraction,lng:start.lng+(target.lng-start.lng)*fraction});
      if(fraction<1)state.driverFrame=requestAnimationFrame(animate);
    };
    state.driverFrame=requestAnimationFrame(animate);
    if(!state.map.getBounds()?.contains(target))state.map.panTo(target);
  };
  window.addEventListener('dashvanti:driver-position', event => {
    document.querySelectorAll('[data-map-driver-location="true"]').forEach(element => {
      const state=states.get(element);
      if(state)updateDriverPosition(state,event.detail);
    });
  });

  const initializeMap = async (element) => {
    if (states.has(element)) return states.get(element);
    await mapsReady;
    const map = new google.maps.Map(element, {
      center: {lat: 39.5, lng: -98.35},
      zoom: 4,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: true,
      gestureHandling: 'greedy',
    });
    const state = {element, map, geocoder: new google.maps.Geocoder(), info: new google.maps.InfoWindow(), bounds: new google.maps.LatLngBounds(), markers: new Map(), addresses: new Map()};
    states.set(element, state);
    element.dashvantiMapState = state;
    map.addListener('idle', () => {
      const bounds = map.getBounds();
      if (!bounds) return;
      const northEast = bounds.getNorthEast();
      const southWest = bounds.getSouthWest();
      document.dispatchEvent(new CustomEvent('dashvanti:map-bounds-changed', {detail: {
        mapId: element.id,
        north: northEast.lat(),
        east: northEast.lng(),
        south: southWest.lat(),
        west: southWest.lng(),
      }}));
    });
    const rows = markerData(element);
    const results = await Promise.allSettled(rows.map(async (item) => {
      const hasCoordinates = window.dashvantiValidCoordinates(item);
      const position = hasCoordinates
        ? {lat: Number(item.latitude), lng: Number(item.longitude)}
        : await geocodeAddress(state.geocoder, item.address);
      return addMarker(state, item, position);
    }));
    const found = results.filter((result) => result.status === 'fulfilled').length;
    if (found > 1) map.fitBounds(state.bounds, 42);
    else if (found === 1) {
      map.setCenter(state.bounds.getCenter());
      map.setZoom(14);
    }
    if (element.dataset.mapCurrentLocation === 'true' && navigator.geolocation) {
      navigator.geolocation.getCurrentPosition((position) => {
        const current = {lat: position.coords.latitude, lng: position.coords.longitude};
        new google.maps.Marker({map, position: current, title: 'Your current location', icon: {path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: '#20583e', fillOpacity: 1, strokeColor: '#ffffff', strokeWeight: 3}});
        document.dispatchEvent(new CustomEvent('dashvanti:customer-position', {detail: {
          mapId: element.id,
          latitude: current.lat,
          longitude: current.lng,
        }}));
        if (!found) {
          map.setCenter(current);
          map.setZoom(13);
        }
      }, () => {}, {enableHighAccuracy: true, maximumAge: 10000, timeout: 15000});
    }
    setStatus(element, found ? `${found} location${found === 1 ? '' : 's'} pinned` : 'Map ready');
    if(element.dataset.mapDriverLocation === 'true' && window.dashvantiDriverPosition)updateDriverPosition(state,window.dashvantiDriverPosition);
    return state;
  };
  const selectLocation = async (detail) => {
    const element = document.getElementById(detail.mapId);
    if (!element) return;
    const state = await initializeMap(element);
    google.maps.event.trigger(state.map, 'resize');
    let entry = detail.id ? state.markers.get(String(detail.id)) : null;
    if (!entry && detail.address) entry = state.addresses.get(detail.address.trim().toLowerCase());
    if (!entry && detail.address) {
      const item = {id: detail.id || detail.address, name: detail.name || 'Selected location', address: detail.address};
      entry = {marker: addMarker(state, item, await geocodeAddress(state.geocoder, item.address)), item, position: state.addresses.get(item.address.trim().toLowerCase()).position};
    }
    if (!entry) return;
    state.map.panTo(entry.position);
    state.map.setZoom(15);
    entry.marker.setAnimation(google.maps.Animation.BOUNCE);
    window.setTimeout(() => entry.marker.setAnimation(null), 700);
  };

  const updateMapPosition = async (detail) => {
    const element = document.getElementById(detail.mapId);
    if (!element) return;
    const latitude = Number(detail.latitude);
    const longitude = Number(detail.longitude);
    if (!window.dashvantiValidCoordinates(detail)) return;
    const state = await initializeMap(element);
    const key = String(detail.id);
    const position = {lat: latitude, lng: longitude};
    let entry = state.markers.get(key);
    if (entry) {
      entry.marker.setPosition(position);
      entry.position = position;
      entry.item = {...entry.item, ...detail};
    } else {
      addMarker(state, {...detail, address: ''}, position);
      entry = state.markers.get(key);
    }
    const bounds = new google.maps.LatLngBounds();
    state.markers.forEach((value) => bounds.extend(value.position));
    state.map.fitBounds(bounds, 56);
    setStatus(element, 'Live locations updated');
  };

  const emitAddress = (result, label = '') => {
    const location = result.geometry?.location || result.location;
    if (!location) return;
    document.dispatchEvent(new CustomEvent('dashvanti:address-selected', {detail: {
      address: result.formatted_address || result.formattedAddress || label,
      latitude: location.lat(),
      longitude: location.lng(),
    }}));
  };
  let addressLookupVersion=0;
  const lookupAddress = async (address) => {
    const version=++addressLookupVersion;
    await mapsReady;
    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({address}, async (results, status) => {
      if(version!==addressLookupVersion)return;
      if(status==='OK'&&results?.[0]){emitAddress(results[0],address);return;}
      try {
        const {Place}=await google.maps.importLibrary('places');
        const {places}=await Place.searchByText({textQuery:address,fields:['location','formattedAddress'],maxResultCount:1});
        if(version!==addressLookupVersion)return;
        if(places?.[0]?.location){emitAddress(places[0],address);return;}
        throw new Error('No matching address. Search and choose an address suggestion.');
      }catch(error){
        if(version!==addressLookupVersion)return;
        document.dispatchEvent(new CustomEvent('dashvanti:address-error',{detail:{message:status==='REQUEST_DENIED'?'Address lookup is unavailable. Please choose the address from search suggestions.':error.message}}));
      }
    });
  };
  document.addEventListener('dashvanti:cancel-address-lookup',()=>{addressLookupVersion++;});
  const useCurrentAddress = async () => {
    await mapsReady;
    if (!navigator.geolocation) {
      document.dispatchEvent(new CustomEvent('dashvanti:address-error', {detail: {message: 'Live location is unavailable'}}));
      return;
    }
    navigator.geolocation.getCurrentPosition((position) => {
      const location = {lat: position.coords.latitude, lng: position.coords.longitude};
      new google.maps.Geocoder().geocode({location}, (results, status) => {
        if (status === 'OK' && results?.[0]) emitAddress(results[0]);
        else document.dispatchEvent(new CustomEvent('dashvanti:address-selected', {detail: {
          address: location.lat.toFixed(5) + ', ' + location.lng.toFixed(5),
          latitude: location.lat,
          longitude: location.lng,
        }}));
      });
    }, () => {
      document.dispatchEvent(new CustomEvent('dashvanti:address-error', {detail: {message: 'Allow location access and try again'}}));
    }, {enableHighAccuracy: true, maximumAge: 5000, timeout: 15000});
  };
  const initializeAddressSearch = async () => {
    const {PlaceAutocompleteElement} = await google.maps.importLibrary('places');
    document.querySelectorAll('[data-address-autocomplete]').forEach((widget) => {
      if (!(widget instanceof PlaceAutocompleteElement)) return;
      if (widget.hasAttribute('data-saved-address')) {
        widget.addEventListener('input', () => {
          const form = widget.closest('form');
          form.elements.details.value = '';
          form.elements.place_id.value = '';
        });
      }
      widget.addEventListener('gmp-select', async ({placePrediction}) => {
        const place = placePrediction.toPlace();
        try {
          await place.fetchFields({fields: ['id', 'formattedAddress', 'location']});
          if (widget.hasAttribute('data-saved-address')) {
            const form = widget.closest('form');
            form.elements.details.value = place.formattedAddress || '';
            form.elements.place_id.value = place.id || '';
            document.querySelector('[data-address-search-status]').textContent = 'Address selected. Add a label and save.';
          } else emitAddress(place);
        } catch (_) {
          const status = document.querySelector('[data-address-search-status]');
          if (status) status.textContent = 'Address lookup failed. Please try again.';
        }
      });
    });
  };

  document.addEventListener('dashvanti:map-select', (event) => selectLocation(event.detail).catch(() => {}));
  document.addEventListener('dashvanti:map-position', (event) => updateMapPosition(event.detail).catch(() => {}));
  document.addEventListener('dashvanti:address-geocode', (event) => lookupAddress(event.detail.address).catch(() => {}));
  document.addEventListener('dashvanti:use-current-location', () => useCurrentAddress().catch(() => {}));
  mapsReady.then(async () => {
    await initializeAddressSearch();
    return Promise.all(mapElements.filter((element) => !element.closest('.is-hidden')).map(initializeMap));
  }).catch(() => {
    mapElements.forEach((element) => setStatus(element, 'Google Maps could not load'));
    document.dispatchEvent(new CustomEvent('dashvanti:address-error', {detail: {message: 'Google Maps could not load'}}));
  });
})();
