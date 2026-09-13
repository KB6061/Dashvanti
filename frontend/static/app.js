const tracker = document.querySelector('[data-track]');
if (tracker) {
  const updateTimeline = (history) => {
    const timeline = document.getElementById('timeline');
    if (!timeline || !Array.isArray(history)) return;
    timeline.replaceChildren(...history.map((event) => {
      const item = document.createElement('li');
      item.textContent = event.status + ' · ' + event.created_at;
      return item;
    }));
  };
  const timer = setInterval(async () => {
    if (document.hidden) return;
    try {
      const response = await fetch(location.pathname + '?poll=1', {
        credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'X-Requested-With': 'fetch'},
      });
      if (!response.ok || response.redirected) return;
      const data = await response.json();
      const status = document.getElementById('order-status');
      if (status) status.textContent = ['ACCEPTED','CONFIRMED','PREPARING'].includes(data.order.status) ? 'Preparing Order' : data.order.status.replaceAll('_', ' ');
      const driverInfo = document.getElementById('driver-info');
      if (driverInfo) {
        driverInfo.textContent = data.driver
          ? 'Driver: ' + data.driver.name + ' · ' + data.driver.phone + (data.driver.vehicle_type ? ' · ' + data.driver.vehicle_type + ' ' + data.driver.vehicle_number : '')
          : 'Driver not assigned';
      }
      const assignment = document.getElementById('driver-assignment-status');
      const vehicle = document.getElementById('driver-vehicle');
      const driverLocation = document.getElementById('driver-location');
      if (assignment) assignment.textContent = data.driver ? data.driver.name + ' is assigned to your order.' : 'Waiting for a delivery partner.';
      if (vehicle) vehicle.textContent = data.driver ? ((data.driver.vehicle_type || 'Vehicle') + ' ' + (data.driver.vehicle_number || '')).trim() : '';
      if (driverLocation) {
        driverLocation.textContent = data.driver_location
          ? 'Live location: ' + Number(data.driver_location.latitude).toFixed(5) + ', ' + Number(data.driver_location.longitude).toFixed(5)
          : 'Waiting for live GPS signal.';
      }
      if (data.driver_location) {
        document.dispatchEvent(new CustomEvent('dashvanti:map-position', {detail: {
          mapId: 'customer-order-map',
          id: 'driver',
          name: data.driver?.name || 'Delivery partner',
          type: 'driver',
          latitude: Number(data.driver_location.latitude),
          longitude: Number(data.driver_location.longitude),
        }}));
      }
      updateTimeline(data.history);
      if (['DELIVERED', 'REJECTED'].includes(data.order.status)) clearInterval(timer);
    } catch (_) {
    }
  }, 5000);
}


if (document.querySelector('[data-auto-refresh]') && !document.querySelector('[data-order-alerts]')) {
  setTimeout(() => {
    if (!document.hidden) location.reload();
  }, 15000);
}

const accountDrawer = document.querySelector('.account-drawer');
const accountBackdrop = document.querySelector('.account-backdrop');
const accountOpen = document.querySelector('[data-account-open]');
const accountClosers = document.querySelectorAll('[data-account-close]');
function setAccount(open) {
  if (!accountDrawer || !accountBackdrop) return;
  accountDrawer.classList.toggle('open', open);
  accountBackdrop.classList.toggle('open', open);
  accountDrawer.setAttribute('aria-hidden', open ? 'false' : 'true');
}
if (accountOpen) accountOpen.addEventListener('click', () => setAccount(!accountDrawer.classList.contains('open')));
accountClosers.forEach((button) => button.addEventListener('click', () => setAccount(false)));
document.addEventListener('click', (event) => {
  if (accountDrawer?.classList.contains('open') && !event.target.closest('.account-drawer,[data-account-open]')) setAccount(false);
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') setAccount(false);
});

const logoutModal = document.querySelector('.logout-modal');
const logoutBackdrop = document.querySelector('.logout-modal-backdrop');
const logoutOpen = document.querySelector('[data-logout-open]');
const logoutClosers = document.querySelectorAll('[data-logout-close]');
function setLogout(open) {
  if (!logoutModal || !logoutBackdrop) return;
  logoutModal.classList.toggle('open', open);
  logoutBackdrop.classList.toggle('open', open);
  logoutModal.setAttribute('aria-hidden', open ? 'false' : 'true');
}
if (logoutOpen) logoutOpen.addEventListener('click', () => setLogout(true));
logoutClosers.forEach((button) => button.addEventListener('click', () => setLogout(false)));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') setLogout(false);
});

const authModal = document.querySelector('.auth-modal');
const authBackdrop = document.querySelector('.auth-modal-backdrop');
const authOpeners = document.querySelectorAll('[data-auth-open]');
const authClosers = document.querySelectorAll('[data-auth-close]');
const authTabs = document.querySelectorAll('[data-auth-tab]');
const authPanels = document.querySelectorAll('[data-auth-panel]');
function setAuthTab(name) {
  authTabs.forEach((tab) => tab.classList.toggle('active', tab.dataset.authTab === name));
  authPanels.forEach((panel) => panel.classList.toggle('active', panel.dataset.authPanel === name));
}
function setAuth(open, tabName) {
  if (!authModal || !authBackdrop) return;
  if (tabName) setAuthTab(tabName);
  authModal.classList.toggle('open', open);
  authBackdrop.classList.toggle('open', open);
  authModal.setAttribute('aria-hidden', open ? 'false' : 'true');
}
authOpeners.forEach((button) => button.addEventListener('click', () => setAuth(true, button.dataset.authOpen)));
authClosers.forEach((button) => button.addEventListener('click', () => setAuth(false)));
authTabs.forEach((button) => button.addEventListener('click', () => setAuthTab(button.dataset.authTab)));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') setAuth(false);
});

document.querySelectorAll('[data-cart-line]').forEach((line) => {
  const input = line.querySelector('[data-cart-quantity]');
  const total = line.querySelector('[data-line-total]');
  const price = Number(line.dataset.price || 0);
  if (!input || !total) return;
  input.addEventListener('input', () => {
    const quantity = Math.max(0, Number(input.value || 0));
    total.textContent = `$${(price * quantity).toFixed(2)}`;
  });
});

const cartLayout = document.querySelector('[data-cart-layout]');
if (cartLayout) {
  const cartStatus = document.querySelector('[data-cart-status]');
  const emptyCart = document.querySelector('[data-cart-empty]');
  const money = (value) => `$${Number(value || 0).toFixed(2)}`;
  const updateText = (selector, value) => {
    const node = document.querySelector(selector);
    if (node) node.textContent = value;
  };
  document.querySelectorAll('[data-cart-update]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitter = event.submitter;
      const formData = new FormData(form);
      if (submitter && submitter.name) formData.set(submitter.name, submitter.value);
      form.querySelectorAll('button').forEach((button) => { button.disabled = true; });
      try {
        const response = await fetch(form.action || location.pathname, {
          method: 'POST',
          body: formData,
          credentials: 'same-origin',
          headers: {'X-Requested-With': 'fetch'},
        });
        if (!response.ok) throw new Error('Cart update failed');
        const cart = await response.json();
        const menuItemId = String(formData.get('menu_item_id'));
        const item = cart.items.find((row) => String(row.menu_item_id) === menuItemId);
        const row = form.closest('.cart-item-row');
        if (item && row) {
          const quantity = Number(item.quantity);
          row.querySelector('[data-cart-quantity]').textContent = quantity;
          row.querySelector('[data-line-total]').textContent = money(item.subtotal);
          const decrease = row.querySelector('[data-cart-decrease]');
          const increase = row.querySelector('[data-cart-increase]');
          if (decrease) decrease.value = Math.max(0, quantity - 1);
          if (increase) {
            increase.value = quantity + 1;
            increase.disabled = quantity >= 50;
          }
        } else if (row) {
          const group = row.closest('[data-cart-group]');
          row.remove();
          if (group && !group.querySelector('.cart-item-row')) group.remove();
        }
        cart.groups.forEach((group) => {
          const total = document.querySelector(`[data-cart-group="${group.restaurant_id}"] [data-cart-group-subtotal]`);
          if (total) total.textContent = money(group.subtotal);
        });
        updateText('[data-cart-subtotal]', money(cart.subtotal));
        updateText('[data-cart-tax]', money(cart.tax));
        updateText('[data-cart-service-fee]', money(cart.service_fee));
        updateText('[data-cart-discount]', money(cart.discount));
        updateText('[data-cart-total]', money(cart.total));
        const cartCount = document.querySelector('.customer-cart-link strong');
        if (cartCount) cartCount.textContent = cart.cart_count;
        if (!cart.items.length) {
          cartLayout.hidden = true;
          if (emptyCart) emptyCart.hidden = false;
        }
        if (cartStatus) cartStatus.textContent = 'Cart updated';
      } catch (_) {
        if (cartStatus) cartStatus.textContent = 'Unable to update cart. Please try again.';
      } finally {
        form.querySelectorAll('button').forEach((button) => { button.disabled = button.matches('[data-cart-increase]') && Number(button.value) > 50; });
      }
    });
  });
}


const orderModeForm = document.querySelector('[data-order-mode-form]');
if (orderModeForm) {
  document.querySelectorAll('[data-order-mode]').forEach((link) => {
    link.addEventListener('click', async (event) => {
      event.preventDefault();
      const mode = link.dataset.orderMode;
      if (link.classList.contains('active')) return;
      const formData = new FormData(orderModeForm);
      formData.set('mode', mode);
      link.closest('.customer-mode')?.classList.add('is-updating');
      try {
        const response = await fetch(orderModeForm.action, {
          method: 'POST', body: formData, credentials: 'same-origin',
          headers: {'X-Requested-With': 'fetch'},
        });
        if (!response.ok) throw new Error('Order mode update failed');
        document.querySelectorAll('[data-order-mode]').forEach((item) => item.classList.toggle('active', item.dataset.orderMode === mode));
        setCustomerOrderMode(mode);
      } catch (_) {
      } finally {
        link.closest('.customer-mode')?.classList.remove('is-updating');
      }
    });
  });
}

const profilePhotoForm = document.querySelector('[data-profile-photo-form]');
if (profilePhotoForm) {
  const photoInput = profilePhotoForm.querySelector('input[type="file"]');
  const photoButton = profilePhotoForm.querySelector('[data-profile-photo-open]');
  photoButton?.addEventListener('click', () => photoInput?.click());
  photoInput?.addEventListener('change', async () => {
    if (!photoInput.files?.length) return;
    const formData = new FormData(profilePhotoForm);
    photoButton.disabled = true;
    try {
      const response = await fetch(profilePhotoForm.action, {
        method: 'POST', body: formData, credentials: 'same-origin',
        headers: {'X-Requested-With': 'fetch'},
      });
      if (!response.ok) throw new Error('Profile photo upload failed');
      const photo = await response.json();
      const image = document.createElement('img');
      image.src = photo.url;
      image.alt = 'Profile photo';
      photoButton.replaceChildren(image);
    } finally {
      photoButton.disabled = false;
      photoInput.value = '';
    }
  });
}


const customerLocationForm = document.querySelector('[data-customer-location-form]');
if (customerLocationForm && navigator.geolocation) {
  const locationText = document.querySelector('[data-customer-location-text]');
  const locationStatus = document.querySelector('[data-customer-location-status]');
  let lastLocationSave = 0;
  const saveLocation = async (position) => {
    const {latitude, longitude} = position.coords;
    if (!window.dashvantiManualAddress) {
      if (locationText) locationText.textContent = latitude.toFixed(5) + ', ' + longitude.toFixed(5);
      if (locationStatus) locationStatus.textContent = 'Live GPS updating';
    }
    if (Date.now() - lastLocationSave < 15000) return;
    lastLocationSave = Date.now();
    const formData = new FormData(customerLocationForm);
    formData.set('latitude', latitude);
    formData.set('longitude', longitude);
    try {
      const response = await fetch(customerLocationForm.action, {
        method: 'POST', body: formData, credentials: 'same-origin',
        headers: {'X-Requested-With': 'fetch'},
      });
      if (!response.ok) throw new Error('Location update failed');
      if (locationStatus) locationStatus.textContent = 'Live GPS saved';
    } catch (_) {
      if (locationStatus) locationStatus.textContent = 'Live GPS unavailable';
    }
  };
  navigator.geolocation.watchPosition(saveLocation, () => {
    if (window.dashvantiManualAddress) return;
    if (locationText) locationText.textContent = 'Search and select your address';
    if (locationStatus) locationStatus.textContent = 'Live GPS needs location permission';
  }, {enableHighAccuracy: true, maximumAge: 10000, timeout: 15000});
}

const customerDashboard = document.querySelector('body.customer-dashboard-page');
if (customerDashboard) {
  let dashboardRequest = 0;
  let dashboardAbort;
  let searchTimer;
  const replaceDashboardSection = (documentFragment, selector) => {
    const current = document.querySelector(selector);
    const incoming = documentFragment.querySelector(selector);
    if (current && incoming) current.replaceWith(incoming);
  };
  const updateDashboard = async (url) => {
    const request = ++dashboardRequest;
    dashboardAbort?.abort();dashboardAbort=new AbortController();
    const response = await fetch(url, {signal:dashboardAbort.signal, credentials: 'same-origin', headers: {'X-Requested-With': 'fetch'}});
    if (!response.ok || response.redirected) throw new Error('Dashboard update failed');
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    if (request !== dashboardRequest) return;
    replaceDashboardSection(page, '#menu-board .customer-section-head');
    replaceDashboardSection(page, '#menu-board [data-restaurant-shelves]');
    replaceDashboardSection(page, '#menu-board .restaurant-list-heading');
    replaceDashboardSection(page, '#menu-board .restaurant-mini-list');
  };
  const updateDashboardCart = async () => {
    const response = await fetch(location.pathname, {credentials: 'same-origin', headers: {'X-Requested-With': 'fetch'}});
    if (!response.ok || response.redirected) throw new Error('Cart refresh failed');
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    replaceDashboardSection(page, '.customer-right-rail .cart-panel');
    replaceDashboardSection(page, '.customer-topbar .customer-cart-link');
  };
  const submitSearch = () => {
    const form = document.querySelector('.customer-search');
    if (!form) return;
    const url = new URL(form.action, location.origin);
    const query = form.querySelector('[name=q]')?.value.trim() || '';
    if (query) url.searchParams.set('q', query);
    else url.searchParams.delete('q');
    updateDashboard(url).catch(() => {});
  };
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (form.matches('.customer-search')) {
      event.preventDefault();
      clearTimeout(searchTimer);
      submitSearch();
      return;
    }
    if (!form.matches('#menu-board .food-card form[action="/customer/cart"]')) return;
    event.preventDefault();
    const button = event.submitter || form.querySelector('button');
    const formData = new FormData(form);
    if (button) button.disabled = true;
    fetch(form.action, {method: 'POST', body: formData, credentials: 'same-origin', headers: {'X-Requested-With': 'fetch'}})
      .then((response) => {
        if (!response.ok) throw new Error('Cart update failed');
        return updateDashboardCart();
      })
      .catch(() => {})
      .finally(() => { if (button) button.disabled = false; });
  });
  document.addEventListener('click', (event) => {
    const link = event.target.closest('#menu-board .category-strip a, #menu-board .customer-section-head a');
    if (!link) return;
    event.preventDefault();
    updateDashboard(link.href).catch(() => {});
  });
  document.querySelector('.customer-search [name=q]')?.addEventListener('input', () => {
    clearTimeout(searchTimer);
    submitSearch();
  });
}


document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!form.matches('[data-menu-cart-add]')) return;
  event.preventDefault();
  const button = event.submitter || form.querySelector('button');
  const status = form.closest('.customer-menu-details')?.querySelector('[data-menu-add-status]');
  if (button) button.disabled = true;
  try {
    const response = await fetch(form.action, {
      method: 'POST', body: new FormData(form), credentials: 'same-origin',
      headers: {'X-Requested-With': 'fetch'},
    });
    if (!response.ok) throw new Error('Cart update failed');
    const cart = await response.json();
    const count = document.querySelector('.customer-cart-link strong');
    if (count) count.textContent = cart.cart_count;
    if (status) status.textContent = 'Added to cart';
  } catch (_) {
    if (status) status.textContent = 'Try again';
  } finally {
    if (button) button.disabled = false;
  }
});


const pickupExplorerPanel = document.querySelector('[data-pickup-explorer]');
const pickupRestaurantPositions = new Map();
const initialPickupLatitudeValue = pickupExplorerPanel?.dataset.customerLatitude || '';
const initialPickupLongitudeValue = pickupExplorerPanel?.dataset.customerLongitude || '';
const initialPickupLatitude = initialPickupLatitudeValue ? Number(initialPickupLatitudeValue) : Number.NaN;
const initialPickupLongitude = initialPickupLongitudeValue ? Number(initialPickupLongitudeValue) : Number.NaN;
let pickupCustomerPosition = Number.isFinite(initialPickupLatitude) && Number.isFinite(initialPickupLongitude)
  ? {latitude: initialPickupLatitude, longitude: initialPickupLongitude}
  : null;
let pickupMapBounds = null;
const pickupDistanceRequests = new WeakMap();
function updatePickupDistances() {
  document.querySelectorAll('[data-pickup-store]').forEach((store) => {
    const position = pickupRestaurantPositions.get(store.dataset.restaurantId);
    const output = store.querySelector('[data-restaurant-distance]');
    if (!output) return;
    if (!pickupCustomerPosition || !position) {
      output.textContent = 'Distance unavailable';
      pickupDistanceRequests.delete(output);
      return;
    }
    const key=JSON.stringify([pickupCustomerPosition,position]);
    if(pickupDistanceRequests.get(output)===key)return;
    pickupDistanceRequests.set(output,key);output.textContent='Calculating distance…';
    window.dashvantiDistance(pickupCustomerPosition,position).then(result=>{
      if(pickupDistanceRequests.get(output)!==key)return;
      const miles=result.distance_miles<0.1&&result.distance_meters>0?'<0.1':result.distance_miles.toFixed(1);
      output.textContent=miles+' mi · '+result.drive_minutes+' min drive';
    }).catch(()=>{
      if(pickupDistanceRequests.get(output)!==key)return;
      output.textContent='Distance unavailable';pickupDistanceRequests.delete(output);
    });
  });
}
function positionInsidePickupBounds(position, bounds) {
  if (!position || !bounds) return true;
  const latitudeMatches = position.latitude >= bounds.south && position.latitude <= bounds.north;
  const longitudeMatches = bounds.west <= bounds.east
    ? position.longitude >= bounds.west && position.longitude <= bounds.east
    : position.longitude >= bounds.west || position.longitude <= bounds.east;
  return latitudeMatches && longitudeMatches;
}
function filterPickupStores() {
  const stores = [...document.querySelectorAll('[data-pickup-store]')];
  const enabled = document.querySelector('[data-map-search-move]')?.checked;
  let visible = 0;
  stores.forEach((store) => {
    const matches = !enabled || !pickupMapBounds
      || positionInsidePickupBounds(pickupRestaurantPositions.get(store.dataset.restaurantId), pickupMapBounds);
    store.hidden = !matches;
    if (matches) visible += 1;
  });
  const count = document.querySelector('[data-pickup-count]');
  if (count) count.textContent = enabled ? visible + ' in map' : stores.length + ' restaurants';
}
document.addEventListener('dashvanti:map-marker-ready', (event) => {
  if (event.detail.mapId !== 'customer-pickup-map' || event.detail.item?.type) return;
  if (!window.dashvantiValidCoordinates(event.detail)) return;
  pickupRestaurantPositions.set(String(event.detail.item.id), {
    latitude: Number(event.detail.latitude),
    longitude: Number(event.detail.longitude),
  });
  const selectedStore=document.querySelector('[data-pickup-store].selected');
  if(selectedStore?.dataset.restaurantId===String(event.detail.item.id)) selectPickupStore(selectedStore);
  updatePickupDistances();
  filterPickupStores();
});
document.addEventListener('dashvanti:customer-position', (event) => {
  if (event.detail.mapId !== 'customer-pickup-map') return;
  if (!window.dashvantiValidCoordinates(event.detail)) return;
  pickupCustomerPosition = {
    latitude: Number(event.detail.latitude),
    longitude: Number(event.detail.longitude),
  };
  updatePickupDistances();
});
document.addEventListener('dashvanti:map-bounds-changed', (event) => {
  if (event.detail.mapId !== 'customer-pickup-map') return;
  pickupMapBounds = event.detail;
  filterPickupStores();
});
document.addEventListener('dashvanti:address-selected', (event) => {
  const latitude = Number(event.detail?.latitude);
  const longitude = Number(event.detail?.longitude);
  if (!window.dashvantiValidCoordinates(event.detail)) return;
  pickupCustomerPosition = {latitude, longitude};
  updatePickupDistances();
});
document.addEventListener('change', (event) => {
  if (event.target.matches('[data-map-search-move]')) filterPickupStores();
});

function selectPickupStore(store) {
  if (!store) return;
  document.querySelectorAll('[data-pickup-store]').forEach((item) => item.classList.toggle('selected', item === store));
  const name = document.querySelector('[data-pickup-map-name]');
  const address = document.querySelector('[data-pickup-map-address]');
  if (name) name.textContent = store.dataset.restaurantName;
  if (address) address.textContent = store.dataset.restaurantAddress || 'Restaurant address unavailable';
  document.dispatchEvent(new CustomEvent('dashvanti:map-select', {detail: {
    mapId: 'customer-pickup-map',
    id: store.dataset.restaurantId,
    name: store.dataset.restaurantName,
    address: store.dataset.restaurantAddress,
  }}));
}
function setCustomerOrderMode(mode) {
  const pickup = document.querySelector('[data-pickup-explorer]');
  const delivery = document.querySelector('[data-delivery-browser]');
  if (!pickup || !delivery) return;
  const isPickup = mode === 'pickup';
  pickup.classList.toggle('is-hidden', !isPickup);
  delivery.classList.toggle('is-hidden', isPickup);
  document.body.classList.toggle('pickup-mode', isPickup);
  if (isPickup) selectPickupStore(document.querySelector('[data-pickup-store].selected') || document.querySelector('[data-pickup-store]'));
}
document.addEventListener('click', (event) => {
  const modeButton = event.target.closest('[data-order-mode]');
  if (modeButton) {
    document.querySelectorAll('[data-order-mode]').forEach((item) => item.classList.toggle('active', item === modeButton));
    setCustomerOrderMode(modeButton.dataset.orderMode);
  }
  const storeButton = event.target.closest('[data-pickup-store-select]');
  if (storeButton) selectPickupStore(storeButton.closest('[data-pickup-store]'));
  const arrow = event.target.closest('[data-menu-scroll]');
  if (arrow) {
    const rail = arrow.closest('.pickup-menu-carousel')?.querySelector('[data-menu-rail]');
    if (rail) {
      const card = rail.querySelector('.pickup-menu-card');
      const distance = (card?.getBoundingClientRect().width || 110) + 8;
      rail.scrollBy({left: Number(arrow.dataset.menuScroll) * distance, behavior: 'smooth'});
    }
  }
});
document.addEventListener('dashvanti:map-marker-selected', (event) => {
  if (event.detail.mapId !== 'customer-pickup-map') return;
  const store = [...document.querySelectorAll('[data-pickup-store]')].find((item) => item.dataset.restaurantId === String(event.detail.item.id));
  if (store) selectPickupStore(store);
});
const selectedOrderMode = document.querySelector('[data-order-mode].active')?.dataset.orderMode;
if (selectedOrderMode) setCustomerOrderMode(selectedOrderMode);


const addressDrawer = document.querySelector('[data-address-drawer]');
const addressBackdrop = document.querySelector('.customer-address-backdrop');
const addressInput = document.querySelector('[data-address-autocomplete]');
const addressStatus = document.querySelector('[data-address-status]');
function setAddressDrawer(open) {
  if (!addressDrawer || !addressBackdrop) return;
  addressDrawer.classList.toggle('open', open);
  addressBackdrop.classList.toggle('open', open);
  addressDrawer.setAttribute('aria-hidden', open ? 'false' : 'true');
  document.body.classList.toggle('address-drawer-open', open);
  if (open) window.setTimeout(() => addressInput?.focus(), 120);
}
async function saveSelectedAddress(detail) {
  if (!customerLocationForm || !detail?.address) return;
  if (addressStatus) addressStatus.textContent = 'Saving address…';
  const formData = new FormData(customerLocationForm);
  formData.set('latitude', detail.latitude);
  formData.set('longitude', detail.longitude);
  formData.set('address', detail.address);
  try {
    const response = await fetch(customerLocationForm.action, {
      method: 'POST',
      body: formData,
      credentials: 'same-origin',
      headers: {'X-Requested-With': 'fetch'},
    });
    if (!response.ok) throw new Error('Address update failed');
    window.dashvantiManualAddress = true;
    const locationText = document.querySelector('[data-customer-location-text]');
    const locationStatus = document.querySelector('[data-customer-location-status]');
    const headerAddress = document.querySelector('[data-customer-header-address]');
    if (locationText) locationText.textContent = detail.address;
    if (locationStatus) locationStatus.textContent = 'Google Maps address saved';
    if (headerAddress) headerAddress.textContent = detail.address.length > 28 ? detail.address.slice(0, 27) + '…' : detail.address;
    if (addressInput) addressInput.value = detail.address;
    if (addressStatus) addressStatus.textContent = 'Current address saved';
    document.querySelectorAll('[data-saved-address]').forEach((item) => item.classList.toggle('selected', item.dataset.address === detail.address));
    document.dispatchEvent(new CustomEvent('dashvanti:map-select', {detail: {
      mapId: 'customer-pickup-map',
      id: 'customer-current-address',
      name: 'Your selected address',
      address: detail.address,
    }}));
    window.setTimeout(() => setAddressDrawer(false), 350);
  } catch (_) {
    if (addressStatus) addressStatus.textContent = 'Address could not be saved. Try again.';
  }
}
document.addEventListener('click', (event) => {
  if (event.target.closest('[data-address-open]')) setAddressDrawer(true);
  if (event.target.closest('[data-address-close]')) setAddressDrawer(false);
  const liveLocation = event.target.closest('[data-use-live-location]');
  if (liveLocation) {
    if (addressStatus) addressStatus.textContent = 'Finding your live location…';
    document.dispatchEvent(new CustomEvent('dashvanti:use-current-location'));
  }
  const savedAddress = event.target.closest('[data-saved-address]');
  if (savedAddress) {
    if (addressStatus) addressStatus.textContent = 'Locating saved address…';
    document.dispatchEvent(new CustomEvent('dashvanti:address-geocode', {detail: {address: savedAddress.dataset.address}}));
  }
});
document.addEventListener('dashvanti:address-selected', (event) => saveSelectedAddress(event.detail));
document.addEventListener('dashvanti:address-error', (event) => {
  if (addressStatus) addressStatus.textContent = event.detail?.message || 'Location unavailable';
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') setAddressDrawer(false);
});

const customerSearchInput = document.querySelector('.customer-search [name="q"]');
const customerSearchPanel = document.querySelector('[data-search-suggestions]');
let customerSearchTimer;
let customerSearchAbort;
let customerSearchRequest = 0;
let customerSearchActive = -1;
function closeCustomerSuggestions() {
  if (!customerSearchPanel) return;
  customerSearchPanel.hidden = true;
  customerSearchPanel.replaceChildren();
  customerSearchActive = -1;
}
function selectCustomerSuggestion(button) {
  if (!button || !customerSearchInput) return;
  customerSearchInput.value = button.dataset.searchValue;
  closeCustomerSuggestions();
  customerSearchInput.form?.requestSubmit();
}
async function loadCustomerSuggestions() {
  const query = customerSearchInput?.value.trim() || '';
  const request = ++customerSearchRequest;
  customerSearchAbort?.abort();
  customerSearchAbort = new AbortController();
  if (!customerSearchPanel || query.length < 1) {
    closeCustomerSuggestions();
    return;
  }
  try {
    const response = await fetch('/customer/search-suggestions?q=' + encodeURIComponent(query), {
      signal: customerSearchAbort.signal,
      credentials: 'same-origin',
      headers: {'Accept': 'application/json', 'X-Requested-With': 'fetch'},
    });
    if (!response.ok || response.redirected) throw new Error('Search unavailable');
    const data = await response.json();
    if (request !== customerSearchRequest) return;
    customerSearchPanel.replaceChildren(...data.items.map((item) => {
      const button = document.createElement('button');
      const icon = document.createElement('span');
      const copy = document.createElement('span');
      const label = document.createElement('strong');
      const subtitle = document.createElement('small');
      button.type = 'button';
      button.className = 'customer-search-suggestion';
      button.dataset.searchValue = item.value;
      button.setAttribute('role', 'option');
      icon.textContent = item.type === 'menu' ? 'M' : item.type === 'restaurant' ? 'R' : 'C';
      label.textContent = item.label;
      subtitle.textContent = item.subtitle;
      copy.append(label, subtitle);
      button.append(icon, copy);
      button.addEventListener('click', () => selectCustomerSuggestion(button));
      return button;
    }));
    customerSearchPanel.hidden = !data.items.length;
    customerSearchActive = -1;
  } catch (error) {
    if (error.name !== 'AbortError' && request === customerSearchRequest) closeCustomerSuggestions();
  }
}
if (customerSearchInput && customerSearchPanel) {
  customerSearchInput.addEventListener('input', () => {
    clearTimeout(customerSearchTimer);
    loadCustomerSuggestions();
  });
  customerSearchInput.addEventListener('focus', () => {
    if (customerSearchInput.value.trim()) loadCustomerSuggestions();
  });
  customerSearchInput.addEventListener('keydown', (event) => {
    const options = [...customerSearchPanel.querySelectorAll('.customer-search-suggestion')];
    if (event.key === 'Escape') {
      closeCustomerSuggestions();
      return;
    }
    if (!options.length || !['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
    if (event.key === 'Enter' && customerSearchActive >= 0) {
      event.preventDefault();
      selectCustomerSuggestion(options[customerSearchActive]);
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      customerSearchActive = event.key === 'ArrowDown'
        ? (customerSearchActive + 1) % options.length
        : (customerSearchActive - 1 + options.length) % options.length;
      options.forEach((option, index) => option.classList.toggle('active', index === customerSearchActive));
      options[customerSearchActive].scrollIntoView({block: 'nearest'});
    }
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.customer-search')) closeCustomerSuggestions();
  });
}


const checkoutPage = document.querySelector('[data-checkout-page]');
const checkoutForm = document.querySelector('[data-checkout-form]');
if (checkoutPage && checkoutForm) {
  const modeInput = checkoutForm.querySelector('[name="mode"]');
  const modeToggle = checkoutForm.querySelector('[data-checkout-mode-toggle]');
  const addressSelect = checkoutForm.querySelector('[data-checkout-address]');
  const deliveryPanel = checkoutForm.querySelector('[data-checkout-delivery-panel]');
  const pickupPanel = checkoutForm.querySelector('[data-checkout-pickup-panel]');
  const destinationTitle = checkoutForm.querySelector('[data-checkout-destination-title]');
  const paymentLabel = checkoutForm.querySelector('[data-checkout-payment-label]');
  const promoInput = checkoutForm.querySelector('[data-checkout-promo]');
  const quoteStatus = checkoutForm.querySelector('[data-checkout-quote-status]');
  const checkoutStatus = checkoutForm.querySelector('[data-checkout-status]');
  const submitButton = checkoutForm.querySelector('[data-checkout-submit]');
  let quoteRequest = 0;

  const checkoutMoney = (value) => '$' + Number(value || 0).toFixed(2);
  const checkoutCsrf = () => checkoutForm.querySelector('[name="csrfmiddlewaretoken"]')?.value || '';
  const selectedDeliveryAddress = () => addressSelect?.selectedOptions?.[0]?.dataset.address || '';

  function updateCheckoutMap(mode) {
    // Restaurant markers stay fixed when the delivery address or order mode changes.
  }

  async function persistCheckoutMode(mode) {
    const body = new FormData();
    body.set('csrfmiddlewaretoken', checkoutCsrf());
    body.set('mode', mode);
    try {
      const response = await fetch('/customer/order-mode', {
        method: 'POST',
        body,
        credentials: 'same-origin',
        headers: {'X-Requested-With': 'fetch'},
      });
      if (!response.ok) throw new Error('Mode update failed');
      if (checkoutStatus) checkoutStatus.textContent = mode === 'pickup' ? 'Pickup selected' : 'Delivery selected';
    } catch (_) {
      if (checkoutStatus) checkoutStatus.textContent = 'Selection will be saved when you place the order.';
    }
  }

  function renderCheckoutQuote(quote) {
    const values = {
      '[data-checkout-subtotal]': quote.subtotal,
      '[data-checkout-tax]': quote.tax,
      '[data-checkout-service-fee]': quote.service_fee,
      '[data-checkout-tip]': quote.tip,
      '[data-checkout-delivery-fee]': quote.delivery_fee,
      '[data-checkout-total]': quote.total,
      '[data-checkout-button-total]': quote.total,
    };
    Object.entries(values).forEach(([selector, value]) => {
      const element = checkoutForm.querySelector(selector);
      if (element) element.textContent = checkoutMoney(value);
    });
    const discount = checkoutForm.querySelector('[data-checkout-discount]');
    if (discount) discount.textContent = '−' + checkoutMoney(quote.discount);
  }

  async function refreshCheckoutQuote() {
    const requestId = ++quoteRequest;
    const body = new FormData();
    body.set('csrfmiddlewaretoken', checkoutCsrf());
    body.set('mode', modeInput.value);
    body.set('promo_code', promoInput?.value.trim() || '');
    body.set('tip', checkoutForm.querySelector('[name=tip]').value || '0');
    if (quoteStatus) quoteStatus.textContent = 'Updating total…';
    try {
      const response = await fetch(checkoutForm.dataset.quoteUrl, {
        method: 'POST',
        body,
        credentials: 'same-origin',
        headers: {'X-Requested-With': 'fetch'},
      });
      const data = await response.json();
      if (requestId !== quoteRequest) return;
      if (!response.ok) throw new Error(data.detail || 'Promotion is unavailable');
      renderCheckoutQuote(data);
      if (quoteStatus) quoteStatus.textContent = promoInput?.value.trim() ? 'Promotion applied' : 'Total updated';
    } catch (error) {
      if (requestId !== quoteRequest) return;
      if (quoteStatus) quoteStatus.textContent = error.message;
    }
  }

  function setCheckoutMode(mode, persist = false) {
    const pickup = mode === 'pickup';
    const tipPanel = checkoutForm.querySelector('[data-tip-panel]');
    if (tipPanel) tipPanel.hidden = pickup;
    if (pickup) {
      checkoutForm.querySelector('[name=tip]').value = '0';
      checkoutForm.querySelectorAll('[data-tip-value]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.tipValue === '0')));
      checkoutForm.querySelector('[data-tip-other]').setAttribute('aria-pressed', 'false');
    }
    modeInput.value = mode;
    checkoutPage.dataset.checkoutMode = mode;
    if (deliveryPanel) deliveryPanel.hidden = pickup;
    if (pickupPanel) pickupPanel.hidden = !pickup;
    if (addressSelect) addressSelect.required = !pickup;
    if (destinationTitle) destinationTitle.textContent = pickup ? 'Pickup from' : 'Deliver to';
    if (paymentLabel) paymentLabel.textContent = pickup ? 'Cash on pickup' : 'Cash on delivery';
    if (modeToggle) {
      modeToggle.dataset.mode = pickup ? 'delivery' : 'pickup';
      modeToggle.textContent = pickup ? 'Delivery instead' : 'Pickup instead';
    }
    updateCheckoutMap(mode);
    refreshCheckoutQuote();
    if (persist) persistCheckoutMode(mode);
  }

  modeToggle?.addEventListener('click', () => setCheckoutMode(modeToggle.dataset.mode, true));
  addressSelect?.addEventListener('change', () => {
    updateCheckoutMap('delivery');
    if (checkoutStatus) checkoutStatus.textContent = addressSelect.value ? 'Delivery address selected' : 'Choose a delivery address';
  });
  checkoutForm.querySelector('[data-checkout-promo-apply]')?.addEventListener('click', refreshCheckoutQuote);
  promoInput?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    refreshCheckoutQuote();
  });
  checkoutForm.addEventListener('submit', (event) => {
    if (modeInput.value === 'delivery' && !addressSelect?.value) {
      event.preventDefault();
      if (checkoutStatus) checkoutStatus.textContent = 'Choose a delivery address before placing the order.';
      addressSelect?.focus();
      return;
    }
    submitButton.disabled = true;
    submitButton.firstChild.textContent = 'Placing order ';
  });
  setInterval(() => { if (!document.hidden && !submitButton.disabled) refreshCheckoutQuote(); }, 5000);

  const tipInput = checkoutForm.querySelector('[name=tip]');
  const customTip = checkoutForm.querySelector('[data-tip-custom]');
  const presets = checkoutForm.querySelectorAll('[data-tip-value]');
  const otherTip = checkoutForm.querySelector('[data-tip-other]');
  presets.forEach(button => button.addEventListener('click', () => {
    tipInput.value = button.dataset.tipValue;
    customTip.hidden = true;
    presets.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    otherTip.setAttribute('aria-pressed', 'false');
    refreshCheckoutQuote();
  }));
  otherTip.addEventListener('click', () => {
    customTip.hidden = false;
    presets.forEach(item => item.setAttribute('aria-pressed', 'false'));
    otherTip.setAttribute('aria-pressed', 'true');
    tipInput.focus();
  });
  tipInput.addEventListener('change', () => {
    if (tipInput.checkValidity()) refreshCheckoutQuote();
    else tipInput.reportValidity();
  });
  setCheckoutMode(modeInput.value || checkoutPage.dataset.checkoutMode || 'delivery');
}

(() => {
 const page=document.querySelector('[data-checkout-page]');
 if(!page)return;
 const form=page.querySelector('form'), mode=form.querySelector('[name=mode]'), address=form.querySelector('[name=address_id]');
 const eta=page.querySelector('[data-checkout-eta]'), title=page.querySelector('[data-time-title]');
 let sequence=0, lastKey='';
 async function estimate(){
  const key=mode.value+':'+(address.value||'');
  if(key===lastKey)return;lastKey=key;const serial=++sequence;
  title.textContent=mode.value==='pickup'?'Pickup time':'Delivery time';
  if(mode.value==='delivery'&&!address.value){eta.textContent='Choose a delivery address for an estimate';return;}
  eta.textContent='Calculating arrival time…';
  try{
   const response=await fetch('/customer/checkout/eta?'+new URLSearchParams({mode:mode.value,address_id:address.value||''}),{credentials:'same-origin'});
   const data=await response.json();if(serial!==sequence)return;
   if(!response.ok)throw new Error(data.detail||'Estimate unavailable');
   eta.textContent=(data.mode==='pickup'?'Ready in about ':'Estimated arrival in ')+data.minutes+' min';
   const detail=document.createElement('span');
   detail.style.display='block';
   detail.textContent=data.groups.map(g=>g.restaurant_name+': '+g.preparation_minutes+' min preparation'+(data.mode==='delivery'?' + '+g.drive_minutes+' min drive · '+g.distance_miles+' mi':'')).join(' / ');
   eta.append(detail);
  }catch(error){if(serial===sequence)eta.textContent=error.message;}
 }
 address.addEventListener('change',estimate);
 new MutationObserver(estimate).observe(page,{attributes:true,attributeFilter:['data-checkout-mode']});
 estimate();
 setInterval(()=>{if(!document.hidden){lastKey='';estimate();}},120000);
})();
