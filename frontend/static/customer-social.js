(() => {
  const host = document.getElementById('social-login');
  if (!host) return;
  const status = document.getElementById('social-status');
  const googlePlaceholder = document.getElementById('google-placeholder');
  const facebookButton = document.getElementById('facebook-button');
  const unavailable = provider => {
    status.textContent = `${provider} sign-in is not available yet. Continue with Email or as Guest.`;
  };
  googlePlaceholder.onclick = () => unavailable('Google');
  facebookButton.onclick = () => unavailable('Facebook');
  let challenge, busy = false;

  async function api(path, body) {
    const headers = {};
    if (body) {
      headers['Content-Type'] = 'application/json';
      headers['X-CSRFToken'] = host.querySelector('[name=csrfmiddlewaretoken]').value;
      if (challenge) headers['X-Social-CSRF'] = challenge.csrf_token;
    }
    const response = await fetch('/customer/auth/' + path, {
      method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers, body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(20000)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Sign-in failed. Please reload and try again.');
    return data;
  }

  async function refreshChallenge() {
    challenge = await api('social/challenge', {});
    return challenge;
  }

  async function finish(provider, token) {
    if (busy) return;
    busy = true;
    facebookButton.disabled = true;
    status.textContent = 'Signing in…';
    try {
      const field = provider === 'google' ? 'id_token' : 'access_token';
      const result = await api(provider, {[field]: token, csrf_token: challenge.csrf_token});
      location.assign(result.redirect_url);
    } catch (error) {
      status.textContent = error.message;
      busy = false;
      facebookButton.disabled = false;
    }
  }

  function loadScript(url) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = url; script.async = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error('Sign-in provider could not load. Continue with Email.'));
      document.head.append(script);
    });
  }

  async function initialize() {
    if (location.protocol !== 'https:') return;
    const config = await api('social/config');
    if (!config.google_enabled && !config.facebook_enabled) return;
    await refreshChallenge();
    const providers = [];
    if (config.google_enabled) {
      providers.push(loadScript('https://accounts.google.com/gsi/client').then(() => {
        google.accounts.id.initialize({client_id: config.google_client_id,
          nonce: challenge.nonce, auto_select: false,
          callback: response => finish('google', response.credential)});
        google.accounts.id.renderButton(document.getElementById('google-button'), {
          theme: 'outline', size: 'large', text: 'continue_with',
          width: Math.min(380, Math.floor(host.clientWidth))
        });
        googlePlaceholder.hidden = true;
      }));
    }
    if (config.facebook_enabled) {
      providers.push(loadScript('https://connect.facebook.net/en_US/sdk.js').then(() => {
        FB.init({appId: config.facebook_app_id, version: config.facebook_graph_version,
          cookie: false, xfbml: false, autoLogAppEvents: false});
        facebookButton.onclick = () => {
          if (busy) return;
          FB.login(response => {
            const token = response.authResponse?.accessToken;
            if (token) finish('facebook', token);
            else status.textContent = 'Facebook sign-in was cancelled.';
          }, {scope: 'public_profile,email', return_scopes: true});
        };
      }));
    }
    const results = await Promise.allSettled(providers);
    const failed = results.find(result => result.status === 'rejected');
    if (failed) status.textContent = failed.reason.message;
  }
  initialize().catch(error => { status.textContent = error.message; });
})();
