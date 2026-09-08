/* ═══════════════════════════════════════════════════════
   SecureVault — App JS v2
   ═══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {

  // ── Mobile sidebar toggle ──────────────────────────────
  const toggleBtn = document.getElementById('sidebar-toggle');
  const sidebar   = document.getElementById('sidebar');
  const overlay   = document.getElementById('sidebar-overlay');

  function openSidebar() {
    sidebar?.classList.add('mobile-open');
    overlay?.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  function closeSidebar() {
    sidebar?.classList.remove('mobile-open');
    overlay?.classList.remove('active');
    document.body.style.overflow = '';
  }

  toggleBtn?.addEventListener('click', () => {
    sidebar?.classList.contains('mobile-open') ? closeSidebar() : openSidebar();
  });
  overlay?.addEventListener('click', closeSidebar);

  // Close sidebar on nav-link click (mobile)
  sidebar?.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth < 992) closeSidebar();
    });
  });

  // ── Auto-dismiss flash alerts ──────────────────────────
  setTimeout(() => {
    document.querySelectorAll('.alert-auto').forEach(el => {
      el.style.transition = 'opacity .5s, max-height .5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    });
  }, 5000);

  // ── File drop zone ─────────────────────────────────────
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');

  if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => fileInput.click());

    ['dragenter','dragover'].forEach(ev =>
      dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add('dragover'); })
    );
    ['dragleave','dragend'].forEach(ev =>
      dropZone.addEventListener(ev, () => dropZone.classList.remove('dragover'))
    );
    dropZone.addEventListener('drop', e => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      fileInput.files = e.dataTransfer.files;
      updateDropLabel(e.dataTransfer.files);
    });
    fileInput.addEventListener('change', () => updateDropLabel(fileInput.files));
  }

  function updateDropLabel(files) {
    const lbl = document.getElementById('drop-label');
    if (!lbl) return;
    lbl.textContent = files.length === 1 ? files[0].name : `${files.length} files selected`;
  }

  // ── Live notification badge ────────────────────────────
  function refreshBadge() {
    fetch('/notifications/count')
      .then(r => r.json())
      .then(data => {
        document.querySelectorAll('[data-notif-badge]').forEach(el => {
          el.textContent = data.count > 99 ? '99+' : data.count;
          el.style.display = data.count > 0 ? '' : 'none';
        });
        // dot in topbar
        document.querySelectorAll('.badge-dot').forEach(dot => {
          dot.style.display = data.count > 0 ? '' : 'none';
        });
      }).catch(() => {});
  }
  refreshBadge();
  setInterval(refreshBadge, 30000);

  // ── Confirm dangerous actions ──────────────────────────
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-confirm]');
    if (btn) {
      if (!confirm(btn.dataset.confirm)) e.preventDefault();
    }
  });

  // ── Card number formatter ──────────────────────────────
  const cardInput = document.getElementById('card-number-input');
  if (cardInput) {
    cardInput.addEventListener('input', e => {
      let v = e.target.value.replace(/\D/g, '').slice(0, 16);
      e.target.value = v.replace(/(.{4})/g, '$1 ').trim();
    });
  }

  // ── Storage bar fill (sidebar) ─────────────────────────
  document.querySelectorAll('.storage-fill[data-pct]').forEach(bar => {
    bar.style.width = (bar.dataset.pct || 0) + '%';
  });

  // ── Rename toggle ──────────────────────────────────────
  document.addEventListener('click', e => {
    const btn = e.target.closest('.rename-trigger');
    if (btn) {
      const id = btn.dataset.target;
      const form = document.getElementById(id);
      if (form) {
        form.classList.toggle('d-none');
        if (!form.classList.contains('d-none')) form.querySelector('input')?.focus();
      }
    }
  });

  // ── Share modal — pre-fill file/folder info ────────────
  const shareFileModal = document.getElementById('shareFileModal');
  if (shareFileModal) {
    shareFileModal.addEventListener('show.bs.modal', e => {
      const btn = e.relatedTarget;
      if (btn) {
        document.getElementById('share-file-id').value         = btn.dataset.fileId   || '';
        document.getElementById('share-file-name').textContent = btn.dataset.fileName || '';
      }
    });
  }
  const shareFolderModal = document.getElementById('shareFolderModal');
  if (shareFolderModal) {
    shareFolderModal.addEventListener('show.bs.modal', e => {
      const btn = e.relatedTarget;
      if (btn) {
        document.getElementById('share-folder-id').value         = btn.dataset.folderId   || '';
        document.getElementById('share-folder-name').textContent = btn.dataset.folderName || '';
      }
    });
  }

});
