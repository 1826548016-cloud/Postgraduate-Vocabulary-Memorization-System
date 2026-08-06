// ===== 小助手共享组件（背诵/专注/复习共用，对话历史互通并持久化） =====
window.AssistantPanel = (function () {
  'use strict';

  var cfg = { aiSettingsUrl: '/settings/#ai-models', getCurrentWord: null };
  var CACHE_KEY = 'vocab-assistant-cache-v1';
  var sending = false;
  var confirmingClear = false;
  var clearTimer = null;
  var slowTimer = null;
  var errTimer = null;

  function el(id) { return document.getElementById(id); }
  function panel() { return el('assistantPanel'); }
  function backdrop() { return el('assistantBackdrop'); }
  function isOpen() {
    var p = panel();
    return !!p && p.classList.contains('open');
  }

  function init(options) {
    cfg = Object.assign(cfg, options || {});
    var input = el('assistantInput');
    if (input) {
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendFromInput();
        }
      });
    }
    var fab = el('assistantFab');
    if (fab) fab.addEventListener('click', toggle);
    var closeBtn = el('assistantCloseBtn');
    if (closeBtn) closeBtn.addEventListener('click', close);
    var bd = backdrop();
    if (bd) bd.addEventListener('click', close);
    var clearBtn = el('assistantClearBtn');
    if (clearBtn) clearBtn.addEventListener('click', clearHistory);
    var chips = el('assistantChips');
    if (chips) {
      chips.addEventListener('click', function (e) {
        var btn = e.target && e.target.closest ? e.target.closest('.assistant-chip') : null;
        if (btn) ask(btn.getAttribute('data-prompt') || '');
      });
    }
    var err = el('assistantError');
    if (err) err.addEventListener('click', hideError);
  }

  // 代码块复制按钮（事件委托）
  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('.assistant-copy-btn') : null;
    if (!btn) return;
    var pre = btn.parentElement && btn.parentElement.nextElementSibling;
    var text = pre ? pre.textContent : '';
    copyText(text).then(function () {
      btn.textContent = '已复制';
      setTimeout(function () { btn.textContent = '复制'; }, 1600);
    });
  });

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta);
      resolve();
    });
  }

  function toggle() { if (isOpen()) close(); else open(); }

  function open() {
    var p = panel();
    if (!p || isOpen()) return;
    p.classList.remove('hidden');
    void p.offsetWidth; // 触发回流以播放动画
    p.classList.add('open');
    var bd = backdrop();
    if (bd) bd.classList.add('open');
    refreshCurrentWord();
    loadHistory();
    var input = el('assistantInput');
    if (input) input.focus();
  }

  function close() {
    var p = panel();
    if (!p) return;
    p.classList.remove('open');
    var bd = backdrop();
    if (bd) bd.classList.remove('open');
    clearTimeout(slowTimer);
    setTimeout(function () { if (!isOpen()) p.classList.add('hidden'); }, 280);
  }

  function setBody(html) {
    var body = el('assistantBody');
    if (body) body.innerHTML = html;
  }

  function emptyHtml() {
    return '<div class="assistant-empty"><i class="ph ph-chat-circle-text"></i>你好，我是你的智能助手！<br>单词考法、近义辨析、例句仿写都可以问我。</div>';
  }

  // 每次打开先展示本地缓存，再静默刷新，保证历史最新（三个模式互通）
  function loadHistory() {
    var cached = loadCache();
    if (cached && cached.length) {
      renderMessages(cached);
    } else {
      setBody(emptyHtml());
    }
    VOCAB_API.get('/api/assistant/').then(function (res) {
      var msgs = (res && res.messages) || [];
      renderMessages(msgs);
      saveCache(msgs);
    }).catch(function () {
      if (!cached || !cached.length) showError('加载对话记录失败，请稍后重试');
    });
  }

  function renderMessages(msgs) {
    if (!msgs || !msgs.length) {
      setBody(emptyHtml());
      return;
    }
    var html = '';
    var lastDate = null;
    msgs.forEach(function (m) {
      var d = m.created_at ? m.created_at.slice(0, 10) : null;
      if (d && d !== lastDate) {
        html += dateDividerHtml(dateLabel(m.created_at));
        lastDate = d;
      }
      html += bubbleHtml(m.role, m.content, m.created_at);
    });
    setBody(html);
    scrollBottom();
  }

  function bubbleHtml(role, content, time) {
    var isUser = role === 'user';
    var body = isUser ? escapeHtml(content) : renderMarkdown(content);
    var icon = isUser ? 'ph-user' : 'ph-chat-circle-text';
    return '<div class="assistant-msg ' + (isUser ? 'user' : 'ai') +
      '" data-date="' + (time ? time.slice(0, 10) : '') + '">' +
      '<div class="assistant-avatar-sm ' + (isUser ? 'user' : 'ai') + '"><i class="ph ' + icon + '"></i></div>' +
      '<div class="assistant-bubble">' + body +
      (time ? '<span class="assistant-msg-time">' + time.slice(11) + '</span>' : '') +
      '</div></div>';
  }

  function dateDividerHtml(label) {
    return '<div class="assistant-date-divider">' + escapeHtml(label) + '</div>';
  }

  function dateKey(s) { return s ? s.slice(0, 10) : null; }

  function dateLabel(s) {
    if (!s) return '';
    var d = new Date(s.replace(' ', 'T'));
    if (isNaN(d.getTime())) return s.slice(0, 10);
    var now = new Date();
    function sameDay(a, b) {
      return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
    }
    function hm(x) { return pad(x.getHours()) + ':' + pad(x.getMinutes()); }
    if (sameDay(d, now)) return '今天 ' + hm(d);
    var yest = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    if (sameDay(d, yest)) return '昨天 ' + hm(d);
    return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + hm(d);
  }

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  // ===== 轻量 Markdown 渲染（仅用于 AI 回答；先转义再排版，天然防 XSS） =====
  function renderMarkdown(src) {
    if (!src) return '';
    // keepGt=true：保留 > 以便识别引用块（> 在文本中无害，不需要转义）
    var lines = escapeHtml(src, true).split('\n');
    var html = '';
    var i = 0;
    var para = [];

    function flushPara() {
      if (para.length) {
        html += '<p>' + para.map(inline).join('<br>') + '</p>';
        para = [];
      }
    }
    function inline(s) {
      s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (m, t, u) {
        return /^(https?:\/\/)/.test(u) ? '<a href="' + u + '" target="_blank" rel="noopener">' + t + '</a>' : m;
      });
      s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
      s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
      s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
      return s;
    }

    while (i < lines.length) {
      var line = lines[i];
      // 围栏代码块
      if (/^\s*```/.test(line)) {
        flushPara();
        var buf = [];
        i++;
        while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i++; }
        html += '<div class="assistant-code-block"><div class="assistant-code-head"><span>代码</span>' +
          '<button type="button" class="assistant-copy-btn">复制</button></div>' +
          '<pre><code>' + buf.join('\n') + '</code></pre></div>';
        i++;
        continue;
      }
      // 标题
      var h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) {
        flushPara();
        html += '<h' + h[1].length + '>' + inline(h[2]) + '</h' + h[1].length + '>';
        i++;
        continue;
      }
      // 分隔线
      if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
        flushPara();
        html += '<hr>';
        i++;
        continue;
      }
      // 引用
      if (/^\s*>\s?/.test(line)) {
        flushPara();
        var q = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          q.push(inline(lines[i].replace(/^\s*>\s?/, '')));
          i++;
        }
        html += '<blockquote>' + q.join('<br>') + '</blockquote>';
        continue;
      }
      // 无序列表（含缩进续行）
      if (/^\s*[-*]\s+/.test(line)) {
        flushPara();
        var ul = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
          var li = inline(lines[i].replace(/^\s*[-*]\s+/, ''));
          i++;
          while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*[-*]\s+/.test(lines[i]) && !/^\s*\d+\.\s+/.test(lines[i])) {
            li += '<br>' + inline(lines[i].trim());
            i++;
          }
          ul.push('<li>' + li + '</li>');
        }
        html += '<ul>' + ul.join('') + '</ul>';
        continue;
      }
      // 有序列表（含缩进续行）
      if (/^\s*\d+\.\s+/.test(line)) {
        flushPara();
        var ol = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          var oli = inline(lines[i].replace(/^\s*\d+\.\s+/, ''));
          i++;
          while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*[-*]\s+/.test(lines[i]) && !/^\s*\d+\.\s+/.test(lines[i])) {
            oli += '<br>' + inline(lines[i].trim());
            i++;
          }
          ol.push('<li>' + oli + '</li>');
        }
        html += '<ol>' + ol.join('') + '</ol>';
        continue;
      }
      // 简单表格（下一行为分隔行时开始收集）
      if (line.indexOf('|') >= 0 && lines[i + 1] && /^\s*\|?[\s:|-]+\|[\s:|-]*\s*$/.test(lines[i + 1])) {
        flushPara();
        var rows = [];
        while (i < lines.length && lines[i] && lines[i].indexOf('|') >= 0) {
          var row = lines[i].trim().replace(/^\||\|$/g, '');
          if (!/^[\s:|-]+$/.test(row.replace(/\|/g, ''))) {
            rows.push(row.split('|').map(function (c) { return c.trim(); }));
          }
          i++;
        }
        if (rows.length) {
          var tbl = '<table><thead><tr>';
          rows[0].forEach(function (h2) { tbl += '<th>' + inline(h2) + '</th>'; });
          tbl += '</tr></thead><tbody>';
          for (var r = 1; r < rows.length; r++) {
            tbl += '<tr>';
            rows[r].forEach(function (c) { tbl += '<td>' + inline(c) + '</td>'; });
            tbl += '</tr>';
          }
          tbl += '</tbody></table>';
          html += '<div class="assistant-table-wrap">' + tbl + '</div>';
        }
        continue;
      }
      // 空行
      if (/^\s*$/.test(line)) { flushPara(); i++; continue; }
      para.push(line);
      i++;
    }
    flushPara();
    return html;
  }

  function escapeHtml(s, keepGt) {
    var t = String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/"/g, '&quot;');
    if (!keepGt) t = t.replace(/>/g, '&gt;');
    return t;
  }

  function scrollBottom() {
    var body = el('assistantBody');
    if (body) body.scrollTop = body.scrollHeight;
  }

  function appendMsg(role, content, time) {
    var body = el('assistantBody');
    if (!body) return;
    var empty = body.querySelector('.assistant-empty');
    if (empty) empty.remove();
    var last = body.querySelector('.assistant-msg:last-child');
    var d = time ? time.slice(0, 10) : null;
    if (d && last && last.getAttribute('data-date') !== d) {
      body.insertAdjacentHTML('beforeend', dateDividerHtml(dateLabel(time)));
    }
    body.insertAdjacentHTML('beforeend', bubbleHtml(role, content, time));
    scrollBottom();
  }

  function showThinking() {
    var body = el('assistantBody');
    if (!body) return;
    hideThinking();
    body.insertAdjacentHTML('beforeend',
      '<div class="assistant-msg ai">' +
      '<div class="assistant-avatar-sm ai"><i class="ph ph-chat-circle-text"></i></div>' +
      '<div class="assistant-bubble"><span class="assistant-thinking" id="assistantThinking">' +
      '<span class="dot"></span><span class="dot"></span><span class="dot"></span></span></div></div>');
    scrollBottom();
  }

  function hideThinking() {
    var t = el('assistantThinking');
    if (t) {
      var row = t.closest ? t.closest('.assistant-msg') : null;
      if (row) row.remove();
    }
  }

  function getWord() {
    if (typeof cfg.getCurrentWord === 'function') {
      var w = cfg.getCurrentWord();
      return w && w.id ? w : null;
    }
    return null;
  }

  function getWordId() {
    var w = getWord();
    return w ? w.id : null;
  }

  function refreshCurrentWord() {
    var cap = el('assistantWordCapsule');
    var nameEl = el('assistantWordName');
    var chips = el('assistantChips');
    var w = getWord();
    var has = !!(w && w.word);
    if (cap && nameEl) {
      nameEl.textContent = has ? w.word : '';
      cap.classList.toggle('hidden', !has);
    }
    if (chips) chips.classList.toggle('hidden', !has);
  }

  function sendFromInput() {
    var input = el('assistantInput');
    if (!input) return;
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    send(text);
  }

  function send(text) {
    if (sending) return;
    sending = true;
    setSending(true);
    appendMsg('user', text, null);
    showThinking();
    slowTimer = setTimeout(function () {
      var t = el('assistantThinking');
      if (t && !t.querySelector('.assistant-thinking-hint')) {
        t.insertAdjacentHTML('beforeend', '<span class="assistant-thinking-hint">模型响应较慢，请稍候…</span>');
      }
    }, 3000);

    VOCAB_API.post('/api/assistant/', { message: text, word_id: getWordId() }).then(function (res) {
      clearTimeout(slowTimer);
      hideThinking();
      if (res && res.success) {
        appendMsg('assistant', res.assistant_message.content, res.assistant_message.created_at);
        appendToCache(res.user_message, res.assistant_message);
      } else {
        showError((res && res.error) || '出错了，请重试');
        if (res && res.error && /模型/.test(res.error)) {
          showToast('请到设置页配置并启用 AI 模型', 'error');
        }
      }
    }).catch(function () {
      clearTimeout(slowTimer);
      hideThinking();
      showError('网络错误，请稍后重试');
    }).finally(function () {
      sending = false;
      setSending(false);
      var input = el('assistantInput');
      if (input) input.focus();
    });
  }

  function setSending(on) {
    var btn = el('assistantSendBtn');
    if (!btn) return;
    btn.disabled = on;
    btn.innerHTML = on
      ? '<i class="ph ph-circle-notch" style="animation: spin 1s linear infinite;"></i>'
      : '<i class="ph ph-paper-plane-tilt"></i>';
  }

  // 快捷提问：把「当前单词」替换成真实单词再发送
  function ask(prompt) {
    var w = getWord();
    if (!w || !w.word) {
      showToast('请先选择一个单词', 'error');
      return;
    }
    var text = String(prompt || '').replace(/当前单词/g, '「' + w.word + '」');
    if (!text.trim()) return;
    send(text);
  }

  // 兼容旧调用：一键询问当前单词的考法
  function askCurrentWord() {
    var w = getWord();
    if (!w || !w.word) {
      showToast('请先选择一个单词', 'error');
      return;
    }
    send('请讲解单词 "' + w.word + '" 的考法、常见搭配和记忆技巧');
  }

  // 两步确认清空，避免误删
  function clearHistory() {
    var btn = el('assistantClearBtn');
    if (!confirmingClear) {
      confirmingClear = true;
      if (btn) {
        btn.innerHTML = '<i class="ph ph-check"></i> 确认？';
        btn.classList.add('btn-danger');
      }
      clearTimer = setTimeout(resetClearConfirm, 3000);
      return;
    }
    resetClearConfirm();
    VOCAB_API.del('/api/assistant/').then(function (res) {
      if (res && res.success) {
        renderMessages([]);
        try { localStorage.removeItem(CACHE_KEY); } catch (e) {}
        showToast('对话记录已清空', 'success');
      } else {
        showToast((res && res.error) || '清空失败', 'error');
      }
    }).catch(function () { showToast('请求失败', 'error'); });
  }

  function resetClearConfirm() {
    confirmingClear = false;
    clearTimeout(clearTimer);
    var btn = el('assistantClearBtn');
    if (btn) {
      btn.innerHTML = '<i class="ph ph-trash"></i>';
      btn.classList.remove('btn-danger');
    }
  }

  function showError(msg) {
    var e = el('assistantError');
    if (!e) return;
    var span = e.querySelector('span');
    if (span) span.textContent = msg || '出错了';
    e.classList.remove('hidden');
    clearTimeout(errTimer);
    errTimer = setTimeout(hideError, 10000);
  }

  function hideError() {
    var e = el('assistantError');
    if (e) e.classList.add('hidden');
  }

  // 本地缓存：先渲染再刷新，减少等待感
  function saveCache(msgs) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify((msgs || []).slice(-50))); } catch (e) {}
  }
  function loadCache() {
    try {
      var s = localStorage.getItem(CACHE_KEY);
      return s ? JSON.parse(s) : null;
    } catch (e) { return null; }
  }
  function appendToCache() {
    var cached = loadCache() || [];
    for (var i = 0; i < arguments.length; i++) {
      if (arguments[i]) cached.push(arguments[i]);
    }
    saveCache(cached);
  }

  return {
    init: init, toggle: toggle, open: open, close: close, isOpen: isOpen,
    sendFromInput: sendFromInput, ask: ask, askCurrentWord: askCurrentWord,
    refreshCurrentWord: refreshCurrentWord, clearHistory: clearHistory,
  };
})();
