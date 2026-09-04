(function () {
  "use strict";

  const TOKEN_KEY = "offline_player_token";
  const READER_KEY = "offline_player_reader";

  const state = {
    view: "games",
    games: [],
    categories: [],
    items: [],
    gameId: "",
    gameName: "",
    gameKind: "",
    catStack: [],
    player: null,
    surface: "manga",
    album: "story",
    pageIndex: 0,
    clipIndex: 0,
    beatIndex: 0,
    /** 同一作品内图/视频进度互不影响 */
    progress: { manga: {}, video: { clipIndex: 0, times: {} } },
    chromeTimer: 0,
    touch: null,
    swiped: false,
    advVoice: null,
    lastAdvBg: "",
    lastAdvMovie: null,
    playedSceneId: "",
    prepareAbort: false,
    prepareSceneId: "",
    listCache: {},
  };

  function loadReaderPrefs() {
    try {
      return JSON.parse(localStorage.getItem(READER_KEY) || "{}");
    } catch (e) {
      return {};
    }
  }

  const prefs = Object.assign(
    {
      readMode: "page",
      rtl: false,
      margin: 24,
      orientation: "auto",
      voiceStop: "click",
    },
    loadReaderPrefs()
  );

  function saveReaderPrefs() {
    localStorage.setItem(
      READER_KEY,
      JSON.stringify({
        readMode: prefs.readMode,
        rtl: prefs.rtl,
        margin: prefs.margin,
        orientation: prefs.orientation,
        voiceStop: prefs.voiceStop === "next" ? "next" : "click",
      })
    );
  }

  const els = {
    title: document.getElementById("header-title"),
    back: document.getElementById("btn-back"),
    viewGames: document.getElementById("view-games"),
    viewCategories: document.getElementById("view-categories"),
    viewItems: document.getElementById("view-items"),
    gamesList: document.getElementById("games-list"),
    categoriesGrid: document.getElementById("categories-grid"),
    itemsGrid: document.getElementById("items-grid"),
    splash: document.getElementById("splash"),
    splashLine: document.getElementById("splash-line"),
    splashSub: document.getElementById("splash-sub"),
    splashPct: document.getElementById("splash-pct"),
    splashFill: document.getElementById("splash-fill"),
    splashCancel: document.getElementById("splash-cancel"),
    playerView: document.getElementById("player-view"),
    playerTitle: document.getElementById("player-title"),
    playerStage: document.getElementById("player-stage"),
    playerClose: document.getElementById("player-close"),
    playerMotion: document.getElementById("player-motion"),
    playerMore: document.getElementById("player-more"),
    playerPage: document.getElementById("player-page"),
    chrome: document.getElementById("reader-chrome"),
    sheetMask: document.getElementById("sheet-mask"),
    sheet: document.getElementById("reader-sheet"),
    advDialogue: document.getElementById("adv-dialogue"),
    advName: document.getElementById("adv-name"),
    advText: document.getElementById("adv-text"),
    advHint: document.getElementById("adv-hint"),
  };

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function qs(extra) {
    const t = getToken();
    const parts = [];
    if (t) parts.push(`token=${encodeURIComponent(t)}`);
    if (extra) parts.push(extra);
    return parts.length ? `?${parts.join("&")}` : "";
  }

  function buildUrl(path, params) {
    const q = new URLSearchParams();
    const t = getToken();
    if (t) q.set("token", t);
    Object.entries(params || {}).forEach(([k, v]) => q.set(k, v));
    const s = q.toString();
    return s ? `${path}?${s}` : path;
  }

  async function api(path, params, options) {
    const retries = options && options.retries != null ? options.retries : 3;
    let lastErr = null;
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const res = await fetch(buildUrl(path, params), { cache: "no-store" });
        if (res.status === 403) throw new Error("访问令牌无效，请在设置中配置 token");
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || res.statusText || `HTTP ${res.status}`);
        }
        return await res.json();
      } catch (err) {
        lastErr = err;
        const msg = String((err && err.message) || err || "");
        const network =
          (err && err.name === "TypeError") ||
          /failed to fetch|networkerror|load failed|network request failed/i.test(msg);
        // 业务错误（令牌/HTTP）不重试
        if (!network || attempt >= retries) break;
        await sleep(280 * Math.pow(2, attempt));
      }
    }
    const msg = String((lastErr && lastErr.message) || lastErr || "");
    if (
      (lastErr && lastErr.name === "TypeError") ||
      /failed to fetch|networkerror|load failed|network request failed/i.test(msg)
    ) {
      throw new Error(
        "网络连接失败：请确认电脑端局域网服务仍在运行，手机与电脑同一 WiFi，然后重试"
      );
    }
    throw lastErr;
  }

  function mediaUrl(url) {
    if (!url) return "";
    if (typeof url === "object") url = url.url;
    return url + qs();
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function setView(name) {
    state.view = name;
    els.viewGames.classList.toggle("active", name === "games");
    els.viewCategories.classList.toggle("active", name === "categories");
    els.viewItems.classList.toggle("active", name === "items");
    els.back.style.visibility = name === "games" ? "hidden" : "visible";
  }

  function showSplash(text, pct, sub, opts) {
    els.splash.classList.add("show");
    els.splashLine.textContent = text || "正在加载…";
    if (els.splashSub) els.splashSub.textContent = sub || "";
    const p = Math.max(3, Math.min(100, pct || 8));
    els.splashPct.textContent = `${p}%`;
    els.splashFill.style.width = `${p}%`;
    const canCancel = !!(opts && opts.cancellable);
    if (els.splashCancel) {
      els.splashCancel.hidden = !canCancel;
    }
  }

  function hideSplash() {
    els.splash.classList.remove("show");
    if (els.splashSub) els.splashSub.textContent = "";
    if (els.splashCancel) els.splashCancel.hidden = true;
    state.prepareAbort = false;
    state.prepareSceneId = "";
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function needsAdvPrepare() {
    const kind = state.gameKind || "";
    return kind === "adv" || kind === "" || kind === "deepone";
  }

  class PrepareCancelledError extends Error {
    constructor() {
      super("已取消");
      this.name = "PrepareCancelledError";
    }
  }

  async function cancelPrepare(sceneId) {
    state.prepareAbort = true;
    if (!state.gameId || !sceneId) return;
    try {
      await api(`/api/games/${encodeURIComponent(state.gameId)}/prepare`, {
        sid: sceneId,
        cancel: "1",
      });
    } catch (e) {
      /* 取消请求失败也照样退出闪屏 */
    }
  }

  async function prepareAdvScene(sceneId, title) {
    state.prepareAbort = false;
    state.prepareSceneId = sceneId;
    showSplash("正在检查场景资源…", 8, title || sceneId, { cancellable: true });
    let guard = 0;
    while (guard < 900) {
      if (state.prepareAbort) throw new PrepareCancelledError();
      guard += 1;
      const st = await api(`/api/games/${encodeURIComponent(state.gameId)}/prepare`, {
        sid: sceneId,
      });
      if (state.prepareAbort || st.status === "cancelled") {
        throw new PrepareCancelledError();
      }
      const total = st.total || 0;
      const done = st.done || 0;
      const pct = st.percent != null ? st.percent : total ? Math.round((done * 100) / total) : 12;
      const name = st.current_name || "";
      let line = st.message || "准备中…";
      if (st.status === "running" && total > 0) {
        line = `下载资源 ${done}/${total}`;
      } else if (st.status === "done" && total === 0) {
        line = st.message || "资源已就绪";
      } else if (st.status === "done") {
        line = st.message || `下载完成 ${st.ok || done}/${total}`;
      }
      showSplash(line, Math.max(8, pct), name || title || sceneId, {
        cancellable: st.status === "running" || !st.ready,
      });

      if (st.status === "done") {
        await sleep(280);
        return st;
      }
      if (st.status === "error") {
        throw new Error(st.error || st.message || "资源下载失败");
      }
      await sleep(450);
    }
    throw new Error("下载超时，请检查电脑网络后重试");
  }

  function renderThumbCard(entry, onClick) {
    const card = document.createElement("div");
    card.className = "thumb-card";
    const imgWrap = document.createElement("div");
    imgWrap.className = "thumb-img";
    if (entry.image_url) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = "";
      img.src = mediaUrl(entry.image_url);
      imgWrap.appendChild(img);
    } else {
      const ph = document.createElement("div");
      ph.className = "thumb-placeholder";
      ph.textContent = entry.title || "无预览";
      imgWrap.appendChild(ph);
    }
    if (entry.badge) {
      const b = document.createElement("span");
      b.className = "badge";
      b.textContent = entry.badge;
      imgWrap.appendChild(b);
    }
    const body = document.createElement("div");
    body.className = "thumb-body";
    body.innerHTML = `<div class="thumb-title">${esc(entry.title)}</div><div class="thumb-sub">${esc(entry.subtitle)}</div>`;
    card.appendChild(imgWrap);
    card.appendChild(body);
    card.addEventListener("click", onClick);
    return card;
  }

  async function loadGames() {
    els.title.textContent = "离线播放器";
    state.catStack = [];
    setView("games");
    const data = await api("/api/games");
    state.games = data.games || [];
    els.gamesList.innerHTML = "";
    if (!state.games.length) {
      els.gamesList.innerHTML = "<div class='empty-state'>没有可用游戏</div>";
      return;
    }
    state.games.forEach((g) => {
      const row = document.createElement("div");
      row.className = "game-row";
      row.innerHTML = `<h3>${esc(g.name)}</h3><p>${esc(g.description || g.kind)} · ${g.scene_count} 项</p>`;
      row.addEventListener("click", () => openGame(g.id, g.name, g.kind));
      els.gamesList.appendChild(row);
    });
  }

  async function openGame(gameId, gameName, gameKind) {
    state.gameId = gameId;
    state.gameName = gameName;
    state.gameKind = gameKind || "";
    state.catStack = [];
    state.listCache = {};
    els.title.textContent = gameName;
    showSplash("正在扫描资源…", 12, gameName);
    try {
      let pct = 15;
      const timer = setInterval(() => {
        pct = Math.min(88, pct + 4);
        showSplash(`正在加载 ${gameName}…`, pct);
      }, 400);
      const bundle = await api(`/api/games/${encodeURIComponent(gameId)}/load`);
      clearInterval(timer);
      hideSplash();
      state.categories = bundle.categories || [];
      els.categoriesGrid.innerHTML = "";
      if (!state.categories.length) {
        els.categoriesGrid.innerHTML = "<div class='empty-state'>暂无分类</div>";
      } else {
        state.categories.forEach((c) => {
          els.categoriesGrid.appendChild(
            renderThumbCard(c, () => openCategory(c.key, c.title, true))
          );
        });
      }
      setView("categories");
    } catch (e) {
      hideSplash();
      alert(e.message || String(e));
    }
  }

  function listCacheKey(catKey) {
    return `${state.gameId}::${catKey}`;
  }

  function renderItemsList(items, catTitle) {
    state.items = items || [];
    els.title.textContent = catTitle || els.title.textContent;
    els.itemsGrid.innerHTML = "";
    if (!state.items.length) {
      els.itemsGrid.innerHTML = "<div class='empty-state'>此分类下没有内容</div>";
    } else {
      state.items.forEach((item) => {
        els.itemsGrid.appendChild(
          renderThumbCard(item, () => {
            if (item.kind === "folder") openCategory(item.key, item.title, false);
            else openPlayer(item.key, item.title);
          })
        );
      });
    }
    setView("items");
  }

  async function openCategory(catKey, catTitle, replaceStack, opts) {
    const skipPush = !!(opts && opts.skipPush);
    const force = !!(opts && opts.force);
    if (!skipPush) {
      if (replaceStack) {
        state.catStack = [{ key: catKey, title: catTitle || catKey }];
      } else {
        state.catStack.push({ key: catKey, title: catTitle || catKey });
      }
    }
    els.title.textContent = catTitle || catKey;
    const cacheKey = listCacheKey(catKey);
    if (!force && state.listCache[cacheKey]) {
      hideSplash();
      renderItemsList(state.listCache[cacheKey], catTitle || catKey);
      return;
    }
    showSplash("正在读取列表…", 20);
    try {
      const data = await api(`/api/games/${encodeURIComponent(state.gameId)}/items`, { cat: catKey });
      hideSplash();
      const items = data.items || [];
      state.listCache[cacheKey] = items;
      renderItemsList(items, catTitle || catKey);
    } catch (e) {
      hideSplash();
      alert(e.message || String(e));
    }
  }

  function isAdvMode() {
    return !!(state.player && state.player.kind === "adv" && (state.player.beats || []).length);
  }

  function stopVoice() {
    if (state.advVoice) {
      try {
        state.advVoice.pause();
        state.advVoice.removeAttribute("src");
        state.advVoice.load();
      } catch (e) {}
    }
  }

  function stopStageVideos() {
    els.playerStage.querySelectorAll("video").forEach((vid) => {
      try {
        vid.pause();
        vid.removeAttribute("src");
        vid.load();
      } catch (e) {}
    });
  }

  function playVoice(url, options) {
    const forceStop = !!(options && options.forceStop);
    const mode = prefs.voiceStop === "next" ? "next" : "click";
    if (mode === "next" && !forceStop) {
      // 下一句有语音时才停并换播；无语音的句子不打断当前语音
      if (!url) return;
      stopVoice();
    } else {
      // 点击时停止 / 回退 / 关闭：立刻停
      stopVoice();
      if (!url) return;
    }
    if (!state.advVoice) state.advVoice = new Audio();
    state.advVoice.src = mediaUrl(url);
    state.advVoice.play().catch(() => {});
  }

  function renderAdvBeat(force, options) {
    const beats = (state.player && state.player.beats) || [];
    if (!beats.length) {
      els.playerStage.innerHTML = "<div class='empty-state' style='color:#ccc'>没有可播放的台本</div>";
      els.advDialogue.hidden = true;
      return;
    }
    const i = Math.max(0, Math.min(state.beatIndex, beats.length - 1));
    state.beatIndex = i;
    const beat = beats[i];
    const stage = els.playerStage;
    stage.classList.add("adv-mode");
    stage.classList.remove("webtoon");

    const bg = beat.bg_url || "";
    const movie = (beat.movies && beat.movies[0]) || null;
    const movieKey = movie ? (movie.urls || []).join("|") : "";

    if (force || !stage.querySelector(".adv-layer")) {
      stage.innerHTML =
        '<div class="adv-layer"><img class="adv-bg" alt=""><video class="adv-movie" playsinline muted style="display:none"></video></div>';
      state.lastAdvBg = "";
      state.lastAdvMovie = null;
    }
    const img = stage.querySelector(".adv-bg");
    const video = stage.querySelector(".adv-movie");

    if (bg !== state.lastAdvBg) {
      state.lastAdvBg = bg;
      if (bg) {
        img.src = mediaUrl(bg);
        img.style.display = "";
      } else {
        img.removeAttribute("src");
        img.style.display = "none";
      }
    }

    if (movieKey !== state.lastAdvMovie) {
      state.lastAdvMovie = movieKey;
      video.onended = null;
      if (movie && movie.urls && movie.urls.length) {
        const urls = movie.urls;
        video.style.display = "block";
        video.loop = urls.length === 1;
        video.src = mediaUrl(urls[0]);
        video.play().catch(() => {});
        if (urls.length > 1) {
          video.onended = () => {
            video.loop = true;
            video.src = mediaUrl(urls[1]);
            video.play().catch(() => {});
            video.onended = null;
          };
        }
      } else {
        try {
          video.pause();
        } catch (e) {}
        video.removeAttribute("src");
        try {
          video.load();
        } catch (e) {}
        video.style.display = "none";
      }
    }

    els.advDialogue.hidden = false;
    const name = beat.speaker || "";
    const text = beat.text || "";
    els.advName.textContent = beat.narration ? "旁白" : name;
    els.advName.classList.toggle("narration", !!beat.narration || !name);
    els.advName.style.display = name || beat.narration ? "" : "none";
    els.advText.textContent = text || (movie || bg ? "" : "（无对白）");
    els.advHint.textContent =
      i >= beats.length - 1
        ? `结尾 ${i + 1}/${beats.length} · 点关闭退出`
        : `${i + 1}/${beats.length} · 点继续 · 左侧上一句`;

    playVoice(beat.voice_url, { forceStop: !!(options && options.reverse) });
    updateChrome();
  }

  function advanceAdv(dir) {
    if (!isAdvMode()) return;
    const beats = state.player.beats || [];
    const next = state.beatIndex + dir;
    if (next < 0) return;
    if (next >= beats.length) {
      showChrome();
      return;
    }
    state.beatIndex = next;
    renderAdvBeat(false, { reverse: dir < 0 });
    showChrome();
  }

  function currentPages() {
    const p = state.player;
    if (!p) return [];
    if (p.kind === "purchased") {
      return state.album === "omake" ? p.omake || [] : p.pages || [];
    }
    return p.images || [];
  }

  function currentVideos() {
    const p = state.player;
    if (!p) return [];
    const list = p.videos || [];
    return list.map((v) => (typeof v === "string" ? { url: v, name: "" } : v));
  }

  function showChrome(sticky) {
    els.chrome.classList.add("show");
    clearTimeout(state.chromeTimer);
    if (sticky) return;
    state.chromeTimer = setTimeout(() => {
      if (!els.sheetMask.hidden) return;
      els.chrome.classList.remove("show");
    }, 2800);
  }

  function hideChrome() {
    if (!els.sheetMask.hidden) return;
    clearTimeout(state.chromeTimer);
    els.chrome.classList.remove("show");
  }

  function toggleChrome() {
    if (els.chrome.classList.contains("show")) hideChrome();
    else showChrome();
  }

  async function applyOrientation() {
    const ori = screen.orientation;
    if (!ori) return;
    try {
      if (prefs.orientation === "portrait") await ori.lock("portrait");
      else if (prefs.orientation === "landscape") await ori.lock("landscape");
      else if (ori.unlock) ori.unlock();
    } catch (e) {
      /* 浏览器可能要求全屏才能锁定 */
    }
  }

  async function unlockOrientation() {
    try {
      if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock();
    } catch (e) {}
  }

  function mangaProgressKey() {
    return state.album === "omake" ? "omake" : "story";
  }

  function emptyProgress() {
    return { manga: {}, video: { clipIndex: 0, times: {} } };
  }

  function saveMangaProgress() {
    if (!state.player || state.surface !== "manga") return;
    if (prefs.readMode === "webtoon") syncWebtoonPageFromScroll();
    const key = mangaProgressKey();
    state.progress.manga[key] = {
      pageIndex: state.pageIndex,
      scrollTop: prefs.readMode === "webtoon" ? els.playerStage.scrollTop : 0,
      readMode: prefs.readMode,
    };
  }

  function saveVideoProgress() {
    if (!state.player || state.surface !== "video") return;
    if (!state.progress.video) state.progress.video = { clipIndex: 0, times: {} };
    const vid = els.playerStage.querySelector("video.page-video");
    state.progress.video.clipIndex = state.clipIndex;
    if (vid && Number.isFinite(vid.currentTime) && vid.currentTime > 0) {
      state.progress.video.times[String(state.clipIndex)] = vid.currentTime;
    }
  }

  function saveCurrentProgress() {
    if (state.surface === "video") saveVideoProgress();
    else if (state.surface === "manga") saveMangaProgress();
  }

  function restoreMangaProgress() {
    const saved = state.progress.manga[mangaProgressKey()];
    if (!saved) return;
    state.pageIndex = Math.max(0, Number(saved.pageIndex) || 0);
  }

  function restoreVideoProgress() {
    const saved = state.progress.video;
    if (!saved) return;
    state.clipIndex = Math.max(0, Number(saved.clipIndex) || 0);
  }

  function savedMangaScrollTop() {
    const saved = state.progress.manga[mangaProgressKey()];
    if (!saved || saved.readMode !== "webtoon") return null;
    const top = Number(saved.scrollTop) || 0;
    return top > 0 ? top : null;
  }

  function savedVideoTime(clipIndex) {
    const times = (state.progress.video && state.progress.video.times) || {};
    const t = Number(times[String(clipIndex)]) || 0;
    return t > 0.25 ? t : 0;
  }

  function updateChrome() {
    const p = state.player;
    if (!p) return;
    if (isAdvMode()) {
      const n = (p.beats || []).length;
      const miss = p.missing_resources || 0;
      els.playerMotion.hidden = true;
      document.getElementById("player-bottom").style.display = "none";
      els.playerPage.textContent =
        `ADV ${state.beatIndex + 1} / ${n}` + (miss ? ` · 缺 ${miss} 个资源` : "");
      return;
    }
    document.getElementById("player-bottom").style.display = "";
    const videos = currentVideos();
    const pages = currentPages();
    const hasManga = (p.pages && p.pages.length) || (p.omake && p.omake.length) || (p.images && p.images.length);
    els.playerMotion.hidden = !(videos.length && state.surface === "manga");
    els.playerMotion.textContent = "动态";
    if (state.surface === "video") {
      els.playerMotion.hidden = !hasManga;
      els.playerMotion.textContent = "漫画";
      const clip = videos[state.clipIndex];
      const n = videos.length;
      let label = n
        ? `动态 ${state.clipIndex + 1} / ${n}${clip && clip.name ? " · " + clip.name : ""}`
        : "无视频";
      const tips = [];
      if (n > 1) tips.push("上下切换");
      if (hasManga) tips.push("左滑回图");
      if (tips.length) label += " · " + tips.join(" · ");
      els.playerPage.textContent = label;
    } else if (prefs.readMode === "webtoon") {
      const n = pages.length;
      const cur = n ? Math.min(Math.max(1, state.pageIndex + 1), n) : 0;
      const album = state.album === "omake" ? "特典 · " : "";
      let label = n ? `${album}条漫 ${cur} / ${n}` : "无图片";
      if (n && videos.length) label += " · 左滑进动态";
      els.playerPage.textContent = label;
    } else {
      els.playerPage.textContent = pages.length
        ? `${state.album === "omake" ? "特典 " : ""}${state.pageIndex + 1} / ${pages.length}`
        : "无图片";
    }
  }

  function syncWebtoonPageFromScroll() {
    if (state.surface !== "manga" || prefs.readMode !== "webtoon") return;
    const stage = els.playerStage;
    const imgs = stage.querySelectorAll(".webtoon-col img");
    if (!imgs.length) return;
    const stageTop = stage.scrollTop;
    const marker = stageTop + Math.min(stage.clientHeight * 0.28, 160);
    let idx = 0;
    for (let i = 0; i < imgs.length; i++) {
      const top = imgs[i].offsetTop;
      if (top <= marker) idx = i;
      else break;
    }
    if (idx !== state.pageIndex) {
      state.pageIndex = idx;
      updateChrome();
    }
  }

  function onWebtoonScroll() {
    syncWebtoonPageFromScroll();
  }

  function renderPlayer() {
    const p = state.player;
    const stage = els.playerStage;
    if (!p) return;

    if (isAdvMode()) {
      renderAdvBeat(true);
      return;
    }

    els.advDialogue.hidden = true;
    stage.classList.remove("adv-mode");
    stage.innerHTML = "";
    stage.classList.toggle("webtoon", state.surface === "manga" && prefs.readMode === "webtoon");

    if (state.surface === "video") {
      const videos = currentVideos();
      if (!videos.length) {
        stage.innerHTML = "<div class='empty-state' style='color:#ccc'>没有动态视频</div>";
        updateChrome();
        return;
      }
      if (state.clipIndex >= videos.length) state.clipIndex = videos.length - 1;
      if (state.clipIndex < 0) state.clipIndex = 0;
      const clip = videos[state.clipIndex];
      const resumeAt = savedVideoTime(state.clipIndex);
      const v = document.createElement("video");
      v.className = "page-video";
      v.controls = true;
      v.playsInline = true;
      v.src = mediaUrl(clip.url);
      stage.appendChild(v);
      const tryPlay = () => {
        v.play().catch(() => {});
      };
      if (resumeAt > 0) {
        const seek = () => {
          try {
            if (Number.isFinite(v.duration) && resumeAt < v.duration) v.currentTime = resumeAt;
            else if (!Number.isFinite(v.duration)) v.currentTime = resumeAt;
          } catch (e) {}
          tryPlay();
        };
        if (v.readyState >= 1) seek();
        else v.addEventListener("loadedmetadata", seek, { once: true });
      } else {
        tryPlay();
      }
      updateChrome();
      return;
    }

    const pages = currentPages();
    if (!pages.length) {
      stage.innerHTML = "<div class='empty-state' style='color:#ccc'>没有可阅读的图片</div>";
      updateChrome();
      return;
    }

    if (prefs.readMode === "webtoon") {
      const col = document.createElement("div");
      col.className = "webtoon-col";
      const pad = Math.max(0, Number(prefs.margin) || 0);
      col.style.paddingLeft = `${pad}px`;
      col.style.paddingRight = `${pad}px`;
      pages.forEach((url) => {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.src = mediaUrl(url);
        col.appendChild(img);
      });
      stage.appendChild(col);
      const target = Math.min(Math.max(0, state.pageIndex), Math.max(0, pages.length - 1));
      state.pageIndex = target;
      const wantScroll = savedMangaScrollTop();
      stage.scrollTop = 0;
      updateChrome();
      let tries = 0;
      const restoreScroll = () => {
        tries += 1;
        const imgs = col.querySelectorAll("img");
        if (wantScroll != null) {
          const ready = stage.scrollHeight >= wantScroll + 40 || tries > 40;
          if (ready) {
            stage.scrollTop = wantScroll;
            // 高度够了再以滚动位置校正页码，避免未加载完把进度打回 0
            syncWebtoonPageFromScroll();
            return;
          }
        } else if (target > 0 && imgs[target]) {
          const top = imgs[target].offsetTop;
          if (top > 0 || tries > 40) {
            stage.scrollTop = top;
            syncWebtoonPageFromScroll();
            return;
          }
        } else {
          syncWebtoonPageFromScroll();
          return;
        }
        setTimeout(restoreScroll, 50);
      };
      requestAnimationFrame(restoreScroll);
      return;
    }

    const img = document.createElement("img");
    img.className = "page-img";
    img.src = mediaUrl(pages[state.pageIndex]);
    stage.appendChild(img);
    updateChrome();
  }

  function turnPage(dir) {
    if (state.surface !== "manga" || prefs.readMode === "webtoon") return;
    const pages = currentPages();
    if (!pages.length) return;
    const step = prefs.rtl ? -dir : dir;
    const next = state.pageIndex + step;
    if (next < 0 || next >= pages.length) return;
    state.pageIndex = next;
    renderPlayer();
    showChrome();
  }

  function turnClip(dir) {
    if (state.surface !== "video") return;
    const videos = currentVideos();
    if (videos.length < 2) return;
    const next = state.clipIndex + dir;
    if (next < 0 || next >= videos.length) return;
    saveVideoProgress();
    state.clipIndex = next;
    if (state.progress.video) state.progress.video.clipIndex = next;
    renderPlayer();
    showChrome();
  }

  function setSurface(name) {
    if (name === state.surface) return;
    saveCurrentProgress();
    const vid = els.playerStage.querySelector("video");
    if (vid) {
      vid.pause();
      vid.removeAttribute("src");
      vid.load();
    }
    state.surface = name;
    if (name === "video" && !currentVideos().length) state.surface = "manga";
    if (state.surface === "manga") {
      const pages = currentPages();
      if (!pages.length && (state.player.omake || []).length) {
        state.album = "omake";
      }
      restoreMangaProgress();
    } else if (state.surface === "video") {
      restoreVideoProgress();
    }
    renderPlayer();
    showChrome();
  }

  function openSheet() {
    const p = state.player;
    if (!p) return;

    const seg = (id, options) => {
      const buttons = options
        .map(
          (o) =>
            `<button type="button" data-act="${id}" data-val="${esc(o.value)}" ${o.disabled ? "disabled" : ""} class="${o.active ? "active" : ""}">${esc(o.label)}</button>`
        )
        .join("");
      return `<div class="sheet-row"><div class="sheet-label">${esc(options[0] && options[0].group ? options[0].group : "")}</div><div class="sheet-seg">${buttons}</div></div>`;
    };

    if (isAdvMode()) {
      let html = `<div class="sheet-title">ADV 设置</div>`;
      html += `<div class="sheet-row"><div class="sheet-label">点屏幕中间/右侧下一句，左侧上一句。画面只在台本换图或开动态时才会变。</div></div>`;
      if (p.missing_resources) {
        html += `<div class="sheet-row"><div class="sheet-label">有 ${p.missing_resources} 个资源本机缺失（需先在电脑端下载完整资源）。</div></div>`;
      }
      html += seg("voiceStop", [
        {
          group: "语音停止时机",
          value: "click",
          label: "点击时",
          active: prefs.voiceStop !== "next",
        },
        {
          group: "语音停止时机",
          value: "next",
          label: "下一句语音前",
          active: prefs.voiceStop === "next",
        },
      ]);
      html += seg("orientation", [
        { group: "屏幕", value: "auto", label: "跟随", active: prefs.orientation === "auto" },
        { group: "屏幕", value: "portrait", label: "竖屏", active: prefs.orientation === "portrait" },
        { group: "屏幕", value: "landscape", label: "横屏", active: prefs.orientation === "landscape" },
      ]);
      els.sheet.innerHTML = html;
      els.sheetMask.hidden = false;
      showChrome(true);
      return;
    }

    const videos = currentVideos();
    const hasPages = (p.pages || p.images || []).length > 0;
    const hasOmake = (p.omake || []).length > 0;
    const hasManga = hasPages || hasOmake;
    const isPurchased = p.kind === "purchased";

    let html = `<div class="sheet-title">阅读设置</div>`;
    html += seg("surface", [
      { group: "内容", value: "manga", label: "漫画", active: state.surface === "manga", disabled: !hasManga },
      { group: "内容", value: "video", label: "动态", active: state.surface === "video", disabled: !videos.length },
    ]);
    if (isPurchased && hasManga) {
      html += seg("album", [
        { group: "图集", value: "story", label: `主线 (${(p.pages || []).length})`, active: state.album === "story", disabled: !hasPages },
        { group: "图集", value: "omake", label: `特典 (${(p.omake || []).length})`, active: state.album === "omake", disabled: !hasOmake },
      ]);
      html += seg("readMode", [
        { group: "阅读", value: "page", label: "翻页", active: prefs.readMode === "page" },
        { group: "阅读", value: "webtoon", label: "条漫", active: prefs.readMode === "webtoon" },
      ]);
      html += seg("rtl", [
        { group: "翻页方向", value: "ltr", label: "从左往右", active: !prefs.rtl },
        { group: "翻页方向", value: "rtl", label: "从右往左", active: prefs.rtl },
      ]);
      html += `<div class="sheet-row"><div class="sheet-label">条漫边距 ${prefs.margin} px</div><input class="sheet-range" id="sheet-margin" type="range" min="0" max="120" step="4" value="${prefs.margin}"></div>`;
    }
    html += seg("orientation", [
      { group: "屏幕", value: "auto", label: "跟随", active: prefs.orientation === "auto" },
      { group: "屏幕", value: "portrait", label: "竖屏", active: prefs.orientation === "portrait" },
      { group: "屏幕", value: "landscape", label: "横屏", active: prefs.orientation === "landscape" },
    ]);
    if (videos.length > 1) {
      html += `<div class="sheet-row"><div class="sheet-label">动态选集</div><div class="sheet-clips">`;
      videos.forEach((clip, i) => {
        html += `<button type="button" data-act="clip" data-val="${i}" class="${i === state.clipIndex ? "active" : ""}">${esc(clip.name || "片段 " + (i + 1))}</button>`;
      });
      html += `</div></div>`;
    }
    els.sheet.innerHTML = html;
    els.sheetMask.hidden = false;
    showChrome(true);
  }

  function closeSheet() {
    els.sheetMask.hidden = true;
    showChrome();
  }

  function onSheetClick(e) {
    const btn = e.target.closest("button[data-act]");
    if (!btn || btn.disabled) return;
    const act = btn.getAttribute("data-act");
    const val = btn.getAttribute("data-val");
    if (act === "surface") setSurface(val);
    else if (act === "album") {
      saveMangaProgress();
      state.album = val;
      const saved = state.progress.manga[mangaProgressKey()];
      state.pageIndex = saved ? Math.max(0, Number(saved.pageIndex) || 0) : 0;
      if (state.surface !== "manga") state.surface = "manga";
      renderPlayer();
    } else if (act === "readMode") {
      saveMangaProgress();
      prefs.readMode = val;
      saveReaderPrefs();
      renderPlayer();
    } else if (act === "rtl") {
      prefs.rtl = val === "rtl";
      saveReaderPrefs();
    }     else if (act === "orientation") {
      prefs.orientation = val;
      saveReaderPrefs();
      applyOrientation();
    } else if (act === "voiceStop") {
      prefs.voiceStop = val === "next" ? "next" : "click";
      saveReaderPrefs();
    } else if (act === "clip") {
      saveCurrentProgress();
      state.clipIndex = Number(val) || 0;
      if (!state.progress.video) state.progress.video = { clipIndex: 0, times: {} };
      state.progress.video.clipIndex = state.clipIndex;
      state.surface = "video";
      renderPlayer();
    }
    openSheet();
  }

  function onSheetInput(e) {
    if (e.target.id !== "sheet-margin") return;
    prefs.margin = Number(e.target.value) || 0;
    saveReaderPrefs();
    const label = e.target.previousElementSibling;
    if (label) label.textContent = `条漫边距 ${prefs.margin} px`;
    if (state.surface === "manga" && prefs.readMode === "webtoon") {
      saveMangaProgress();
      renderPlayer();
    }
  }

  function onStageClick(e) {
    if (state.swiped) {
      state.swiped = false;
      return;
    }
    if (!els.sheetMask.hidden) return;

    if (isAdvMode()) {
      const rect = els.playerStage.getBoundingClientRect();
      const x = (e.clientX - rect.left) / Math.max(1, rect.width);
      if (x < 0.28) advanceAdv(-1);
      else advanceAdv(1);
      return;
    }

    if (e.target.closest("video")) {
      showChrome();
      return;
    }
    if (state.surface === "manga" && prefs.readMode === "webtoon") {
      toggleChrome();
      return;
    }
    if (state.surface === "video") {
      toggleChrome();
      return;
    }
    const rect = els.playerStage.getBoundingClientRect();
    const x = (e.clientX - rect.left) / Math.max(1, rect.width);
    if (x < 0.28) turnPage(-1);
    else if (x > 0.72) turnPage(1);
    else toggleChrome();
  }

  function onStageTouchStart(e) {
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    const rect = els.playerStage.getBoundingClientRect();
    const yRatio = rect.height > 0 ? (t.clientY - rect.top) / rect.height : 0;
    // 视频底部控件区不抢滑动，避免和进度条冲突
    const nearControls = state.surface === "video" && yRatio > 0.86;
    state.touch = {
      x: t.clientX,
      y: t.clientY,
      t: Date.now(),
      nearControls,
    };
  }

  function onStageTouchEnd(e) {
    const start = state.touch;
    state.touch = null;
    if (!start || !e.changedTouches.length || start.nearControls) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);

    if (isAdvMode()) {
      if (absX < 50 || absX < absY * 1.15) return;
      state.swiped = true;
      e.preventDefault();
      if (dx < 0) advanceAdv(1);
      else advanceAdv(-1);
      return;
    }

    if (state.surface === "video") {
      const hasManga =
        ((state.player.pages || state.player.images || []).length > 0) ||
        ((state.player.omake || []).length > 0);
      // 右往左：回图片
      if (absX >= 64 && absX > absY * 1.1 && dx < 0 && hasManga) {
        state.swiped = true;
        e.preventDefault();
        setSurface("manga");
        return;
      }
      // 上下：切换视频
      if (absY >= 64 && absY > absX * 1.1) {
        state.swiped = true;
        e.preventDefault();
        if (dy < 0) turnClip(1);
        else turnClip(-1);
      }
      return;
    }

    if (absX < 50 || absX < absY * 1.15) return;
    state.swiped = true;
    e.preventDefault();
    if (state.surface === "manga" && prefs.readMode === "webtoon") {
      if (dx < 0 && currentVideos().length) setSurface("video");
      return;
    }
    if (state.surface !== "manga") return;
    if (dx < 0) turnPage(1);
    else turnPage(-1);
  }

  async function refreshCurrentItems() {
    if (!state.gameId || !state.catStack.length) return;
    const cat = state.catStack[state.catStack.length - 1];
    try {
      const data = await api(`/api/games/${encodeURIComponent(state.gameId)}/items`, {
        cat: cat.key,
      });
      const items = data.items || [];
      state.listCache[listCacheKey(cat.key)] = items;
      renderItemsList(items, cat.title || cat.key);
    } catch (e) {
      /* 列表刷新失败不影响关闭播放 */
    }
  }

  async function openPlayer(sceneId, title) {
    showSplash("正在准备…", 30, title || sceneId);
    try {
      if (needsAdvPrepare()) {
        await prepareAdvScene(sceneId, title);
        showSplash("正在载入台本…", 92, title || sceneId);
      }
      const data = await api(`/api/games/${encodeURIComponent(state.gameId)}/scene`, { sid: sceneId });
      hideSplash();
      state.player = data;
      state.playedSceneId = sceneId;
      state.album = (data.pages && data.pages.length) || !(data.omake && data.omake.length) ? "story" : "omake";
      state.pageIndex = 0;
      state.clipIndex = 0;
      state.beatIndex = 0;
      state.progress = emptyProgress();
      state.lastAdvBg = "";
      state.lastAdvMovie = null;
      const hasManga = (data.pages || []).length || (data.omake || []).length || (data.images || []).length;
      const hasVideo = (data.videos || []).length;
      if (data.kind === "purchased") {
        state.surface = hasManga ? "manga" : hasVideo ? "video" : "manga";
      } else if (data.kind === "adv" && (data.beats || []).length) {
        state.surface = "manga";
      } else {
        state.surface = hasVideo ? "video" : "manga";
      }
      els.playerTitle.textContent = data.title || title || sceneId;
      els.playerView.classList.add("show");
      if (data.note && !(data.beats || []).length) {
        alert(data.note);
      }
      renderPlayer();
      showChrome();
      applyOrientation();
    } catch (e) {
      hideSplash();
      if (e && e.name === "PrepareCancelledError") return;
      alert(e.message || String(e));
    }
  }

  function closePlayer() {
    const shouldRefresh = needsAdvPrepare() && !!state.playedSceneId;
    saveCurrentProgress();
    stopVoice();
    stopStageVideos();
    unlockOrientation();
    closeSheet();
    hideChrome();
    els.advDialogue.hidden = true;
    els.playerView.classList.remove("show");
    els.playerStage.innerHTML = "";
    els.playerStage.classList.remove("adv-mode", "webtoon");
    state.player = null;
    state.playedSceneId = "";
    state.progress = emptyProgress();
    state.lastAdvBg = "";
    state.lastAdvMovie = null;
    if (shouldRefresh) refreshCurrentItems();
  }

  function isPlayerOpen() {
    return els.playerView.classList.contains("show");
  }

  function canGoBackInApp() {
    if (els.splash && els.splash.classList.contains("show") && state.prepareSceneId) return true;
    if (!els.sheetMask.hidden) return true;
    if (isPlayerOpen()) return true;
    if (state.view === "items" || state.view === "categories") return true;
    return false;
  }

  function performAppBack() {
    if (els.splash && els.splash.classList.contains("show") && state.prepareSceneId) {
      cancelPrepare(state.prepareSceneId);
      showSplash("正在取消…", 100, "", { cancellable: false });
      return true;
    }
    if (!els.sheetMask.hidden) {
      closeSheet();
      return true;
    }
    if (isPlayerOpen()) {
      closePlayer();
      return true;
    }
    if (state.view === "items") {
      if (state.catStack.length > 1) {
        state.catStack.pop();
        const parent = state.catStack[state.catStack.length - 1];
        openCategory(parent.key, parent.title, false, { skipPush: true });
      } else {
        state.catStack = [];
        els.title.textContent = state.gameName;
        setView("categories");
      }
      return true;
    }
    if (state.view === "categories") {
      loadGames();
      return true;
    }
    return false;
  }

  function armSystemBackTrap() {
    try {
      history.pushState({ app: "offline-player" }, "");
    } catch (e) {}
  }

  window.addEventListener("popstate", () => {
    if (performAppBack()) {
      // 还在应用内层级时，再垫一层，避免下一次系统返回直接退出浏览器
      if (canGoBackInApp()) armSystemBackTrap();
    }
  });

  els.back.addEventListener("click", () => {
    performAppBack();
  });

  if (els.splashCancel) {
    els.splashCancel.addEventListener("click", () => {
      const sid = state.prepareSceneId;
      cancelPrepare(sid);
      showSplash("正在取消…", 100, "", { cancellable: false });
    });
  }

  els.playerClose.addEventListener("click", closePlayer);
  els.playerMotion.addEventListener("click", () => {
    setSurface(state.surface === "video" ? "manga" : "video");
  });
  els.playerMore.addEventListener("click", openSheet);
  els.sheetMask.addEventListener("click", (e) => {
    if (e.target === els.sheetMask) closeSheet();
  });
  els.sheet.addEventListener("click", onSheetClick);
  els.sheet.addEventListener("input", onSheetInput);
  els.playerStage.addEventListener("click", onStageClick);
  els.playerStage.addEventListener("touchstart", onStageTouchStart, { passive: true });
  els.playerStage.addEventListener("touchend", onStageTouchEnd, { passive: false });
  els.playerStage.addEventListener(
    "scroll",
    () => {
      if (state.surface === "manga" && prefs.readMode === "webtoon") onWebtoonScroll();
    },
    { passive: true }
  );

  (async function boot() {
    try {
      const ping = await api("/api/ping");
      if (ping.token_required && !getToken()) {
        const t = prompt("请输入访问令牌（settings.json 局域网.token）");
        if (t) localStorage.setItem(TOKEN_KEY, t);
      }
      await loadGames();
      armSystemBackTrap();
    } catch (e) {
      els.gamesList.innerHTML = `<div class='empty-state'>${esc(e.message)}<br><br>请确认电脑已运行 serve_lan.bat，且手机与电脑在同一 WiFi。</div>`;
      setView("games");
      armSystemBackTrap();
    }
  })();
})();
