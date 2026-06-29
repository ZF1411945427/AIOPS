// ============================================================
// AIOPS Platform - Core UI Utilities
// ============================================================

// --- Toast Notification System ---
var Toast = {
  queue: [],
  container: null,

  init: function() {
    this.container = document.getElementById('toast-container');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'toast-container';
      document.body.appendChild(this.container);
    }
  },

  show: function(message, type, duration) {
    this.init();
    type = type || 'info';
    duration = duration || 4000;
    var icons = { info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌' };
    var el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.innerHTML = '<span class="toast-icon">' + (icons[type] || '') + '</span><span class="toast-msg">' + message + '</span>';
    this.container.appendChild(el);
    requestAnimationFrame(function() { el.classList.add('toast-visible'); });
    var self = this;
    setTimeout(function() { self.dismiss(el); }, duration);
    return el;
  },

  dismiss: function(el) {
    el.classList.remove('toast-visible');
    el.classList.add('toast-hiding');
    var self = this;
    setTimeout(function() {
      if (el.parentNode) el.parentNode.removeChild(el);
      self.queue = self.queue.filter(function(e) { return e !== el; });
    }, 300);
  }
};

// --- Dark Mode ---
var Theme = {
  key: 'aiops-theme',

  init: function() {
    var saved = localStorage.getItem(this.key);
    if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark');
    }
    this.updateToggle();
  },

  toggle: function() {
    document.documentElement.classList.toggle('dark');
    var isDark = document.documentElement.classList.contains('dark');
    localStorage.setItem(this.key, isDark ? 'dark' : 'light');
    this.updateToggle();
    Toast.show(isDark ? '已切换为暗色模式' : '已切换为亮色模式', 'info', 2000);
  },

  updateToggle: function() {
    var btn = document.getElementById('themeToggle');
    if (btn) {
      var isDark = document.documentElement.classList.contains('dark');
      btn.innerHTML = isDark ? '☀️' : '🌙';
      btn.title = isDark ? '切换亮色模式' : '切换暗色模式';
    }
  }
};

// --- Loading Overlay ---
var Loader = {
  show: function(msg) {
    var el = document.getElementById('loading-overlay');
    if (!el) {
      el = document.createElement('div');
      el.id = 'loading-overlay';
      el.className = 'loading-overlay';
      el.innerHTML = '<div class="loading-spinner"><div class="spinner-ring"></div><p class="loading-text">' + (msg || '加载中...') + '</p></div>';
      document.body.appendChild(el);
    }
    el.style.display = 'flex';
    el.querySelector('.loading-text').textContent = msg || '加载中...';
  },

  hide: function() {
    var el = document.getElementById('loading-overlay');
    if (el) el.style.display = 'none';
  }
};

// --- Tab Helpers ---
function openTabFallback(url, title) {
  // Calls the global openTab defined in base.html if available
  if (typeof openTab === 'function') {
    openTab(url, title);
  } else {
    window.location.href = url;
  }
}

// --- Auto-dismiss alerts ---
function autoDismissAlerts() {
  var alerts = document.querySelectorAll('.alert-dismissible');
  alerts.forEach(function(a) {
    setTimeout(function() {
      a.style.opacity = '0';
      a.style.transform = 'translateY(-10px)';
      setTimeout(function() { if (a.parentNode) a.parentNode.removeChild(a); }, 400);
    }, 5000);
  });
}

// --- K8s Cluster Persistence ---
var ClusterKeeper = {
  key: 'aiops_k8s_cluster',
  init: function() {
    var select = document.querySelector('select[name="cluster"]');
    if (!select) return;

    select.addEventListener('change', function() {
      localStorage.setItem(ClusterKeeper.key, this.value);
    });

    var urlParams = new URLSearchParams(window.location.search);
    if (!urlParams.has('cluster')) {
      var saved = localStorage.getItem(this.key);
      if (saved && !select.value) {
        select.value = saved;
        var form = select.closest('form');
        if (form) form.submit();
      }
    } else {
      var clusterVal = urlParams.get('cluster') || '';
      if (clusterVal) localStorage.setItem(this.key, clusterVal);
    }
  }
};

// --- Cluster Filter Enhancements ---
function enhanceClusterFilter() {
  var select = document.querySelector('select[name="cluster"]');
  if (!select) return;
  select.classList.add('cluster-select');
  select.style.cssText = 'padding: 8px 14px; border-radius: 8px; border: 1px solid rgba(148,163,184,0.2); background: var(--card-bg,#fff); color: var(--text-primary,#1e293b); font-size: 14px; min-width: 180px; cursor: pointer;';

  var filterCard = select.closest('.card, .toolbar');
  if (filterCard) {
    filterCard.style.cssText = 'background: var(--card-bg,#fff); border-radius: 12px; padding: 16px 20px; border: 1px solid rgba(148,163,184,0.12); margin-bottom: 20px;';
  }

  var form = select.closest('form');
  if (form) {
    form.style.cssText = 'display: flex; gap: 12px; align-items: center; flex-wrap: wrap;';
  }
}

// --- Enhance table cards ---
function enhanceTables() {
  document.querySelectorAll('.table').forEach(function(tbl) {
    tbl.style.cssText = 'width: 100%; border-collapse: collapse; font-size: 14px;';
    tbl.querySelectorAll('thead th').forEach(function(th) {
      th.style.cssText = 'padding: 10px 12px; font-weight: 600; color: var(--text-secondary,#64748b); border-bottom: 2px solid rgba(148,163,184,0.12); text-align: left; white-space: nowrap;';
    });
    tbl.querySelectorAll('tbody td').forEach(function(td) {
      td.style.cssText = 'padding: 10px 12px; border-bottom: 1px solid rgba(148,163,184,0.06); color: var(--text-primary,#1e293b);';
    });
    tbl.querySelectorAll('tbody tr').forEach(function(tr) {
      tr.addEventListener('mouseenter', function() { this.style.background = 'rgba(129,140,248,0.04)'; });
      tr.addEventListener('mouseleave', function() { this.style.background = ''; });
    });
    tbl.querySelectorAll('thead tr').forEach(function(tr) {
      tr.style.cssText = 'background: rgba(148,163,184,0.04);';
    });
  });
}

document.addEventListener('DOMContentLoaded', function() {
  ClusterKeeper.init();
  enhanceClusterFilter();
  enhanceTables();
  autoDismissAlerts();
});

// Initialize theme on load
Theme.init();
