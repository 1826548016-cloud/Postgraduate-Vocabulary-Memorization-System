// ===== TTS 发音引擎（全局单例） =====
(function () {
  var voices = [];
  var ready = false;

  // 预加载语音列表
  function loadVoices() {
    voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      ready = true;
    }
    // 默认选 en-US 女声
    var best = null;
    for (var i = 0; i < voices.length; i++) {
      if (voices[i].lang.startsWith('en-US') && voices[i].name.includes('Female')) {
        best = voices[i]; break;
      }
    }
    if (!best) {
      for (var i = 0; i < voices.length; i++) {
        if (voices[i].lang.startsWith('en-US')) { best = voices[i]; break; }
      }
    }
    if (!best && voices.length > 0) best = voices[voices.length - 1];
    return best;
  }

  var voice = null;

  // 初始加载
  if (window.speechSynthesis) {
    voice = loadVoices();
    window.speechSynthesis.addEventListener('voiceschanged', function () {
      voice = loadVoices();
    });
    // Chrome 有时不会触发 voiceschanged，定时重试
    setTimeout(function () {
      if (!ready) voice = loadVoices();
    }, 300);
  }

  // 暴露全局 speak 函数
  window.VOCAB_SPEAK = function (text, lang) {
    if (!window.speechSynthesis || !text) return;
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.lang = lang || 'en-US';
    u.rate = 0.9;
    u.pitch = 1;
    if (voice) u.voice = voice;
    window.speechSynthesis.speak(u);
  };
})();
