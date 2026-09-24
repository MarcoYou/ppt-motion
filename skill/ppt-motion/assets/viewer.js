/* PDF geometry stays intact. Temporary animation wrappers settle to the source. */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const IDENTITY = [1, 0, 0, 1, 0, 0];
  const $ = id => document.getElementById(id);
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const cache = new Map();
  const ui = Object.fromEntries(['stage', 'workbench', 'reference', 'caption', 'notice', 'inspector', 'previous', 'next', 'replay', 'motion', 'emphasis', 'inspect', 'compare', 'fullscreen', 'slide-select'].map(id => [id, $(id)]));
  let deck, current = 0, serial = 0, generation = 0, svg = null;
  let effects = [], active = [], motion = true, emphasis = true, inspect = false, compare = false, selected = null;
  let noticeTimer;
  try { motion = localStorage.getItem('ppt-motion-effects') !== 'off'; } catch {}

  function node(tag, attributes = {}) {
    const value = document.createElementNS(NS, tag);
    for (const [key, attribute] of Object.entries(attributes)) value.setAttribute(key, String(attribute));
    return value;
  }
  function numbers(value) { return String(value || '').trim().split(/[\s,]+/).map(Number); }
  function matrix(value) {
    const values = numbers(value);
    if (values.length !== 6 || !values.every(Number.isFinite)) throw new Error('data-parent-matrix가 없거나 올바르지 않습니다.');
    return values;
  }
  function inverse(m) {
    const d = m[0]*m[3]-m[1]*m[2];
    if (Math.abs(d) < 1e-12) throw new Error('역변환할 수 없는 요소입니다.');
    return [m[3]/d, -m[1]/d, -m[2]/d, m[0]/d, (m[2]*m[5]-m[3]*m[4])/d, (m[1]*m[4]-m[0]*m[5])/d];
  }
  function point(m, x, y) { return [m[0]*x+m[2]*y+m[4], m[1]*x+m[3]*y+m[5]]; }
  function boxInParent(box, parent, padding = 0) {
    const inv = inverse(parent), [x1,y1,x2,y2] = box;
    const points = [[x1-padding,y1-padding],[x2+padding,y1-padding],[x1-padding,y2+padding],[x2+padding,y2+padding]].map(([x,y]) => point(inv,x,y));
    return [Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))];
  }
  function transformFrame(parent, origin, scaleX, scaleY) {
    // This is P^-1 B P in factored form: bar ancestors are axis aligned;
    // the isotropic star scale commutes with every invertible parent matrix.
    // Matching transform functions also interpolate correctly at exact scale 0,
    // unlike singular matrix() keyframes that browsers may animate discretely.
    const local = point(inverse(parent),origin[0],origin[1]);
    return {transform:`translate(${local[0]}px,${local[1]}px) scale(${scaleX},${scaleY}) translate(${-local[0]}px,${-local[1]}px)`};
  }
  function wrap(source) {
    const wrapper = node('g');
    source.replaceWith(wrapper);
    wrapper.append(source);
    return wrapper;
  }
  function radialPath(center, radius, startAngle, sweepAngle) {
    // A radius/2 arc with radius-wide stroke reveals a sector of the full disk.
    // Two or more arcs also handle a complete circle without a degenerate A command.
    const r = radius / 2;
    const position = angle => {
      const radians = angle * Math.PI / 180;
      return [center[0] + r * Math.cos(radians), center[1] + r * Math.sin(radians)];
    };
    const parts = Math.ceil(Math.abs(sweepAngle) / 180);
    let d = `M ${position(startAngle).join(' ')}`;
    for (let i = 1; i <= parts; i++) {
      d += ` A ${r} ${r} 0 0 ${sweepAngle > 0 ? 1 : 0} ${position(startAngle + sweepAngle * i / parts).join(' ')}`;
    }
    return d;
  }
  function radialTrack(source, color) {
    // Clone geometry in the same clipped parent; pattern-filled PDF rectangles
    // still inherit their exact sector clip. Never recolor raster images or text.
    if (!color || !['path','rect','circle','ellipse','polygon'].includes(source.localName) || getComputedStyle(source).fill === 'none') return null;
    const track = source.cloneNode(false);
    for (const attr of [...track.attributes]) if (attr.name.startsWith('data-') || attr.name === 'id') track.removeAttribute(attr.name);
    track.style.fill = color;
    track.style.stroke = 'none';
    track.style.pointerEvents = 'none';
    track.setAttribute('aria-hidden','true');
    track.setAttribute('data-radial-track','true');
    return track;
  }
  function announce(message, timeout = 5000) {
    clearTimeout(noticeTimer);
    ui.notice.textContent = message;
    ui.notice.hidden = !message;
    if (message && timeout) noticeTimer = setTimeout(() => { ui.notice.hidden = true; }, timeout);
  }
  function canPlay() { return motion && !media.matches && !document.hidden; }
  function stop() {
    for (const animation of active) { animation.onfinish = null; animation.cancel(); }
    active = [];
    for (const effect of effects) effect.settle?.();
  }
  function updateControls() {
    ui.previous.disabled = !deck || current <= 0;
    ui.next.disabled = !deck || current >= deck.slides.length-1;
    ui.motion.textContent = media.matches ? '효과 끔 · 접근성' : motion ? '효과 켬' : '효과 끔';
    ui.motion.setAttribute('aria-pressed', String(motion && !media.matches));
    ui.motion.disabled = media.matches;
    ui.replay.disabled = !canPlay() || !effects.some(item => emphasis || !item.isEmphasis);
    ui.emphasis.textContent = emphasis ? '강조 켬' : '강조 끔';
    ui.emphasis.setAttribute('aria-pressed', String(emphasis));
    ui.emphasis.disabled = !svg?.querySelector('[data-emphasis]');
    ui.inspect.setAttribute('aria-pressed', String(inspect));
    ui.compare.setAttribute('aria-pressed', String(compare));
    ui.fullscreen.textContent = document.fullscreenElement ? '전체화면 종료' : '전체화면';
  }
  function applyEmphasis() {
    for (const element of svg?.querySelectorAll('[data-emphasis]') || []) element.dataset.hidden = String(!emphasis);
  }
  function prepare(root) {
    const identifier = ++serial;
    let definitions = [...root.children].find(child => child.localName === 'defs');
    if (!definitions) { definitions = node('defs'); root.prepend(definitions); }
    const warnings = [];
    for (const source of [...root.querySelectorAll('[data-motion]')]) {
      const kind = source.dataset.motion;
      const duration = Math.max(1, Number(source.dataset.duration) || 750);
      const delay = Math.max(0, Number(source.dataset.delay) || 0);
      const isEmphasis = !!source.closest('[data-emphasis]');
      const effect = {kind, duration, delay, isEmphasis, target:source};
      try {
        if (['bar-x','bar-y','star','line','wipe','radial'].includes(kind)) {
          const parent = source.dataset.parentMatrix ? matrix(source.dataset.parentMatrix) : isEmphasis ? IDENTITY : matrix('');
          const box = numbers(source.dataset.bbox);
          if (box.length !== 4 || !box.every(Number.isFinite)) {
            // Generated emphasis paths may use their identity-space native bounds.
            if (!isEmphasis) throw new Error('요소의 페이지 좌표가 없습니다.');
            const rect = source.getBBox();
            box.splice(0,box.length,rect.x,rect.y,rect.x+rect.width,rect.y+rect.height);
          }
          if (['bar-x','bar-y','wipe'].includes(kind) && (Math.abs(parent[1])>1e-9 || Math.abs(parent[2])>1e-9)) throw new Error('회전·기울어진 부모 좌표에서는 이 효과를 지원하지 않습니다.');
          // Each wrapper lives in its source parent's coordinates, never in page coordinates.
          if (kind === 'bar-x' || kind === 'bar-y' || kind === 'star') {
            const origin = source.dataset.origin ? numbers(source.dataset.origin) : kind === 'star' ? [(box[0]+box[2])/2,(box[1]+box[3])/2] : null;
            if (!origin || origin.length !== 2 || !origin.every(Number.isFinite)) throw new Error('막대의 기준점 data-origin이 필요합니다.');
            const frames = kind === 'star'
              ? [{...transformFrame(parent,origin,1,1),offset:0},{...transformFrame(parent,origin,1.2,1.2),offset:.45},{...transformFrame(parent,origin,1,1),offset:1}]
              : [transformFrame(parent,origin,kind==='bar-x'?0:1,kind==='bar-y'?0:1),transformFrame(parent,origin,1,1)];
            effect.target = wrap(source);
            effect.target.style.transformOrigin = '0px 0px';
            effect.target.style.transformBox = 'view-box';
            effect.frames = frames;
          } else if (kind === 'radial') {
            const center = numbers(source.dataset.center), radius = Number(source.dataset.radius);
            const startAngle = Number(source.dataset.startAngle ?? -90), sweepAngle = Number(source.dataset.sweepAngle ?? 360);
            if (center.length !== 2 || !center.every(Number.isFinite) || !Number.isFinite(radius) || radius <= 0 || !Number.isFinite(startAngle) || !Number.isFinite(sweepAngle) || !sweepAngle || Math.abs(sweepAngle) > 360) throw new Error('원형 채우기의 중심·반경·각도가 올바르지 않습니다.');
            const trackColor = source.dataset.trackColor;
            if (trackColor && !/^#[0-9a-f]{6}$/i.test(trackColor)) throw new Error('원형 트랙 색상이 올바르지 않습니다.');
            const [x1,y1,x2,y2] = boxInParent(box,parent,2);
            const id = `pm-${identifier}-radial-${effects.length}`;
            const mask = node('mask',{id,maskUnits:'userSpaceOnUse',maskContentUnits:'userSpaceOnUse',x:x1,y:y1,width:x2-x1,height:y2-y1});
            // Keep mask geometry in page space even through scaled/reflected parents.
            const coordinates = node('g',{transform:`matrix(${inverse(parent).join(' ')})`});
            const trace = node('path',{d:radialPath(center,radius,startAngle,sweepAngle),fill:'none',stroke:'#fff','stroke-width':radius,'stroke-linecap':'butt'});
            coordinates.append(trace); mask.append(coordinates); definitions.append(mask);
            const length = trace.getTotalLength();
            trace.style.strokeDasharray = `${length} ${length}`;
            trace.style.strokeDashoffset = '0';
            const track = radialTrack(source,trackColor);
            const wrapper = wrap(source);
            effect.target = trace;
            effect.begin = () => {
              if (track) wrapper.before(track);
              wrapper.setAttribute('mask',`url(#${id})`);
            };
            effect.settle = () => { wrapper.removeAttribute('mask'); track?.remove(); };
            effect.frames = [{strokeDashoffset:String(length)},{strokeDashoffset:'0'}];
          } else if (kind === 'line') {
            if (typeof source.getTotalLength !== 'function') throw new Error('선 효과는 길이를 계산할 수 있는 SVG 도형에만 적용됩니다.');
            const length = source.getTotalLength();
            if (!(length>0)) throw new Error('경로 길이가 0입니다.');
            const [x1,y1,x2,y2] = boxInParent(box,parent,8);
            const id = `pm-${identifier}-trace-${effects.length}`;
            const mask = node('mask',{id,maskUnits:'userSpaceOnUse',maskContentUnits:'userSpaceOnUse',x:x1,y:y1,width:x2-x1,height:y2-y1});
            const trace = source.cloneNode(false);
            const computed = getComputedStyle(source);
            for (const attribute of [...trace.attributes]) if (attribute.name.startsWith('data-') || ['id','mask','clip-path','filter'].includes(attribute.name)) trace.removeAttribute(attribute.name);
            trace.style.fill = 'none';
            trace.style.stroke = '#fff';
            trace.style.strokeWidth = String((parseFloat(computed.strokeWidth)||1)+3);
            trace.style.strokeOpacity = '1';
            trace.style.opacity = '1';
            trace.style.strokeLinecap = 'round';
            trace.style.strokeLinejoin = 'round';
            trace.style.strokeDasharray = `${length} ${length}`;
            trace.style.strokeDashoffset = '0';
            mask.append(trace); definitions.append(mask);
            const wrapper = wrap(source);
            effect.target = trace;
            effect.begin = () => wrapper.setAttribute('mask',`url(#${id})`);
            effect.settle = () => wrapper.removeAttribute('mask');
            effect.frames = [{strokeDashoffset:String(length)},{strokeDashoffset:'0'}];
          } else {
            const id = `pm-${identifier}-wipe-${effects.length}`;
            const [x1,y1,x2,y2] = boxInParent(box,parent,1);
            const clip = node('clipPath',{id,clipPathUnits:'userSpaceOnUse'});
            const rect = node('rect',{x:x1,y:y1,width:x2-x1,height:y2-y1});
            clip.append(rect); definitions.append(clip);
            const wrapper = wrap(source);
            const startX = parent[0] < 0 ? x2 : x1;
            effect.target = rect;
            effect.begin = () => wrapper.setAttribute('clip-path',`url(#${id})`);
            effect.settle = () => wrapper.removeAttribute('clip-path');
            effect.frames = [{x:`${startX}px`,width:'0px'},{x:`${x1}px`,width:`${x2-x1}px`}];
          }
        } else if (kind === 'fade' || kind === 'tile') {
          const opacity = Number(getComputedStyle(source).opacity);
          effect.frames = [{opacity:0},{opacity:Number.isFinite(opacity)?opacity:1}];
        } else throw new Error(`지원하지 않는 효과: ${kind}`);
        effects.push(effect);
      } catch (error) {
        source.dataset.motionError = error.message;
        warnings.push(`${source.dataset.leaf || kind}: ${error.message}`);
      }
    }
    root.dataset.motionCount = String(effects.length);
    if (warnings.length) announce(`${warnings.length}개 효과를 건너뛰었습니다. ${warnings[0]}`,0);
  }
  function play() {
    stop();
    updateControls();
    if (!canPlay()) return;
    for (const effect of effects) {
      if (effect.isEmphasis && !emphasis) continue;
      effect.begin?.();
      try {
        const animation = effect.target.animate(effect.frames, {duration:effect.duration,delay:effect.delay,fill:'both',easing:['line','radial'].includes(effect.kind)?'linear':'cubic-bezier(.22,.61,.36,1)'});
        active.push(animation);
        animation.onfinish = () => {
          effect.settle?.();
          animation.cancel();
          active = active.filter(item=>item!==animation);
        };
      } catch (error) { effect.settle?.(); announce(`이 브라우저에서 효과를 재생할 수 없습니다: ${error.message}`); }
    }
  }
  function fit() {
    if (!deck) return;
    const slide = deck.slides[current], ratio = Number(slide.width)/Number(slide.height);
    for (const [wrapper,target] of [[$('current-wrapper'),ui.stage],[$('reference-wrapper'),ui.reference]]) {
      const width = Math.max(1,Math.min(wrapper.clientWidth,wrapper.clientHeight*ratio));
      target.style.width = `${width}px`;
      target.style.height = `${width/ratio}px`;
    }
  }
  function cleanSelection() {
    selected = null;
    svg?.querySelector('.inspection-outline')?.remove();
    $('inspection-result').textContent = '';
    $('copy-id').hidden = true;
    $('inspection-hint').textContent = '슬라이드의 요소를 클릭하면 정확한 ID와 좌표가 표시됩니다.';
  }
  function safeAsset(path) {
    const url = new URL(path,location.href);
    if (url.origin !== location.origin || !['http:','https:','file:'].includes(url.protocol)) throw new Error('자료 경로는 같은 사이트의 파일이어야 합니다.');
    return url.href;
  }
  function importSvg(text) {
    const documentSvg = new DOMParser().parseFromString(text,'image/svg+xml');
    const root = documentSvg.documentElement;
    if (root.localName !== 'svg' || documentSvg.querySelector('parsererror')) throw new Error('SVG 파일 형식이 올바르지 않습니다.');
    // Exported vectors need neither active content nor external resources.
    for (const element of [root,...root.querySelectorAll('*')]) {
      if (['script','foreignObject','iframe','object','embed','animate','animateTransform','set'].includes(element.localName)) { element.remove(); continue; }
      for (const attribute of [...element.attributes]) {
        if (/^on/i.test(attribute.name)) element.removeAttribute(attribute.name);
        if (attribute.localName==='href' && !attribute.value.startsWith('#') && !attribute.value.startsWith('data:image/')) element.removeAttributeNS(attribute.namespaceURI,attribute.localName);
      }
    }
    return document.importNode(root,true);
  }
  async function mount(index, updateHash = true) {
    if (!deck?.slides.length) return;
    current = Math.max(0,Math.min(deck.slides.length-1,index));
    const token = ++generation, slide = deck.slides[current];
    stop(); effects = []; cleanSelection(); svg = null;
    ui.stage.replaceChildren(); ui.stage.setAttribute('aria-busy','true');
    ui['slide-select'].value = String(current);
    $('slide-title').textContent = slide.title || `슬라이드 ${current+1}`;
    $('slide-message').textContent = slide.message || '';
    ui.caption.hidden = !slide.message;
    $('current-label').textContent = `발표 화면 · ${current+1} / ${deck.slides.length}`;
    ui.reference.alt = `${slide.title || `슬라이드 ${current+1}`} · 원본 PDF`;
    ui.reference.src = safeAsset(slide.reference);
    if (updateHash) history.replaceState(null,'',`#slide=${current+1}`);
    updateControls(); fit();
    try {
      const url = safeAsset(slide.svg);
      if (!cache.has(url)) cache.set(url,fetch(url).then(response=>{
        if (!response.ok) throw new Error(`SVG를 읽지 못했습니다 (${response.status}).`);
        return response.text();
      }).catch(error=>{cache.delete(url);throw error;}));
      const source = await cache.get(url);
      if (token !== generation) return;
      svg = importSvg(source);
      svg.setAttribute('role','img');
      if (!svg.querySelector('title,desc')) svg.setAttribute('aria-label',slide.title || `슬라이드 ${current+1}`);
      ui.stage.append(svg); prepare(svg); applyEmphasis();
      ui.stage.removeAttribute('aria-busy');
      play(); fit();
      svg.dataset.ready = 'true';
    } catch (error) {
      if (token !== generation) return;
      ui.stage.removeAttribute('aria-busy');
      announce(error.message,0);
    }
  }
  function hashIndex() {
    const value = Number(new URLSearchParams(location.hash.slice(1)).get('slide'));
    return Number.isInteger(value) && value>0 ? value-1 : 0;
  }
  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
      else announce('이 브라우저는 페이지 전체화면을 지원하지 않습니다.');
    } catch (error) { announce(`전체화면을 열지 못했습니다: ${error.message}`); }
  }
  ui.previous.addEventListener('click',()=>mount(current-1));
  ui.next.addEventListener('click',()=>mount(current+1));
  ui['slide-select'].addEventListener('change',event=>mount(Number(event.target.value)));
  ui.replay.addEventListener('click',play);
  ui.motion.addEventListener('click',()=>{
    motion=!motion;
    try { localStorage.setItem('ppt-motion-effects',motion?'on':'off'); } catch {}
    play();
  });
  ui.emphasis.addEventListener('click',()=>{emphasis=!emphasis;stop();applyEmphasis();updateControls();});
  ui.inspect.addEventListener('click',()=>{
    inspect=!inspect;stop();ui.inspector.hidden=!inspect;
    ui.stage.classList.toggle('inspecting',inspect);cleanSelection();updateControls();fit();
  });
  ui.compare.addEventListener('click',()=>{
    compare=!compare;stop();ui.workbench.classList.toggle('comparing',compare);
    document.querySelector('.reference-panel').hidden=!compare;updateControls();fit();
  });
  ui.fullscreen.addEventListener('click',fullscreen);
  ui.stage.addEventListener('click',event=>{
    if (!inspect || !svg) return;
    const leaf = event.target.closest('[data-leaf]');
    if (!leaf || !svg.contains(leaf)) return;
    cleanSelection();
    const box = numbers(leaf.dataset.bbox);
    selected = leaf.dataset.leaf;
    $('inspection-hint').textContent = '선택한 원본 요소';
    $('inspection-result').textContent = `${selected}  ·  bbox [${box.join(', ')}] pt`;
    $('copy-id').hidden = false;
    if (box.length===4 && box.every(Number.isFinite)) svg.append(node('rect',{x:box[0],y:box[1],width:box[2]-box[0],height:box[3]-box[1],class:'inspection-outline'}));
  });
  $('copy-id').addEventListener('click',async()=>{
    if (!selected) return;
    try { await navigator.clipboard.writeText(selected); announce(`복사했습니다: ${selected}`); }
    catch { announce(`복사할 ID: ${selected}`,0); }
  });
  document.addEventListener('keydown',event=>{
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    if (event.key==='ArrowRight' || event.key==='PageDown') { event.preventDefault();mount(current+1); }
    else if (event.key==='ArrowLeft' || event.key==='PageUp') { event.preventDefault();mount(current-1); }
    else if (event.key.toLowerCase()==='r') { event.preventDefault();play(); }
    else if (event.key.toLowerCase()==='f') { event.preventDefault();fullscreen(); }
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();updateControls();});
  document.addEventListener('fullscreenchange',()=>{updateControls();fit();});
  media.addEventListener('change',()=>{stop();updateControls();});
  window.addEventListener('hashchange',()=>mount(hashIndex(),false));
  new ResizeObserver(fit).observe(ui.workbench);
  new ResizeObserver(fit).observe($('current-wrapper'));
  window.addEventListener('pagehide',()=>{generation++;stop();});

  fetch('deck.json').then(response=>{
    if(!response.ok)throw new Error(`deck.json을 읽지 못했습니다 (${response.status}).`);
    return response.json();
  }).then(value=>{
    if(!Array.isArray(value.slides) || !value.slides.length)throw new Error('표시할 슬라이드가 없습니다.');
    if(value.slides.some(slide=>!(Number(slide.width)>0 && Number(slide.height)>0) || !slide.svg || !slide.reference))throw new Error('슬라이드 크기 또는 파일 경로가 올바르지 않습니다.');
    deck=value;
    document.title=String(deck.title || 'PPT Motion');
    $('deck-title').textContent=String(deck.title || 'PPT Motion');
    deck.slides.forEach((slide,index)=>{
      const option=document.createElement('option');option.value=String(index);
      option.textContent=`${index+1} / ${deck.slides.length} · ${slide.title || `원본 ${slide.page || index+1}쪽`}`;
      ui['slide-select'].append(option);
    });
    return mount(hashIndex());
  }).catch(error=>announce(`${error.message} 로컬 서버로 열었는지 확인해 주세요.`,0));
})();
