(() => {
  "use strict";
  const t = window.gettext || ((value) => value);
  const locale = document.documentElement.lang;
  const apiTest = !!document.getElementById("raw-json");
  const viewList = document.getElementById("view-list");
  const viewDetail = document.getElementById("view-detail");
  const grid = document.getElementById("grid");
  const loading = document.getElementById("loading");
  const errorEl = document.getElementById("error");
  const detailBody = document.getElementById("detail-body");
  const more = document.getElementById("load-more");
  const status = document.getElementById("api-status");
  let cache = [],
    nextUrl = null,
    busy = false;
  function element(tag, className, value) {
    const node = document.createElement(tag);
    node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function mediaElement(item, preview = false) {
    if (!item.image) return null;
    const kind = item.media_kind || "image";
    if (kind === "image") {
      const image = element("img", preview ? "card-image" : "detail-image");
      image.src = item.image;
      image.alt = preview ? "" : item.title;
      image.loading = "lazy";
      image.decoding = "async";
      return image;
    }
    if (preview) {
      if (item.poster && kind !== "video") {
        const image = element("img", "card-image");
        image.src = item.poster;
        image.alt = "";
        image.loading = "lazy";
        image.decoding = "async";
        return image;
      }
      if (kind === "video") {
        const wrapper = element("span", "media-preview video-preview");
        const video = element("video", "card-image");
        video.src = item.image;
        video.preload = "none";
        video.muted = true;
        video.playsInline = true;
        if (item.poster) video.poster = item.poster;
        else video.dataset.videoPreview = "";
        video.setAttribute("aria-hidden", "true");
        video.tabIndex = -1;
        wrapper.append(video, element("span", "video-preview-icon", "▶"));
        return wrapper;
      }
      return element("span", "media-preview", kind === "audio" ? "♫" : "▶");
    }
    const wrapper = element("div", "media-player");
    if (kind === "audio" || kind === "video") {
      const player = element(kind, "");
      player.controls = true;
      player.preload = "metadata";
      player.setAttribute("aria-label", item.title);
      if (kind === "video") {
        player.playsInline = true;
        if (item.poster) player.poster = item.poster;
        else player.dataset.videoPreview = "";
      }
      player.src = item.image;
      player.addEventListener("error", () => {
        if (!wrapper.querySelector(".player-notice"))
          wrapper.append(
            element(
              "p",
              "player-notice",
              t("Не удалось воспроизвести файл. Его можно скачать."),
            ),
          );
      });
      wrapper.append(player);
    }
    const link = element("a", "media-download", t("Скачать файл"));
    link.href = item.image;
    link.download = "";
    wrapper.append(link);
    return wrapper;
  }
  function formatDate(value) {
    return new Date(value).toLocaleDateString(locale, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }
  function pauseDetail() {
    detailBody?.querySelectorAll("video,audio").forEach((e) => {
      e.pause();
      e.removeAttribute("src");
      e.load();
    });
  }
  function showList() {
    pauseDetail();
    if (viewDetail) viewDetail.hidden = true;
    viewList.hidden = false;
  }
  function openDetail(item, push = true) {
    if (apiTest) {
      location.href = "/posts/" + Number(item.id) + "/";
      return;
    }
    pauseDetail();
    detailBody.replaceChildren();
    const media = mediaElement(item);
    if (media) detailBody.append(media);
    detailBody.append(element("h2", "detail-title", item.title));
    const meta = element("div", "detail-meta");
    meta.append(
      element("span", "", item.author?.username || "МойСайт"),
      element("span", "", formatDate(item.created_at)),
    );
    detailBody.append(meta);
    detailBody.append(
      element("p", "detail-description", item.description || ""),
    );
    const link = element(
      "a",
      "post-discussion-link",
      t("Комментарии и оценки") + " →",
    );
    link.href = "/posts/" + Number(item.id) + "/";
    detailBody.append(link);
    viewList.hidden = true;
    viewDetail.hidden = false;
    window.scrollTo({ top: 0, behavior: "instant" });
    if (push)
      history.pushState({ post: item.id }, "", "#post-" + Number(item.id));
  }
  function appendCard(item) {
    const card = element("button", "card");
    card.type = "button";
    card.setAttribute("aria-label", item.title);
    const media = mediaElement(item, true);
    if (media) card.append(media);
    const body = element("span", "card-body");
    body.append(
      element("span", "card-title", item.title),
      element("span", "card-date", formatDate(item.created_at)),
    );
    const summary = element("span", "card-summary");
    summary.append(
      element(
        "span",
        "",
        "★ " +
          (item.rating_count
            ? Number(item.average_rating).toLocaleString(locale, {
                maximumFractionDigits: 1,
              })
            : "—"),
      ),
      element("span", "", t("Комментарии") + " · " + (item.comment_count || 0)),
    );
    body.append(summary);
    card.append(body);
    card.addEventListener("click", () => openDetail(item));
    grid.append(card);
  }
  async function loadList(append = false) {
    if (busy) return;
    busy = true;
    more.disabled = true;
    errorEl.hidden = true;
    if (!append) {
      cache = [];
      nextUrl = null;
      grid.replaceChildren();
      grid.hidden = true;
      loading.hidden = false;
      showList();
    }
    try {
      const url = append ? nextUrl : "/api/media/";
      if (!url) return;
      const target = new URL(url, location.origin);
      if (target.origin !== location.origin) throw Error("Invalid origin");
      const response = await fetch(target, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw Error("HTTP " + response.status);
      const data = await response.json();
      cache.push(...(data.results || []));
      nextUrl = data.next;
      (data.results || []).forEach(appendCard);
      loading.hidden = true;
      grid.hidden = false;
      if (!cache.length) {
        const empty = element("div", "state", t("Пока нет медиа."));
        grid.append(empty);
      }
      more.hidden = !nextUrl;
      if (apiTest) {
        document.getElementById("raw-json").textContent = JSON.stringify(
          data,
          null,
          2,
        );
        status.textContent =
          t("Всего записей:") +
          " " +
          data.count +
          " · " +
          t("Показано:") +
          " " +
          cache.length;
      }
    } catch (error) {
      loading.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = t("Не удалось загрузить. Проверьте соединение.");
    } finally {
      busy = false;
      more.disabled = false;
    }
  }
  document
    .getElementById("refresh-btn")
    .addEventListener("click", () => loadList());
  document.getElementById("back-btn")?.addEventListener("click", () => {
    if (location.hash.startsWith("#post-")) history.back();
    else showList();
  });
  more.addEventListener("click", () => loadList(true));
  window.addEventListener("popstate", () => {
    const match = location.hash.match(/^#post-(\d+)$/);
    const item = match && cache.find((p) => Number(p.id) === Number(match[1]));
    if (item) openDetail(item, false);
    else showList();
  });
  if (!apiTest && "serviceWorker" in navigator)
    navigator.serviceWorker.register("/static/hi/sw.js").catch(() => {});
  loadList();
})();
