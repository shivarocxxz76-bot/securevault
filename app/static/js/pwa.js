/* =====================================================
   SecureVault PWA — Service Worker Registration
   + Install Prompt
===================================================== */

/* ── Register Service Worker ────────────────────── */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .then(reg => {
        console.log('[PWA] Service Worker registered, scope:', reg.scope);

        // Check for updates every 60 seconds
        setInterval(() => reg.update(), 60000);

        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing;
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              showUpdateBanner();
            }
          });
        });
      })
      .catch(err => console.warn('[PWA] SW registration failed:', err));
  });
}

/* ── Install Prompt (Android Chrome) ────────────── */
let deferredPrompt = null;

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  deferredPrompt = e;
  showInstallBanner();
});

window.addEventListener('appinstalled', () => {
  deferredPrompt = null;
  hideInstallBanner();
  console.log('[PWA] App installed!');
});

function showInstallBanner() {
  // Don't show if already running as installed PWA
  if (window.matchMedia('(display-mode: standalone)').matches) return;
  if (sessionStorage.getItem('pwa-banner-dismissed')) return;

  const banner = document.createElement('div');
  banner.id = 'pwa-install-banner';
  banner.innerHTML = `
    <div style="
      position:fixed;bottom:0;left:0;right:0;z-index:9999;
      background:linear-gradient(135deg,#0d1117,#0a1628);
      border-top:1px solid rgba(0,212,212,.2);
      padding:.9rem 1rem;
      display:flex;align-items:center;gap:.75rem;
      box-shadow:0 -4px 24px rgba(0,0,0,.4);
      font-family:'Segoe UI',Inter,sans-serif;
    ">
      <img src="/static/img/icon-72.png" width="42" height="42"
           style="border-radius:10px;flex-shrink:0;" alt="SecureVault">
      <div style="flex:1;min-width:0;">
        <div style="font-size:.85rem;font-weight:700;color:#f1f5f9;">Install SecureVault</div>
        <div style="font-size:.72rem;color:rgba(255,255,255,.45);">Add to home screen for quick access</div>
      </div>
      <button onclick="installPWA()" style="
        background:linear-gradient(135deg,#00c8c8,#4f46e5);
        border:none;border-radius:8px;padding:.45rem .9rem;
        color:#fff;font-weight:700;font-size:.78rem;cursor:pointer;
        white-space:nowrap;flex-shrink:0;">
        Install
      </button>
      <button onclick="dismissInstallBanner()" style="
        background:rgba(255,255,255,.06);border:none;border-radius:8px;
        padding:.45rem .6rem;color:rgba(255,255,255,.5);font-size:.8rem;cursor:pointer;
        flex-shrink:0;">✕</button>
    </div>`;
  document.body.appendChild(banner);
}

function hideInstallBanner() {
  const b = document.getElementById('pwa-install-banner');
  if (b) b.remove();
}

function installPWA() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then(result => {
    if (result.outcome === 'accepted') console.log('[PWA] User accepted install');
    deferredPrompt = null;
    hideInstallBanner();
  });
}

function dismissInstallBanner() {
  sessionStorage.setItem('pwa-banner-dismissed', '1');
  hideInstallBanner();
}

/* ── Update banner ───────────────────────────────── */
function showUpdateBanner() {
  const banner = document.createElement('div');
  banner.innerHTML = `
    <div style="
      position:fixed;top:0;left:0;right:0;z-index:9999;
      background:rgba(0,212,212,.12);
      border-bottom:1px solid rgba(0,212,212,.3);
      padding:.6rem 1rem;
      display:flex;align-items:center;justify-content:center;gap:1rem;
      font-family:Inter,sans-serif;font-size:.8rem;color:#5eead4;
    ">
      <i class="bi bi-arrow-repeat"></i>
      A new version of SecureVault is available.
      <button onclick="window.location.reload()" style="
        background:rgba(0,212,212,.2);border:1px solid rgba(0,212,212,.3);
        border-radius:6px;padding:.2rem .7rem;color:#5eead4;font-size:.78rem;cursor:pointer;">
        Update Now
      </button>
    </div>`;
  document.body.prepend(banner);
}

/* ── iOS install instructions ────────────────────── */
function showiOSInstallHint() {
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const isInStandalone = window.navigator.standalone;
  if (!isIOS || isInStandalone) return;
  if (sessionStorage.getItem('ios-hint-shown')) return;

  sessionStorage.setItem('ios-hint-shown', '1');
  const hint = document.createElement('div');
  hint.innerHTML = `
    <div style="
      position:fixed;bottom:1rem;left:.75rem;right:.75rem;z-index:9999;
      background:#0d1117;border:1px solid rgba(0,212,212,.2);
      border-radius:14px;padding:1rem 1.1rem;
      box-shadow:0 8px 30px rgba(0,0,0,.5);
      font-family:Inter,sans-serif;
    ">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;">
        <div style="font-size:.85rem;font-weight:700;color:#f1f5f9;">📲 Install SecureVault</div>
        <button onclick="this.closest('div').parentElement.remove()" style="background:none;border:none;color:rgba(255,255,255,.4);font-size:1rem;cursor:pointer;">✕</button>
      </div>
      <div style="font-size:.78rem;color:rgba(255,255,255,.55);line-height:1.6;">
        Tap the <strong style="color:#5eead4;">Share</strong> button
        <span style="font-size:1rem;">⬆</span> at the bottom of Safari,<br>
        then tap <strong style="color:#5eead4;">"Add to Home Screen"</strong>
        <span style="font-size:1rem;">➕</span>
      </div>
      <!-- Arrow pointing down -->
      <div style="text-align:center;margin-top:.5rem;font-size:1.2rem;">⬇</div>
    </div>`;
  document.body.appendChild(hint);
  setTimeout(() => hint.remove(), 8000);
}

// Show iOS hint after 2 seconds
setTimeout(showiOSInstallHint, 2000);
