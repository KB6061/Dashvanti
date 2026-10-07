(() => {
  let places;
  async function library() {
    if (!places) places = (async () => {
      for (let attempt = 0; attempt < 100; attempt++) {
        if (window.google?.maps?.importLibrary) return google.maps.importLibrary('places');
        await new Promise(resolve => setTimeout(resolve, 150));
      }
      throw new Error('Address suggestions are unavailable. You can enter the address manually.');
    })().catch(error => { places = null; throw error; });
    return places;
  }
  async function initialize() {
    for (const widget of document.querySelectorAll('[data-account-address-search]:not([data-ready])')) {
      widget.dataset.ready = 'true';
      const form = widget.closest('form'), status = form.querySelector('[data-account-address-status]');
      const field = name => form.elements.namedItem(name);
      let version = 0;
      const clearCoordinates = () => { version++; field('latitude').value = ''; field('longitude').value = ''; };
      const region = () => { widget.includedRegionCodes = [field('country').value.toLowerCase()]; };
      widget.addEventListener('input', () => { clearCoordinates(); status.textContent = ''; });
      field('details').addEventListener('input', clearCoordinates);
      field('country').addEventListener('change', () => { clearCoordinates(); region(); });
      try {
        await library();
        if (!widget.isConnected) continue;
        region();
        widget.addEventListener('gmp-error', () => { status.textContent = 'Suggestions unavailable. Enter your address manually.'; status.classList.add('account-error'); });
        widget.addEventListener('gmp-select', async ({placePrediction}) => {
          const selected = ++version;
          status.textContent = 'Loading address…'; status.classList.remove('account-error');
          try {
            const place = placePrediction.toPlace();
            await place.fetchFields({fields: ['formattedAddress', 'location', 'addressComponents']});
            if (selected !== version || !widget.isConnected) return;
            if (!place.location) throw new Error('Select an address with a map location.');
            const component = (type, short = false) => {
              const value = place.addressComponents?.find(item => item.types.includes(type));
              return value?.[short ? 'shortText' : 'longText'] || '';
            };
            const country = component('country', true);
            if (!['US', 'IN'].includes(country)) throw new Error('Choose an address in the United States or India.');
            field('details').value = place.formattedAddress || '';
            field('city').value = component('locality') || component('postal_town') || component('administrative_area_level_3');
            field('state').value = component('administrative_area_level_1');
            field('zip_code').value = component('postal_code');
            field('country').value = country;
            field('latitude').value = place.location.lat();
            field('longitude').value = place.location.lng();
            status.textContent = 'Address selected. Add your apartment or instructions and save.';
          } catch (error) {
            if (selected !== version) return;
            clearCoordinates(); status.textContent = error.message; status.classList.add('account-error');
          }
        });
      } catch (error) { status.textContent = error.message; status.classList.add('account-error'); }
    }
  }
  initialize();
  window.addEventListener('dashvanti:account-panel', initialize);
})();
