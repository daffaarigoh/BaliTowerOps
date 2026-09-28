/**
 * BaliTowerOps Enterprise Minimalist Operations Center
 * Features: Left-Sided Resizable Data Sidebar, Interactive AI Command Center, In-App PDF Previewer, Real-Time DuckDB Sync.
 */

const state = {
  stats: {},
  items: [],
  categories: [],
  prs: [],
  currentModalPrNumber: null,
  isResizing: false
};

function getEffectiveTenant() {
  const rawTenant = (sessionStorage.getItem('tenant_id') || '').toUpperCase().trim();
  const rawUsername = (sessionStorage.getItem('username') || '').toLowerCase().trim();

  if (rawUsername === 'usera' || rawTenant === 'INVENTORY' || rawTenant === 'TENANT_A') {
    return 'INVENTORY';
  }
  if (rawUsername === 'userb' || rawTenant === 'HR' || rawTenant === 'TENANT_B') {
    return 'HR';
  }
  if (rawUsername === 'userc' || rawTenant === 'FINANCE' || rawTenant === 'TENANT_C') {
    return 'FINANCE';
  }
  return 'ALL';
}

document.addEventListener('DOMContentLoaded', () => {
  const uName = sessionStorage.getItem('username');
  const uRole = sessionStorage.getItem('role');
  const effectiveTenant = getEffectiveTenant();

  if (uName) {
    const el = document.getElementById('displayUsername');
    if (el) el.textContent = uName;
  }
  const elTenant = document.getElementById('displayTenant');
  if (elTenant) {
    elTenant.textContent = effectiveTenant;
  }
  if (uRole === 'ADMIN' || (uName && uName.toLowerCase() === 'admin')) {
    window.location.href = '/static/admin.html';
    return;
  }

  // Set initial sidebar toggle button text
  const isCollapsed = document.body.classList.contains('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) {
    btnText.textContent = isCollapsed ? 'Catalog & Data' : 'Close Sidebar';
  }

  // Modal backdrop click handlers (M-3)
  const pdfModal = document.getElementById('pdfPreviewModal');
  if (pdfModal) {
    pdfModal.addEventListener('click', (e) => {
      if (e.target === pdfModal) closePdfModal();
    });
  }
  const helpModal = document.getElementById('flowHelpModal');
  if (helpModal) {
    helpModal.addEventListener('click', (e) => {
      if (e.target === helpModal) closeFlowHelpModal();
    });
  }

  initSidebarResizer();
  restoreUiCustomizations();
  restoreCopilotFeed();
  initPromptInputAutoResize();
  initAmbientSpotlight();
  applyTenantSecurityAndPersonalization();
  loadAllData();
  
  // Real-time synchronization (optimized 20s interval when tab is active + instant refresh on window focus)
  setInterval(() => {
    if (!document.hidden) loadAllData();
  }, 20000);
  window.addEventListener('focus', () => loadAllData());
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) loadAllData();
  });
});

// Logout Helper
function logoutSession() {
  sessionStorage.clear();
  localStorage.clear();
  window.location.href = '/static/login.html';
}

// Override fetch to inject Auth Headers automatically
const originalFetch = window.fetch;
window.fetch = async function(resource, config = {}) {
  const token = sessionStorage.getItem('access_token');
  let headers = {};

  if (resource instanceof Request) {
    resource.headers.forEach((val, key) => { headers[key] = val; });
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const newReq = new Request(resource, { headers });
    return await originalFetch(newReq);
  }

  if (config.headers instanceof Headers) {
    headers = new Headers(config.headers);
    if (token) headers.set('Authorization', `Bearer ${token}`);
  } else if (config.headers && typeof config.headers === 'object') {
    headers = { ...config.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } else {
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  const newConfig = { ...config, headers };
  const res = await originalFetch(resource, newConfig);
  if (res.status === 401 && !window.location.pathname.includes('login.html')) {
    sessionStorage.clear();
    localStorage.clear();
    window.location.href = '/static/login.html';
  }
  return res;
};

// --- Left-Sided Resizable Sidebar Splitter Logic (Drag to Resize / Slide to Left) ---
function initSidebarResizer() {
  const resizer = document.getElementById('sidebarResizer');
  const sidebar = document.getElementById('dataSidebar');
  if (!resizer || !sidebar) return;

  // Restore saved width from localStorage (defaulting comfortably to 580px for multi-column data)
  const savedWidth = localStorage.getItem('ar_sidebar_width');
  if (savedWidth && !isNaN(Number(savedWidth))) {
    const w = Math.max(520, Math.min(window.innerWidth * 0.85, Number(savedWidth)));
    document.documentElement.style.setProperty('--sidebar-width', `${w}px`);
  } else {
    document.documentElement.style.setProperty('--sidebar-width', '580px');
  }

  let startX = 0;
  let startWidth = 0;

  const onMouseDown = (e) => {
    state.isResizing = true;
    startX = e.clientX;
    startWidth = sidebar.getBoundingClientRect().width;
    resizer.classList.add('is-dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const onMouseMove = (e) => {
    if (!state.isResizing) return;
    // Since sidebar is on the LEFT, dragging mouse right increases width, dragging left decreases width
    const deltaX = e.clientX - startX;
    let newWidth = startWidth + deltaX;

    // Minimum collapse threshold (slide left into hidden state)
    if (newWidth < 240) {
      closeDataSidebar();
      return;
    }

    // Constraints: min 360px, max 85% of screen width (max 1100px)
    newWidth = Math.max(360, Math.min(window.innerWidth * 0.85, Math.min(1100, newWidth)));

    document.body.classList.remove('sidebar-collapsed');
    const btnText = document.getElementById('toggleSidebarText');
    if (btnText) btnText.textContent = 'Tutup Sidebar';

    document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
    localStorage.setItem('ar_sidebar_width', newWidth);
  };

  const onMouseUp = () => {
    if (!state.isResizing) return;
    state.isResizing = false;
    resizer.classList.remove('is-dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';

    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
  };

  resizer.addEventListener('mousedown', onMouseDown);
}

function toggleExpandSidebar() {
  const sidebar = document.getElementById('dataSidebar');
  const btn = document.getElementById('btnExpandSidebar');
  if (!sidebar) return;

  const isExpanded = sidebar.classList.contains('sidebar-maximized');
  if (isExpanded) {
    sidebar.classList.remove('sidebar-maximized');
    const prevWidth = localStorage.getItem('ar_sidebar_prev_width') || '580';
    document.documentElement.style.setProperty('--sidebar-width', `${prevWidth}px`);
    if (btn) btn.title = 'Perlebar / Maksimalkan Panel';
  } else {
    const currentWidth = sidebar.getBoundingClientRect().width;
    localStorage.setItem('ar_sidebar_prev_width', currentWidth);
    sidebar.classList.add('sidebar-maximized');
    const targetWidth = Math.min(window.innerWidth * 0.75, 920);
    document.documentElement.style.setProperty('--sidebar-width', `${targetWidth}px`);
    if (btn) btn.title = 'Kembalikan Ukuran Panel';
  }
}

function restoreUiCustomizations() {
  try {
    const customUi = JSON.parse(localStorage.getItem('ar_ui_custom') || '{}');
    for (const [id, label] of Object.entries(customUi)) {
      const el = document.getElementById(id);
      if (el) el.textContent = label;
    }
  } catch (e) {
    console.error("Failed to restore UI customizations:", e);
  }
}

// --- Chat History Persistence in LocalStorage ---
function saveCopilotFeed() {
  const feed = document.getElementById('copilotFeed');
  const container = document.getElementById('geminiChatContainer');
  if (feed) {
    localStorage.setItem('ar_copilot_feed', feed.innerHTML);
    if (container) {
      if (feed.children.length === 0) {
        container.classList.add('is-empty-state');
      } else {
        container.classList.remove('is-empty-state');
      }
    }
  }
}

function restoreCopilotFeed() {
  let saved = localStorage.getItem('ar_copilot_feed');
  const feed = document.getElementById('copilotFeed');
  const container = document.getElementById('geminiChatContainer');
  if (saved && feed && saved.trim().length > 0) {
    // Sanitize any stale or legacy model names cached from previous sessions (e.g., Nemotron -> qwen-38)
    if (/nemotron/i.test(saved)) {
      saved = saved.replace(/LLM\s+Nemotron(?:-\w+)?/gi, 'LLM qwen-38')
                   .replace(/Nemotron(?:-\w+)?/gi, 'qwen-38');
      localStorage.setItem('ar_copilot_feed', saved);
    }
    feed.innerHTML = saved;
    feed.scrollTop = feed.scrollHeight;
    if (container) container.classList.remove('is-empty-state');
  } else {
    if (container) container.classList.add('is-empty-state');
  }
}

function clearCopilotFeed() {
  const feed = document.getElementById('copilotFeed');
  const container = document.getElementById('geminiChatContainer');
  if (feed) {
    feed.innerHTML = '';
    localStorage.removeItem('ar_copilot_feed');
  }
  if (container) {
    container.classList.add('is-empty-state');
  }
  showToast("Activity history cleared", "info");
}

// --- Interactive Ambient Spotlight Controller (Linear / Raycast Style) ---
function initAmbientSpotlight() {
  const container = document.getElementById('geminiChatContainer');
  const layer = document.getElementById('ambientSpotlightLayer');
  if (!container || !layer) return;

  let targetX = container.clientWidth * 0.5 || window.innerWidth * 0.5;
  let targetY = container.clientHeight * 0.45 || window.innerHeight * 0.45;
  let currentX = targetX;
  let currentY = targetY;
  let isMouseInside = false;

  function onMouseMove(e) {
    const rect = container.getBoundingClientRect();
    targetX = e.clientX - rect.left;
    targetY = e.clientY - rect.top;
    isMouseInside = true;
  }

  function onMouseLeave() {
    isMouseInside = false;
    const rect = container.getBoundingClientRect();
    targetX = rect.width * 0.5;
    targetY = rect.height * 0.45;
  }

  function renderSpotlight() {
    // Smooth spring lerp (linear interpolation) physics
    const lerpSpeed = isMouseInside ? 0.085 : 0.035;
    currentX += (targetX - currentX) * lerpSpeed;
    currentY += (targetY - currentY) * lerpSpeed;

    layer.style.setProperty('--spot-x', `${currentX.toFixed(1)}px`);
    layer.style.setProperty('--spot-y', `${currentY.toFixed(1)}px`);

    requestAnimationFrame(renderSpotlight);
  }

  container.addEventListener('mousemove', onMouseMove, { passive: true });
  container.addEventListener('mouseleave', onMouseLeave, { passive: true });

  requestAnimationFrame(renderSpotlight);
}

// --- Left Sidebar Controls ---
function toggleDataSidebar() {
  const isCollapsed = document.body.classList.toggle('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) {
    btnText.textContent = isCollapsed ? 'Data & Modules' : 'Collapse Panel';
  }
}

function openDataSidebar(tabId) {
  document.body.classList.remove('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) btnText.textContent = 'Tutup Sidebar';
  if (tabId) switchCanvasTab(tabId);
}

function closeDataSidebar() {
  document.body.classList.add('sidebar-collapsed');
  const btnText = document.getElementById('toggleSidebarText');
  if (btnText) btnText.textContent = 'Katalog & Data';
}

// --- Tenant Security & UI Personalization ---
function applyTenantSecurityAndPersonalization() {
  const tenant = getEffectiveTenant();
  const username = sessionStorage.getItem('username') || 'User';

  const pillInv = document.getElementById('modPillInventory');
  const pillHr = document.getElementById('modPillHr');
  const pillFin = document.getElementById('modPillFinance');

  const tabInv = document.getElementById('sidebarTabInventory');
  const tabHr = document.getElementById('sidebarTabHr');
  const tabFin = document.getElementById('sidebarTabFinance');
  const tabPrs = document.getElementById('sidebarTabPrs');
  const tabPos = document.getElementById('sidebarTabPos');
  const tabTerminal = document.getElementById('sidebarTabTerminal');

  const heroTitle = document.getElementById('heroTitle');
  const heroSubtitle = document.getElementById('heroSubtitle');
  const promptInput = document.getElementById('promptInput');
  const inputHint = document.getElementById('inputHintText');

  if (tenant === 'INVENTORY') {
    // Hide HR & Finance from header and sidebar
    if (pillHr) pillHr.style.display = 'none';
    if (pillFin) pillFin.style.display = 'none';
    if (pillInv) pillInv.style.display = 'inline-flex';

    if (tabHr) tabHr.style.display = 'none';
    if (tabFin) tabFin.style.display = 'none';
    if (tabInv) tabInv.style.display = 'inline-flex';
    if (tabPrs) tabPrs.style.display = 'inline-flex';
    if (tabPos) tabPos.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'Inventory & Logistics Command Center';
    if (heroSubtitle) heroSubtitle.textContent = `Selamat datang, ${username}. Panel operasional terisolasi material menara telekomunikasi, kabel fiber optic, monitoring saldo gudang regional, serta alur pengadaan barang PT Bali Towerindo Sentra Tbk.`;
    if (promptInput) promptInput.placeholder = '';
    if (inputHint) inputHint.textContent = 'Akses Terisolasi: Divisi Inventory & Logistik Material Menara/FO (DuckDB Live Sync)';

    switchCanvasTab('canvas-inventory');
  } else if (tenant === 'HR') {
    // Hide Inventory & Finance from header and sidebar
    if (pillInv) pillInv.style.display = 'none';
    if (pillFin) pillFin.style.display = 'none';
    if (pillHr) pillHr.style.display = 'inline-flex';

    if (tabInv) tabInv.style.display = 'none';
    if (tabFin) tabFin.style.display = 'none';
    if (tabPrs) tabPrs.style.display = 'none';
    if (tabPos) tabPos.style.display = 'none';
    if (tabHr) tabHr.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'HR & Field Workforce Command Center';
    if (heroSubtitle) heroSubtitle.textContent = `Selamat datang, ${username}. Panel manajemen ketenagakerjaan teknisi lapangan, kualifikasi sertifikat K3 TKPK rigger, dan pengajuan cuti PT Bali Towerindo Sentra Tbk.`;
    if (promptInput) promptInput.placeholder = '';
    if (inputHint) inputHint.textContent = 'Akses Terisolasi: Divisi Human Resources & Field Operations';

    switchCanvasTab('canvas-hr');
  } else if (tenant === 'FINANCE') {
    // Hide Inventory & HR from header and sidebar
    if (pillInv) pillInv.style.display = 'none';
    if (pillHr) pillHr.style.display = 'none';
    if (pillFin) pillFin.style.display = 'inline-flex';

    if (tabInv) tabInv.style.display = 'none';
    if (tabHr) tabHr.style.display = 'none';
    if (tabPrs) tabPrs.style.display = 'none';
    if (tabPos) tabPos.style.display = 'none';
    if (tabFin) tabFin.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'Finance & Telecom Billing Command Center';
    if (heroSubtitle) heroSubtitle.textContent = `Selamat datang, ${username}. Panel rekonsiliasi keuangan, penagihan invoice sewa menara ke operator telekomunikasi, kontrak MLA, sewa lahan site, dan utilitas listrik PT Bali Towerindo Sentra Tbk.`;
    if (promptInput) promptInput.placeholder = '';
    if (inputHint) inputHint.textContent = 'Akses Terisolasi: Divisi Finance, Billing & Accounting';

    switchCanvasTab('canvas-finance');
  } else {
    // Admin or Multi-Tenant (ALL)
    if (pillInv) pillInv.style.display = 'inline-flex';
    if (pillHr) pillHr.style.display = 'inline-flex';
    if (pillFin) pillFin.style.display = 'inline-flex';

    if (tabInv) tabInv.style.display = 'inline-flex';
    if (tabHr) tabHr.style.display = 'inline-flex';
    if (tabFin) tabFin.style.display = 'inline-flex';
    if (tabPrs) tabPrs.style.display = 'inline-flex';
    if (tabPos) tabPos.style.display = 'inline-flex';
    if (tabTerminal) tabTerminal.style.display = 'inline-flex';

    if (heroTitle) heroTitle.textContent = 'Bali Tower Operations Command Center';
    if (heroSubtitle) heroSubtitle.textContent = 'Pusat komando terpadu PT Bali Towerindo Sentra Tbk. Akses komprehensif ke seluruh 18 basis data operasional: Inventaris Menara & FO, Ketenagakerjaan & K3 Lapangan, serta Keuangan & Billing Operator.';
    if (promptInput) promptInput.placeholder = '';
    if (inputHint) inputHint.textContent = 'Hak Akses Administrator Enterprise: Terhubung ke seluruh 18 basis data operasional DuckDB';

    switchCanvasTab('canvas-inventory');
  }

  // Update Claude-style dynamic typewriter prompts
  if (window.claudePromptTypewriter) {
    window.claudePromptTypewriter.setTenant(tenant);
  }

  // Render tenant-specific example questions
  renderTenantHelpExamples();
}

// --- Tab Switching ---
function switchCanvasTab(tabId) {
  const tenant = getEffectiveTenant();

  // Strict guard against navigating to unauthorized tabs for tenant-specific users
  if (tenant === 'INVENTORY' && ['canvas-hr', 'canvas-finance'].includes(tabId)) {
    tabId = 'canvas-inventory';
  } else if (tenant === 'HR' && ['canvas-inventory', 'canvas-finance', 'canvas-prs', 'canvas-pos'].includes(tabId)) {
    tabId = 'canvas-hr';
  } else if (tenant === 'FINANCE' && ['canvas-inventory', 'canvas-hr', 'canvas-prs', 'canvas-pos'].includes(tabId)) {
    tabId = 'canvas-finance';
  }

  document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-target') === tabId);
  });

  document.querySelectorAll('.canvas-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === tabId);
  });

  // Update header quick pills
  document.querySelectorAll('.mod-pill').forEach(pill => {
    const fn = pill.getAttribute('onclick') || '';
    pill.classList.toggle('active', fn.includes(tabId));
  });

  if (tabId === 'canvas-inventory') {
    loadInventoryItems();
    loadStockBalances();
  } else if (tabId === 'canvas-hr') {
    loadHrData();
    loadEmployees();
  } else if (tabId === 'canvas-finance') {
    loadFinanceData();
    loadClients();
  } else if (tabId === 'canvas-prs') {
    loadApprovals();
  } else if (tabId === 'canvas-pos') {
    loadPurchaseOrders();
  }
}

// --- Sub-Tab Switching ---
function switchInvSubTab(subTabId) {
  document.querySelectorAll('#canvas-inventory .sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', (btn.getAttribute('onclick') || '').includes(subTabId));
  });
  document.querySelectorAll('#canvas-inventory .sub-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === subTabId);
  });

  if (subTabId === 'sub-inv-items') loadInventoryItems();
  else if (subTabId === 'sub-inv-balances') loadStockBalances();
  else if (subTabId === 'sub-inv-warehouses') loadWarehouses();
  else if (subTabId === 'sub-inv-suppliers') loadSuppliers();
}

function switchHrSubTab(subTabId) {
  document.querySelectorAll('#canvas-hr .sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', (btn.getAttribute('onclick') || '').includes(subTabId));
  });
  document.querySelectorAll('#canvas-hr .sub-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === subTabId);
  });

  if (subTabId === 'sub-hr-employees') loadEmployees();
  else if (subTabId === 'sub-hr-leaves') loadHrData();
  else if (subTabId === 'sub-hr-candidates') loadHrData();
  else if (subTabId === 'sub-hr-jobs') loadJobPostings();
}

function switchFinSubTab(subTabId) {
  document.querySelectorAll('#canvas-finance .sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', (btn.getAttribute('onclick') || '').includes(subTabId));
  });
  document.querySelectorAll('#canvas-finance .sub-tab-content').forEach(content => {
    content.classList.toggle('active', content.id === subTabId);
  });

  if (subTabId === 'sub-fin-invoices') loadFinanceData();
  else if (subTabId === 'sub-fin-clients') loadClients();
  else if (subTabId === 'sub-fin-mla') loadMlaContracts();
  else if (subTabId === 'sub-fin-leases') loadLandLeases();
  else if (subTabId === 'sub-fin-utilities') loadSiteUtilities();
}

// --- Visual Refresh Button Animation ---
async function triggerVisualRefresh(btnId, callback) {
  const btn = document.getElementById(btnId);
  const icon = btn ? btn.querySelector('.refresh-icon, svg') : null;

  if (icon) icon.classList.add('spin-icon');
  if (btn) btn.disabled = true;

  try {
    await callback();
    showToast("Data refreshed successfully", "success");
  } catch (e) {
    showToast("Failed to refresh data", "error");
  } finally {
    if (icon) icon.classList.remove('spin-icon');
    if (btn) btn.disabled = false;
  }
}

// --- Categories ---
async function loadCategories() {
  try {
    if (state.items && state.items.length > 0) {
      const cats = new Set(state.items.map(it => it.category));
      state.categories = Array.from(cats).filter(Boolean);
      renderCategoryOptions();
    }
  } catch (e) {
    console.error("Failed to load categories:", e);
  }
}

function renderCategoryOptions() {
  const select = document.getElementById('filterCategory');
  if (!select) return;
  const currentVal = select.value;

  select.innerHTML = `<option value="">Semua Kategori</option>` + (state.categories || []).map(c => {
    return `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`;
  }).join('');

  if (currentVal && state.categories.includes(currentVal)) {
    select.value = currentVal;
  }
}

// --- Data Fetching (Multi-Domain & Tenant Isolated) ---
async function loadAllData() {
  const tenant = getEffectiveTenant();

  if (tenant === 'INVENTORY') {
    await Promise.allSettled([
      loadInventoryItems(),
      loadStockBalances(),
      loadWarehouses(),
      loadSuppliers(),
      loadPurchaseOrders(),
      loadApprovals(),
      loadDashboardStats()
    ]);
    await loadCategories();
  } else if (tenant === 'HR') {
    await Promise.allSettled([
      loadHrData(),
      loadEmployees(),
      loadJobPostings(),
      loadSites()
    ]);
  } else if (tenant === 'FINANCE') {
    await Promise.allSettled([
      loadFinanceData(),
      loadClients(),
      loadMlaContracts(),
      loadLandLeases(),
      loadSiteUtilities(),
      loadCoa()
    ]);
  } else {
    // Admin / Multi-Tenant: load all 18 tables across all domains!
    await Promise.allSettled([
      loadInventoryItems(),
      loadStockBalances(),
      loadWarehouses(),
      loadSuppliers(),
      loadPurchaseOrders(),
      loadApprovals(),
      loadDashboardStats(),
      loadHrData(),
      loadEmployees(),
      loadJobPostings(),
      loadSites(),
      loadFinanceData(),
      loadClients(),
      loadMlaContracts(),
      loadLandLeases(),
      loadSiteUtilities(),
      loadCoa()
    ]);
    await loadCategories();
  }
}

// ==============================================================================
// DOMAIN 1: INVENTORY & LOGISTICS LOADERS
// ==============================================================================

function updateSidebarRowCount(count, label) {
  const el = document.getElementById('sidebarRowCountInfo');
  if (el) {
    el.textContent = `${count} ${label}`;
  }
}

async function loadStockBalances() {
  const tbody = document.getElementById('invBalancesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/inventory/stock-balances?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      state.stockBalances = data || [];
      filterBalancesTable();
    }
  } catch (e) {
    console.error("Failed to load stock balances:", e);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 24px; color: #DC2626;">Failed to load warehouse stock balances.</td></tr>`;
    }
  }
}

function renderStockBalancesTable(data) {
  const tbody = document.getElementById('invBalancesTableBody');
  if (!tbody) return;
  updateSidebarRowCount(data ? data.length : 0, 'Warehouse Balances');
  if (!data || data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 24px; color: var(--text-muted);">No matching warehouse stock balances found.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.map(b => {
    let statusBadge = 'badge-normal';
    let statusText = 'NORMAL';
    if (b.stock_status === 'CRITICAL') {
      statusBadge = 'badge-out_of_stock';
      statusText = 'CRITICAL';
    } else if (b.stock_status === 'LOW_STOCK') {
      statusBadge = 'badge-low_stock';
      statusText = 'WARNING';
    }
    return `
      <tr>
        <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(b.balance_id)}</td>
        <td><strong>${escapeHtml(b.item_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(b.item_code)}</span></td>
        <td><strong>${escapeHtml(b.warehouse_name)}</strong></td>
        <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(b.region)}</span></td>
        <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #0F172A;">${Number(b.quantity_on_hand).toLocaleString('id-ID')} <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">${escapeHtml(b.unit || 'pcs')}</span></td>
        <td class="text-right" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${Number(b.quantity_reserved || 0).toLocaleString('id-ID')}</td>
        <td class="text-right" style="font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: #D97706;">${Number(b.reorder_point).toLocaleString('id-ID')}</td>
        <td class="text-center"><span class="badge ${statusBadge}">${statusText}</span></td>
        <td class="text-center" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(b.last_stock_take_date || '-')}</td>
      </tr>
    `;
  }).join('');
}

function filterBalancesTable() {
  const search = (document.getElementById('searchBalances')?.value || '').toLowerCase().trim();
  const status = document.getElementById('filterBalanceStatus')?.value || '';

  const list = state.stockBalances || [];
  const filtered = list.filter(b => {
    const matchSearch = !search ||
      (b.item_name || '').toLowerCase().includes(search) ||
      (b.item_code || '').toLowerCase().includes(search) ||
      (b.warehouse_name || '').toLowerCase().includes(search) ||
      (b.region || '').toLowerCase().includes(search) ||
      (b.balance_id || '').toLowerCase().includes(search);

    let matchStatus = true;
    if (status === 'CRITICAL') matchStatus = (b.stock_status === 'CRITICAL');
    else if (status === 'LOW') matchStatus = (b.stock_status === 'LOW_STOCK');
    else if (status === 'NORMAL') matchStatus = (b.stock_status === 'NORMAL');

    return matchSearch && matchStatus;
  });

  renderStockBalancesTable(filtered);
}

async function loadWarehouses() {
  const tbody = document.getElementById('invWarehousesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/inventory/warehouses?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--text-muted);">No warehouse facilities found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(w => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11.5px; font-weight: 700; color: #2563EB;">${escapeHtml(w.warehouse_id)}</td>
          <td><strong>${escapeHtml(w.warehouse_name)}</strong></td>
          <td><span style="font-size: 11px; background: #EFF6FF; color: #1E40AF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${escapeHtml(w.warehouse_type)}</span></td>
          <td>${escapeHtml(w.region)}</td>
          <td style="font-size: 11px; color: #334155; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(w.address)}">${escapeHtml(w.address)}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 700;">${Number(w.capacity_sqm).toLocaleString('id-ID')} m²</td>
          <td class="text-center"><span class="badge ${w.status === 'ACTIVE' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(w.status)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load warehouses:", e);
  }
}

async function loadSuppliers() {
  const tbody = document.getElementById('invSuppliersTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/inventory/suppliers?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--text-muted);">No partner suppliers found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(s => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(s.supplier_id)}</td>
          <td><strong>${escapeHtml(s.supplier_name)}</strong></td>
          <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(s.category)}</span></td>
          <td>${escapeHtml(s.contact_person || '-')}</td>
          <td style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">${escapeHtml(s.phone || '-')}<br>${escapeHtml(s.email || '-')}</td>
          <td class="text-center"><span style="font-weight: 800; color: #D97706; font-family: var(--font-mono);">${s.rating}</span> / 5.0</td>
          <td class="text-center"><span style="font-size: 11px; background: #EFF6FF; color: #1E40AF; padding: 2px 6px; border-radius: 4px;">${escapeHtml(s.payment_terms)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load suppliers:", e);
  }
}

async function loadPurchaseOrders() {
  const tbodyTop = document.getElementById('topPosTableBody');
  const badgeTop = document.getElementById('topPoCountBadge');
  if (!tbodyTop) return;
  try {
    const res = await fetch(`/api/balitower/inventory/purchase-orders?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (badgeTop) badgeTop.textContent = `${data ? data.length : 0} PO`;
      if (!data || data.length === 0) {
        tbodyTop.innerHTML = `<tr><td colspan="9" class="text-center" style="padding: 24px; color: var(--text-muted);">No Purchase Orders issued yet.</td></tr>`;
        return;
      }
      const rowsHtml = data.map(po => {
        let statusBadge = 'badge-pending';
        if (po.po_status === 'DELIVERED') statusBadge = 'badge-approved';
        else statusBadge = 'badge-pending';
        return `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 11.5px; font-weight: 700; color: #2563EB;">${escapeHtml(po.po_number)}</td>
            <td><strong>${escapeHtml(po.supplier_name)}</strong></td>
            <td>${escapeHtml(po.item_name)}</td>
            <td class="text-right" style="font-weight: 700; font-family: var(--font-mono);">${Number(po.order_quantity).toLocaleString('id-ID')}</td>
            <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #0F172A;">${formatCurrency(po.total_amount)}</td>
            <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(po.order_date)}</td>
            <td class="text-center" style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(po.expected_delivery || '-')}</td>
            <td class="text-center"><span class="badge ${statusBadge}">${escapeHtml(po.po_status)}</span></td>
            <td class="text-center" style="white-space: nowrap;">
              ${po.po_status === 'ORDERED' ? `
              <button class="btn btn-primary btn-xs" style="padding: 3px 8px; font-size: 11px; background: #16A34A; border-color: #15803D; margin-right: 4px; display: inline-flex; align-items: center; gap: 4px;" onclick="confirmGoodsReceiptQuick('${escapeHtml(po.po_id)}', '${escapeHtml(po.po_number)}')">
                <svg width="11" height="11" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                <span>Receive Goods</span>
              </button>
              ` : ''}
              <button class="btn btn-secondary btn-xs" style="padding: 3px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="openPoPdfModal('${escapeHtml(po.po_id)}', '${escapeHtml(po.po_number)}', '${escapeHtml(po.supplier_name)}', ${po.total_amount}, '${escapeHtml(po.po_status)}')">
                <svg width="11" height="11" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>PDF</span>
              </button>
            </td>
          </tr>
        `;
      }).join('');
      tbodyTop.innerHTML = rowsHtml;
    }
  } catch (e) {
    console.error("Failed to load POs:", e);
  }
}

function confirmGoodsReceiptQuick(poId, poNumber) {
  const input = document.getElementById('promptInput');
  if (input) {
    const targetPo = (poNumber && poNumber.trim()) ? poNumber : poId;
    input.value = `Barang untuk ${targetPo} sudah sampai di gudang, tolong catat penerimaannya`;
    input.focus();
    submitPrompt();
  }
}

// ==============================================================================
// DOMAIN 2: HR & FIELD WORKFORCE LOADERS
// ==============================================================================

async function loadEmployees() {
  const tbody = document.getElementById('hrEmployeesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/hr/employees?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      state.employees = data || [];
      filterEmployeesTable();
    } else {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Access restricted or data unavailable for this session.</td></tr>`;
    }
  } catch (e) {
    console.error("Failed to load employees:", e);
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Failed to load employee records.</td></tr>`;
  }
}

function renderEmployeesTable(data) {
  const tbody = document.getElementById('hrEmployeesTableBody');
  if (!tbody) return;
  updateSidebarRowCount(data ? data.length : 0, 'Employees');
  if (!data || data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">No matching employee records found.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.map(e => `
    <tr>
      <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(e.employee_id)}</td>
      <td><strong>${escapeHtml(e.full_name)}</strong></td>
      <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(e.department)}</span></td>
      <td>${escapeHtml(e.job_title)}</td>
      <td class="text-center"><span class="badge ${e.employment_status === 'PERMANENT' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(e.employment_status)}</span></td>
      <td class="text-center"><span class="badge ${e.k3_certification !== 'NON_CERTIFIED' ? 'badge-tkpk' : 'badge-pending'}">${escapeHtml(e.k3_certification)}</span></td>
      <td class="text-center" style="font-family: var(--font-mono); font-weight: 700; color: #0F172A;">${e.leave_balance_days} days</td>
    </tr>
  `).join('');
}

function filterEmployeesTable() {
  const search = (document.getElementById('searchEmployees')?.value || '').toLowerCase().trim();
  const list = state.employees || [];
  const filtered = list.filter(e => {
    return !search ||
      (e.full_name || '').toLowerCase().includes(search) ||
      (e.employee_id || '').toLowerCase().includes(search) ||
      (e.department || '').toLowerCase().includes(search) ||
      (e.job_title || '').toLowerCase().includes(search);
  });
  renderEmployeesTable(filtered);
}

async function loadJobPostings() {
  const tbody = document.getElementById('hrJobsTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/hr/job-postings?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">No open job postings available.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(j => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(j.job_id)}</td>
          <td><strong>${escapeHtml(j.job_title)}</strong></td>
          <td>${escapeHtml(j.department)}</td>
          <td class="text-center"><span class="badge badge-tkpk">${escapeHtml(j.required_k3_cert)}</span></td>
          <td class="text-center" style="font-family: var(--font-mono);">${j.min_experience_years} yrs</td>
          <td class="text-center" style="font-weight: 700; color: #2563EB;">${j.open_positions} pos</td>
          <td>${escapeHtml(j.work_location)}</td>
          <td class="text-center"><span class="badge ${j.status === 'OPEN' ? 'badge-approved' : 'badge-rejected'}">${escapeHtml(j.status)}</span></td>
        </tr>
      `).join('');
    } else {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Access restricted or data unavailable for this session.</td></tr>`;
    }
  } catch (e) {
    console.error("Failed to load job postings:", e);
    tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">Failed to load job postings.</td></tr>`;
  }
}

async function loadSites() {
  const tbody = document.getElementById('hrSitesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/hr/sites?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">No tower sites found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(s => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(s.site_id)}</td>
          <td><strong>${escapeHtml(s.site_name)}</strong></td>
          <td><span style="font-size: 11px; background: #EFF6FF; color: #1E40AF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${escapeHtml(s.site_type)}</span></td>
          <td>${escapeHtml(s.region)}</td>
          <td class="text-center" style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${Number(s.latitude).toFixed(4)}, ${Number(s.longitude).toFixed(4)}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 700;">${s.height_meters} m</td>
          <td>${escapeHtml(s.structure_type)}</td>
          <td class="text-center"><span class="badge" style="background:#F1F5F9; color:#475569;">${s.tenant_count} Operator</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load sites:", e);
  }
}

// --- HR & Field Workforce Data Loader ---
async function loadHrData() {
  try {
    // 1. HR Summary KPIs
    const sumRes = await fetch(`/api/balitower/hr/summary?t=${Date.now()}`, { cache: 'no-store' });
    if (sumRes.ok) {
      const s = await sumRes.json();
      const el1 = document.getElementById('kpiHrTotalEmp');
      if (el1) el1.textContent = s.total_employees;
      const el2 = document.getElementById('kpiHrFieldTech');
      if (el2) el2.textContent = s.field_technicians;
      const el3 = document.getElementById('kpiHrK3Cert');
      const el4 = document.getElementById('kpiHrJobOpenings') || document.getElementById('kpiHrOvertime');
      if (el4) el4.textContent = (s.open_job_vacancies !== undefined ? s.open_job_vacancies : 4);
    }

    // 3. Candidates Filter & Screening
    const candRes = await fetch(`/api/balitower/hr/candidates?t=${Date.now()}`, { cache: 'no-store' });
    const tbodyCand = document.getElementById('hrCandidatesTableBody');
    if (candRes.ok && tbodyCand) {
      const cands = await candRes.json();
      tbodyCand.innerHTML = cands.map(c => `
        <tr>
          <td><strong>${escapeHtml(c.full_name)}</strong><br><span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(c.current_city)}</span></td>
          <td>${escapeHtml(c.job_title)}<br><span style="font-size: 11px; color: var(--text-muted);">${c.years_of_experience} yrs experience</span></td>
          <td class="text-center"><span class="badge badge-tkpk">${escapeHtml(c.k3_cert_held)}</span></td>
          <td class="text-center"><span class="badge ${c.medical_checkup_status.includes('FIT_FOR_HEIGHT') ? 'badge-paid' : 'badge-unpaid'}">${escapeHtml(c.medical_checkup_status)}</span></td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #2563EB;">${c.technical_score}</td>
          <td class="text-center"><span class="badge badge-pending">${escapeHtml(c.recruitment_stage)}</span></td>
        </tr>
      `).join('');
    }

    // 4. Leave Requests
    const leaveRes = await fetch(`/api/balitower/hr/leave-requests?t=${Date.now()}`, { cache: 'no-store' });
    const tbodyLeave = document.getElementById('hrLeavesTableBody');
    if (leaveRes.ok && tbodyLeave) {
      const leaves = await leaveRes.json();
      if (!leaves || leaves.length === 0) {
        tbodyLeave.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 24px; color: var(--text-muted);">Belum ada riwayat permohonan cuti (0 Permohonan).</td></tr>`;
      } else {
        tbodyLeave.innerHTML = leaves.map(l => `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(l.leave_id)}</td>
            <td><strong>${escapeHtml(l.applicant_name)}</strong><br><span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(l.job_title)}</span></td>
            <td>${escapeHtml(l.leave_type)}</td>
            <td class="text-center" style="font-weight: 700;">${l.days_requested}</td>
            <td style="font-size: 11.5px;">${escapeHtml(l.reason)}<br><span style="color: var(--text-muted); font-size: 10.5px;">Start: ${l.start_date}</span></td>
            <td>${escapeHtml(l.substitute_name)}</td>
            <td class="text-center"><span class="badge ${l.approval_status === 'APPROVED' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(l.approval_status)}</span></td>
            <td class="text-center" style="white-space: nowrap;">
              <button class="btn btn-secondary btn-sm" onclick="openLeavePdfModal('${l.leave_id}', '${escapeHtml(l.applicant_name)}', '${escapeHtml(l.leave_type)}', ${l.days_requested}, '${escapeHtml(l.approval_status)}')" style="padding: 3px 10px; font-size: 11.5px;" title="View PDF Document">
                PDF
              </button>
            </td>
          </tr>
        `).join('');
      }
    }
    // Also keep employees table synchronized
    loadEmployees();
  } catch (e) {
    console.error("Failed to load HR data:", e);
  }
}

async function approveLeaveQuick(leaveId) {
  try {
    const res = await fetch(`/api/balitower/hr/leave-requests/${leaveId}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'APPROVE' })
    });
    if (res.ok) {
      showToast("Leave request approved successfully", "success");
      loadHrData();
      loadEmployees();
    }
  } catch (e) {
    showToast("Failed to approve leave request", "error");
  }
}

// ==============================================================================
// DOMAIN 3: FINANCE & TELECOM BILLING LOADERS
// ==============================================================================

async function loadClients() {
  const tbody = document.getElementById('finClientsTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/clients?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">No client operators found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(c => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(c.client_id)}</td>
          <td><strong>${escapeHtml(c.client_name)}</strong></td>
          <td><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(c.client_type)}</span></td>
          <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(c.npwp || '-')}</td>
          <td style="font-size: 11px; color: var(--text-muted);">${escapeHtml(c.billing_email || '-')}<br>${escapeHtml(c.phone || '-')}</td>
          <td class="text-center" style="font-weight: 700; font-family: var(--font-mono);">${c.active_lease_sites} Site</td>
          <td class="text-right" style="font-weight: 700; font-family: var(--font-mono);">${formatCurrency(c.credit_limit_idr)}</td>
          <td class="text-center" style="font-family: var(--font-mono);">${c.payment_terms_days} days</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load clients:", e);
  }
}

async function loadMlaContracts() {
  const tbody = document.getElementById('finMlaTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/mla-contracts?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">No MLA contracts found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(m => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(m.contract_id)}</td>
          <td><strong>${escapeHtml(m.client_name)}</strong></td>
          <td><strong>${escapeHtml(m.site_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(m.site_id)}</span></td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #0F172A;">${formatCurrency(m.monthly_rate)}</td>
          <td class="text-center"><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(m.billing_frequency)}</span></td>
          <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(m.start_date)} to ${escapeHtml(m.end_date)}</td>
          <td class="text-center"><span class="badge ${m.electricity_included ? 'badge-approved' : 'badge-pending'}">${m.electricity_included ? 'PLN Included' : 'Separate'}</span></td>
          <td class="text-center"><span class="badge ${m.status === 'ACTIVE' ? 'badge-approved' : 'badge-rejected'}">${escapeHtml(m.status)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load MLA contracts:", e);
  }
}

async function loadLandLeases() {
  const tbody = document.getElementById('finLandLeasesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/land-leases?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">No land lease records found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(l => {
        const isPaidActive = l.status === 'ACTIVE_PAID' || l.status === 'ACTIVE' || l.status === 'PAID';
        return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(l.lease_id)}</td>
          <td><strong>${escapeHtml(l.site_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(l.site_id)}</span></td>
          <td>${escapeHtml(l.region)}</td>
          <td>${escapeHtml(l.landowner_name)}</td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #DC2626;">${formatCurrency(l.annual_lease_cost)}</td>
          <td class="text-center" style="font-family: var(--font-mono);">${l.lease_duration_years} yrs</td>
          <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(l.end_date)}</td>
          <td class="text-center"><span class="badge ${isPaidActive ? 'badge-active_paid' : 'badge-pending'}">${escapeHtml(l.status)}</span></td>
        </tr>
      `;
      }).join('');
    }
  } catch (e) {
    console.error("Failed to load land leases:", e);
  }
}

async function loadSiteUtilities() {
  const tbody = document.getElementById('finUtilitiesTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/site-utilities?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center" style="padding: 20px; color: var(--text-muted);">No site utility records found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(u => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(u.utility_id)}</td>
          <td><strong>${escapeHtml(u.site_name)}</strong><br><span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--text-muted);">${escapeHtml(u.site_id)}</span></td>
          <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(u.billing_period)}</td>
          <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(u.pln_meter_id || '-')}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 600;">${formatCurrency(u.pln_cost)}</td>
          <td class="text-right" style="font-family: var(--font-mono); font-weight: 600;">${formatCurrency(u.genset_fuel_cost)}</td>
          <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: #DC2626;">${formatCurrency(u.total_utility_cost)}</td>
          <td class="text-center"><span class="badge ${u.paid_status === 'PAID' ? 'badge-paid' : 'badge-unpaid'}">${escapeHtml(u.paid_status)}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load site utilities:", e);
  }
}

async function loadCoa() {
  const tbody = document.getElementById('finCoaTableBody');
  if (!tbody) return;
  try {
    const res = await fetch(`/api/balitower/finance/chart-of-accounts?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 20px; color: var(--text-muted);">No Chart of Accounts records found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(a => `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11.5px; font-weight: 800; color: #2563EB;">${escapeHtml(a.account_code)}</td>
          <td><strong>${escapeHtml(a.account_name)}</strong></td>
          <td class="text-center"><span style="font-size: 11px; background: #F1F5F9; color: #475569; padding: 2px 6px; border-radius: 4px;">${escapeHtml(a.account_type)}</span></td>
          <td class="text-center"><span class="badge ${a.normal_balance === 'DEBIT' ? 'badge-approved' : 'badge-pending'}">${escapeHtml(a.normal_balance)}</span></td>
          <td style="font-size: 11.5px; color: #334155;">${escapeHtml(a.description || '-')}</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Failed to load COA:", e);
  }
}

// --- Finance & Accounting Data Loader ---
async function loadFinanceData() {
  try {
    // 1. Finance Summary KPIs
    const sumRes = await fetch(`/api/balitower/finance/summary?t=${Date.now()}`, { cache: 'no-store' });
    if (sumRes.ok) {
      const s = await sumRes.json();
      const el1 = document.getElementById('kpiFinRevenue');
      if (el1) el1.textContent = 'Rp ' + (s.total_revenue_billed_idr / 1000000).toFixed(1) + 'M';
      const el2 = document.getElementById('kpiFinPaid');
      if (el2) el2.textContent = 'Rp ' + (s.total_revenue_collected_idr / 1000000).toFixed(1) + 'M';
      const el3 = document.getElementById('kpiFinUnpaid');
      if (el3) el3.textContent = 'Rp ' + (s.outstanding_accounts_receivable_idr / 1000000).toFixed(1) + 'M';
      const el4 = document.getElementById('kpiFinNetCash');
      if (el4) el4.textContent = '+Rp ' + (s.net_cash_flow_idr / 1000000).toFixed(1) + 'M';
    }

    // 2. Revenue Invoices
    const invRes = await fetch(`/api/balitower/finance/invoices?t=${Date.now()}`, { cache: 'no-store' });
    if (invRes.ok) {
      const invs = await invRes.json();
      state.invoices = invs || [];
      filterInvoicesTable();
    }

    // 3. Transactions / General Ledger (if table element is present)
    const tbodyTrx = document.getElementById('finTrxTableBody');
    if (tbodyTrx) {
      const trxRes = await fetch(`/api/balitower/finance/transactions?limit=25&t=${Date.now()}`, { cache: 'no-store' });
      if (trxRes.ok) {
        const trxs = await trxRes.json();
        if (!trxs || trxs.length === 0) {
          tbodyTrx.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 20px; color: var(--text-muted);">No general ledger journal transactions found.</td></tr>`;
        } else {
          tbodyTrx.innerHTML = trxs.map(t => `
            <tr>
              <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${escapeHtml(t.trx_id)}</td>
              <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(t.trx_date)}</td>
              <td><span style="font-weight: 600;">${escapeHtml(t.account_name)}</span></td>
              <td class="text-center"><span class="${t.trx_type === 'INFLOW' ? 'badge-inflow' : 'badge-outflow'}">${t.trx_type === 'INFLOW' ? '+ INFLOW' : '- OUTFLOW'}</span></td>
              <td class="text-right" style="font-weight: 800; font-family: var(--font-mono); color: ${t.trx_type === 'INFLOW' ? '#059669' : '#DC2626'};">Rp ${Number(t.amount).toLocaleString('id-ID')}</td>
              <td style="font-size: 11.5px; color: #334155;">${escapeHtml(t.description || '-')}</td>
            </tr>
          `).join('');
        }
      }
    }
  } catch (e) {
    console.error("Failed to load Finance data:", e);
  }
}

function renderInvoicesTable(data) {
  const tbodyInv = document.getElementById('finInvoicesTableBody');
  if (!tbodyInv) return;
  updateSidebarRowCount(data ? data.length : 0, 'Invoices');
  if (!data || data.length === 0) {
    tbodyInv.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">No matching invoices found.</td></tr>`;
    return;
  }
  tbodyInv.innerHTML = data.map(i => {
    const isPaid = (i.payment_status || '').toUpperCase() === 'PAID' || (i.payment_status || '').toUpperCase() === 'ACTIVE_PAID';
    const displayStatus = isPaid ? 'PAID' : 'PENDING';
    const badgeClass = isPaid ? 'badge-paid' : 'badge-pending';
    const invId = i.invoice_id || '';
    const invNum = i.invoice_number || '';
    const clientName = i.client_name || '';
    const totalBilled = Number(i.total_billed || 0);
    const cleanDueDate = i.due_date ? String(i.due_date).split(' ')[0].split('T')[0] : '-';

    return `
    <tr>
      <td style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; color: #2563EB;">${escapeHtml(invNum)}</td>
      <td><strong>${escapeHtml(clientName)}</strong></td>
      <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(i.period_covered || '-')}</td>
      <td class="text-right" style="font-weight: 800; font-family: var(--font-mono);">Rp ${totalBilled.toLocaleString('id-ID')}</td>
      <td class="text-center" style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(cleanDueDate)}</td>
      <td class="text-center"><span class="badge ${badgeClass}">${displayStatus}</span></td>
      <td class="text-center">
        <button class="btn btn-secondary btn-sm" style="padding: 3px 9px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;" onclick="openInvoicePdfModal('${escapeHtml(invId)}', '${escapeHtml(invNum)}', '${escapeHtml(clientName)}', ${totalBilled}, '${displayStatus}')" title="Open Official PDF Document">
          <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <span>PDF</span>
        </button>
      </td>
    </tr>
  `;
  }).join('');
}

function filterInvoicesTable() {
  const search = (document.getElementById('searchInvoices')?.value || '').toLowerCase().trim();
  const list = state.invoices || [];
  const filtered = list.filter(i => {
    return !search ||
      (i.invoice_number || '').toLowerCase().includes(search) ||
      (i.client_name || '').toLowerCase().includes(search);
  });
  renderInvoicesTable(filtered);
}

async function loadDashboardStats() {
  try {
    const res = await fetch(`/api/stream/inventory-summary?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      state.stats = await res.json();
    }
  } catch (e) {
    console.error("Failed to fetch stats:", e);
  }
}

// --- Inventory Catalog ---
async function loadInventoryItems() {
  const tbody = document.getElementById('catalogTableBody');
  try {
    let res = await fetch(`/api/balitower/inventory/items?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) {
      res = await fetch(`/api/inventory/items?t=${Date.now()}`, { cache: 'no-store' });
    }
    if (res.ok) {
      const rawItems = await res.json();
      state.items = (rawItems || []).map(it => ({
        sku: it.item_code || it.item_id || it.sku || '',
        name: it.name || it.item_name || '',
        supplier_name: it.supplier_name || '-',
        category: it.category || 'General',
        current_stock: Number(it.total_stock !== undefined ? it.total_stock : it.current_stock) || 0,
        unit: it.unit || 'pcs',
        min_stock: Number(it.min_stock !== undefined ? it.min_stock : it.min_threshold) || 0,
        max_stock: Number(it.max_stock !== undefined ? it.max_stock : (it.max_threshold !== undefined ? it.max_threshold : (it.min_stock * 3))) || 0,
        unit_price: Number(it.unit_price) || 0,
        stock_status: it.stock_status || ''
      }));
      filterCatalogTable();
    } else {
      const err = await res.json().catch(() => ({}));
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: #DC2626; font-weight: 500;">Failed to load inventory data (${escapeHtml(err.detail || 'HTTP ' + res.status)}). Please sign in again.</td></tr>`;
      }
    }
  } catch (e) {
    console.error("Failed to load inventory:", e);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 24px; color: #DC2626; font-weight: 500;">Connection error while fetching catalog.</td></tr>`;
    }
  }
}

function renderCatalogTable(items) {
  const tbody = document.getElementById('catalogTableBody');
  if (!tbody) return;
  updateSidebarRowCount(items ? items.length : 0, 'Catalog Items');

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 20px; color: var(--text-muted);">Catalog is empty or no matching items found.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(it => {
    let badgeClass = 'badge-normal';
    let statusLabel = 'Normal';
    if (it.current_stock === 0) {
      badgeClass = 'badge-out_of_stock';
      statusLabel = 'Out of Stock';
    } else if (it.current_stock < it.min_stock) {
      badgeClass = 'badge-out_of_stock';
      statusLabel = 'Critical';
    } else if (it.current_stock <= it.min_stock * 1.3) {
      badgeClass = 'badge-low_stock';
      statusLabel = 'Warning';
    }

    return `
      <tr>
        <td>
          <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 11.5px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${it.sku}</span>
        </td>
        <td>
          <div style="font-weight: 600; color: #0F172A;">${escapeHtml(it.name)}</div>
        </td>
        <td>
          <span style="font-size: 11px; background: #F1F5F9; color: #475569; border: 1px solid #E2E8F0; padding: 2px 6px; border-radius: 4px;">${escapeHtml(it.category)}</span>
        </td>
        <td class="text-right" style="font-weight: 700; color: #0F172A;">${it.current_stock.toLocaleString('id-ID')} <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">${it.unit}</span></td>
        <td class="text-right" style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">${it.min_stock.toLocaleString('id-ID')} / ${it.max_stock.toLocaleString('id-ID')}</td>
        <td class="text-right" style="font-weight: 600; color: #0F172A;">${formatCurrency(it.unit_price)}</td>
        <td class="text-center"><span class="badge ${badgeClass}">${statusLabel}</span></td>
      </tr>
    `;
  }).join('');
}

function filterCatalogTable() {
  const search = document.getElementById('searchCatalog')?.value.toLowerCase() || '';
  const category = document.getElementById('filterCategory')?.value || '';

  const filtered = state.items.filter(it => {
    const matchSearch = it.name.toLowerCase().includes(search) || it.sku.toLowerCase().includes(search);
    const matchCat = !category || it.category.toLowerCase() === category.toLowerCase();
    return matchSearch && matchCat;
  });

  renderCatalogTable(filtered);
}

// --- Purchase Requisitions ---
async function loadApprovals() {
  try {
    const res = await fetch(`/api/approval/list?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) {
      const allPrs = await res.json();

      state.prs = allPrs.sort((a, b) => {
        const aPending = String(a.status).toUpperCase() === 'PENDING' ? 1 : 0;
        const bPending = String(b.status).toUpperCase() === 'PENDING' ? 1 : 0;
        if (aPending !== bPending) return bPending - aPending;
        return (b.pr_number || '').localeCompare(a.pr_number || '');
      });

      renderPrsTable(state.prs);
    }
  } catch (e) {
    console.error("Failed to load PRs:", e);
  }
}

function renderPrsTable(prs) {
  const tbody = document.getElementById('prsTableBody');
  if (!tbody) return;

  if (!prs || prs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 20px; color: var(--text-muted);">No Purchase Requisitions issued yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = prs.map(pr => {
    const rawStatus = String(pr.status || '').toUpperCase();
    const isApproved = rawStatus === 'APPROVED';
    const isRejected = rawStatus === 'REJECTED';

    let supplierName = pr.supplier_name;
    if (!supplierName && pr.items && pr.items.length > 0) {
      const vendors = Array.from(new Set(pr.items.map(it => it.vendor_name).filter(Boolean)));
      if (vendors.length === 1) supplierName = vendors[0];
      else if (vendors.length > 1) supplierName = `Multi-Vendor (${vendors.length})`;
    }
    supplierName = supplierName || 'Vendor Terdaftar';
    const escapedSupplier = escapeHtml(supplierName).replace(/'/g, "\\'");

    const grandTotal = Number(pr.total_budget ?? pr.grand_total ?? 0);

    let badgeClass = 'badge-pending';
    let statusLabel = 'PENDING';
    if (isApproved) {
      badgeClass = 'badge-approved';
      statusLabel = 'APPROVED';
    } else if (isRejected) {
      badgeClass = 'badge-rejected';
      statusLabel = 'REJECTED';
    }

    const isAdmin = sessionStorage.getItem('role') === 'ADMIN';

    return `
      <tr id="row-pr-${pr.pr_number}">
        <td style="white-space: nowrap;">
          <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 11.5px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${pr.pr_number}</span>
        </td>
        <td style="font-weight: 600; color: #0F172A; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(supplierName)}">
          ${escapeHtml(supplierName)}
        </td>
        <td class="text-center" style="color: var(--text-secondary); white-space: nowrap;">${pr.items?.length || 0} items</td>
        <td class="text-right" style="font-weight: 700; color: #0F172A; white-space: nowrap;">${formatCurrency(grandTotal)}</td>
        <td class="text-center" id="badge-container-${pr.pr_number}" style="white-space: nowrap;">
          <span class="badge ${badgeClass}">${statusLabel}</span>
        </td>
        <td class="text-center" style="white-space: nowrap;">
          <div style="display: inline-flex; gap: 4px;" id="actions-container-${pr.pr_number}">
            <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${grandTotal}, '${rawStatus}')">
              View PDF
            </button>
            ${!isApproved && !isRejected && isAdmin ? `
              <button class="btn btn-success btn-sm btn-approve-action" data-pr="${pr.pr_number}" onclick="approvePrQuick('${pr.pr_number}')">
                Approve
              </button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// --- In-App PDF Preview Modal ---
function openPdfModal(prNumber, supplierName, grandTotal, status) {
  state.currentModalPrNumber = prNumber;
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  // Resolve current status from state.prs if available to avoid stale feed status
  const foundPr = state.prs?.find(p => p.pr_number === prNumber);
  const effectiveStatus = foundPr ? foundPr.status : status;

  const rawStatus = String(effectiveStatus || '').toUpperCase();
  const isApproved = rawStatus === 'APPROVED';
  const isRejected = rawStatus === 'REJECTED';
  const isAdmin = sessionStorage.getItem('role') === 'ADMIN';

  document.getElementById('modalPrNumber').textContent = prNumber;
  document.getElementById('modalSupplierName').textContent = supplierName ? `| ${supplierName}` : '';
  document.getElementById('modalGrandTotal').textContent = `Grand Total: ${formatCurrency(grandTotal || 0)}`;

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    if (isApproved) {
      statusBadge.className = 'badge badge-approved';
      statusBadge.textContent = 'APPROVED';
    } else if (isRejected) {
      statusBadge.className = 'badge badge-rejected';
      statusBadge.textContent = 'REJECTED';
    } else {
      statusBadge.className = 'badge badge-pending';
      statusBadge.textContent = 'PENDING APPROVAL';
    }
  }

  // Setujui button in modal: ONLY for ADMIN and ONLY when status is PENDING
  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) {
    if (isAdmin && !isApproved && !isRejected) {
      modalApproveBtn.style.display = 'inline-flex';
      modalApproveBtn.disabled = false;
      modalApproveBtn.innerHTML = `
        <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
        </svg>
        <span>Approve PR Document</span>
      `;
    } else {
      modalApproveBtn.style.display = 'none';
    }
  }

  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/pr/${prNumber}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${prNumber}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

function closePdfModal() {
  const modal = document.getElementById('pdfPreviewModal');
  if (modal) {
    modal.classList.remove('open');
    const iframe = document.getElementById('pdfPreviewIframe');
    if (iframe) iframe.src = 'about:blank';
  }
}

// --- Open Official Purchase Order (PO) Typst PDF In-App Preview Modal ---
function openPoPdfModal(poId, poNumber, supplierName, grandTotal, poStatus) {
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  const prNumberEl = document.getElementById('modalPrNumber');
  if (prNumberEl) prNumberEl.textContent = poNumber || poId;

  const supplierNameEl = document.getElementById('modalSupplierName');
  if (supplierNameEl) supplierNameEl.textContent = supplierName || "Official Purchase Order";

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    const rawStatus = (poStatus || "ORDERED").toUpperCase();
    if (rawStatus === 'DELIVERED') statusBadge.className = 'badge badge-approved';
    else statusBadge.className = 'badge badge-pending';
    statusBadge.textContent = rawStatus;
  }

  const grandTotalEl = document.getElementById('modalGrandTotal');
  if (grandTotalEl) grandTotalEl.textContent = grandTotal ? `PO Budget Total: ${formatCurrency(grandTotal)}` : "Official Purchase Order PT Bali Towerindo Sentra Tbk";

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) modalApproveBtn.style.display = 'none';

  const cleanPoId = encodeURIComponent(poId);
  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/po/${cleanPoId}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${poId}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/po/${cleanPoId}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/po/${cleanPoId}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

// --- Open Official Leave Request Typst PDF In-App Preview Modal ---
function openLeavePdfModal(leaveId, applicantName, leaveType, daysRequested, status) {
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  const prNumberEl = document.getElementById('modalPrNumber');
  if (prNumberEl) prNumberEl.textContent = leaveId;

  const supplierNameEl = document.getElementById('modalSupplierName');
  if (supplierNameEl) supplierNameEl.textContent = `${applicantName} - ${leaveType}`;

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    const rawStatus = (status || "PENDING_APPROVAL").toUpperCase();
    if (rawStatus === 'APPROVED') statusBadge.className = 'badge badge-approved';
    else if (rawStatus === 'REJECTED') statusBadge.className = 'badge badge-rejected';
    else statusBadge.className = 'badge badge-pending';
    statusBadge.textContent = rawStatus;
  }

  const grandTotalEl = document.getElementById('modalGrandTotal');
  if (grandTotalEl) grandTotalEl.textContent = `Leave Duration: ${daysRequested} Working Days`;

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) modalApproveBtn.style.display = 'none';

  const cleanLeaveId = encodeURIComponent(leaveId);
  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/leave/${cleanLeaveId}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${leaveId}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/leave/${cleanLeaveId}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/leave/${cleanLeaveId}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

// --- Open Official Tower Lease Invoice Typst PDF In-App Preview Modal ---
function openInvoicePdfModal(invoiceId, invoiceNumber, clientName, totalBilled, status) {
  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;

  const prNumberEl = document.getElementById('modalPrNumber');
  if (prNumberEl) prNumberEl.textContent = invoiceNumber || invoiceId;

  const supplierNameEl = document.getElementById('modalSupplierName');
  if (supplierNameEl) supplierNameEl.textContent = clientName || "Tower Lease Agreement & Billing Invoice";

  const statusBadge = document.getElementById('modalPrStatusBadge');
  if (statusBadge) {
    const rawStatus = (status || "PENDING").toUpperCase();
    if (rawStatus === 'PAID' || rawStatus === 'ACTIVE_PAID') {
      statusBadge.className = 'badge badge-paid';
      statusBadge.textContent = 'PAID';
    } else {
      statusBadge.className = 'badge badge-pending';
      statusBadge.textContent = 'PENDING';
    }
  }

  const grandTotalEl = document.getElementById('modalGrandTotal');
  if (grandTotalEl) grandTotalEl.textContent = totalBilled ? `Total Billed: ${formatCurrency(totalBilled)}` : "Tower Lease Agreement & Billing Invoice PT Bali Towerindo Sentra Tbk";

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) modalApproveBtn.style.display = 'none';

  const cleanInvId = encodeURIComponent(invoiceId);
  const downloadBtn = document.getElementById('modalDownloadBtn');
  if (downloadBtn) {
    downloadBtn.href = `/api/documents/invoice/${cleanInvId}/download?download=true&t=${Date.now()}`;
    downloadBtn.setAttribute('download', `${invoiceId}.pdf`);
  }

  const openTabBtn = document.getElementById('modalOpenTabBtn');
  if (openTabBtn) {
    openTabBtn.href = `/api/documents/invoice/${cleanInvId}/download?inline=true&t=${Date.now()}`;
  }

  const iframe = document.getElementById('pdfPreviewIframe');
  if (iframe) {
    iframe.src = `/api/documents/invoice/${cleanInvId}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
  }

  modal.classList.add('open');
}

// --- Approve Action From Inside Modal ---
async function approvePrFromModal() {
  const prNumber = state.currentModalPrNumber;
  if (!prNumber) return;

  const modalApproveBtn = document.getElementById('modalApproveBtn');
  if (modalApproveBtn) {
    modalApproveBtn.disabled = true;
    modalApproveBtn.textContent = "Approving...";
  }

  await approvePrQuick(prNumber);

  // If still in modal, ensure view is refreshed to APPROVED
  if (state.currentModalPrNumber === prNumber) {
    const statusBadge = document.getElementById('modalPrStatusBadge');
    if (statusBadge) {
      statusBadge.className = 'badge badge-approved';
      statusBadge.textContent = 'APPROVED';
    }
    if (modalApproveBtn) {
      modalApproveBtn.style.display = 'none';
    }
    const iframe = document.getElementById('pdfPreviewIframe');
    if (iframe) {
      iframe.src = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
    }
  }
}

// --- Quick Approve Action ---
async function approvePrQuick(prNumber) {
  const allActionButtons = document.querySelectorAll(`[data-pr="${prNumber}"]`);
  allActionButtons.forEach(btn => {
    btn.disabled = true;
    btn.textContent = "Approving...";
  });

  try {
    const res = await fetch('/api/approval/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pr_number: prNumber,
        action: 'APPROVE',
        manager_name: sessionStorage.getItem('username') || 'Warehouse Manager'
      })
    });

    if (res.ok) {
      showToast(`Purchase Requisition ${prNumber} approved successfully`, 'success');

      // Update PR status in local state
      if (state.prs) {
        const p = state.prs.find(item => item.pr_number === prNumber);
        if (p) p.status = 'APPROVED';
      }

      allActionButtons.forEach(btn => {
        const approvedBadge = document.createElement('span');
        approvedBadge.className = 'badge badge-approved';
        approvedBadge.textContent = 'APPROVED';
        btn.replaceWith(approvedBadge);
      });

      const tableBadgeContainer = document.getElementById(`badge-container-${prNumber}`);
      if (tableBadgeContainer) {
        tableBadgeContainer.innerHTML = `<span class="badge badge-approved">APPROVED</span>`;
      }

      // If the modal is currently open for this PR, update modal header & refresh iframe
      if (state.currentModalPrNumber === prNumber) {
        const statusBadge = document.getElementById('modalPrStatusBadge');
        if (statusBadge) {
          statusBadge.className = 'badge badge-approved';
          statusBadge.textContent = 'APPROVED';
        }
        const modalApproveBtn = document.getElementById('modalApproveBtn');
        if (modalApproveBtn) {
          modalApproveBtn.style.display = 'none';
        }
        const iframe = document.getElementById('pdfPreviewIframe');
        if (iframe) {
          iframe.src = `/api/documents/pr/${prNumber}/download?inline=true&t=${Date.now()}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
        }
      }

      await loadAllData();
      saveCopilotFeed();
    } else {
      throw new Error("Failed to approve document.");
    }
  } catch (e) {
    showToast(e.message || "Failed to approve PR", "error");
    allActionButtons.forEach(btn => {
      btn.disabled = false;
      btn.textContent = "Approve";
    });
  }
}

// --- Interactive Prompt Auto-Resizing & Submission ---
function autoResizePromptInput() {
  const textarea = document.getElementById('promptInput');
  if (!textarea) return;
  textarea.style.height = 'auto';
  const newHeight = Math.min(Math.max(textarea.scrollHeight, 24), 220);
  textarea.style.height = newHeight + 'px';
  
  const container = textarea.closest('.input-bar-container');
  if (container) {
    if (newHeight > 34) {
      container.classList.add('is-multiline');
    } else {
      container.classList.remove('is-multiline');
    }
    if (textarea.value && textarea.value.trim().length > 0) {
      container.classList.add('has-value');
    } else {
      container.classList.remove('has-value');
    }
  }

  if (window.claudePromptTypewriter) {
    window.claudePromptTypewriter.updateVisibility();
  }
}

function initPromptInputAutoResize() {
  const textarea = document.getElementById('promptInput');
  if (!textarea) return;
  textarea.addEventListener('input', autoResizePromptInput);
  textarea.addEventListener('paste', () => setTimeout(autoResizePromptInput, 0));
  textarea.addEventListener('focus', autoResizePromptInput);
  textarea.addEventListener('blur', autoResizePromptInput);
  autoResizePromptInput();

  // Initialize Claude-style typewriter controller
  if (!window.claudePromptTypewriter) {
    window.claudePromptTypewriter = new ClaudePromptTypewriter();
  }
}

function handlePromptInputChange() {
  autoResizePromptInput();
  if (window.claudePromptTypewriter) {
    window.claudePromptTypewriter.updateVisibility();
  }
}

function handlePromptInputFocus() {
  autoResizePromptInput();
  if (window.claudePromptTypewriter) {
    window.claudePromptTypewriter.updateVisibility();
  }
}

function handlePromptInputBlur() {
  autoResizePromptInput();
  if (window.claudePromptTypewriter) {
    window.claudePromptTypewriter.updateVisibility();
  }
}

// --- Claude-Style Dynamic Rotating Prompt Typewriter ---
function getTenantTypewriterPrompts(tenant) {
  if (tenant === 'INVENTORY') {
    return [
      "What's on your mind? Ask operational workflows, analytics, or tasks...",
      "Tanyakan stok material menara & kabel fiber optic...",
      "Catat penerimaan PO tiba (contoh: PO-2026-006 sampai di Bandung)...",
      "Buat draf Purchase Requisition (PR) untuk restock material menara...",
      "Periksa safety stock material yang berada di bawah ambang batas...",
      "Kirim dokumen resmi PR & PO format PDF ke email manajer logistik..."
    ];
  } else if (tenant === 'HR') {
    return [
      "What's on your mind? Ask HR, workforce, or technician management...",
      "Mutasi divisi atau posisi jabatan karyawan (contoh: mutasi Dewi Lestari ke IT)...",
      "Ajukan permohonan cuti teknisi lapangan (cuti tahunan / sakit)...",
      "Cari teknisi rigger bersertifikat K3 TKPK aktif...",
      "Audit daftar pengajuan cuti yang masih pending persetujuan...",
      "Tampilkan daftar lowongan kerja teknisi dan kualifikasi K3..."
    ];
  } else if (tenant === 'FINANCE') {
    return [
      "What's on your mind? Ask billing, contracts, or tower finance...",
      "Cek daftar invoice sewa menara operator yang jatuh tempo...",
      "Tampilkan rincian kontrak Master Lease Agreement (MLA) Indosat...",
      "Audit biaya utilitas listrik PLN & sewa lahan site menara...",
      "Kirim draf tagihan invoice perdana dan mutasi kas ke email finance..."
    ];
  } else {
    return [
      "What's on your mind? Ask operational workflows, analytics, or tasks...",
      "Tanyakan stok material menara telekomunikasi & kabel fiber optic...",
      "Catat penerimaan PO tiba di gudang regional...",
      "Buat draf Purchase Requisition (PR) restock material menara...",
      "Ajukan permohonan cuti teknisi atau cek invoice jatuh tempo..."
    ];
  }
}

class ClaudePromptTypewriter {
  constructor() {
    this.overlayEl = document.getElementById('promptTypewriterOverlay');
    this.textEl = document.getElementById('typewriterText');
    this.inputEl = document.getElementById('promptInput');
    this.containerEl = document.getElementById('inputBarContainer');
    this.prompts = [];
    this.currentPromptIndex = 0;
    this.charIndex = 0;
    this.isDeleting = false;
    this.timer = null;
    this.typingSpeed = 38;
    this.deletingSpeed = 20;
    this.pauseDuration = 3200;
    this.pauseAfterDelete = 400;

    this.init();
  }

  init() {
    if (!this.inputEl) return;

    this.inputEl.addEventListener('input', () => this.updateVisibility());
    this.inputEl.addEventListener('focus', () => this.updateVisibility());
    this.inputEl.addEventListener('blur', () => this.updateVisibility());

    const initialTenant = getEffectiveTenant();
    window.activeTenant = initialTenant;
    this.setTenant(initialTenant);
  }

  setTenant(tenant) {
    const newPrompts = getTenantTypewriterPrompts(tenant);
    this.prompts = newPrompts;
    this.currentPromptIndex = 0;
    this.charIndex = 0;
    this.isDeleting = false;
    if (this.timer) clearTimeout(this.timer);
    this.tick();
  }

  updateVisibility() {
    if (!this.inputEl) return;
    const hasValue = Boolean(this.inputEl.value && this.inputEl.value.trim().length > 0);
    if (this.containerEl) {
      if (hasValue) {
        this.containerEl.classList.add('has-value');
      } else {
        this.containerEl.classList.remove('has-value');
      }
    }
    if (this.overlayEl) {
      if (hasValue) {
        this.overlayEl.classList.add('is-hidden');
      } else {
        this.overlayEl.classList.remove('is-hidden');
      }
    }
  }

  tick() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    if (!this.prompts || this.prompts.length === 0 || !this.textEl) return;

    const currentString = this.prompts[this.currentPromptIndex];

    if (!this.isDeleting) {
      this.charIndex++;
      this.textEl.textContent = currentString.substring(0, this.charIndex);

      if (this.charIndex >= currentString.length) {
        this.isDeleting = true;
        this.timer = setTimeout(() => this.tick(), this.pauseDuration);
        return;
      }

      const variance = Math.floor(Math.random() * 15);
      this.timer = setTimeout(() => this.tick(), this.typingSpeed + variance);
    } else {
      this.charIndex--;
      this.textEl.textContent = currentString.substring(0, this.charIndex);

      if (this.charIndex <= 0) {
        this.isDeleting = false;
        this.currentPromptIndex = (this.currentPromptIndex + 1) % this.prompts.length;
        this.timer = setTimeout(() => this.tick(), this.pauseAfterDelete);
        return;
      }

      this.timer = setTimeout(() => this.tick(), this.deletingSpeed);
    }
  }
}

// --- Quick Action Chip Handler ---
function quickFillPrompt(promptText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = promptText;
    autoResizePromptInput();
    if (window.claudePromptTypewriter) {
      window.claudePromptTypewriter.updateVisibility();
    }
    input.focus();
    submitPrompt();
  }
}

// --- Global Prompt Execution & Abort Controller (Gemini Style Stop Action) ---
let activePromptAbortController = null;
let isAgentPromptRunning = false;

function setAgentPromptRunning(isRunning) {
  isAgentPromptRunning = isRunning;
  const btn = document.getElementById('btnSendPrompt');
  if (!btn) return;

  if (isRunning) {
    btn.classList.add('btn-stop-state');
    btn.disabled = false;
    btn.setAttribute('title', 'Stop response');
    btn.setAttribute('aria-label', 'Stop response');
    btn.innerHTML = `
      <svg class="stop-icon" width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
        <rect x="5" y="5" width="14" height="14" rx="2" />
      </svg>
    `;
  } else {
    btn.classList.remove('btn-stop-state');
    btn.disabled = false;
    btn.setAttribute('title', 'Send instruction');
    btn.setAttribute('aria-label', 'Send instruction');
    btn.innerHTML = `
      <span>Send</span>
      <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/>
      </svg>
    `;
  }
}

function stopPromptExecution() {
  if (activePromptAbortController) {
    activePromptAbortController.abort();
    activePromptAbortController = null;
  }
  setAgentPromptRunning(false);
}

// Global keydown listener for Escape key to dismiss modals or cancel ongoing prompt execution (M-3)
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const pdfModal = document.getElementById('pdfPreviewModal');
    if (pdfModal && pdfModal.classList.contains('open')) {
      e.preventDefault();
      closePdfModal();
      return;
    }
    const helpModal = document.getElementById('flowHelpModal');
    if (helpModal && helpModal.style.display !== 'none' && helpModal.style.display !== '') {
      e.preventDefault();
      closeFlowHelpModal();
      return;
    }
    if (isAgentPromptRunning) {
      e.preventDefault();
      stopPromptExecution();
    }
  }
});

// --- Interactive Prompt Submission ---
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (isAgentPromptRunning) return; // Prevent duplicate submission while running
    submitPrompt();
  } else if (e.key === 'Enter' && e.shiftKey) {
    setTimeout(autoResizePromptInput, 0);
  }
}

function useClarificationHint(hintText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = hintText;
    input.focus();
    submitPrompt();
  }
}

function handleStreamAborted(streamBubble, accumulatedText = '') {
  if (!streamBubble) return;

  const cursor = streamBubble.querySelector('.stream-cursor');
  if (cursor) cursor.remove();

  const inlineCancel = streamBubble.querySelector('.btn-cancel-inline');
  if (inlineCancel) inlineCancel.remove();

  const activeChips = streamBubble.querySelectorAll('.stage-chip.active');
  activeChips.forEach(c => {
    c.classList.remove('active');
    c.classList.add('done');
    const pulse = c.querySelector('.stage-pulse-dot');
    if (pulse) pulse.remove();
  });

  const stagesContainer = streamBubble.querySelector('.stage-chips-container');
  if (stagesContainer) {
    const stoppedChip = document.createElement('div');
    stoppedChip.className = 'stage-chip stopped';
    stoppedChip.innerHTML = `
      <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" style="color: #64748B;"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
      <span>Dibatalkan oleh pengguna</span>
    `;
    stagesContainer.appendChild(stoppedChip);
  }

  const textSlot = streamBubble.querySelector('.stream-text-slot');
  if (textSlot) {
    if (accumulatedText) {
      textSlot.innerHTML = formatMarkdownResponse(accumulatedText) + `
        <div class="stream-stopped-hint">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
          <span>Proses pembuatan respon dihentikan.</span>
        </div>
      `;
    }
  }
  scrollChatToBottom();
}

window.quickFillPrompt = function(promptText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = promptText;
    if (typeof autoResizePromptInput === 'function') autoResizePromptInput();
    submitPrompt();
  }
};

async function submitPrompt() {
  // If agent is currently running and user clicks the Stop button:
  if (isAgentPromptRunning) {
    stopPromptExecution();
    return;
  }

  const input = document.getElementById('promptInput');
  if (!input) return;

  const promptText = input.value.trim();
  if (!promptText) return;

  input.value = '';
  input.style.height = 'auto';
  const barContainer = input.closest('.input-bar-container');
  if (barContainer) {
    barContainer.classList.remove('is-multiline');
    barContainer.classList.remove('has-value');
  }
  if (window.claudePromptTypewriter) {
    window.claudePromptTypewriter.updateVisibility();
  }

  const chatHistory = getChatHistory();
  appendUserMessage(promptText);

  const lower = promptText.toLowerCase();
  const isAuditOrReview = ["periksa", "cek", "audit", "tinjau", "lihat", "daftar", "rekap", "pending", "status", "laporan", "otorisasi", "persetujuan"].some(w => lower.includes(w));
  const isLeaveFormIntent = !isAuditOrReview && [
    "ajukan cuti", "input cuti", "buka form cuti", "buka formulir cuti", "isi form cuti", 
    "isi formulir cuti", "minta cuti", "mau cuti", "input data cuti", "buat pengajuan cuti",
    "buat cuti", "form permohonan cuti", "formulir permohonan cuti"
  ].some(k => lower.includes(k));

  if (isLeaveFormIntent && (getEffectiveTenant() === 'HR' || getEffectiveTenant() === 'ALL')) {
    renderLeaveRequestChatForm();
    saveCopilotFeed();
    return;
  }

  const streamBubble = appendAgentStreamBubble();
  activePromptAbortController = new AbortController();
  setAgentPromptRunning(true);

  try {
    const res = await fetch('/api/agent/stream-prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: promptText, destinations: [], history: chatHistory }),
      signal: activePromptAbortController.signal
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      if (streamBubble) streamBubble.remove();
      appendAgentErrorMessage(errJson.detail || "Failed to process instruction.");
      saveCopilotFeed();
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedText = '';
    let completedPayload = null;

    // Claude-style smooth typewriter streamer
    let displayedText = '';
    let typewriterInterval = null;

    const flushTypewriter = () => {
      if (typewriterInterval) {
        clearInterval(typewriterInterval);
        typewriterInterval = null;
      }
      if (displayedText !== accumulatedText) {
        displayedText = accumulatedText;
        updateStreamText(streamBubble, displayedText);
      }
    };

    const pumpTypewriter = () => {
      if (!streamBubble || activePromptAbortController?.signal?.aborted) {
        if (typewriterInterval) clearInterval(typewriterInterval);
        typewriterInterval = null;
        return;
      }
      const diff = accumulatedText.length - displayedText.length;
      if (diff > 0) {
        // Natural adaptive typing pace: smooth & responsive
        const step = diff > 80 ? Math.ceil(diff / 4) : (diff > 30 ? 4 : (diff > 10 ? 2 : 1));
        displayedText = accumulatedText.substring(0, displayedText.length + step);
        updateStreamText(streamBubble, displayedText);
      }
    };

    typewriterInterval = setInterval(pumpTypewriter, 18);

    while (true) {
      if (activePromptAbortController?.signal?.aborted) break;

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (activePromptAbortController?.signal?.aborted) break;

        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const rawJson = trimmed.substring(5).trim();
        if (!rawJson) continue;

        try {
          const evt = JSON.parse(rawJson);
          if (evt.type === 'status') {
            updateStreamStage(streamBubble, evt.stage, evt.message);
          } else if (evt.type === 'clarification') {
            renderClarificationBox(streamBubble, evt.clarification);
          } else if (evt.type === 'token') {
            accumulatedText += evt.content;
            if (!typewriterInterval) {
              typewriterInterval = setInterval(pumpTypewriter, 18);
            }
          } else if (evt.type === 'complete') {
            completedPayload = evt.payload;
          } else if (evt.type === 'error') {
            throw new Error(evt.message || "Error streaming response.");
          }
        } catch (err) {
          console.warn('Error parsing stream event:', err, rawJson);
        }
      }
    }

    // Smoothly drain any remaining backlog
    if (accumulatedText.length > displayedText.length && !activePromptAbortController?.signal?.aborted) {
      const startDrain = Date.now();
      while (displayedText.length < accumulatedText.length && (Date.now() - startDrain) < 180) {
        await new Promise(r => setTimeout(r, 18));
        pumpTypewriter();
      }
    }
    flushTypewriter();

    // Check if aborted right after loop
    if (activePromptAbortController?.signal?.aborted) {
      handleStreamAborted(streamBubble, accumulatedText);
      saveCopilotFeed();
      return;
    }

    // Finalize stream bubble with complete response data
    finalizeStreamBubble(streamBubble, completedPayload, accumulatedText);
    await loadAllData();
    saveCopilotFeed();

  } catch (e) {
    flushTypewriter();
    const isAborted = e.name === 'AbortError' || activePromptAbortController?.signal?.aborted;
    if (isAborted) {
      handleStreamAborted(streamBubble);
      saveCopilotFeed();
      return;
    }

    if (streamBubble) streamBubble.remove();
    appendAgentErrorMessage(e.message || "Failed to connect to backend server.");
    saveCopilotFeed();
  } finally {
    setAgentPromptRunning(false);
    activePromptAbortController = null;
  }
}

function scrollChatToBottom() {
  const wrapper = document.getElementById('copilotFeedWrapper');
  const feed = document.getElementById('copilotFeed');
  if (wrapper) wrapper.scrollTop = wrapper.scrollHeight;
  if (feed) feed.scrollTop = feed.scrollHeight;
}

function getAgentBubbleHeaderHtml(badgeText = 'Agent Active', isError = false) {
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `
    <div class="agent-bubble-header">
      <div class="agent-avatar ${isError ? 'error-avatar' : ''}">
        <svg width="15" height="15" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M6 5C10 1.2 22 1.2 26 5" stroke="#004B93" stroke-width="2.2" stroke-linecap="round"/>
          <path d="M9.5 8C12.5 5 19.5 5 22.5 8" stroke="#004B93" stroke-width="2" stroke-linecap="round"/>
          <circle cx="16" cy="11" r="2.2" fill="#004B93"/>
          <path d="M12.5 13H19.5V17C19.5 18.9 17.9 20.5 16 20.5C14.1 20.5 12.5 18.9 12.5 17V13Z" fill="#F26F21"/>
          <path d="M16 20.5V27M13 27H19" stroke="#F26F21" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </div>
      <div class="agent-name">BaliTower AI Agent</div>
      <div class="agent-status-badge">
        <span class="live-dot"></span>
        ${escapeHtml(badgeText)}
      </div>
      <div class="agent-time">${timeStr}</div>
    </div>
  `;
}

function getChatHistory() {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return [];
  const history = [];
  const children = feed.children;
  for (let i = 0; i < children.length; i++) {
    const el = children[i];
    if (el.classList.contains('user-query-bubble')) {
      const txt = el.querySelector('.bubble-text');
      if (txt && txt.textContent.trim()) {
        history.push({ role: 'user', content: txt.textContent.trim() });
      }
    } else if (el.classList.contains('agent-response-box')) {
      const clarifMsg = el.querySelector('.clarification-message');
      const streamTxt = el.querySelector('.stream-text-slot');
      let assistantContent = '';
      if (clarifMsg && clarifMsg.textContent.trim()) {
        assistantContent = clarifMsg.textContent.trim();
      } else if (streamTxt && streamTxt.textContent.trim()) {
        assistantContent = streamTxt.textContent.trim();
      }
      if (assistantContent) {
        history.push({ role: 'assistant', content: assistantContent });
      }
    }
  }
  return history.slice(-6);
}

function appendUserMessage(text) {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');

  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const userBox = document.createElement('div');
  userBox.className = 'user-query-bubble';
  userBox.innerHTML = `
    <div class="bubble-meta">
      <span class="bubble-sender">YOU</span>
      <span class="bubble-time">${timeStr}</span>
    </div>
    <div class="bubble-text">${escapeHtml(text)}</div>
  `;
  feed.appendChild(userBox);
  scrollChatToBottom();
}

function appendAgentStreamBubble() {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return null;

  const id = 'stream_' + Date.now();
  const box = document.createElement('div');
  box.id = id;
  box.className = 'agent-response-box';
  box.innerHTML = `
    ${getAgentBubbleHeaderHtml('Agent Active')}
    <div class="agent-plan-box">
      <div class="stage-chips-container">
        <div class="stage-chip active">
          <span class="stage-pulse-dot"></span>
          <span>Analyzing instruction and permissions...</span>
        </div>
      </div>
      <div class="clarification-slot"></div>
      <div class="stream-text-slot" style="font-size: 13.5px; color: #0F172A; line-height: 1.65;">
        <span class="stream-cursor"></span>
      </div>
      <div class="stream-artifacts-slot" style="margin-top: 8px;"></div>
    </div>
  `;
  feed.appendChild(box);
  scrollChatToBottom();
  return box;
}

function updateStreamStage(streamBubble, stage, message) {
  if (!streamBubble) return;
  const stagesContainer = streamBubble.querySelector('.stage-chips-container');
  if (!stagesContainer) return;

  const msgTrimmed = (message || '').trim();
  if (!msgTrimmed) return;

  const existingChips = stagesContainer.querySelectorAll('.stage-chip');
  
  // If the initial default chip exists and matches or is active, update it rather than duplicating
  if (existingChips.length === 1) {
    const textSpan = existingChips[0].querySelector('span:not(.stage-pulse-dot)');
    if (textSpan && (textSpan.textContent.includes('Menganalisis instruksi') || textSpan.textContent.includes('Analyzing instruction'))) {
      textSpan.textContent = msgTrimmed;
      return;
    }
  }

  // If the last chip already has this exact text, do not duplicate
  const lastChip = existingChips[existingChips.length - 1];
  if (lastChip) {
    const lastText = (lastChip.querySelector('span:not(.stage-pulse-dot)')?.textContent || '').trim();
    if (lastText === msgTrimmed) return;
  }

  const prevActive = stagesContainer.querySelector('.stage-chip.active');
  if (prevActive) {
    prevActive.classList.remove('active');
    prevActive.classList.add('done');
    const pulse = prevActive.querySelector('.stage-pulse-dot');
    if (pulse) pulse.remove();
  }

  const inlineCancel = stagesContainer.querySelector('.btn-cancel-inline');

  const chip = document.createElement('div');
  chip.className = 'stage-chip active';
  chip.innerHTML = `
    <span class="stage-pulse-dot"></span>
    <span>${escapeHtml(msgTrimmed)}</span>
  `;

  if (inlineCancel) {
    stagesContainer.insertBefore(chip, inlineCancel);
  } else {
    stagesContainer.appendChild(chip);
  }
  scrollChatToBottom();
}

function renderClarificationBox(streamBubble, clarification) {
  if (!streamBubble || !clarification) return;
  const slot = streamBubble.querySelector('.clarification-slot');
  if (!slot) return;

  const hint = clarification.hint || '';
  const escapedHint = escapeHtml(hint).replace(/'/g, "\\'");

  slot.innerHTML = `
    <div class="clarification-box">
      <div class="clarification-title">
        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>${escapeHtml(clarification.title || 'Clarification Needed')}</span>
      </div>
      <div class="clarification-message">${escapeHtml(clarification.message || '')}</div>
      ${hint ? `
        <button type="button" class="clarification-hint-btn" onclick="useClarificationHint('${escapedHint}')">
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span>Use Suggestion: "<strong>${escapeHtml(hint)}</strong>"</span>
        </button>
      ` : ''}
    </div>
  `;
  scrollChatToBottom();
}

function updateStreamText(streamBubble, text) {
  if (!streamBubble) return;
  const textSlot = streamBubble.querySelector('.stream-text-slot');
  if (!textSlot) return;

  textSlot.innerHTML = formatMarkdownResponse(text) + '<span class="stream-cursor"></span>';
  scrollChatToBottom();
}

function finalizeStreamBubble(streamBubble, payload, streamedText) {
  if (!streamBubble) return;

  const cursor = streamBubble.querySelector('.stream-cursor');
  if (cursor) cursor.remove();

  const inlineCancel = streamBubble.querySelector('.btn-cancel-inline');
  if (inlineCancel) inlineCancel.remove();

  const activeChips = streamBubble.querySelectorAll('.stage-chip.active');
  activeChips.forEach(c => {
    c.classList.remove('active');
    c.classList.add('done');
    const pulse = c.querySelector('.stage-pulse-dot');
    if (pulse) pulse.remove();
  });

  if (!payload) return;

  const prs = (payload.generated_prs && payload.generated_prs.length > 0) ? payload.generated_prs : (payload.prs || []);
  const items = payload.affected_items || [];
  const actionType = payload.action_type || 'general';

  if (actionType === 'hr_leave_form' || (payload.parsed_intent && payload.parsed_intent.workflow_id === 'hr_leave_form')) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      renderLeaveRequestChatForm(artifactsSlot);
    }
  } else if (prs.length > 0) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const isEmailSent = Boolean(payload.email_sent);
      const prCards = prs.map(rawPr => {
        let pr = rawPr;
        if (typeof pr === 'string') {
          pr = { pr_number: pr, supplier_name: 'PT Fiber Optik Nusantara', grand_total: payload.total_budget || 0, items: [] };
        }
        const rawStatus = String(pr.status || '').toUpperCase();
        const supplier = pr.supplier_name || 'PT Fiber Optik Nusantara';
        const grandTotal = Number(pr.grand_total || pr.total_budget || 0);
        const escapedSupplier = escapeHtml(supplier).replace(/'/g, "\\'");
        const prEmailSent = pr.email_sent !== undefined ? Boolean(pr.email_sent) : isEmailSent;

        return `
          <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px; margin-top: 8px; box-shadow: var(--shadow-xs);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div>
                <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 12px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${pr.pr_number}</span>
                <span style="font-size: 12.5px; margin-left: 6px; color: #334155; font-weight: 600;">${escapeHtml(supplier)}</span>
              </div>
              <span style="font-weight: 800; font-size: 14px; color: #0F172A;">${formatCurrency(grandTotal)}</span>
            </div>
            <div style="font-size: 12.5px; color: #475569; margin-bottom: 10px; line-height: 1.6;">
              ${(pr.items || []).map(it => `• <strong>${escapeHtml(it.item_name || it.name)}</strong>: ${it.quantity || it.reorder_qty} ${it.unit || 'pcs'}`).join('<br>')}
            </div>
            ${prEmailSent ? `
            <div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px;">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              <span>Dokumen PR resmi telah dikompilasi (PDF) dan permohonan persetujuan telah otomatis dikirimkan ke email tujuan.</span>
            </div>
            ` : `
            <div id="email-action-box-${pr.pr_number}" class="pr-email-action-box" style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
              <div style="font-weight: 700; font-size: 13px; color: #0F172A; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
                <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#2563EB"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                <span>Kirim Notifikasi Persetujuan via Email?</span>
              </div>
              <div style="font-size: 12px; color: #64748B; margin-bottom: 10px; line-height: 1.5;">
                Draf PR berhasil dibuat dan dicatat ke dalam database sistem. Anda dapat langsung meneruskannya ke Manajer Logistik untuk otorisasi.
              </div>
              <div id="email-action-buttons-${pr.pr_number}" style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
                <button type="button" class="btn btn-primary btn-sm" onclick="dispatchPrEmail('${pr.pr_number}', 'manager.logistik@balitower.co.id')">
                  <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                  <span>Kirim ke Manajer Logistik (manager.logistik@balitower.co.id)</span>
                </button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCustomEmailInput('${pr.pr_number}')">
                  <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
                  <span>Kirim ke Email Lain...</span>
                </button>
                <button type="button" class="btn btn-secondary btn-sm" style="color: #64748B;" onclick="skipPrEmail('${pr.pr_number}')">
                  <span>Lewati (Hanya Simpan Draf)</span>
                </button>
              </div>
              <div id="custom-email-form-${pr.pr_number}" style="display: none; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #CBD5E1;">
                <div style="font-size: 11.5px; font-weight: 600; color: #475569; margin-bottom: 6px;">Masukkan Alamat Email Tujuan:</div>
                <div style="display: flex; gap: 6px; align-items: center;">
                  <input type="email" id="custom-email-input-${pr.pr_number}" placeholder="contoh: manager.name@balitower.co.id" class="form-input" style="flex: 1; padding: 6px 10px; font-size: 12px; border: 1px solid #CBD5E1; border-radius: 6px;" onkeydown="if(event.key === 'Enter') submitCustomEmail('${pr.pr_number}')" />
                  <button type="button" class="btn btn-primary btn-sm" onclick="submitCustomEmail('${pr.pr_number}')">
                    <span>Kirim</span>
                  </button>
                  <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCustomEmailInput('${pr.pr_number}')">
                    <span>Batal</span>
                  </button>
                </div>
              </div>
            </div>
            `}
            <div style="display: flex; justify-content: flex-end;">
              <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${grandTotal}, '${rawStatus}')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>Lihat Dokumen PDF</span>
              </button>
            </div>
          </div>
        `;
      }).join('');

      artifactsSlot.innerHTML = `
        <div class="action-card" style="border-left: 4px solid ${isEmailSent ? '#16A34A' : '#2563EB'}; background: ${isEmailSent ? '#F0FDF4' : '#F8FAFC'}; border: 1px solid ${isEmailSent ? '#DCFCE7' : '#E2E8F0'}; margin-top: 10px;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: ${isEmailSent ? '#15803D' : '#1E40AF'};">${isEmailSent ? `DOKUMEN PR TERBIT & TERKIRIM KE EMAIL (${prs.length})` : `DRAF DOKUMEN PR TERBIT (${prs.length})`}</span>
            <span class="badge ${isEmailSent ? 'badge-approved' : 'badge-pending'}">${isEmailSent ? 'TERKIRIM KE EMAIL' : 'DRAF TERSIMPAN'}</span>
          </div>
          <div class="action-card-body">
            ${prCards}
          </div>
        </div>
      `;
      openDataSidebar('canvas-prs');
    }
  }

  if (payload.onboarding_id) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const onbId = payload.onboarding_id;
      const clientName = payload.client_name || 'Klien Operator';
      const siteId = payload.site_id || '';
      const totalBilled = payload.total_billed || 0;
      artifactsSlot.innerHTML = `
        <div class="action-card" style="border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7; margin-top: 10px;">
          <div class="action-card-header" style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 700; font-size: 12.5px; color: #15803D;">NEW OPERATOR TOWER LEASE APPLICATION (${escapeHtml(onbId)})</span>
            <span class="badge badge-approved" style="background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D;">PENDING APPROVAL</span>
          </div>
          <div class="action-card-body" style="padding-top: 8px;">
            <div style="font-size: 12.5px; color: #334155; margin-bottom: 8px;">
              <strong>Client:</strong> ${escapeHtml(clientName)} ${siteId ? `• <strong>Site:</strong> ${escapeHtml(siteId)}` : ''}
            </div>
            <div style="background: #FFFFFF; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px;">
              <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              <span>Tower lease billing invoice & agreement files compiled (PDF) and dispatched via email for approval.</span>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 8px;">
              <a href="/api/documents/invoice/${encodeURIComponent(onbId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                <span>Download Invoice PDF</span>
              </a>
              <button class="btn btn-primary btn-sm" onclick="openInvoicePdfModal('${escapeHtml(onbId)}', '${escapeHtml(onbId)}', '${escapeHtml(clientName)}', ${totalBilled}, 'PENDING')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>View PDF Document</span>
              </button>
            </div>
          </div>
        </div>
      `;
      openDataSidebar('canvas-finance');
      if (typeof loadFinanceData === 'function') loadFinanceData();
      if (typeof loadClients === 'function') loadClients();
      if (typeof loadMlaContracts === 'function') loadMlaContracts();
    }
  }

  if (payload.leave_id) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const lId = payload.leave_id;
      const appName = payload.applicant_name || 'Karyawan';
      const lType = payload.leave_type || 'Cuti';
      const days = payload.days_requested || 1;
      artifactsSlot.innerHTML = `
        <div style="display: flex; justify-content: flex-end; margin-top: 10px; gap: 8px;">
          <a href="/api/documents/leave/${encodeURIComponent(lId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
            <span>Download Leave PDF</span>
          </a>
          <button class="btn btn-primary btn-sm" onclick="openLeavePdfModal('${escapeHtml(lId)}', '${escapeHtml(appName)}', '${escapeHtml(lType)}', ${days}, 'PENDING_APPROVAL')">
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            <span>View PDF Document</span>
          </button>
        </div>
      `;
    }
  } else if (items.length > 0 && (actionType === 'register_product' || actionType === 'update_threshold')) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const isReg = actionType === 'register_product';
      const title = isReg ? 'NEW PRODUCT REGISTERED SUCCESSFULLY' : 'STOCK REORDER THRESHOLD UPDATED';
      const badge = isReg ? '<span class="badge badge-approved">SUCCESS</span>' : '<span class="badge badge-updated">UPDATED</span>';
      
      const rows = items.map(it => {
        const itemName = typeof it === 'string' ? it : (it.name || it.item_name || '-');
        const curStock = typeof it === 'object' && it.current_stock !== undefined ? it.current_stock : '-';
        const minStock = typeof it === 'object' && it.min_stock !== undefined ? it.min_stock : '-';
        const unit = typeof it === 'object' && it.unit ? it.unit : '';
        return `
        <tr>
          <td><strong>${escapeHtml(itemName)}</strong></td>
          <td>${curStock} ${unit}</td>
          <td><span style="color: #2563EB; font-weight: 600;">${minStock}</span> ${unit}</td>
        </tr>
      `;
      }).join('');

      artifactsSlot.innerHTML = `
        <div class="action-card" style="border-left: 4px solid #2563EB; background: #F8FAFC; border: 1px solid #E2E8F0; margin-top: 10px; max-width: 100%; box-sizing: border-box; overflow: hidden; border-radius: 8px;">
          <div class="action-card-header" style="display: flex; justify-content: space-between; align-items: center; padding: 4px 6px;">
            <span style="font-weight: 700; font-size: 12.5px; color: #1E293B;">${title} (${items.length})</span>
            ${badge}
          </div>
          <div class="action-card-body" style="padding: 6px 10px; max-width: 100%; box-sizing: border-box; overflow-x: auto;">
            <table class="data-table" style="font-size: 12px; margin: 4px 0; width: 100%; table-layout: auto;">
              <thead>
                <tr>
                  <th style="white-space: normal; min-width: 180px;">Item Name</th>
                  <th style="white-space: nowrap; text-align: center;">Physical Stock</th>
                  <th style="white-space: nowrap; text-align: center;">Min Threshold</th>
                </tr>
              </thead>
              <tbody>
                ${rows}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }
  }

  const currentTenant = (typeof getEffectiveTenant === 'function' ? getEffectiveTenant() : '') || '';
  const isHrScope = (currentTenant === 'HR' || actionType === 'hr_mutation' || actionType === 'hr_leave' || actionType === 'hr_query');

  if ((payload.po_id || payload.pdf_download_url) && !isHrScope) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      const poId = payload.po_id || (payload.parsed_intent && payload.parsed_intent.po_id);
      if (poId) {
        const poNum = payload.po_number || poId;
        const supplier = payload.supplier_name || 'Vendor Terdaftar';
        const total = payload.grand_total || 0;
        const st = payload.status || 'ORDERED';
        artifactsSlot.innerHTML = `
          <div style="display: flex; justify-content: flex-end; margin-top: 10px; gap: 8px;">
            <a href="/api/documents/po/${encodeURIComponent(poId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
              <span>Download PO PDF</span>
            </a>
            <button class="btn btn-primary btn-sm" onclick="openPoPdfModal('${escapeHtml(poId)}', '${escapeHtml(poNum)}', '${escapeHtml(supplier)}', ${total}, '${escapeHtml(st)}')">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              <span>View PO Document (PDF)</span>
            </button>
          </div>
        `;
      }
    }
  }

  // Automatic real-time table sync for HR mutations & leave requests
  if (actionType === 'hr_mutation' || payload.mutated_employee) {
    if (typeof loadEmployees === 'function') loadEmployees();
    if (typeof loadHrWorkforceData === 'function') loadHrWorkforceData();
  } else if (actionType === 'hr_leave' || payload.leave_id) {
    if (typeof loadHrData === 'function') loadHrData();
    if (typeof loadHrWorkforceData === 'function') loadHrWorkforceData();
  }

  // Handle workflow creation / missing workflow request to Administrator
  const isRefusalOrGreeting = (() => {
    const rawP = (payload.prompt_text || '').toLowerCase().trim();
    const rawMsg = (payload.message || '').toLowerCase().trim();
    if (actionType === 'out_of_scope' || actionType === 'security_refusal') return true;
    if (rawMsg.includes('hanya berwenang melayani pertanyaan') || rawMsg.includes('akses ditolak')) return true;
    const pleasantries = ['halo', 'hai', 'hi', 'selamat pagi', 'selamat siang', 'selamat sore', 'selamat malam', 'terima kasih', 'terimakasih', 'makasih', 'thanks', 'thank you'];
    const pClean = rawP.replace(/[^\w\s]/g, '').trim();
    if (pleasantries.includes(pClean) || pleasantries.includes(rawP)) return true;
    return false;
  })();

  if (actionType === 'render_workflow_request_form') {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      renderWorkflowRequestChatForm(artifactsSlot, { prompt: payload.prompt_text || '' });
    }
  } else if (!isRefusalOrGreeting && (actionType === 'workflow_not_found' || payload.is_tool_blocked || payload.can_request_admin)) {
    const artifactsSlot = streamBubble.querySelector('.stream-artifacts-slot');
    if (artifactsSlot) {
      renderWorkflowRequestCard(artifactsSlot, payload.prompt_text || '');
    }
  }

  scrollChatToBottom();
}

function renderWorkflowRequestCard(container, promptText) {
  if (!container) return;
  const cardId = 'wf_req_' + Date.now();
  const cleanPrompt = (promptText || '').trim();
  const escapedPrompt = escapeHtml(cleanPrompt).replace(/'/g, "\\'");

  const cardHtml = `
    <div class="action-card" id="${cardId}" style="border-left: 4px solid #2563EB; background: #F8FAFC; border: 1px solid #E2E8F0; margin-top: 10px; border-radius: 8px; padding: 14px; box-shadow: var(--shadow-xs);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 7px; font-weight: 700; font-size: 13px; color: #0F172A;">
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#2563EB">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <span>Request Workflow from Administrator</span>
        </div>
        <span class="badge" style="background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; font-size: 10.5px; font-weight: 700; letter-spacing: 0.03em;">ADMINISTRATOR ONLY</span>
      </div>
      <div style="font-size: 12.5px; color: #475569; margin-bottom: 10px; line-height: 1.55;">
        Standard workflow is not registered for this instruction. Under system governance policy, new workflows can only be provisioned by Administrators. You can submit this request to the Administrator.
      </div>
      ${cleanPrompt ? `
      <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; margin-bottom: 12px; font-size: 12px; color: #334155; font-family: var(--font-mono); line-height: 1.5;">
        "${escapeHtml(cleanPrompt)}"
      </div>
      ` : ''}
      <div id="btn-group-${cardId}" style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <button type="button" class="btn btn-primary btn-sm" onclick="submitUserWorkflowRequest('${escapedPrompt}', '${cardId}')">
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
          </svg>
          <span>Quick Submit to Admin</span>
        </button>
        <button type="button" class="btn btn-secondary btn-sm" onclick="triggerWorkflowRequestChatForm('${escapedPrompt}', '${cardId}')">
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
          </svg>
          <span>Fill Complete Form</span>
        </button>
      </div>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', cardHtml);
  scrollChatToBottom();
}

function triggerWorkflowRequestChatForm(initialPrompt = '', cardToReplaceId = null) {
  let targetContainer = null;
  if (cardToReplaceId) {
    const oldCard = document.getElementById(cardToReplaceId);
    if (oldCard && oldCard.parentElement) {
      targetContainer = oldCard.parentElement;
      oldCard.remove();
    }
  }
  renderWorkflowRequestChatForm(targetContainer, { prompt: initialPrompt });
}

function renderWorkflowRequestChatForm(targetContainer = null, initialData = {}) {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');

  let parent = targetContainer;
  if (!parent) {
    const feed = document.getElementById('copilotFeed');
    if (!feed) return;
    const agentBox = document.createElement('div');
    agentBox.className = 'agent-response-box';
    agentBox.innerHTML = `
      ${getAgentBubbleHeaderHtml('Workflow Governance')}
      <div class="stream-text-content" style="margin-bottom: 8px;">
        Please complete the workflow request form below. Your request will be directly dispatched to the Administrator review queue to be compiled into the system.
      </div>
      <div class="stream-artifacts-slot"></div>
    `;
    feed.appendChild(agentBox);
    parent = agentBox.querySelector('.stream-artifacts-slot');
  }

  const effectiveTenant = (typeof getEffectiveTenant === 'function' ? getEffectiveTenant() : 'INVENTORY') || 'INVENTORY';
  const formId = 'wfForm_' + Date.now();
  const initPrompt = initialData.prompt || '';
  const isGenericPrompt = /^(mau\s+ajukan|ajukan|request|buka\s+form|form)\s+(workflow|alur\s+kerja)/i.test(initPrompt.trim());
  const prefillPrompt = isGenericPrompt ? '' : initPrompt;

  const formHtml = `
    <div class="wf-request-form-card" id="${formId}">
      <div class="wf-request-form-header">
        <div style="display: flex; align-items: center; gap: 8px;">
          <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="#2563EB">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <span class="wf-request-form-title">New Workflow Request Form</span>
        </div>
        <span class="badge" style="background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; font-size: 10.5px; font-weight: 700;">WORKFLOW REQUEST</span>
      </div>
      
      <div class="wf-request-form-body">
        <div class="wf-form-row">
          <div class="wf-form-col">
            <label class="wf-form-label">Workflow Title / Name <span style="color: #DC2626;">*</span></label>
            <input type="text" class="wf-form-input" id="${formId}_title" placeholder="e.g. Monthly Genset Utilization Audit">
          </div>
          <div class="wf-form-col">
            <label class="wf-form-label">Division / Operational Domain <span style="color: #DC2626;">*</span></label>
            <select class="wf-form-select" id="${formId}_tenant">
              <option value="INVENTORY" ${effectiveTenant === 'INVENTORY' ? 'selected' : ''}>Logistics & Inventory Division (Schema A)</option>
              <option value="HR" ${effectiveTenant === 'HR' ? 'selected' : ''}>Field HR & Personnel Division (Schema B)</option>
              <option value="FINANCE" ${effectiveTenant === 'FINANCE' ? 'selected' : ''}>Finance & Billing Division (Schema C)</option>
              <option value="ALL" ${effectiveTenant === 'ALL' ? 'selected' : ''}>Cross-Divisional / Universal (Schema ALL)</option>
            </select>
          </div>
        </div>

        <div class="wf-form-group">
          <label class="wf-form-label">Example Prompt / Instruction <span style="color: #DC2626;">*</span></label>
          <input type="text" class="wf-form-input" id="${formId}_prompt" placeholder="e.g. Check all site genset fuel consumption at month end and log reports" value="${escapeHtml(prefillPrompt)}">
        </div>

        <div class="wf-form-group">
          <label class="wf-form-label">Operational Needs & Urgency Description (Optional)</label>
          <textarea class="wf-form-textarea" id="${formId}_notes" rows="2" placeholder="Explain the operational purpose or justification for this workflow..."></textarea>
        </div>
      </div>

      <div class="wf-request-form-footer">
        <span id="${formId}_error" style="color: #DC2626; font-size: 12px; display: none;"></span>
        <div style="display: flex; gap: 8px; align-items: center; margin-left: auto;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="cancelWorkflowRequestForm('${formId}')">
            <span>Cancel</span>
          </button>
          <button type="button" class="btn btn-primary btn-sm" id="${formId}_btn" onclick="submitInteractiveWorkflowForm('${formId}')">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
            </svg>
            <span>Submit Request to Admin</span>
          </button>
        </div>
      </div>
    </div>
  `;

  parent.insertAdjacentHTML('beforeend', formHtml);
  scrollChatToBottom();
}

function cancelWorkflowRequestForm(formId) {
  const el = document.getElementById(formId);
  if (el) el.remove();
}

async function submitInteractiveWorkflowForm(formId) {
  const titleEl = document.getElementById(`${formId}_title`);
  const tenantEl = document.getElementById(`${formId}_tenant`);
  const promptEl = document.getElementById(`${formId}_prompt`);
  const notesEl = document.getElementById(`${formId}_notes`);
  const btn = document.getElementById(`${formId}_btn`);
  const errorEl = document.getElementById(`${formId}_error`);

  if (!promptEl) return;
  const title = titleEl ? titleEl.value.trim() : '';
  const tenant = tenantEl ? tenantEl.value.trim() : 'INVENTORY';
  const promptText = promptEl.value.trim();
  const notes = notesEl ? notesEl.value.trim() : '';

  if (errorEl) errorEl.style.display = 'none';

  if (!promptText) {
    if (errorEl) {
      errorEl.textContent = 'Please enter the desired prompt or instruction.';
      errorEl.style.display = 'block';
    }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `
      <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="width: 12px; height: 12px; border-width: 1.5px;"></span>
      <span>Submitting...</span>
    `;
  }

  try {
    const token = sessionStorage.getItem('access_token') || localStorage.getItem('access_token') || sessionStorage.getItem('token') || localStorage.getItem('token') || '';
    const res = await fetch('/api/workflows/request', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        title: title || undefined,
        prompt: promptText,
        tenant_id: tenant,
        notes: notes || undefined
      })
    });

    if (res.ok) {
      const data = await res.json();
      const formCard = document.getElementById(formId);
      if (formCard) {
        formCard.innerHTML = `
          <div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 8px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <div style="display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 13px; color: #166534;">
                <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <span>Workflow Request Successfully Submitted</span>
              </div>
              <span class="badge" style="background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; font-weight: 700; font-size: 10.5px;">PENDING REVIEW</span>
            </div>
            <div style="font-size: 12.5px; color: #14532D; line-height: 1.5;">
              Official workflow request <strong style="font-family: var(--font-mono);">${escapeHtml(data.request_id || 'REQ')}</strong> has been successfully submitted to Enterprise Administrator review queue.
            </div>
            <div style="font-size: 12px; color: #15803D; background: #FFFFFF; border: 1px solid #BBF7D0; border-radius: 6px; padding: 8px 12px; font-family: var(--font-mono);">
              "${escapeHtml(promptText)}"
            </div>
          </div>
        `;
      }
    } else {
      const err = await res.json().catch(() => ({}));
      if (errorEl) {
        errorEl.textContent = `Failed to submit request: ${err.detail || 'A server error occurred.'}`;
        errorEl.style.display = 'block';
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span>Submit Request to Admin</span>`;
      }
    }
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = 'Failed to connect to server. Please check your network connection.';
      errorEl.style.display = 'block';
    }
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>Submit Request to Admin</span>`;
    }
  }
}

async function submitUserWorkflowRequest(promptText, cardId) {
  const btnGroup = document.getElementById(`btn-group-${cardId}`);
  if (btnGroup) {
    btnGroup.innerHTML = `
      <span style="font-size: 12px; color: #64748B; display: inline-flex; align-items: center; gap: 6px;">
        <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="width: 12px; height: 12px; border-width: 1.5px;"></span>
        Sending notification to Administrator...
      </span>
    `;
  }
  
  try {
    const token = sessionStorage.getItem('access_token') || localStorage.getItem('access_token') || sessionStorage.getItem('token') || localStorage.getItem('token') || '';
    const res = await fetch('/api/workflows/request', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ prompt: promptText })
    });
    
    if (res.ok) {
      const data = await res.json();
      if (btnGroup) {
        btnGroup.innerHTML = `
          <div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px; width: 100%;">
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
            <span>Request (${data.request_id || 'REQ'}) successfully submitted to Administrator. Status: Pending Review.</span>
          </div>
        `;
      }
    } else {
      const err = await res.json().catch(() => ({}));
      if (btnGroup) {
        btnGroup.innerHTML = `
          <div style="color: #DC2626; font-size: 12px;">
            Failed to submit: ${escapeHtml(err.detail || 'An error occurred.')}
          </div>
        `;
      }
    }
  } catch (e) {
    if (btnGroup) {
      btnGroup.innerHTML = `
        <div style="color: #DC2626; font-size: 12px;">
          Failed to connect to server.
        </div>
      `;
    }
  }
}

// ==============================================================================
// 1-CLICK EMAIL DISPATCH & INTERACTIVE ACTION HANDLERS FOR PR DRAFTS
// ==============================================================================

window.toggleCustomEmailInput = function(prNumber) {
  const form = document.getElementById(`custom-email-form-${prNumber}`);
  if (form) {
    const isHidden = form.style.display === 'none' || form.style.display === '';
    form.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
      const input = document.getElementById(`custom-email-input-${prNumber}`);
      if (input) input.focus();
    }
  }
};

window.submitCustomEmail = async function(prNumber) {
  const input = document.getElementById(`custom-email-input-${prNumber}`);
  if (!input) return;
  const email = (input.value || '').trim();
  if (!email || !email.includes('@')) {
    showToast("Mohon masukkan alamat email tujuan yang valid.", "error");
    if (input) input.focus();
    return;
  }
  await window.dispatchPrEmail(prNumber, email);
};

window.skipPrEmail = function(prNumber) {
  const box = document.getElementById(`email-action-box-${prNumber}`);
  if (box) {
    box.outerHTML = `
      <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #475569; display: flex; align-items: center; gap: 8px;">
        <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
        <span>Dokumen PR resmi telah dikompilasi (PDF) dan tersimpan sebagai draf di sistem inventaris.</span>
      </div>
    `;
  }
  saveCopilotFeed();
  showToast(`Dokumen PR resmi telah dikompilasi (PDF) dan tersimpan sebagai draf di sistem inventaris.`, 'info');
};

window.dispatchPrEmail = async function(prNumber, email) {
  const box = document.getElementById(`email-action-box-${prNumber}`);
  const targetEmail = email || "manager.logistik@balitower.co.id";

  if (box) {
    box.innerHTML = `
      <div style="display: flex; align-items: center; gap: 10px; padding: 10px 6px; font-size: 12.5px; color: #2563EB;">
        <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/></svg>
        <span>Mengirimkan berkas permohonan persetujuan ${escapeHtml(prNumber)} ke ${escapeHtml(targetEmail)}...</span>
      </div>
    `;
  }

  try {
    const token = sessionStorage.getItem('access_token') || localStorage.getItem('access_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch('/api/approval/dispatch-email', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        pr_number: prNumber,
        recipient_email: targetEmail
      })
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || data.message || "Gagal mengirimkan email permohonan persetujuan.");
    }

    if (box) {
      box.outerHTML = `
        <div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px;">
          <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
          <span>Dokumen PR resmi telah dikompilasi (PDF) dan permohonan persetujuan telah berhasil dikirimkan ke <strong>${escapeHtml(targetEmail)}</strong>.</span>
        </div>
      `;
    }

    const cardEl = box ? box.closest('.action-card') : null;
    if (cardEl) {
      const headerTag = cardEl.querySelector('.action-card-header .badge');
      if (headerTag) {
        headerTag.className = 'badge badge-approved';
        headerTag.textContent = 'TERKIRIM KE EMAIL';
      }
      const titleSpan = cardEl.querySelector('.action-card-header span:first-child');
      if (titleSpan) {
        titleSpan.style.color = '#15803D';
        titleSpan.textContent = titleSpan.textContent.replace('DRAF', 'TERKIRIM KE EMAIL');
      }
    }

    saveCopilotFeed();
    showToast(`Dokumen PR resmi telah dikompilasi (PDF) dan permohonan persetujuan telah berhasil dikirimkan ke ${targetEmail}`, 'success');
  } catch (err) {
    console.error("dispatchPrEmail error:", err);
    if (box) {
      box.innerHTML = `
        <div style="color: #DC2626; font-size: 12px; margin-bottom: 8px;">
          ${escapeHtml(err.message || "Gagal mengirimkan email.")}
        </div>
        <div style="display: flex; gap: 6px;">
          <button type="button" class="btn btn-primary btn-sm" onclick="dispatchPrEmail('${prNumber}', '${targetEmail}')">
            <span>Coba Lagi</span>
          </button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="skipPrEmail('${prNumber}')">
            <span>Lewati</span>
          </button>
        </div>
      `;
    }
    showToast(err.message || "Gagal mengirimkan email", 'error');
  }
};

function appendAgentErrorMessage(errorText) {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const box = document.createElement('div');
  box.className = 'agent-response-box';
  box.innerHTML = `
    ${getAgentBubbleHeaderHtml('System Error', true)}
    <div class="agent-plan-box" style="border-left: 4px solid #DC2626; background: #FEF2F2; border-color: #FECACA;">
      <div class="agent-plan-title" style="color: #DC2626;">AN ERROR OCCURRED</div>
      <div style="font-size: 13px; color: #991B1B; line-height: 1.5;">${escapeHtml(errorText)}</div>
    </div>
  `;
  feed.appendChild(box);
  scrollChatToBottom();
}

function formatMarkdownResponse(text) {
  if (!text) return '';

  // Strip emojis across the board
  const stripEmojis = (str) => (str || '').replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F1E0}-\u{1F1FF}\u{1F900}-\u{1F9FF}\u{1F004}\u{1F0CF}\u{1F170}-\u{1F251}\u{2300}-\u{23FF}\u{2B50}\u{2B55}\u{2934}\u{2935}\u{2B05}\u{2B06}\u{2B07}]/gu, '').trim();

  const lines = text.split('\n');
  let inTable = false;
  let html = '';
  let tableRows = [];

  const cleanText = (str) => stripEmojis(str || '').replace(/\*\*/g, '').replace(/`/g, '').trim();

  for (let line of lines) {
    let trimmed = line.trim();

    // Skip code block fences if any
    if (trimmed.startsWith('```')) continue;

    // Parse markdown table rows
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      if (trimmed.includes('---')) continue; // skip header separator
      inTable = true;
      const cells = trimmed.split('|').slice(1, -1).map(c => cleanText(c));
      tableRows.push(cells);
    } else {
      if (inTable && tableRows.length > 0) {
        html += `<div style="overflow-x:auto; margin: 10px 0;"><table class="data-table" style="font-size: 11.5px; width: 100%;"><thead><tr>` +
          tableRows[0].map(c => `<th style="padding: 6px 8px;">${c}</th>`).join('') +
          `</tr></thead><tbody>` +
          tableRows.slice(1).map(row => `<tr>` + row.map(c => `<td style="padding: 6px 8px;">${c}</td>`).join('') + `</tr>`).join('') +
          `</tbody></table></div>`;
        inTable = false;
        tableRows = [];
      }

      // Clean header lines (### or ## or #)
      if (trimmed.startsWith('#')) {
        const hTitle = cleanText(trimmed.replace(/^#+\s*/, ''));
        if (hTitle) {
          html += `<div style="font-size: 13.5px; font-weight: 700; color: #0F172A; margin: 8px 0 4px 0;">${hTitle}</div>`;
        }
        continue;
      }

      // Clean blockquote lines (> ...)
      if (trimmed.startsWith('>')) {
        const bQuote = cleanText(trimmed.replace(/^>\s*/, ''));
        if (bQuote) {
          html += `<div style="background: #F8FAFC; border-left: 3px solid #CBD5E1; padding: 7px 10px; margin: 6px 0; font-size: 12px; color: #475569; border-radius: 0 6px 6px 0; line-height: 1.5;">${bQuote}</div>`;
        }
        continue;
      }

      const cLine = cleanText(trimmed);
      if (cLine.startsWith('- ')) {
        html += `<div style="margin: 3px 0 3px 12px; font-size: 12.5px;">- ${cLine.substring(2)}</div>`;
      } else if (cLine.length > 0) {
        html += `<div style="margin: 4px 0; font-size: 13px; line-height: 1.5;">${cLine}</div>`;
      }
    }
  }
  if (inTable && tableRows.length > 0) {
    html += `<div style="overflow-x:auto; margin: 10px 0;"><table class="data-table" style="font-size: 11.5px; width: 100%;"><thead><tr>` +
      tableRows[0].map(c => `<th style="padding: 6px 8px;">${c}</th>`).join('') +
      `</tr></thead><tbody>` +
      tableRows.slice(1).map(row => `<tr>` + row.map(c => `<td style="padding: 6px 8px;">${c}</td>`).join('') + `</tr>`).join('') +
      `</tbody></table></div>`;
  }

  return html;
}

function appendAgentResponseCard(data) {
  const feed = document.getElementById('copilotFeed');
  if (!feed) return;

  const intent = data.parsed_intent || {};
  const actionType = data.action_type || 'general';
  const prs = data.generated_prs || [];
  const items = data.affected_items || [];

  const container = document.createElement('div');
  container.className = 'agent-response-box';

  // Scenario 0: Safe Fallback / Security Guardrail / Out of Scope (Zero-Gap Hardening)
  if (actionType === 'unrecognized_intent' || actionType === 'out_of_scope' || actionType === 'security_refusal') {
    const isSecurity = actionType === 'security_refusal';
    const borderColor = isSecurity ? '#DC2626' : '#F59E0B';
    const bgColor = isSecurity ? '#FEF2F2' : '#FFFBEB';
    const borderWrap = isSecurity ? '1px solid #FECACA' : '1px solid #FDE68A';
    const textColor = isSecurity ? '#991B1B' : '#92400E';
    const badgeTitle = isSecurity ? 'Security Guardrail' : 'Out of Scope';

    container.innerHTML = `
      ${getAgentBubbleHeaderHtml(badgeTitle, true)}
      <div class="agent-plan-box" style="border-left: 4px solid ${borderColor}; background: ${bgColor}; border: ${borderWrap};">
        <div style="font-size: 13.5px; color: ${textColor}; line-height: 1.6;">
          ${formatMarkdownResponse(data.message || 'Mohon maaf, instruksi yang Anda masukkan berada di luar cakupan wewenang operasional sistem PT Bali Towerindo Sentra Tbk.')}
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 1: Bali Tower Domain queries (HR, Finance, Inventory) & General responses
  if (['hr_query', 'hr_mutation', 'hr_leave', 'finance_query', 'inventory_query', 'general', 'workflow_execution'].includes(actionType) && prs.length === 0 && actionType !== 'update_threshold' && actionType !== 'register_product') {
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Report')}
      <div class="agent-plan-box">
        <div style="font-size: 13px; color: #0F172A; line-height: 1.6;">
          ${formatMarkdownResponse(data.message || intent.reasoning || 'Instruction processed successfully.')}
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 1b: Goods Receipt Confirmation (Penerimaan Barang Fisik Gudang via Prompt Chat)
  if (actionType === 'goods_receipt') {
    const isAlreadyDelivered = intent.workflow_id === 'goods_receipt_already_delivered';
    const isClarification = intent.workflow_id === 'goods_receipt_clarification';
    const isNotFound = intent.workflow_id === 'goods_receipt_not_found';
    
    let headerTitle = "PHYSICAL GOODS RECEIPT RECORDED";
    let badgeText = "DELIVERED";
    let badgeClass = "badge-approved";
    let borderStyle = "border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7;";
    let headerColor = "#15803D";
    
    if (isAlreadyDelivered) {
      headerTitle = "DELIVERY STATUS: ALREADY RECEIVED";
      badgeText = "COMPLETED";
      badgeClass = "badge-approved";
      borderStyle = "border-left: 4px solid #2563EB; background: #EFF6FF; border: 1px solid #BFDBFE;";
      headerColor = "#1D4ED8";
    } else if (isClarification) {
      headerTitle = "ACTIVE PURCHASE ORDER (ORDERED)";
      badgeText = "ORDERED";
      badgeClass = "badge-low_stock";
      borderStyle = "border-left: 4px solid #D97706; background: #FFFBEB; border: 1px solid #FDE68A;";
      headerColor = "#B45309";
    } else if (isNotFound) {
      headerTitle = "PURCHASE ORDER NOT FOUND";
      badgeText = "VERIFY";
      badgeClass = "badge-rejected";
      borderStyle = "border-left: 4px solid #DC2626; background: #FEF2F2; border: 1px solid #FECACA;";
      headerColor = "#B91C1C";
    }

    const targetPoId = data.po_id || intent.po_id;
    const poBtnHtml = (targetPoId && !isNotFound && !isClarification) ? `
      <div style="display: flex; justify-content: flex-end; margin-top: 10px; gap: 8px;">
        <a href="/api/documents/po/${encodeURIComponent(targetPoId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
          <span>Download PO PDF</span>
        </a>
        <button class="btn btn-secondary btn-sm" onclick="openPoPdfModal('${escapeHtml(targetPoId)}', '${escapeHtml(data.po_number || intent.po_number || targetPoId)}')">
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          <span>View PO Document (PDF)</span>
        </button>
      </div>
    ` : '';

    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Logistics Receiving')}
      <div class="agent-plan-box">
        <div class="action-card" style="${borderStyle} margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: ${headerColor};">${headerTitle}</span>
            <span class="badge ${badgeClass}">${badgeText}</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #0F172A; line-height: 1.6;">
            ${formatMarkdownResponse(data.message)}
            ${poBtnHtml}
          </div>
        </div>
      </div>
    `;
    if (!isNotFound && !isClarification) {
      openDataSidebar('canvas-pos');
    }
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 1c: View / Download PO Document via AI Prompt
  if (actionType === 'view_po_document') {
    const poId = data.po_id || intent.po_id;
    const poNum = data.po_number || intent.po_number || poId;
    const supplier = data.supplier_name || 'Vendor Terdaftar';
    const total = data.grand_total || 0;
    const st = data.status || 'ORDERED';

    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('PO Document (PDF)')}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid #2563EB; background: #EFF6FF; border: 1px solid #BFDBFE; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #1D4ED8;">OFFICIAL PURCHASE ORDER ISSUED (PDF)</span>
            <span class="badge badge-approved">${escapeHtml(st)}</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #1E3A8A; line-height: 1.6;">
            ${formatMarkdownResponse(data.message)}
            <div style="display: flex; justify-content: flex-end; margin-top: 12px; gap: 8px;">
              <a href="/api/documents/po/${encodeURIComponent(poId)}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                <span>Download PDF</span>
              </a>
              <button class="btn btn-primary btn-sm" onclick="openPoPdfModal('${escapeHtml(poId)}', '${escapeHtml(poNum)}', '${escapeHtml(supplier)}', ${total}, '${escapeHtml(st)}')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                <span>View PDF Document</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 2: PR Document(s) Generated
  if (prs.length > 0) {
    const isEmailSent = Boolean(data.email_sent);
    const prCards = prs.map(rawPr => {
      let pr = rawPr;
      if (typeof pr === 'string') {
        pr = { pr_number: pr, supplier_name: 'PT Fiber Optik Nusantara', grand_total: data.total_budget || 0, items: [] };
      }
      const rawStatus = String(pr.status || '').toUpperCase();
      const supplier = pr.supplier_name || 'PT Fiber Optik Nusantara';
      const grandTotal = Number(pr.grand_total || pr.total_budget || 0);
      const escapedSupplier = escapeHtml(supplier).replace(/'/g, "\\'");
      const prEmailSent = pr.email_sent !== undefined ? Boolean(pr.email_sent) : isEmailSent;

      return `
        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px; margin-top: 8px; box-shadow: var(--shadow-xs);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div>
              <span style="font-family: var(--font-mono); font-weight: 700; color: #2563EB; font-size: 12px; background: #EFF6FF; padding: 2px 6px; border-radius: 4px; border: 1px solid #BFDBFE;">${pr.pr_number}</span>
              <span style="font-size: 12.5px; margin-left: 6px; color: #334155; font-weight: 600;">${escapeHtml(supplier)}</span>
            </div>
            <span style="font-weight: 800; font-size: 14px; color: #0F172A;">${formatCurrency(grandTotal)}</span>
          </div>
          <div style="font-size: 12.5px; color: #475569; margin-bottom: 10px; line-height: 1.6;">
            ${(pr.items || []).map(it => `• <strong>${escapeHtml(it.item_name || it.name)}</strong>: ${it.quantity || it.reorder_qty} ${it.unit || 'pcs'}`).join('<br>')}
          </div>
          ${prEmailSent ? `
          <div style="background: #F0FDF4; border: 1px solid #DCFCE7; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; color: #166534; display: flex; align-items: center; gap: 8px;">
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
            <span>Dokumen PR resmi telah dikompilasi (PDF) dan permohonan persetujuan telah otomatis dikirimkan ke email tujuan.</span>
          </div>
          ` : `
          <div id="email-action-box-${pr.pr_number}" class="pr-email-action-box" style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="font-weight: 700; font-size: 13px; color: #0F172A; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#2563EB"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              <span>Kirim Notifikasi Persetujuan via Email?</span>
            </div>
            <div style="font-size: 12px; color: #64748B; margin-bottom: 10px; line-height: 1.5;">
              Draf PR berhasil dibuat dan dicatat ke dalam database sistem. Anda dapat langsung meneruskannya ke Manajer Logistik untuk otorisasi.
            </div>
            <div id="email-action-buttons-${pr.pr_number}" style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
              <button type="button" class="btn btn-primary btn-sm" onclick="dispatchPrEmail('${pr.pr_number}', 'manager.logistik@balitower.co.id')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                <span>Kirim ke Manajer Logistik (manager.logistik@balitower.co.id)</span>
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCustomEmailInput('${pr.pr_number}')">
                <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
                <span>Kirim ke Email Lain...</span>
              </button>
              <button type="button" class="btn btn-secondary btn-sm" style="color: #64748B;" onclick="skipPrEmail('${pr.pr_number}')">
                <span>Lewati (Hanya Simpan Draf)</span>
              </button>
            </div>
            <div id="custom-email-form-${pr.pr_number}" style="display: none; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #CBD5E1;">
              <div style="font-size: 11.5px; font-weight: 600; color: #475569; margin-bottom: 6px;">Masukkan Alamat Email Tujuan:</div>
              <div style="display: flex; gap: 6px; align-items: center;">
                <input type="email" id="custom-email-input-${pr.pr_number}" placeholder="contoh: manager.name@balitower.co.id" class="form-input" style="flex: 1; padding: 6px 10px; font-size: 12px; border: 1px solid #CBD5E1; border-radius: 6px;" onkeydown="if(event.key === 'Enter') submitCustomEmail('${pr.pr_number}')" />
                <button type="button" class="btn btn-primary btn-sm" onclick="submitCustomEmail('${pr.pr_number}')">
                  <span>Kirim</span>
                </button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCustomEmailInput('${pr.pr_number}')">
                  <span>Batal</span>
                </button>
              </div>
            </div>
          </div>
          `}
          <div style="display: flex; justify-content: flex-end;">
            <button class="btn btn-secondary btn-sm" onclick="openPdfModal('${pr.pr_number}', '${escapedSupplier}', ${grandTotal}, '${rawStatus}')">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              <span>Lihat Dokumen PDF</span>
            </button>
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('PR Terbit')}
      <div class="agent-plan-box">
        <div style="font-size: 13px; font-weight: 600; color: #0F172A; margin-bottom: 6px; line-height: 1.5;">
          ${escapeHtml(intent.reasoning || data.message || 'Dokumen pengadaan berhasil diterbitkan dan dicatat.')}
        </div>
        <div class="action-card" style="border-left: 4px solid ${isEmailSent ? '#16A34A' : '#2563EB'}; background: ${isEmailSent ? '#F0FDF4' : '#F8FAFC'}; border: 1px solid ${isEmailSent ? '#DCFCE7' : '#E2E8F0'};">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: ${isEmailSent ? '#15803D' : '#1E40AF'};">${isEmailSent ? `DOKUMEN PR TERBIT & TERKIRIM KE EMAIL (${prs.length})` : `DRAF DOKUMEN PR TERBIT (${prs.length})`}</span>
            <span class="badge ${isEmailSent ? 'badge-approved' : 'badge-pending'}">${isEmailSent ? 'TERKIRIM KE EMAIL' : 'DRAF TERSIMPAN'}</span>
          </div>
          <div class="action-card-body">
            ${prCards}
          </div>
        </div>
      </div>
    `;
    openDataSidebar('canvas-prs');
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 3: Threshold Updated
  if (actionType === 'update_threshold') {
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Stock Threshold')}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid #2563EB; background: #EFF6FF; border: 1px solid #DBEAFE; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #1D4ED8;">STOCK THRESHOLD UPDATED</span>
            <span class="badge badge-approved">SAVED</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #1E3A8A; line-height: 1.5;">
            ${escapeHtml(data.message)}
          </div>
        </div>
      </div>
    `;
    openDataSidebar('canvas-inventory');
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 3b: Product Registration
  if (actionType === 'register_product') {
    const isError = data.message && (data.message.includes('ditolak') || data.message.includes('kurang') || data.message.includes('gagal'));
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml(isError ? 'Registration Rejected' : 'Product Registered', isError)}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid ${isError ? '#DC2626' : '#16A34A'}; background: ${isError ? '#FEF2F2' : '#F0FDF4'}; border: 1px solid ${isError ? '#FECACA' : '#DCFCE7'}; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: ${isError ? '#B91C1C' : '#15803D'};">NEW PRODUCT REGISTRATION</span>
            <span class="badge ${isError ? 'badge-rejected' : 'badge-approved'}">${isError ? 'REJECTED' : 'REGISTERED'}</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: ${isError ? '#991B1B' : '#166534'}; line-height: 1.5;">
            ${escapeHtml(data.message)}
            ${items.length > 0 ? `
              <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed ${isError ? '#FCA5A5' : '#BBF7D0'}; display: flex; flex-wrap: wrap; gap: 6px;">
                ${items.map(it => `
                  <span class="badge badge-normal">
                    ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit} (Min: ${it.min_stock})
                  </span>
                `).join('')}
              </div>
            ` : ''}
          </div>
        </div>
      </div>
    `;
    if (!isError) {
      openDataSidebar('canvas-inventory');
    }
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 4: Email Notification
  if (actionType === 'notify_email') {
    container.innerHTML = `
      ${getAgentBubbleHeaderHtml('Email Notification')}
      <div class="agent-plan-box">
        <div class="action-card" style="border-left: 4px solid #16A34A; background: #F0FDF4; border: 1px solid #DCFCE7; margin-top: 0;">
          <div class="action-card-header">
            <span style="font-weight: 700; font-size: 12.5px; color: #15803D;">AUTOMATION & NOTIFICATION</span>
            <span class="badge badge-approved">SENT</span>
          </div>
          <div class="action-card-body" style="font-size: 13px; color: #166534;">
            ${escapeHtml(data.message)}
            ${items.length > 0 ? `
              <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #BBF7D0; display: flex; flex-wrap: wrap; gap: 6px;">
                ${items.map(it => `
                  <span class="badge ${it.current_stock <= 0 ? 'badge-out_of_stock' : (it.current_stock <= it.min_stock ? 'badge-low_stock' : 'badge-approved')}">
                    ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit}
                  </span>
                `).join('')}
              </div>
            ` : ''}
          </div>
        </div>
      </div>
    `;
    feed.appendChild(container);
    scrollChatToBottom();
    return;
  }

  // Scenario 5: General with affected items
  container.innerHTML = `
    ${getAgentBubbleHeaderHtml('Inventory Report')}
    <div class="agent-plan-box">
      <div class="action-card" style="border-left: 4px solid #2563EB; background: #F8FAFC; border: 1px solid #E2E8F0; margin-top: 0;">
        <div class="action-card-header">
          <span style="font-weight: 700; font-size: 12.5px; color: #2563EB;">INVENTORY REPORT & INFORMATION</span>
          <span class="badge badge-normal">REAL-TIME STATUS</span>
        </div>
        <div class="action-card-body" style="font-size: 13px; color: #334155; line-height: 1.5;">
          ${escapeHtml(data.message || 'Inventory report compiled successfully.')}
          ${items.length > 0 ? `
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #E2E8F0; display: flex; flex-wrap: wrap; gap: 6px;">
              ${items.map(it => `
                <span class="badge ${it.current_stock <= 0 ? 'badge-out_of_stock' : (it.current_stock <= it.min_stock ? 'badge-low_stock' : 'badge-approved')}">
                  ${escapeHtml(it.name)}: ${it.current_stock} ${it.unit}
                </span>
              `).join('')}
            </div>
          ` : ''}
        </div>
      </div>
    </div>
  `;

  feed.appendChild(container);
  scrollChatToBottom();
}

// --- Terminal Logs ---
function appendTerminalLog(log) {
  const terminal = document.getElementById('liveAgentTerminal');
  if (!terminal) return;

  const line = document.createElement('div');
  line.className = 'terminal-line';

  let msgClass = 'terminal-msg-info';
  if (log.status === 'success') msgClass = 'terminal-msg-success';
  if (log.status === 'warning') msgClass = 'terminal-msg-warning';
  if (log.status === 'error') msgClass = 'terminal-msg-error';

  line.innerHTML = `
    <span class="terminal-time">[${log.timestamp || '00:00:00'}]</span>
    <span class="terminal-agent">[${escapeHtml(log.agent_name || 'Agent')}]</span>
    <span class="terminal-step">${escapeHtml(log.step_name || 'Step')}:</span>
    <span class="${msgClass}">${escapeHtml(log.message || '')}</span>
  `;

  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function clearTerminalLogs() {
  const terminal = document.getElementById('liveAgentTerminal');
  if (terminal) terminal.innerHTML = '';
}

// --- Utilities ---
function formatCurrency(num) {
  const n = Number(num);
  if (isNaN(n) || num === null || num === undefined) {
    return 'Rp 0';
  }
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0
  }).format(n);
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
    .replace(/\n/g, '<br>');
}

function showToast(message, type = 'info') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type === 'success' ? 'toast-success' : (type === 'error' ? 'toast-error' : '')}`;
  
  let iconSvg = `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`;
  if (type === 'success') {
    iconSvg = `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#10B981"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`;
  } else if (type === 'error') {
    iconSvg = `<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="#EF4444"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>`;
  }

  toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 3000);
}

// --- API Health Checker ---
async function checkApiHealth() {
  const dot = document.getElementById('apiHealthDot');
  const text = document.getElementById('apiHealthText');
  const offlineBanner = document.getElementById('aiEngineOfflineBanner');
  if (!dot || !text) return;

  try {
    const res = await fetch('/health', { method: 'GET' });
    const data = await res.json().catch(() => ({}));

    if (res.ok && data.llm_connected) {
      dot.style.backgroundColor = '#10B981';
      dot.style.boxShadow = '0 0 6px rgba(16, 185, 129, 0.4)';
      text.textContent = 'API Connected';
      text.style.color = '#15803D';
      if (offlineBanner) offlineBanner.style.display = 'none';
    } else {
      dot.style.backgroundColor = '#EF4444';
      dot.style.boxShadow = '0 0 6px rgba(239, 68, 68, 0.4)';
      text.textContent = 'API Disconnected';
      text.style.color = '#DC2626';
      if (offlineBanner) offlineBanner.style.display = 'flex';
    }
  } catch (e) {
    dot.style.backgroundColor = '#EF4444';
    dot.style.boxShadow = '0 0 6px rgba(239, 68, 68, 0.4)';
    text.textContent = 'API Disconnected';
    text.style.color = '#DC2626';
    if (offlineBanner) offlineBanner.style.display = 'flex';
  }
}

checkApiHealth();
setInterval(() => {
  if (!document.hidden) checkApiHealth();
}, 20000);

function useCopilotSuggestion(promptText) {
  const input = document.getElementById('promptInput');
  if (input) {
    input.value = promptText;
    autoResizePromptInput();
    input.focus();
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// ==============================================================================
// MINIMALIST FLOW HELP & EXAMPLE PROMPTS REGISTRY (PER TENANT)
// ==============================================================================

const FLOW_HELP_REGISTRY = {
  INVENTORY: {
    title: 'Divisi Logistik & Inventaris (Schema A)',
    description: 'Manajemen persediaan material menara telekomunikasi, kabel fiber optic, draf pengadaan PR/PO, dan penerimaan fisik gudang.',
    flows: [
      {
        id: 'WF-A01',
        name: 'Pipeline Pengadaan Material PR-to-PO',
        desc: 'Inspeksi stok di bawah batas aman, kalkulasi reorder otomatis, dan kompilasi PR PDF.',
        examples: [
          'Periksa seluruh stok material yang menipis/kritis dan buat draft PR pengadaan barang dan kirimkan ke email .....@gmail.com'
        ]
      },
      {
        id: 'WF-A02',
        name: 'Penerimaan Barang Fisik PO & Update Saldo',
        desc: 'Verifikasi kedatangan barang PO di gudang regional dan sinkronisasi penambahan stok fisik.',
        examples: [
          'Catat penerimaan PO/BLT/2026/09/031 untuk semua gudang'
        ]
      },
      {
        id: 'GENERAL',
        name: 'Informasi Persediaan Gudang',
        desc: 'Pengecekan sisa stok SKU spesifik atau rekapitulasi status kesehatan barang regional.',
        examples: [
          'Berapa sisa stok ODC 48 Port di Gudang Surabaya?'
        ]
      }
    ]
  },
  HR: {
    title: 'Divisi Human Resources & Operasional Lapangan (Schema B)',
    description: 'Manajemen ketenagakerjaan teknisi lapangan, kualifikasi sertifikasi K3 TKPK rigger, mutasi karyawan, dan pengajuan cuti.',
    flows: [
      {
        id: 'WF-6D8863',
        name: 'Mutasi Karyawan',
        desc: 'Melakukan mutasi departemen dan posisi/jabatan karyawan dengan data yang baru.',
        examples: [
          'Mutasi Dewi Lestari ke departemen IT dengan jabatan Full Stack'
        ]
      },
      {
        id: 'WF-B02',
        name: 'Filter & Screening Pelamar Teknisi K3',
        desc: 'Menyaring kandidat teknisi lapangan secara dinamis berdasarkan kualifikasi posisi dan sertifikasi K3 (TKPK Tingkat 1, TKPK Tingkat 2, K3 Umum, atau seluruh pelamar).',
        examples: [
          'Filter kandidat rigger tower yang memiliki sertifikat TKPK tingkat 2'
        ]
      },
      {
        id: 'WF-B03',
        name: 'Pengajuan Cuti Teknisi dan Penerbitan Dokumen PDF HR',
        desc: 'Mencatat permohonan cuti teknisi ke database DuckDB, mencetak formulir resmi PDF Typst, dan mendistribusikan notifikasi email ke HR.',
        examples: [
          'Ajukan cuti tahunan 3 hari untuk teknisi Budi Santoso mulai besok'
        ]
      }
    ]
  },
  FINANCE: {
    title: 'Divisi Keuangan & Commercial Billing (Schema C)',
    description: 'Manajemen kontrak sewa menara MLA dengan operator telekomunikasi, penagihan invoice, dan audit beban operasional.',
    flows: [
      {
        id: 'WF-C01',
        name: 'Laporan Pendapatan & Invoice Sewa Menara',
        desc: 'Rekapitulasi tagihan invoice sewa menara ke operator telekomunikasi (Telkomsel, Indosat, XL, Smartfren).',
        examples: [
          'Tampilkan rekapitulasi invoice sewa menara per operator dan status pembayarannya'
        ]
      },
      {
        id: 'WF-C02',
        name: 'Audit Beban Listrik PLN & Sewa Lahan',
        desc: 'Laporan pengeluaran operasional utilitas listrik PLN, BBM genset cadangan, dan sewa lahan site.',
        examples: [
          'Audit pengeluaran operasional listrik PLN dan sewa lahan menara regional Jawa Barat'
        ]
      },
      {
        id: 'WF-C04',
        name: 'Pendaftaran Klien Operator & Kontrak Sewa MLA',
        desc: 'Pendaftaran operator telekomunikasi baru dan draf kontrak sewa menara (MLA). Sistem menyimpan draf ke database (PENDING_APPROVAL) dan mengklarifikasi atau mengirimkan berkas faktur ke email otorisasi.',
        examples: [
          'Daftarkan kontrak sewa menara baru untuk operator Telkomsel selama 5 tahun dengan tarif 15 juta per bulan dan kirimkan ke email finance.mgr@balitower.co.id'
        ]
      }
    ]
  },
  ALL: {
    title: 'Superadministrator Enterprise',
    description: 'Akses komprehensif ke seluruh alur kerja operasional, orkestrasi alur dinamis, dan tata kelola basis data multi-tenant.',
    flows: [
      {
        id: 'ORCHESTRATOR',
        name: 'Kompilasi Alur Kerja Dinamis',
        desc: 'Penyusunan alur kerja baru secara otomatis berbasis bahasa alami.',
        examples: [
          'Buat alur kerja baru untuk audit berkala genset dan kirim laporan ke email operasional'
        ]
      },
      {
        id: 'DATABASE',
        name: 'Tata Kelola 18 Basis Data DuckDB',
        desc: 'Pemeriksaan integritas skema data operasional DuckDB dan batasan hak akses tenant.',
        examples: [
          'Tampilkan statistik integritas data pada 18 tabel basis data operasional DuckDB'
        ]
      },
      {
        id: 'CROSS_DOMAIN',
        name: 'Akses Komprehensif Lintas Divisi',
        desc: 'Eksekusi operasional terintegrasi lintas logistik gudang, HR, dan penagihan keuangan.',
        examples: [
          'Periksa stok menara yang kritis dan buat draft PR pengadaan barang'
        ]
      }
    ]
  }
};

function renderTenantHelpExamples() {
  const container = document.getElementById('examplesGrid');
  if (!container) return;

  const tenant = getEffectiveTenant();
  const registry = FLOW_HELP_REGISTRY[tenant] || FLOW_HELP_REGISTRY.ALL;

  let cardsHtml = '';
  registry.flows.forEach(flow => {
    if (flow.examples && flow.examples.length > 0) {
      const exampleText = flow.examples[0];
      const safeEx = escapeHtml(exampleText).replace(/'/g, "\\'");
      cardsHtml += `
        <div class="example-card" onclick="selectExamplePrompt('${safeEx}')" title="Klik untuk memasukkan ke chat">
          <div class="example-card-top">
            <span class="example-card-badge">${escapeHtml(flow.id)}</span>
            <span class="example-card-flow-name">${escapeHtml(flow.name)}</span>
          </div>
          <div class="example-card-text">"${escapeHtml(exampleText)}"</div>
        </div>
      `;
    }
  });

  container.innerHTML = cardsHtml;
}

function selectExamplePrompt(promptText) {
  useCopilotSuggestion(promptText);
}

let currentHelpModalTab = 'catalog';

function switchHelpModalTab(tabName) {
  currentHelpModalTab = tabName;
  const btnCatalog = document.getElementById('helpTabBtnCatalog');
  const btnModel = document.getElementById('helpTabBtnModel');
  const btnPolicy = document.getElementById('helpTabBtnPolicy');

  if (btnCatalog) btnCatalog.classList.toggle('active', tabName === 'catalog');
  if (btnModel) btnModel.classList.toggle('active', tabName === 'model');
  if (btnPolicy) btnPolicy.classList.toggle('active', tabName === 'policy');

  const bodyEl = document.getElementById('flowHelpModalBody');
  if (!bodyEl) return;

  if (tabName === 'catalog') {
    renderHelpCatalogTab(bodyEl);
  } else if (tabName === 'model') {
    renderHelpModelTab(bodyEl);
  } else if (tabName === 'policy') {
    renderHelpPolicyTab(bodyEl);
  }
}

async function openFlowHelpModal() {
  const modal = document.getElementById('flowHelpModal');
  const titleEl = document.getElementById('helpModalTenantTitle');
  const bodyEl = document.getElementById('flowHelpModalBody');
  if (!modal || !bodyEl) return;

  const tenant = (typeof getEffectiveTenant === 'function' ? getEffectiveTenant() : 'INVENTORY') || 'INVENTORY';
  const fallbackRegistry = FLOW_HELP_REGISTRY[tenant] || FLOW_HELP_REGISTRY.ALL;

  if (titleEl) {
    titleEl.textContent = `Operational Workflow Guide: ${fallbackRegistry.title}`;
  }

  modal.style.display = 'flex';
  modal.scrollTop = 0;
  switchHelpModalTab(currentHelpModalTab || 'catalog');
}

async function renderHelpCatalogTab(bodyEl) {
  const tenant = (typeof getEffectiveTenant === 'function' ? getEffectiveTenant() : 'INVENTORY') || 'INVENTORY';
  const fallbackRegistry = FLOW_HELP_REGISTRY[tenant] || FLOW_HELP_REGISTRY.ALL;

  // Fetch dynamic workflows from backend
  let flowsToRender = [];
  try {
    const res = await fetch(`/api/workflows/help-catalog?tenant=${encodeURIComponent(tenant)}&t=${Date.now()}`);
    if (res.ok) {
      const data = await res.json();
      if (data.workflows && data.workflows.length > 0) {
        flowsToRender = data.workflows.map(wf => ({
          id: wf.id,
          name: wf.name,
          desc: wf.description || wf.business_instruction,
          examples: (wf.example_prompts || []).slice(0, 1)
        }));
      }
    }
  } catch (e) {
    console.warn("[HELP MODAL] Could not fetch dynamic workflows, falling back to local registry", e);
  }

  if (!flowsToRender || flowsToRender.length === 0) {
    flowsToRender = fallbackRegistry.flows;
  }

  let html = `
    <div class="flow-help-intro-box">
      <div class="flow-help-intro-title">Integrated Operational Workflow Guide</div>
      <div>${escapeHtml(fallbackRegistry.description)}</div>
    </div>
  `;

  flowsToRender.forEach(flow => {
    html += `
      <div class="flow-help-card">
        <div class="flow-help-card-header">
          <span class="flow-badge">${escapeHtml(flow.id)}</span>
          <span class="flow-title">${escapeHtml(flow.name)}</span>
        </div>
        <div class="flow-desc">${escapeHtml(flow.desc)}</div>
        <div class="flow-examples-label">
          Example Prompts (Click to insert into chat):
        </div>
        <div class="flow-prompts-list">
    `;

    (flow.examples || []).slice(0, 1).forEach(ex => {
      const safeEx = escapeHtml(ex).replace(/'/g, "\\'");
      html += `
        <button type="button" class="flow-prompt-item" onclick="selectExamplePromptAndClose('${safeEx}')" title="Click to insert prompt into chat">
          <span class="prompt-text">"${escapeHtml(ex)}"</span>
          <span class="prompt-action-tag">
            <span>Use</span>
            <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/>
            </svg>
          </span>
        </button>
      `;
    });

    html += `
        </div>
      </div>
    `;
  });

  bodyEl.innerHTML = html;
}

function renderHelpModelTab(bodyEl) {
  bodyEl.innerHTML = `
    <div class="help-model-section">
      <div class="help-model-card" style="border-left: 4px solid #16A34A;">
        <div class="help-model-card-header">
          <span class="badge" style="background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; font-weight: 700; font-size: 11px;">DIRECT SINGLE-TOOL</span>
          <span class="help-model-card-title">1. Direct Single-Tool Execution (Instant)</span>
        </div>
        <div class="help-model-card-desc">
          For daily single-step operational inquiries (e.g. checking remaining stock for a specific item in a warehouse, tower technician attendance history, or lease contract billing status), the AI executes direct isolated queries against DuckDB without requiring a custom workflow from the Administrator. Results are presented in seconds within a clean structured table.
        </div>
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; font-size: 12px; color: #334155; font-family: var(--font-mono);">
          Example: "Berapa sisa stok ODC 48 Port di Gudang Surabaya?"
        </div>
      </div>

      <div class="help-model-card" style="border-left: 4px solid #2563EB;">
        <div class="help-model-card-header">
          <span class="badge" style="background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; font-weight: 700; font-size: 11px;">ADMIN WORKFLOW</span>
          <span class="help-model-card-title">2. Administrator Managed Workflows (Multi-Step & Guarded)</span>
        </div>
        <div class="help-model-card-desc">
          Complex and high-impact business processes (such as PR-to-PO procurement cycles, reorder budget calculations, PO authorizations, and official email distribution) are strictly governed by Administrators via standardized workflows. This ensures internal audit compliance and eliminates unauthorized operations.
        </div>
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; font-size: 12px; color: #334155; font-family: var(--font-mono);">
          Example: "Periksa seluruh stok material yang kritis dan buat draft PR pengadaan barang"
        </div>
      </div>

      <div class="help-model-card" style="border-left: 4px solid #F59E0B;">
        <div class="help-model-card-header">
          <span class="badge" style="background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; font-weight: 700; font-size: 11px;">WORKFLOW REQUEST</span>
          <span class="help-model-card-title">3. In-Chat Workflow Request Proposal</span>
        </div>
        <div class="help-model-card-desc">
          If you require a new operational workflow that is not yet registered in the system, you don't need to file manual tickets. Simply type prompts like <strong>"request workflow"</strong> or <strong>"mau ajukan workflow"</strong>, and an interactive proposal form will render directly in the chat. Your request is automatically routed to the Administrator review queue.
        </div>
        <div style="display: flex; gap: 8px; margin-top: 4px;">
          <button type="button" class="btn btn-primary btn-sm" onclick="selectExamplePromptAndClose('request workflow')">
            <span>Try Now: "request workflow"</span>
          </button>
        </div>
      </div>
    </div>
  `;
}

function renderHelpPolicyTab(bodyEl) {
  bodyEl.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 12px;">
      <div style="font-size: 12.5px; color: #475569; line-height: 1.55;">
        The system enforces an enterprise <strong>Two-Tier Tool Verification Policy</strong>. All operations are strictly classified: <strong>Direct Access</strong> tools execute immediately for safe data inspection, while <strong>Guarded / Workflow Required</strong> tools require registered workflows approved by an Administrator to ensure data integrity and enterprise governance.
      </div>

      <div style="display: flex; gap: 8px; margin-bottom: 4px; flex-wrap: wrap;">
        <span class="badge" style="background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; font-weight: 700; padding: 4px 10px; font-size: 11.5px;">Direct Access (16 Tools)</span>
        <span class="badge" style="background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; font-weight: 700; padding: 4px 10px; font-size: 11.5px;">Workflow Required (18 Tools)</span>
      </div>

      <div class="help-policy-table-container" style="max-height: 480px; overflow-y: auto;">
        <table class="help-policy-table">
          <thead>
            <tr>
              <th style="width: 210px;">Tool Name</th>
              <th style="width: 150px;">Module Category</th>
              <th style="width: 140px;">Access Tier</th>
              <th>Description & Security Policy</th>
            </tr>
          </thead>
          <tbody>
            <!-- DIRECT ACCESS TOOLS -->
            <tr>
              <td><code>inventory.check_specific_stock</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Warehouse Logistics</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Pemeriksaan saldo fisik barang spesifik di gudang (Jakarta, Bandung, Surabaya, dll). Aman dieksekusi langsung tanpa mengubah data.</td>
            </tr>
            <tr>
              <td><code>inventory.get_low_stock_products</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Warehouse Logistics</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Query pembacaan stok material kritis yang berada di bawah ambang batas (safety stock).</td>
            </tr>
            <tr>
              <td><code>inventory.get_all_products</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Warehouse Logistics</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Inspeksi katalog seluruh master barang untuk keperluan audit fisik gudang.</td>
            </tr>
            <tr>
              <td><code>po.query_orders</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Purchase Order</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Pelacakan status pesanan aktif (ACTIVE, IN_TRANSIT, APPROVED, PENDING_APPROVAL).</td>
            </tr>
            <tr>
              <td><code>tool_view_po</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Purchase Order</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Pratinjau (preview) berkas PDF Purchase Order resmi yang tersimpan di sistem. Tidak mengubah saldo fisik.</td>
            </tr>
            <tr>
              <td><code>tool_query_database</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #475569;">Universal Query</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Eksekusi query baca terproteksi (SELECT only) dengan isolasi multi-tenant antar-divisi. Memblokir manipulasi data.</td>
            </tr>
            <tr>
              <td><code>hr.filter_candidates</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #047857;">HR & Safety</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Penyaringan dan screening kandidat Rigger Menara berkualifikasi sertifikat K3 TKPK 1 atau TKPK 2.</td>
            </tr>
            <tr>
              <td><code>hr.query_pending_leaves</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #047857;">HR & Safety</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Audit daftar pengajuan cuti teknisi/karyawan yang masih menunggu otorisasi persetujuan.</td>
            </tr>
            <tr>
              <td><code>hr.audit_attendance</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #047857;">HR & Safety</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Pemeriksaan kehadiran GPS geofencing teknisi site tower dan perhitungan jam lembur.</td>
            </tr>
            <tr>
              <td><code>finance.revenue_report</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Rekapitulasi pendapatan sewa menara per operator, total tagihan terbit, pembayaran lunas, dan piutang (AR).</td>
            </tr>
            <tr>
              <td><code>finance.opex_audit</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Audit beban pengeluaran operasional site BTS (listrik PLN, sewa lahan site, BBM genset).</td>
            </tr>
            <tr>
              <td><code>finance.cashflow_summary</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Kalkulasi ringkasan arus kas masuk vs keluar dan surplus kas bersih operasional perusahaan.</td>
            </tr>
            <tr>
              <td><code>finance.audit_client_onboardings</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Pemeriksaan antrean registrasi operator baru dan permohonan sewa menara yang menunggu otorisasi.</td>
            </tr>
            <tr>
              <td><code>calculate_reorder_quantity</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #6D28D9;">Reasoning Engine</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Kalkulasi formula matematis kuantitas restock, burn rate, dan buffer persediaan tanpa mutasi basis data.</td>
            </tr>
            <tr>
              <td><code>system.check_profile</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #334155;">Universal System</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Pemeriksaan kredensial profil akun login, hak akses role pengguna, dan wewenang tenant.</td>
            </tr>
            <tr>
              <td><code>system.get_system_info</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #334155;">Universal System</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Audit status kesehatan server API, koneksi DuckDB backend, dan performa AI Gateway.</td>
            </tr>
            <tr>
              <td><code>system.get_company_guidelines</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #334155;">Universal System</span></td>
              <td><span class="badge-direct-access">Direct Access</span></td>
              <td>Menampilkan panduan SOP operasional dan kontak darurat NOC Helpdesk 24/7 BaliTower.</td>
            </tr>

            <!-- GUARDED / WORKFLOW REQUIRED TOOLS -->
            <tr style="background: #FFFBEB;">
              <td><code>inventory.update_threshold</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Warehouse Logistics</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Perubahan batas minimum/maksimum stok material. Wajib melalui alur kerja terdaftar agar tidak merusak algoritma auto-restock.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>inventory.register_product</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Warehouse Logistics</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Penambahan SKU material baru ke master katalog inventaris. Memerlukan verifikasi atribut kode barang.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>purchase_order.create_draft</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Purchase Order</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Penerbitan draf Purchase Requisition (PR) bernilai anggaran belanja perusahaan. Wajib melalui alur pengadaan resmi WF-A01.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>po.approve</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Purchase Order</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Otorisasi dokumen pesanan pembelian menjadi APPROVED. Mengikat komitmen legal pesanan ke vendor pemasok.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>inventory.crud_record</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #1D4ED8;">Warehouse Logistics</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Operasi penulisan/mutasi stok fisik barang, supplier, dan PO secara langsung. Terproteksi demi integritas saldo gudang.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>hr.mutate_employee</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #047857;">HR & Safety</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Mutasi jabatan, divisi, dan status kepegawaian karyawan. Memerlukan surat keputusan alur mutasi resmi WF-6D8863.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>hr.approve_leave</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #047857;">HR & Safety</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Otorisasi izin cuti dan pemotongan otomatis saldo kuota tahunan pegawai. Memerlukan persetujuan atasan berwenang.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>hr.submit_leave_request</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #047857;">HR & Safety</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Pencatatan pengajuan cuti resmi dan pendaftaran teknisi pengganti. Wajib melalui alur WF-B03.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>hr.crud_record</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #047857;">HR & Safety</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Mutasi data personalia (status pelamar Screened->Interview, gaji, dsb). Dilarang dilakukan sepihak tanpa workflow.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>finance.draft_client_onboarding</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Penyusunan draf kontrak sewa BTS (MLA) dan penetapan tarif sewa per site operator baru. Wajib alur WF-C04.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>finance.approve_client_onboarding</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Pengesahan aktivasi kontrak sewa menara dan penerbitan faktur tagihan resmi di database.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>finance.generate_invoice</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Penerbitan faktur tagihan sewa BTS komersial resmi bernilai hukum komersial kepada operator.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>finance.crud_record</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #B45309;">Finance & Billing</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Mutasi data penagihan, status invoice (PAID/UNPAID), nilai kontrak MLA, dan biaya OPEX.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>docgen.compile</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #7C3AED;">Document Generation</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Kompilasi dokumen resmi Purchase Requisition (PR) PDF beresolusi tinggi mesin Typst.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>docgen.compile_po</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #7C3AED;">Document Generation</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Kompilasi berkas resmi Purchase Order (PO) PDF berkop surat PT Bali Towerindo Sentra Tbk.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>docgen.compile_leave_pdf</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #7C3AED;">Document Generation</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Kompilasi surat resmi pengajuan izin/cuti karyawan bertanda tangan format PDF Typst.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>notification.dispatch</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #7C3AED;">Notification & Dispatch</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Distribusi notifikasi multi-channel dan email resmi dengan tombol verifikasi persetujuan.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>notification.send_email</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #7C3AED;">Notification & Dispatch</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Pengiriman email SMTP resmi ke manajer operasional atau vendor luar. Memerlukan pengawasan alur resmi.</td>
            </tr>
            <tr style="background: #FFFBEB;">
              <td><code>agent.reason_and_validate</code></td>
              <td><span style="font-size: 11px; font-weight: 600; color: #6D28D9;">Reasoning Engine</span></td>
              <td><span class="badge-workflow-guarded">Workflow Required</span></td>
              <td>Evaluasi prasyarat kelayakan bisnis dan batasan sebelum aksi mutasi diizinkan untuk di-commit.</td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div style="font-size: 12px; color: #64748B; background: #F8FAFC; border: 1px solid #E2E8F0; padding: 10px 14px; border-radius: 8px; line-height: 1.5;">
        <strong>Operational Instruction:</strong> If you need to trigger an action classified under <strong>Guarded Tools</strong>, type <code>"mau ajukan workflow"</code> or <code>"request workflow"</code> in the AI Chat Assistant to open the administrative workflow request submission form.
      </div>
    </div>
  `;
}

function selectExamplePromptAndClose(promptText) {
  selectExamplePrompt(promptText);
  closeFlowHelpModal();
}

function closeFlowHelpModal() {
  const modal = document.getElementById('flowHelpModal');
  if (modal) modal.style.display = 'none';
}

// ==============================================================================
// DOMAIN 2 (HR & WORKFORCE): INTERACTIVE CHAT LEAVE APPLICATION FORM
// ==============================================================================

async function renderLeaveRequestChatForm(targetContainer = null) {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');

  let parent = targetContainer;
  if (!parent) {
    const feed = document.getElementById('copilotFeed');
    if (!feed) return;
    const agentBox = document.createElement('div');
    agentBox.className = 'agent-response-box';
    agentBox.innerHTML = `
      ${getAgentBubbleHeaderHtml('HR Assistant')}
      <div class="stream-text-content" style="margin-bottom: 8px;">
        Please complete the employee leave application form below. Once submitted, records will be saved to DuckDB and an official PDF document will be dispatched to HR.
      </div>
      <div class="stream-artifacts-slot"></div>
    `;
    feed.appendChild(agentBox);
    parent = agentBox.querySelector('.stream-artifacts-slot');
  }

  // Fetch employees list if not already cached
  if (!state.employeesList || state.employeesList.length === 0) {
    try {
      const res = await fetch(`/api/balitower/hr/employees?t=${Date.now()}`);
      if (res.ok) {
        state.employeesList = await res.json();
      }
    } catch (e) {
      console.warn("Failed to load employees for leave form:", e);
    }
  }

  const emps = state.employeesList || [];
  const empOptions = emps.map(e => `
    <option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.full_name)} (${escapeHtml(e.employee_id)}) - ${escapeHtml(e.job_title)}</option>
  `).join('');

  const subOptions = `<option value="">-- Select Substitute Technician (Optional) --</option>` + emps.map(e => `
    <option value="${escapeHtml(e.employee_id)}">${escapeHtml(e.full_name)} - ${escapeHtml(e.job_title)}</option>
  `).join('');

  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const defaultDate = tomorrow.toISOString().split('T')[0];

  const formId = 'leaveForm_' + Date.now();

  parent.innerHTML = `
    <div class="leave-form-card" id="${formId}">
      <div class="leave-form-header">
        <span class="leave-form-title">Employee Leave Application Form</span>
        <span class="badge badge-pending">NEW DRAFT</span>
      </div>
      <div class="leave-form-body">
        <!-- Field 1: Applicant Employee (Full Width) -->
        <div class="leave-form-group">
          <label class="leave-form-label">Applicant Employee <span style="color: #DC2626;">*</span></label>
          <select class="leave-form-select" id="${formId}_emp">
            ${empOptions}
          </select>
        </div>

        <!-- Row 1: Leave Type & Duration -->
        <div class="leave-form-row">
          <div class="leave-form-col">
            <label class="leave-form-label">Leave Type <span style="color: #DC2626;">*</span></label>
            <select class="leave-form-select" id="${formId}_type">
              <option value="ANNUAL_LEAVE">Annual Leave (Cuti Tahunan)</option>
              <option value="SICK_LEAVE">Sick Leave (Cuti Sakit)</option>
              <option value="SPECIAL_LEAVE">Special / Emergency Leave (Cuti Khusus)</option>
              <option value="MATERNITY_LEAVE">Maternity Leave (Cuti Melahirkan)</option>
            </select>
          </div>
          <div class="leave-form-col">
            <label class="leave-form-label">Working Days Duration <span style="color: #DC2626;">*</span></label>
            <input type="number" class="leave-form-input" id="${formId}_days" value="1" min="1" max="30" placeholder="Number of days...">
          </div>
        </div>

        <!-- Row 2: Leave Start Date & Substitute Technician -->
        <div class="leave-form-row">
          <div class="leave-form-col">
            <label class="leave-form-label">Leave Start Date <span style="color: #DC2626;">*</span></label>
            <input type="date" class="leave-form-input" id="${formId}_start" value="${defaultDate}">
          </div>
          <div class="leave-form-col">
            <label class="leave-form-label">Substitute Technician / Backup (Optional)</label>
            <select class="leave-form-select" id="${formId}_sub">
              ${subOptions}
            </select>
          </div>
        </div>

        <!-- Field 4: Reason for Leave (Full Width) -->
        <div class="leave-form-group">
          <label class="leave-form-label">Reason for Leave <span style="color: #DC2626;">*</span></label>
          <input type="text" class="leave-form-input" id="${formId}_reason" placeholder="e.g. Urgent family matter out of town..." value="">
        </div>
      </div>

      <div class="leave-form-footer">
        <span id="${formId}_error" style="color: #DC2626; font-size: 12px; display: none;"></span>
        <button class="btn btn-primary btn-sm" id="${formId}_btn" onclick="submitLeaveRequestForm('${formId}')">
          <span>Submit Leave Application</span>
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/>
          </svg>
        </button>
      </div>
    </div>
  `;

  scrollChatToBottom();
}

function triggerLeaveFormInChat() {
  const container = document.getElementById('geminiChatContainer');
  if (container) container.classList.remove('is-empty-state');
  renderLeaveRequestChatForm();
}

async function submitLeaveRequestForm(formId) {
  const empEl = document.getElementById(`${formId}_emp`);
  const typeEl = document.getElementById(`${formId}_type`);
  const startEl = document.getElementById(`${formId}_start`);
  const daysEl = document.getElementById(`${formId}_days`);
  const subEl = document.getElementById(`${formId}_sub`);
  const reasonEl = document.getElementById(`${formId}_reason`);
  const btn = document.getElementById(`${formId}_btn`);
  const errorEl = document.getElementById(`${formId}_error`);

  if (!empEl || !typeEl || !startEl || !daysEl || !reasonEl) return;

  const employeeId = empEl.value.trim();
  const leaveType = typeEl.value;
  const startDate = startEl.value.trim();
  const daysRequested = parseInt(daysEl.value, 10);
  const reason = reasonEl.value.trim();
  const substituteId = subEl ? subEl.value.trim() : null;

  if (errorEl) errorEl.style.display = 'none';

  if (!employeeId) {
    if (errorEl) { errorEl.textContent = 'Please select an applicant employee.'; errorEl.style.display = 'block'; }
    return;
  }
  if (!startDate) {
    if (errorEl) { errorEl.textContent = 'Please specify the leave start date.'; errorEl.style.display = 'block'; }
    return;
  }
  if (!daysRequested || daysRequested < 1) {
    if (errorEl) { errorEl.textContent = 'Leave duration must be at least 1 working day.'; errorEl.style.display = 'block'; }
    return;
  }
  if (!reason) {
    if (errorEl) { errorEl.textContent = 'Reason for leave is required.'; errorEl.style.display = 'block'; }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>Saving to DB & Generating PDF...</span>`;
  }

  try {
    const res = await fetch('/api/balitower/hr/leave-requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        employee_id: employeeId,
        leave_type: leaveType,
        start_date: startDate,
        days_requested: daysRequested,
        reason: reason,
        substitute_employee_id: substituteId || null
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to submit leave request.");
    }

    const respData = await res.json();
    const d = respData.data || {};
    const leaveId = respData.leave_id || d.leave_id || 'LV-2026-NEW';
    const formCard = document.getElementById(formId);

    if (formCard) {
      // Update parent bubble stream text to avoid duplicate text
      const parentBox = formCard.closest('.agent-response-box');
      if (parentBox) {
        const streamText = parentBox.querySelector('.stream-text-content');
        if (streamText) {
          streamText.textContent = 'Leave application successfully recorded and submitted to HR Division:';
        }
      }

      const typeLabelMap = {
        'ANNUAL_LEAVE': 'Annual Leave (Cuti Tahunan)',
        'SICK_LEAVE': 'Sick Leave (Cuti Sakit)',
        'SPECIAL_LEAVE': 'Special / Emergency Leave (Cuti Khusus)',
        'MATERNITY_LEAVE': 'Maternity Leave (Cuti Melahirkan)'
      };
      const typeLabel = typeLabelMap[d.leave_type] || d.leave_type;

      formCard.className = 'leave-success-card';
      formCard.innerHTML = `
        <div class="leave-success-header">
          <span class="leave-success-title">Leave Application Successfully Submitted</span>
          <span class="badge badge-approved">SUBMITTED TO HR</span>
        </div>
        <div class="leave-success-body">
          <div class="leave-info-grid">
            <div class="leave-info-item">
              <span class="leave-info-k">Application No:</span>
              <span class="badge" style="background:#EFF6FF; color:#2563EB; font-family:var(--font-mono); font-weight:700;">${escapeHtml(leaveId)}</span>
            </div>
            <div class="leave-info-item">
              <span class="leave-info-k">Applicant:</span>
              <span class="leave-info-v"><strong>${escapeHtml(d.applicant_name || '-')}</strong> (${escapeHtml(d.job_title || '-')})</span>
            </div>
            <div class="leave-info-item">
              <span class="leave-info-k">Leave Period:</span>
              <span class="leave-info-v">${escapeHtml(d.start_date)} to ${escapeHtml(d.end_date)} (<strong>${d.days_requested} working days</strong>)</span>
            </div>
            <div class="leave-info-item">
              <span class="leave-info-k">Leave Type:</span>
              <span class="leave-info-v">${escapeHtml(typeLabel)}</span>
            </div>
            <div class="leave-info-item" style="grid-column: 1 / -1;">
              <span class="leave-info-k">Reason:</span>
              <span class="leave-info-v">${escapeHtml(d.reason || '-')}</span>
            </div>
          </div>
          <div class="leave-dispatch-notice">
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
            </svg>
            <span>Official PDF application document generated and notification dispatched to HR.</span>
          </div>
          <div class="leave-action-row">
            <button class="btn btn-primary btn-sm" onclick="openLeavePdfModal('${leaveId}', '${escapeHtml(d.applicant_name || '')}', '${escapeHtml(typeLabel)}', ${d.days_requested}, 'PENDING_APPROVAL')">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
              </svg>
              <span>View PDF Document</span>
            </button>
            <a href="/api/documents/leave/${leaveId}/download?download=true" target="_blank" class="btn btn-secondary btn-sm">
              <svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
              <span>Download PDF</span>
            </a>
          </div>
        </div>
      `;
    }

    showToast(`Leave request ${leaveId} submitted successfully to HR`, 'success');
    loadHrData();
    loadEmployees();
    saveCopilotFeed();
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = err.message || "Failed to submit leave request.";
      errorEl.style.display = 'block';
    }
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>Submit Leave Application</span>`;
    }
    showToast(err.message || "Failed to submit leave request", 'error');
  }
}

// --- Auto-Refresh on Window Focus / Tab Activation (e.g., returning from Email Quick Approval) ---
window.addEventListener('focus', () => {
  const hrCanvas = document.getElementById('canvas-hr');
  if (hrCanvas && hrCanvas.classList.contains('active')) {
    loadHrData();
    loadEmployees();
  }
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    const hrCanvas = document.getElementById('canvas-hr');
    if (hrCanvas && hrCanvas.classList.contains('active')) {
      loadHrData();
      loadEmployees();
    }
  }
});
