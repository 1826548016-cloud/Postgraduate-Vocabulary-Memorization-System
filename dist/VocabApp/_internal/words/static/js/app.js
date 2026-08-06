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

// ===== Study Time =====
// 学习页显式调用 start() 后，仅在页面可见时计时；切换标签页、最小化窗口或离开页面都会暂停并同步。
// 多标签页去重：通过 BroadcastChannel + localStorage 锁，保证同一时刻只有一个标签页上报时长。
window.VocabStudyTimer = (function () {
  var active = false;
  var lastActiveAt = 0;
  var pendingSeconds = 0;
  var intervalId = null;
  var isMaster = false; // 是否为持有计时报的主标签页
  var TAB_ID = 'tab-' + Date.now() + '-' + Math.random().toString(36).slice(2);
  var LOCK_KEY = 'vocab_study_timer_master';
  var channel = null;
  try { channel = new BroadcastChannel('vocab_study_timer'); } catch (e) {}

  // 尝试获取主标签页锁
  function acquireLock() {
    if (isMaster) return true;
    var current = localStorage.getItem(LOCK_KEY);
    // 锁超过 8 秒视为过期
    if (current && Date.now() - parseInt(current.split('|')[1], 10) < 8000) return false;
    localStorage.setItem(LOCK_KEY, TAB_ID + '|' + Date.now());
    // 再读一次确认自己抢到了
    if (localStorage.getItem(LOCK_KEY).indexOf(TAB_ID) === 0) {
      isMaster = true;
      if (channel) channel.postMessage({ type: 'master_changed', tab: TAB_ID });
      return true;
    }
    return false;
  }

  // 定期续租锁
  function renewLock() {
    if (!isMaster) return;
    localStorage.setItem(LOCK_KEY, TAB_ID + '|' + Date.now());
  }

  function releaseLock() {
    if (!isMaster) return;
    isMaster = false;
    localStorage.removeItem(LOCK_KEY);
    if (channel) channel.postMessage({ type: 'master_changed', tab: null });
  }

  function collect() {
    if (!active || !isMaster || document.hidden || !lastActiveAt) return;
    var seconds = Math.floor((Date.now() - lastActiveAt) / 1000);
    if (seconds > 0) pendingSeconds += seconds;
    lastActiveAt = Date.now();
  }

  function flush() {
    collect();
    var seconds = Math.min(pendingSeconds, 90);
    if (!seconds) return;
    pendingSeconds -= seconds;
    fetch('/api/study-duration/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds: seconds }),
      keepalive: true,
    }).catch(function () { pendingSeconds += seconds; });
  }

  function start() {
    if (active) return;
    active = true;
    intervalId = setInterval(function () {
      // 每个周期：尝试获取锁、续租锁、如果可见则计时
      if (!isMaster) acquireLock();
      if (isMaster) {
        renewLock();
        if (!document.hidden) {
          if (!lastActiveAt) lastActiveAt = Date.now();
          flush();
        }
      }
    }, 20000);
    // 立即尝试获取锁
    if (!document.hidden) acquireLock();
    lastActiveAt = document.hidden ? 0 : Date.now();
  }

  function stop() {
    if (!active) return;
    flush();
    releaseLock();
    active = false;
    lastActiveAt = 0;
    if (intervalId) clearInterval(intervalId);
    intervalId = null;
  }

  document.addEventListener('visibilitychange', function () {
    if (!active) return;
    if (document.hidden) {
      flush();
      releaseLock();
      lastActiveAt = 0;
    } else {
      acquireLock();
      lastActiveAt = Date.now();
    }
  });

  // 监听其他标签页释放锁的消息，尝试接管
  if (channel) {
    channel.onmessage = function (e) {
      if (e.data && e.data.type === 'master_changed' && !e.data.tab && active && !document.hidden) {
        acquireLock();
      }
    };
  }

  // 页面卸载时释放锁
  window.addEventListener('pagehide', function () {
    flush();
    if (active) releaseLock();
  });

  return { start: start, stop: stop, flush: flush };
})();

// ===== Init =====
document.addEventListener('DOMContentLoaded', function () {
  initFontSize();
});
