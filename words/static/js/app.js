// ===== Font Size =====
function initFontSize() {
  var size = localStorage.getItem('vocab-font-size') || 'medium';
  document.documentElement.setAttribute('data-font-size', size);
}

// ===== Toast =====
function showToast(message, type, duration) {
  type = type || 'success';
  duration = duration || 2600;
  var container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  var t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = message;
  container.appendChild(t);
  setTimeout(function () {
    t.style.opacity = '0';
    t.style.transform = 'translateY(-10px)';
    t.style.transition = 'all .25s ease';
    setTimeout(function () { t.remove(); }, 250);
  }, duration);
}

// ===== API Helper =====
var VOCAB_API = {
  get: async function (url) {
    var r = await fetch(url);
    return r.json();
  },
  post: async function (url, data) {
    data = data || {};
    var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
    var r = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf ? csrf.value : '',
      },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  del: async function (url, data) {
    if (data) {
      var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
      var r = await fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf ? csrf.value : '',
        },
        body: JSON.stringify(data),
      });
      return r.json();
    }
    var r = await fetch(url, { method: 'DELETE' });
    return r.json();
  },
};

// ===== Init =====
document.addEventListener('DOMContentLoaded', function () {
  initFontSize();
});
