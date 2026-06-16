/* Engine deterministic dùng chung cho mọi template.
 * Mọi animation = hàm thuần của t (giây). KHÔNG Date/Math.random, KHÔNG CSS @keyframes.
 * Particle ngẫu nhiên => hash(i) seeded theo index (không random mỗi frame).
 *
 * Template chỉ cần: BT.init(opts) lúc load, rồi trong seek(t) gọi BT.bg / BT.embers /
 * BT.entrance(Words) / BT.foilSheen / BT.fireGlow + phần layout riêng. Tất cả null-safe. */
window.BT = {
  // ── math ──
  clamp01: function (x) { return Math.max(0, Math.min(1, x)); },
  easeOutCubic: function (p) { return 1 - Math.pow(1 - p, 3); },
  easeInOutCubic: function (p) { return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2; },
  lerp: function (a, b, p) { return a + (b - a) * p; },
  seg: function (t, start, dur) { return this.easeOutCubic(this.clamp01((t - start) / dur)); },
  hash: function (n) { var x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); },
  pulse: function (t, bpm, amp) { return amp * Math.sin(t * (bpm / 60) * 6.28318530718); },
  flash: function (t, t0) { var d = t - t0; return d < 0 ? 0 : Math.exp(-d * 15); },
  flashLevel: function (t, beats) { var fl = 0, k; for (k = 0; k < (beats || []).length; k++) { var v = this.flash(t, beats[k]); if (v > fl) fl = v; } return fl; },

  _esc: function (s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; },
  _autofit: function (el, fs, minfs, maxW) {
    el.style.fontSize = fs + 'px';
    while (fs > minfs) {
      if (el.scrollWidth <= maxW && el.offsetHeight <= fs * 2.35) break;
      fs -= 3; el.style.fontSize = fs + 'px';
    }
  },

  /* init: split title theo từ (+ nhấn 1 từ qua opts.emphasis), auto-fit, sinh embers.
     opts: {emphasis:int|-1, maxFont, minFont, maxW, emberCount} */
  init: function (opts) {
    opts = opts || {};
    this._D = window.DURATION_SEC || 12;
    var title = document.getElementById('title');
    if (title) {
      // splitTitle:false → giữ title 1 khối (cho foil/background-clip:text hoạt động liền mạch)
      if (opts.splitTitle !== false) {
        var words = title.textContent.trim().split(/\s+/), emph = (opts.emphasis == null ? -1 : opts.emphasis);
        if (emph === 'last') emph = words.length - 1;
        if (emph === 'first') emph = 0;
        title.innerHTML = words.map(function (w, i) {
          return '<span class="tw' + (emph === i ? ' tt-em' : '') + '">' + window.BT._esc(w) + '</span>';
        }).join(' ');
      }
      this.autofitTitle(opts);
    }
    var box = document.getElementById('embers');
    if (box && opts.emberCount) {
      for (var i = 0; i < opts.emberCount; i++) {
        var s = 2 + this.hash(i + 3) * 5, d = document.createElement('div');
        d.className = 'ember'; d.style.width = s + 'px'; d.style.height = s + 'px'; box.appendChild(d);
      }
    }
  },
  autofitTitle: function (opts) {
    opts = opts || {};
    var title = document.getElementById('title');
    if (title) this._autofit(title, opts.maxFont || 96, opts.minFont || 52, opts.maxW || 902);
  },
  /* co khối .highlights cho vừa chiều cao maxH (chữ nhiều → scale nhỏ lại, không tràn).
     transform-origin top → giữ mép trên cố định; entrance từng .hl vẫn chạy bình thường. */
  fitHighlights: function (maxH) {
    var el = document.querySelector('.highlights'); if (!el) return;
    el.style.transform = ''; el.style.transformOrigin = 'top left';
    var h = el.scrollHeight;
    if (h > maxH) el.style.transform = 'scale(' + (maxH / h).toFixed(4) + ')';
  },

  /* nền: reveal (fade tối + punch-in) + slow zoom + pulse nhịp + shake(theo flash) + brighten.
     opts: {reveal, zoomFrom, zoomTo, bpm, pulseAmp, driftY, fl, shake} → trả progress reveal */
  bg: function (t, opts) {
    opts = opts || {};
    var el = document.getElementById('bg'); var D = this._D || (window.DURATION_SEC || 12);
    // window.REVEAL (inject từ render): scene>0 dùng reveal ~0 (xfade lo phần vào cảnh)
    var revDur = (window.REVEAL != null ? window.REVEAL : (opts.reveal || 0.9));
    var rv = this.seg(t, 0, Math.max(revDur, 0.001));
    var dark = document.getElementById('dark'); if (dark) dark.style.opacity = 1 - rv;
    var fl = opts.fl || 0, flash = document.getElementById('flash');
    if (flash) flash.style.opacity = Math.min(fl * 0.85, 0.85);
    if (el) {
      var bp = this.clamp01(t / D);
      var base = this.lerp(opts.zoomFrom || 1.06, opts.zoomTo || 1.16, bp) + this.pulse(t, opts.bpm || 120, opts.pulseAmp || 0.012);
      var scale = this.lerp(1.28, base, rv);
      var shk = opts.shake === false ? 0 : fl, fi = Math.floor(t * 60);
      var shx = shk * (this.hash(fi) - 0.5) * 18, shy = shk * (this.hash(fi + 99) - 0.5) * 18;
      var dy = opts.driftY == null ? 10 : opts.driftY;
      el.style.transform = 'scale(' + scale + ') translate(' + shx + 'px,' + (shy + this.lerp(-dy, dy, bp)) + 'px)';
      el.style.filter = 'blur(' + this.lerp(14, 0, rv) + 'px) brightness(' + (1 + fl * 0.55) + ')';
    }
    return rv;
  },

  embers: function (t, rv) {
    var box = document.getElementById('embers'); if (!box) return; var kids = box.children, H = 1920, W = 1080, i;
    for (i = 0; i < kids.length; i++) {
      var hp = this.hash(i + 7), hf = this.hash(i + 11);
      var x = this.hash(i) * W, speed = 60 + this.hash(i + 3) * 120, span = H + 80;
      var y = H - (((t * speed) + hp * span) % span), drift = Math.sin(t * (0.6 + hf) + hp * 6.28) * 22;
      var tw = 0.35 + 0.4 * (0.5 + 0.5 * Math.sin(t * (2 + hf * 3) + hp * 6.28));
      kids[i].style.transform = 'translate(' + (x + drift) + 'px,' + y + 'px)';
      kids[i].style.opacity = tw * (rv == null ? 1 : rv) * this.clamp01(y / 220);
    }
  },

  set: function (id, op, tx, ty, sc, bl) {
    var e = document.getElementById(id); if (!e) return;
    e.style.opacity = op;
    e.style.transform = 'translate(' + (tx || 0) + 'px,' + (ty || 0) + 'px) scale(' + (sc == null ? 1 : sc) + ')';
    e.style.filter = bl > 0.05 ? 'blur(' + bl + 'px)' : 'none';
  },
  /* entrance 1 element: fromY/fromX = lệch ban đầu */
  entrance: function (t, id, start, dur, fromY, fromX) {
    var p = this.seg(t, start, dur);
    this.set(id, p, this.lerp(fromX || 0, 0, p), this.lerp(fromY || 0, 0, p), this.lerp(0.96, 1, p), this.lerp(8, 0, p));
    return p;
  },
  /* entrance từng từ của title (slam) */
  entranceWords: function (t, start, stagger, fromY) {
    var ws = document.querySelectorAll('#title .tw'), i;
    for (i = 0; i < ws.length; i++) {
      var p = this.seg(t, start + i * (stagger || 0.12), 0.55);
      ws[i].style.opacity = p;
      ws[i].style.transform = 'translateY(' + this.lerp(fromY == null ? 42 : fromY, 0, p) + 'px) scale(' + this.lerp(1.22, 1, p) + ')';
      ws[i].style.filter = p < 0.95 ? 'blur(' + this.lerp(10, 0, p) + 'px)' : 'none';
    }
  },
  /* sheen foil chạy qua chữ (cho .tt-foil) */
  foilSheen: function (id, t, speed) { var e = document.getElementById(id); if (e) e.style.backgroundPosition = ((t * (speed || 42)) % 230) + '% 0'; },
  /* fire-glow warm flicker + bùng khi flash */
  fireGlow: function (id, t, fl) {
    var e = document.getElementById(id); if (!e) return;
    var g = 16 + 8 * Math.sin(t * 7) + (fl || 0) * 42, w = 0.55 + 0.18 * Math.sin(t * 9);
    e.style.textShadow = '0 0 ' + g + 'px rgba(255,170,60,' + w + '),0 0 ' + (g * 2) + 'px rgba(255,90,20,' + (w * 0.5) + '),0 3px 18px rgba(0,0,0,0.6)';
  },
  /* phụ đề theo cụm: hiện cue đúng [t0,t1) + fade mép (cho template Đơn sắc).
     cues = [{t0,t1,text}] inject từ render. elId mặc định 'caption'. */
  caption: function (t, cues, elId) {
    var el = document.getElementById(elId || 'caption'); if (!el) return;
    cues = cues || []; var cur = -1, i;
    for (i = 0; i < cues.length; i++) { if (t >= cues[i].t0 && t < cues[i].t1) { cur = i; break; } }
    if (cur < 0) { el.style.opacity = 0; return; }
    if (el.getAttribute('data-cue') !== String(cur)) { el.textContent = cues[cur].text; el.setAttribute('data-cue', String(cur)); }
    var fade = 0.18, inP = this.clamp01((t - cues[cur].t0) / fade), outP = this.clamp01((cues[cur].t1 - t) / fade);
    el.style.opacity = Math.min(inP, outP, 1);
  }
};
