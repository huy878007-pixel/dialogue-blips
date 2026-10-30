
// ---------------------------------------------------------------- 参数定义
const DEFAULTS = {
  WaveType:2, MasterVolume:0.5, AttackTime:0, SustainTime:0.3, SustainPunch:0,
  DecayTime:0.4, CompressionAmount:0.3, MinFrequency:0, Slide:0, DeltaSlide:0,
  VibratoDepth:0, VibratoSpeed:0, Overtones:0, OvertoneFalloff:0,
  ChangeRepeat:0, ChangeAmount:0, ChangeSpeed:1, ChangeAmount2:0, ChangeSpeed2:0,
  SquareDuty:0, DutySweep:0, RepeatSpeed:0, FlangerOffset:0, FlangerSweep:0,
  LpFilterCutoff:1, LpFilterCutoffSweep:0, LpFilterResonance:0,
  HpFilterCutoff:0, HpFilterCutoffSweep:0, BitCrush:0, BitCrushSweep:0,
};

const WAVES = ["方波 Square","锯齿 Saw","正弦 Sine","白噪音 Noise","三角 Triangle",
  "粉噪音 Pink Noise","Tan 失真","哨音 Whistle","Breaker 碎波","Bitnoise 1-bit",
  "Combo 轮换","Buzz 蜂鸣"];

// 主面板露出来的参数
const MAIN_GROUPS = [
  ["包络", [
    ["AttackTime","起音",0,1,0.001],
    ["SustainTime","持续",0,1,0.001],
    ["DecayTime","衰减",0,1,0.001],
    ["SustainPunch","冲击",0,1,0.01],
  ]],
  ["音高", [
    ["Slide","下滑",-1,1,0.01],
    ["VibratoDepth","颤音幅度",0,1,0.01],
    ["VibratoSpeed","颤音速度",0,1,0.01],
  ]],
  ["音色", [
    ["Overtones","泛音数",0,1,0.01],
    ["OvertoneFalloff","泛音衰减",0,1,0.01],
    ["SquareDuty","方波占空",0,1,0.01],
    ["CompressionAmount","压缩",0,1,0.01],
  ]],
  ["滤波", [
    ["LpFilterCutoff","低通",0,1,0.01],
    ["LpFilterResonance","低通共振",0,1,0.01],
    ["HpFilterCutoff","高通",0,1,0.01],
  ]],
  ["脏化", [
    ["BitCrush","降位",0,1,0.01],
  ]],
];

const ADV_GROUPS = [
  ["进阶调制", [
    ["DeltaSlide","下滑加速",-1,1,0.01],
    ["DutySweep","占空扫描",-1,1,0.01],
    ["ChangeAmount","变调幅度",-1,1,0.01],
    ["ChangeSpeed","变调速度",0,1,0.01],
    ["ChangeRepeat","变调重复",0,1,0.01],
    ["ChangeAmount2","变调幅度2",-1,1,0.01],
    ["ChangeSpeed2","变调速度2",0,1,0.01],
    ["RepeatSpeed","重复速度",0,1,0.01],
    ["FlangerOffset","镶边偏移",-1,1,0.01],
    ["FlangerSweep","镶边扫描",-1,1,0.01],
    ["MinFrequency","最低频率",0,1,0.01],
    ["LpFilterCutoffSweep","低通扫描",-1,1,0.01],
    ["HpFilterCutoffSweep","高通扫描",-1,1,0.01],
    ["BitCrushSweep","降位扫描",-1,1,0.01],
  ]],
];

// ---------------------------------------------------------------- 预设
const PARAM_KEYS = Object.keys(DEFAULTS);

// 只有 PARAM_KEYS 里的键会发给引擎，避免层参数（gain/delay）混进合成参数表
function mk(hz, o, gain, delay){
  return {hz, gain: gain === undefined ? 1 : gain, delay: delay || 0, mute:false,
          p:Object.assign({}, DEFAULTS, o || {})};
}

function makePresets(){ return {
  "男 · 粗粝": [ mk(105, {WaveType:1, LpFilterCutoff:0.62, AttackTime:0.03, SustainTime:0.12,
      DecayTime:0.22, Slide:-0.08, VibratoDepth:0.28, VibratoSpeed:0.55, Overtones:0.20,
      OvertoneFalloff:0.55, CompressionAmount:0.25, BitCrush:0.12}) ],
  "男 · 普通": [ mk(145, {WaveType:4, LpFilterCutoff:0.55, AttackTime:0.03, SustainTime:0.07,
      DecayTime:0.16, Slide:-0.12}) ],
  "男 · 老成": [ mk(122, {WaveType:2, LpFilterCutoff:0.45, AttackTime:0.06, SustainTime:0.10,
      DecayTime:0.20, Slide:-0.06, Overtones:0.08}) ],
  "女 · 年轻": [ mk(1056, {WaveType:4, LpFilterCutoff:0.42, AttackTime:0.05, SustainTime:0.07,
      DecayTime:0.18, Slide:-0.10}) ],
  "女 · 成熟": [ mk(620, {WaveType:4, LpFilterCutoff:0.55, AttackTime:0.04, SustainTime:0.06,
      DecayTime:0.16, Slide:-0.16, VibratoDepth:0.06, VibratoSpeed:0.35}) ],
  "中性":      [ mk(420, {WaveType:2, LpFilterCutoff:0.60, AttackTime:0.04, SustainTime:0.05,
      DecayTime:0.15, Slide:-0.20}) ],
  "女年轻 + 粉噪气声": [
    mk(1056, {WaveType:4, LpFilterCutoff:0.42, AttackTime:0.05, SustainTime:0.07,
      DecayTime:0.18, Slide:-0.10}, 1.0),
    mk(1056, {WaveType:5, LpFilterCutoff:0.50, AttackTime:0.02, SustainTime:0.03,
      DecayTime:0.10, Slide:0}, 0.22),
  ],
  "男粗粝 + bitnoise 毛刺": [
    mk(105, {WaveType:1, LpFilterCutoff:0.62, AttackTime:0.03, SustainTime:0.12,
      DecayTime:0.22, Slide:-0.08, VibratoDepth:0.28, VibratoSpeed:0.55, Overtones:0.20,
      OvertoneFalloff:0.55, CompressionAmount:0.25, BitCrush:0.12}, 1.0),
    mk(320, {WaveType:9, LpFilterCutoff:0.40, AttackTime:0.01, SustainTime:0.02,
      DecayTime:0.06, Slide:0}, 0.30, 2),
  ],
  "三角波 + 高八度叠层": [
    mk(1056, {WaveType:4, LpFilterCutoff:0.42, AttackTime:0.05, SustainTime:0.07,
      DecayTime:0.18, Slide:-0.10}, 1.0),
    mk(2112, {WaveType:4, LpFilterCutoff:0.55, AttackTime:0.04, SustainTime:0.04,
      DecayTime:0.12, Slide:-0.14}, 0.25),
  ],
  "粉噪主 + 三角体": [
    mk(900, {WaveType:5, LpFilterCutoff:0.55, AttackTime:0.02, SustainTime:0.05,
      DecayTime:0.14, Slide:-0.10}, 1.0),
    mk(1050, {WaveType:4, LpFilterCutoff:0.42, AttackTime:0.05, SustainTime:0.07,
      DecayTime:0.18, Slide:-0.10}, 0.65),
  ],
}; }
let PRESETS = makePresets();

// ---------------------------------------------------------------- 状态
let layers = JSON.parse(JSON.stringify(PRESETS["女 · 年轻"]));
let audio = new Audio();
const actx = new (window.AudioContext || window.webkitAudioContext)();
let timer = null;
let requestId = 0, downloadUrl = null, playbackUrl = null;

const $ = s => document.querySelector(s);

function applyPreset(name){
  layers = JSON.parse(JSON.stringify(PRESETS[name]));
  renderLayers(); schedule();
}

// ---------------------------------------------------------------- 渲染 UI
function renderPresets(){
  const host = $("#presets");
  host.innerHTML = "";
  for (const name in PRESETS){
    const b = document.createElement("button");
    b.textContent = name;
    b.onclick = ()=>applyPreset(name);
    host.appendChild(b);
  }
}

function slider(label, key, min, max, step, val, oninput){
  const row = document.createElement("div");
  row.className = "row";
  const id = "s_" + key + "_" + Math.random().toString(36).slice(2,7);
  row.innerHTML = `<label for="${id}">${label}</label>
    <input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${val}">
    <span class="val"></span>`;
  const inp = row.querySelector("input");
  const out = row.querySelector(".val");
  const show = v => parseFloat(v).toFixed(step >= 0.1 ? 1 : (step >= 0.01 ? 2 : 3));
  out.textContent = show(val);
  inp.oninput = ()=>{ out.textContent = show(inp.value); oninput(parseFloat(inp.value)); };
  return row;
}

function renderLayers(){
  const host = $("#layers");
  host.innerHTML = "";
  layers.forEach((L, i)=>{
    const card = document.createElement("div");
    card.className = "layer open" + (L.mute ? " off" : "");

    const head = document.createElement("div");
    head.className = "lhead";
    head.innerHTML = `<span class="dot"></span>
      <span class="name">第 ${i+1} 层 · ${WAVES[L.p.WaveType|0]}</span>
      <span class="sum">${Math.round(L.hz)} Hz · 音量 ${L.gain.toFixed(2)}</span>`;
    head.onclick = e => { if (e.target.tagName !== "BUTTON") card.classList.toggle("open"); };

    const body = document.createElement("div");
    body.className = "lbody";

    // 波形
    const wrow = document.createElement("div");
    wrow.className = "row";
    wrow.innerHTML = `<label>波形</label>`;
    const sel = document.createElement("select");
    WAVES.forEach((w, k)=>{ const o = document.createElement("option"); o.value=k; o.textContent=`${k} · ${w}`; sel.appendChild(o); });
    sel.value = L.p.WaveType|0;
    sel.onchange = ()=>{ L.p.WaveType = parseFloat(sel.value); head.querySelector(".name").textContent = `第 ${i+1} 层 · ${WAVES[L.p.WaveType|0]}`; schedule(); };
    wrow.appendChild(sel);
    body.appendChild(wrow);

    // 音高 / 音量 / 延迟
    body.appendChild(slider("音高 Hz", "hz", 40, 3000, 1, L.hz, v=>{ L.hz = v;
      head.querySelector(".sum").textContent = `${Math.round(L.hz)} Hz · 音量 ${L.gain.toFixed(2)}`; schedule(); }));
    body.appendChild(slider("层音量", "gain", 0, 1.5, 0.01, L.gain, v=>{ L.gain = v;
      head.querySelector(".sum").textContent = `${Math.round(L.hz)} Hz · 音量 ${L.gain.toFixed(2)}`; schedule(); }));
    body.appendChild(slider("延迟 ms", "delay", 0, 120, 1, L.delay, v=>{ L.delay = v; schedule(); }));

    // 主分组
    MAIN_GROUPS.forEach(([title, params])=>{
      const sub = document.createElement("div");
      sub.style.cssText = "margin:10px 0 4px;font-size:11px;color:#6f7a91;letter-spacing:.4px";
      sub.textContent = title;
      body.appendChild(sub);
      params.forEach(([k, label, mn, mx, st])=>{
        body.appendChild(slider(label, k, mn, mx, st, L.p[k], v=>{ L.p[k] = v; schedule(); }));
      });
    });

    // 进阶
    const advToggle = document.createElement("span");
    advToggle.className = "adv-toggle";
    advToggle.textContent = "▸ 进阶参数（变调 / 镶边 / 扫描）";
    const adv = document.createElement("div");
    adv.className = "adv";
    advToggle.onclick = ()=>{ adv.classList.toggle("open");
      advToggle.textContent = (adv.classList.contains("open") ? "▾ " : "▸ ") + "进阶参数（变调 / 镶边 / 扫描）"; };
    body.appendChild(advToggle);
    ADV_GROUPS.forEach(([title, params])=>{
      params.forEach(([k, label, mn, mx, st])=>{
        adv.appendChild(slider(label, k, mn, mx, st, L.p[k], v=>{ L.p[k] = v; schedule(); }));
      });
    });
    body.appendChild(adv);

    // 层操作
    const ops = document.createElement("div");
    ops.style.cssText = "display:flex;gap:6px;margin-top:10px";
    const bMute = document.createElement("button");
    bMute.className = "ghost";
    bMute.textContent = L.mute ? "启用" : "静音";
    bMute.onclick = ()=>{ L.mute = !L.mute; renderLayers(); schedule(); };
    const bDup = document.createElement("button");
    bDup.className = "ghost"; bDup.textContent = "复制";
    bDup.disabled = layers.length >= 8;
    bDup.onclick = ()=>{ if (layers.length >= 8) return; layers.splice(i+1, 0, JSON.parse(JSON.stringify(L))); renderLayers(); schedule(); };
    const bDel = document.createElement("button");
    bDel.className = "ghost danger"; bDel.textContent = "删除";
    bDel.onclick = ()=>{ if (layers.length === 1) return; layers.splice(i,1); renderLayers(); schedule(); };
    ops.append(bMute, bDup, bDel);
    body.appendChild(ops);

    card.append(head, body);
    host.appendChild(card);
  });
  $("#addLayer").disabled = layers.length >= 8;
}

// ---------------------------------------------------------------- 与引擎通信
function buildForm(){
  const f = new URLSearchParams();
  layers.forEach((L, i)=>{
    f.set(`layer${i}.mute`, L.mute ? 1 : 0);
    f.set(`layer${i}.gain`, L.gain);
    f.set(`layer${i}.delay`, L.delay);
    f.set(`layer${i}.hz`, L.hz);
    if (L.mute) return;
    // 只发合成参数，gain/delay 已单独处理，不会串味
    for (const k of PARAM_KEYS) f.set(`layer${i}.${k}`, L.p[k]);
  });
  return f;
}

async function fetchWav(path, form){
  const res = await fetch(path, {method:"POST", body:form});
  if (!res.ok) throw new Error("HTTP " + res.status + ": " + await res.text());
  return await res.arrayBuffer();
}

function playUrl(url){
  audio.pause();
  if (playbackUrl && playbackUrl !== downloadUrl) URL.revokeObjectURL(playbackUrl);
  playbackUrl = url;
  audio = new Audio(url);
  audio.onended = ()=>{
    if (playbackUrl === url){
      playbackUrl = null;
      if (url !== downloadUrl) URL.revokeObjectURL(url);
    }
  };
  return audio.play();
}

function showMetrics(buf){
  drawWave(buf);
  $("#dur").textContent = (buf.duration*1000).toFixed(0) + " ms";
  let pk = 0; const data = buf.getChannelData(0);
  for (const sample of data) pk = Math.max(pk, Math.abs(sample));
  $("#peak").textContent = "峰值 " + (pk*100).toFixed(0) + "%";
}

function drawWave(buf){
  const c = $("#wave"), ctx = c.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  c.width = c.clientWidth * dpr; c.height = c.clientHeight * dpr;
  ctx.scale(dpr, dpr);
  const w = c.clientWidth, h = c.clientHeight;
  ctx.clearRect(0,0,w,h);
  ctx.strokeStyle = "#2c3346"; ctx.beginPath();
  ctx.moveTo(0, h/2); ctx.lineTo(w, h/2); ctx.stroke();
  const data = buf.getChannelData(0);
  const step = Math.max(1, Math.floor(data.length / w));
  ctx.strokeStyle = "#5ee0c0"; ctx.lineWidth = 1; ctx.beginPath();
  for (let x = 0; x < w; x++){
    let mn = 1, mx = -1;
    for (let i = 0; i < step; i++){
      const v = data[x*step + i] || 0;
      if (v < mn) mn = v; if (v > mx) mx = v;
    }
    ctx.moveTo(x, h/2 - mx*h/2*0.92);
    ctx.lineTo(x, h/2 - mn*h/2*0.92);
  }
  ctx.stroke();
}

async function refresh(play){
  clearTimeout(timer);
  const id = ++requestId;
  try{
    $("#status").textContent = "生成中…";
    const ab = await fetchWav("/api/voice", buildForm());
    const buf = await actx.decodeAudioData(ab.slice(0));
    if (id !== requestId) return;
    showMetrics(buf);

    const url = URL.createObjectURL(new Blob([ab], {type:"audio/wav"}));
    if (downloadUrl && downloadUrl !== playbackUrl) URL.revokeObjectURL(downloadUrl);
    downloadUrl = url;
    $("#dlSingle").href = url;
    $("#dlSingle").download = "blip.wav";
    if (play){
      await playUrl(url);
    }
    if (id !== requestId) return;
    $("#status").textContent = "就绪 · " + layers.length + " 层";
  }catch(e){
    if (id === requestId) $("#status").textContent = "错误：" + e.message;
  }
}

function schedule(playAnyway){
  clearTimeout(timer);
  ++requestId;
  timer = setTimeout(()=>refresh(playAnyway !== false && $("#autoplay").checked), 160);
}

async function playSentence(){
  clearTimeout(timer);
  const id = ++requestId;
  try{
    $("#status").textContent = "生成句子…";
    const f = buildForm();
    f.set("text", $("#text").value);
    f.set("interval", $("#interval").value);
    f.set("throttle", $("#throttle").value);
    f.set("jitter", $("#jitter").value);
    const ab = await fetchWav("/api/sentence", f);
    const buf = await actx.decodeAudioData(ab.slice(0));
    if (id !== requestId) return;
    const url = URL.createObjectURL(new Blob([ab], {type:"audio/wav"}));
    showMetrics(buf);
    await playUrl(url);
    if (id !== requestId) return;
    $("#status").textContent = "就绪 · 句子";
  }catch(e){ if (id === requestId) $("#status").textContent = "错误：" + e.message; }
}

// ---------------------------------------------------------------- 绑定
$("#addLayer").onclick = ()=>{
  if (layers.length >= 8) return;
  layers.push({hz:1050, gain:0.5, delay:0, mute:false, p:Object.assign({}, DEFAULTS, {WaveType:5})});
  renderLayers(); schedule();
};
$("#playSingle").onclick = ()=>refresh(true);
$("#playSentence").onclick = playSentence;
["interval","throttle","jitter"].forEach(id=>{
  const el = $("#"+id), out = $("#"+id+"V");
  el.oninput = ()=>{ out.textContent = el.value + (id === "jitter" ? "%" : ""); };
});
$("#intervalV").textContent = "30";
$("#throttleV").textContent = "70";
$("#jitterV").textContent = "6%";

async function init(){
  try{
    const response = await fetch("/api/meta");
    if (!response.ok) throw new Error("HTTP " + response.status);
    const meta = await response.json();
    Object.assign(DEFAULTS, meta.voiceBase);
    PRESETS = makePresets();
    // The generator is the source of truth for the six approved voices.
    Object.keys(PRESETS).slice(0,6).forEach((name,i)=>{
      const voice = meta.voices[i];
      PRESETS[name] = [mk(voice.hz, voice.p)];
    });
    layers = JSON.parse(JSON.stringify(PRESETS["女 · 年轻"]));
    renderPresets(); renderLayers();
    await refresh(false);
  }catch(e){ $("#status").textContent = "错误：" + e.message; }
}
init();
