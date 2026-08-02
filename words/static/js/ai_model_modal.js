// ===== AI 模型配置独立窗口（API 填写）=====
// 全局可用：AI 单词导入 / 设置 / 小助手等页面均可通过 openAddModel() 打开此窗口。
// 配置统一存入数据库 AIModel 表，后端 resolve_ai_model 读取。
// 保存成功后调用 window.aiModelModalOnSaved 钩子（由当前页面注册，用于刷新模型列表/选择框）。

// 模型服务商预设（全部为 OpenAI 兼容接口），models 元素: { id, vision: 是否支持图片识别 }
var AI_PROVIDERS = [
  { id: 'openai', name: 'OpenAI', base: 'https://api.openai.com/v1', models: [
    { id: 'gpt-4o', vision: true }, { id: 'gpt-4o-mini', vision: true },
    { id: 'gpt-4.1', vision: true }, { id: 'gpt-4.1-mini', vision: true },
  ]},
  { id: 'gemini', name: 'Google Gemini', base: 'https://generativelanguage.googleapis.com/v1beta/openai', models: [
    { id: 'gemini-2.5-pro', vision: true }, { id: 'gemini-2.5-flash', vision: true },
    { id: 'gemini-2.0-flash', vision: true },
  ]},
  { id: 'anthropic', name: 'Anthropic Claude', base: 'https://api.anthropic.com/v1', models: [
    { id: 'claude-sonnet-4-5', vision: true }, { id: 'claude-opus-4-1', vision: true },
    { id: 'claude-3-7-sonnet', vision: true },
  ]},
  { id: 'xai', name: 'xAI (Grok)', base: 'https://api.x.ai/v1', models: [
    { id: 'grok-4', vision: true }, { id: 'grok-4-fast', vision: true }, { id: 'grok-3', vision: true },
  ]},
  { id: 'qwen', name: '通义千问 (阿里云百炼)', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: [
    { id: 'qwen-vl-max', vision: true }, { id: 'qwen-vl-plus', vision: true },
    { id: 'qwen2.5-vl-72b-instruct', vision: true },
  ]},
  { id: 'zhipu', name: '智谱 GLM (BigModel)', base: 'https://open.bigmodel.cn/api/paas/v4', models: [
    { id: 'glm-4v-plus', vision: true }, { id: 'glm-4v-flash', vision: true },
    { id: 'glm-4.5v', vision: true }, { id: 'glm-4.5', vision: false },
  ]},
  { id: 'deepseek', name: 'DeepSeek', base: 'https://api.deepseek.com/v1', models: [
    { id: 'deepseek-chat', vision: false }, { id: 'deepseek-reasoner', vision: false },
  ]},
  { id: 'kimi', name: '月之暗面 Kimi', base: 'https://api.moonshot.cn/v1', models: [
    { id: 'kimi-latest', vision: true }, { id: 'moonshot-v1-8k', vision: true },
  ]},
  { id: 'siliconflow', name: '硅基流动 SiliconFlow', base: 'https://api.siliconflow.cn/v1', models: [
    { id: 'Qwen/Qwen2.5-VL-72B-Instruct', vision: true },
    { id: 'Qwen/Qwen2.5-VL-32B-Instruct', vision: true },
    { id: 'deepseek-ai/deepseek-vl2', vision: true },
  ]},
  { id: 'ark', name: '火山引擎 (豆包)', base: 'https://ark.cn-beijing.volces.com/api/v3', models: [
    { id: 'doubao-seed-1.6-vision', vision: true },
    { id: 'doubao-1.5-vision-pro', vision: true },
  ]},
  { id: 'hunyuan', name: '腾讯混元', base: 'https://api.hunyuan.cloud.tencent.com/v1', models: [
    { id: 'hunyuan-vision', vision: true }, { id: 'hunyuan-lite', vision: true },
  ]},
  { id: 'qianfan', name: '百度千帆', base: 'https://qianfan.baidubce.com/v2', models: [
    { id: 'ernie-4.5-vl-8b', vision: true }, { id: 'ernie-4.5-vl-2b-fp8', vision: true },
  ]},
  { id: 'minimax', name: 'MiniMax', base: 'https://api.minimax.chat/v1', models: [
    { id: 'MiniMax-VL-01', vision: true }, { id: 'MiniMax-M2', vision: true },
  ]},
  { id: 'groq', name: 'Groq', base: 'https://api.groq.com/openai/v1', models: [
    { id: 'llama-3.2-90b-vision-preview', vision: true },
    { id: 'llama-3.2-11b-vision-preview', vision: true },
  ]},
  { id: 'mistral', name: 'Mistral', base: 'https://api.mistral.ai/v1', models: [
    { id: 'pixtral-large-2509', vision: true }, { id: 'pixtral-12b', vision: true },
  ]},
  { id: 'openrouter', name: 'OpenRouter', base: 'https://openrouter.ai/api/v1', models: [
    { id: 'openai/gpt-4o', vision: true }, { id: 'google/gemini-2.5-flash', vision: true },
  ]},
  { id: 'ollama', name: 'Ollama (本地)', base: 'http://localhost:11434/v1', models: [
    { id: 'llama3.2-vision', vision: true }, { id: 'qwen2.5-vl', vision: true },
  ]},
  { id: 'novita', name: 'Novita', base: 'https://api.novita.ai/v3/openai', models: [
    { id: 'google/gemini-2.5-flash', vision: true }, { id: 'meta-llama/llama-3.2-90b-vision', vision: true },
  ]},
  { id: 'zai', name: 'Z.ai (GLM 海外)', base: 'https://api.z.ai/api/paas/v4', models: [
    { id: 'glm-4.5v', vision: true }, { id: 'glm-4v-plus', vision: true },
  ]},
  { id: 'opencode', name: 'opencode (本地服务)', base: 'http://localhost:4096/v1', models: [] },
  { id: 'custom', name: '自定义（OpenAI 兼容）', base: 'https://api.openai.com/v1', models: [] },
];

function aiProviderInfo(pid) {
  return AI_PROVIDERS.find(function (p) { return p.id === pid; }) || AI_PROVIDERS[AI_PROVIDERS.length - 1];
}

function openAddModel(m) {
  fillAddModel(m || null);
  document.getElementById('amEditId').value = m ? m.id : '';
  document.getElementById('amModalTitle').textContent = m ? '编辑模型' : '添加模型';
  document.getElementById('amSubmitBtn').innerHTML = '<i class="ph ph-check"></i> ' + (m ? '保存模型' : '添加模型');
  document.getElementById('addModelModal').classList.remove('hidden');
}

function closeAddModel() {
  document.getElementById('addModelModal').classList.add('hidden');
}

function fillAddModel(m) {
  var psel = document.getElementById('amProvider');
  psel.innerHTML = '';
  AI_PROVIDERS.forEach(function (p) {
    var opt = document.createElement('option');
    opt.value = p.id; opt.textContent = p.name;
    psel.appendChild(opt);
  });
  psel.value = m ? m.provider : AI_PROVIDERS[0].id;
  renderAMPresets(psel.value);

  var preset = document.getElementById('amModelPreset');
  var inPreset = Array.prototype.some.call(preset.options, function (o) { return o.value === (m ? m.model_id : ''); });
  if (m && !inPreset) {
    preset.value = '__custom__';
    document.getElementById('amCustomModelWrap').classList.remove('hidden');
    document.getElementById('amModelId').value = m.model_id;
  } else if (m) {
    preset.value = m.model_id;
    document.getElementById('amCustomModelWrap').classList.add('hidden');
  } else {
    document.getElementById('amCustomModelWrap').classList.add('hidden');
  }

  document.getElementById('amApiKey').value = m ? (m.api_key || '') : '';
  document.getElementById('amBaseUrl').value = m ? (m.endpoint || m.base_url || '') : '';
  document.getElementById('amFullUrl').checked = !!(m && m.endpoint);
  onAMFullUrlChange();
  document.getElementById('amDisplayName').value = m ? (m.display_name || '') : '';
  document.getElementById('amContext').value = m ? (m.context || '128K') : '128K';
  document.getElementById('amAdvanced').classList.add('hidden');
  document.getElementById('amAdvCaret').className = 'ph ph-caret-right';
  document.getElementById('amTestResult').className = 'ai-test-result';
  document.getElementById('amTestResult').innerHTML = '';
}

function changeAMProvider() {
  renderAMPresets(document.getElementById('amProvider').value);
}

function renderAMPresets(pid) {
  var p = aiProviderInfo(pid);
  var sel = document.getElementById('amModelPreset');
  sel.innerHTML = '';
  p.models.forEach(function (m) {
    var opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.id + (m.vision ? '（视觉）' : '（文本模式）');
    sel.appendChild(opt);
  });
  var opt2 = document.createElement('option');
  opt2.value = '__custom__'; opt2.textContent = '使用其他模型';
  sel.appendChild(opt2);
  sel.value = p.models.length ? p.models[0].id : '__custom__';
  onAMPresetChange();
}

function onAMPresetChange() {
  var custom = document.getElementById('amModelPreset').value === '__custom__';
  document.getElementById('amCustomModelWrap').classList.toggle('hidden', !custom);
  if (custom) document.getElementById('amModelId').value = '';
}

function toggleAMAdvanced() {
  var adv = document.getElementById('amAdvanced');
  var show = adv.classList.toggle('hidden');
  document.getElementById('amAdvCaret').className = show ? 'ph ph-caret-right' : 'ph ph-caret-down';
}

function onAMFullUrlChange() {
  var full = document.getElementById('amFullUrl').checked;
  var input = document.getElementById('amBaseUrl');
  var hint = document.getElementById('amUrlHint');
  if (full) {
    input.placeholder = 'http://localhost:4096/v1/chat/completions';
    hint.textContent = '将直接使用该完整地址发起请求（不再自动拼接 /chat/completions）';
  } else {
    input.placeholder = 'https://api.openai.com/v1';
    hint.textContent = '关闭：填基础地址，自动拼接 /chat/completions；打开：直接填完整请求地址，如 http://localhost:4096/v1/chat/completions';
  }
}

function toggleAMKeyVisible() {
  var input = document.getElementById('amApiKey');
  var icon = document.querySelector('#amKeyToggle i');
  if (input.type === 'password') {
    input.type = 'text';
    icon.className = 'ph ph-eye-slash';
  } else {
    input.type = 'password';
    icon.className = 'ph ph-eye';
  }
}

// 提交添加/编辑模型：先测试连接，成功后保存到数据库，再刷新当前页面的模型列表/选择框
async function submitAddModel() {
  var editId = document.getElementById('amEditId').value;
  var provider = document.getElementById('amProvider').value;
  var preset = document.getElementById('amModelPreset').value;
  var modelId = preset === '__custom__' ? document.getElementById('amModelId').value.trim() : preset;
  var apiKey = document.getElementById('amApiKey').value.trim();
  var customUrl = document.getElementById('amBaseUrl').value.trim();
  var fullUrl = document.getElementById('amFullUrl').checked;
  var displayName = document.getElementById('amDisplayName').value.trim();
  var context = document.getElementById('amContext').value;

  if (!modelId) { showToast('请填写模型 ID', 'error'); return; }

  // 视觉能力判断：预置模型按标记，自定义默认支持；非视觉模型可通过文本/文件方式导入
  var vision = true;
  if (preset !== '__custom__') {
    var pCheck = aiProviderInfo(provider);
    var presetObj = pCheck.models.find(function (x) { return x.id === preset; });
    vision = presetObj ? presetObj.vision : true;
  }

  var p = aiProviderInfo(provider);
  var endpoint = '';                 // 完整请求地址（打开"完整 URL"开关时）
  var baseUrl = p.base;              // 基础地址（关闭开关时）
  if (fullUrl) {
    endpoint = customUrl;
    if (!endpoint) { showToast('请填写完整的请求地址，如 http://localhost:4096/v1/chat/completions', 'error'); return; }
    baseUrl = '';
  } else if (customUrl) {
    baseUrl = customUrl;
  }

  var btn = document.getElementById('amSubmitBtn');
  var box = document.getElementById('amTestResult');
  btn.disabled = true;
  btn.innerHTML = '<i class="ph ph-circle-notch" style="animation: spin 1s linear infinite;"></i> 验证连接中…';
  box.className = 'ai-test-result';
  box.innerHTML = '<span class="ai-test-loading"><i class="ph ph-circle-notch" style="animation: spin 1s linear infinite;"></i> 正在验证连接…</span>';

  try {
    var res = await VOCAB_API.post('/api/ai/test/', {
      api_key: apiKey,
      base_url: baseUrl,
      endpoint: endpoint,
      model: modelId,
    });
    if (!res.success) {
      box.className = 'ai-test-result ai-test-fail';
      var hint = res.key_invalid ? '（密钥无效，请检查后重试）' : (res.model_invalid ? '（模型或接口地址错误）' : '');
      box.innerHTML = '<i class="ph ph-x-circle"></i> ' + (res.error || '验证失败') + hint;
      return;
    }
    var saveRes = await VOCAB_API.post('/api/ai-models/', {
      id: editId || undefined,
      provider: provider,
      model_id: modelId,
      display_name: displayName,
      base_url: baseUrl,
      endpoint: endpoint,
      api_key: apiKey,
      context: context,
      vision: vision,
      enabled: true,
    });
    if (!saveRes.success) {
      box.className = 'ai-test-result ai-test-fail';
      box.innerHTML = '<i class="ph ph-x-circle"></i> ' + (saveRes.error || '保存失败');
      return;
    }
    box.className = 'ai-test-result ai-test-ok';
    box.innerHTML = '<i class="ph ph-check-circle"></i> 连接成功，模型已' + (editId ? '更新' : '添加');
    // 刷新当前页面：设置页刷新模型列表，AI 导入页刷新选择框等
    if (typeof window.aiModelModalOnSaved === 'function') {
      try { await window.aiModelModalOnSaved(); } catch (e) {}
    }
    setTimeout(function () { closeAddModel(); }, 700);
  } catch (e) {
    box.className = 'ai-test-result ai-test-fail';
    box.innerHTML = '<i class="ph ph-x-circle"></i> ' + ((e && e.error) || '验证请求失败');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="ph ph-check"></i> ' + (editId ? '保存模型' : '添加模型');
  }
}

// ESC 关闭弹窗
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && !document.getElementById('addModelModal').classList.contains('hidden')) {
    closeAddModel();
  }
});
