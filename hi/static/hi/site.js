(() => {
  "use strict";
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduced && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0, rootMargin: "0px 0px 160px 0px" },
    );
    document.querySelectorAll("[data-reveal]").forEach((node) => {
      node.classList.add("will-reveal");
      observer.observe(node);
    });
  }
  document.querySelectorAll(".language-switch").forEach((form) =>
    form.addEventListener("submit", (event) => {
      const language = event.submitter?.value;
      if (!language || language === document.documentElement.lang) return;
      form.querySelector(".language-track").dataset.language = language;
      if (!reduced) {
        event.preventDefault();
        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "language";
        hidden.value = language;
        form.append(hidden);
        document.body.classList.add("language-changing");
        setTimeout(() => HTMLFormElement.prototype.submit.call(form), 160);
      }
    }),
  );
  document.querySelectorAll(".rating-option input").forEach((input) =>
    input.addEventListener("change", () => {
      input.closest(".rating-options").classList.remove("rating-selected");
      requestAnimationFrame(() =>
        input.closest(".rating-options").classList.add("rating-selected"),
      );
    }),
  );
  document.addEventListener("click", (event) =>
    document.querySelectorAll(".account-menu[open]").forEach((menu) => {
      if (!menu.contains(event.target)) menu.open = false;
    }),
  );
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape")
      document
        .querySelectorAll(".account-menu[open]")
        .forEach((menu) => (menu.open = false));
  });
  let activeHover = null;
  document.addEventListener(
    "play",
    (event) => {
      if (!event.target.matches("video,audio")) return;
      if (activeHover?.video === event.target) return;
      activeHover?.stop();
      document.querySelectorAll("video,audio").forEach((media) => {
        if (media !== event.target) media.pause();
      });
    },
    true,
  );
  const hoverVideos = new WeakMap();
  const canHover = matchMedia("(hover: hover) and (pointer: fine)");
  function prepareHover(video) {
    if (hoverVideos.has(video)) return;
    const surface =
      video.closest(".video-preview") ||
      (video.closest(".media-card") ? video : null);
    if (!surface) return;
    let timer,
      saved = null;
    const stop = (keepPosition = false) => {
      clearTimeout(timer);
      if (!saved) return;
      const previous = saved;
      saved = null;
      video.pause();
      video.muted = previous.muted;
      video.loop = previous.loop;
      video.controls = previous.controls;
      if (!keepPosition && video.readyState >= 1) {
        try {
          video.currentTime = previous.time;
        } catch (_) {}
      }
      if (activeHover?.video === video) activeHover = null;
    };
    const enter = (event) => {
      if (event.pointerType !== "mouse" || !canHover.matches) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (
          !video.isConnected ||
          !surface.matches(":hover") ||
          video.closest("[hidden]") ||
          document.hidden ||
          !video.paused
        )
          return;
        // A hover must never interrupt listening or a deliberately started movie.
        const occupied = [...document.querySelectorAll("video,audio")].some(
          (media) =>
            media !== video &&
            !media.paused &&
            !media.ended &&
            media !== activeHover?.video,
        );
        if (occupied) return;
        activeHover?.stop();
        videoPreviews.get(video)?.cancel();
        saved = {
          muted: video.muted,
          loop: video.loop,
          controls: video.controls,
          time: video.currentTime,
        };
        const attempt = saved;
        activeHover = { video, stop };
        video.muted = true;
        video.loop = true;
        // A frame click starts normal playback; native controls return then.
        // Otherwise a click on the temporary preview's Pause control can get
        // swallowed inside the browser's media-control shadow tree.
        video.controls = false;
        try {
          const playback = video.play();
          playback?.catch(() => {
            if (saved === attempt) stop();
          });
        } catch (_) {
          stop();
        }
      }, 180);
    };
    const interact = () => {
      if (surface !== video) stop(true);
    };
    const key = () => stop(true);
    const activate = (event) => {
      if (!saved || !saved.controls) return;
      event.preventDefault();
      stop(true);
      video.play()?.catch(() => {});
    };
    const leave = () => stop();
    surface.addEventListener("pointerenter", enter);
    surface.addEventListener("pointerleave", leave);
    surface.addEventListener("pointerdown", interact, true);
    surface.addEventListener("keydown", key, true);
    surface.addEventListener("click", activate, true);
    video.addEventListener("error", leave);
    hoverVideos.set(video, {
      destroy: () => {
        stop();
        surface.removeEventListener("pointerenter", enter);
        surface.removeEventListener("pointerleave", leave);
        surface.removeEventListener("pointerdown", interact, true);
        surface.removeEventListener("keydown", key, true);
        surface.removeEventListener("click", activate, true);
        video.removeEventListener("error", leave);
      },
    });
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) activeHover?.stop();
  });
  window.addEventListener("pagehide", () => activeHover?.stop());
  canHover.addEventListener("change", () => {
    if (!canHover.matches) activeHover?.stop();
  });
  // Decode one still frame near the viewport; never call play() for a preview.
  // Existing posters need no video request. Audio players remain preload=none.
  const videoPreviews = new WeakMap();
  const previewObserver =
    "IntersectionObserver" in window
      ? new IntersectionObserver(
          (entries) => {
            entries.forEach(({ target, isIntersecting }) => {
              if (isIntersecting) videoPreviews.get(target)?.load();
            });
          },
          { rootMargin: "240px 0px" },
        )
      : null;
  function preparePreview(video) {
    prepareHover(video);
    if (
      !video.hasAttribute("data-video-preview") ||
      videoPreviews.has(video) ||
      video.hasAttribute("poster")
    )
      return;
    let started = false,
      finished = false,
      timer;
    const events = [];
    const listen = (name, handler) => {
      video.addEventListener(name, handler);
      events.push([name, handler]);
    };
    const finish = () => {
      finished = true;
      clearTimeout(timer);
      previewObserver?.unobserve(video);
      events.forEach(([name, handler]) =>
        video.removeEventListener(name, handler),
      );
    };
    const seek = () => {
      // A user who has already started or sought the video takes precedence.
      if (
        finished ||
        !video.paused ||
        video.currentTime > 0 ||
        !video.isConnected
      ) {
        finish();
        return;
      }
      if (!Number.isFinite(video.duration) || video.duration <= 0) {
        finish();
        return;
      }
      try {
        video.currentTime = Math.min(0.1, video.duration / 2);
      } catch (_) {
        finish();
      }
    };
    const load = () => {
      if (started || finished || !video.isConnected) return;
      started = true;
      timer = setTimeout(finish, 15000);
      listen("loadedmetadata", seek);
      listen("seeked", finish);
      listen("error", finish);
      if (video.readyState >= 1) seek();
      else {
        video.preload = "metadata";
        video.load();
      }
    };
    // Native controls must remain responsive, including a quick Play click.
    ["pointerdown", "keydown", "play"].forEach((name) => listen(name, finish));
    videoPreviews.set(video, { load, cancel: finish });
    if (previewObserver) previewObserver.observe(video);
    else load();
  }
  function eachPreview(root, callback) {
    if (root.nodeType !== 1) return;
    if (root.matches("video")) callback(root);
    root.querySelectorAll("video").forEach(callback);
  }
  eachPreview(document.documentElement, preparePreview);
  // The application inserts and removes its cards and detail player dynamically.
  new MutationObserver((records) => {
    records.forEach((record) => {
      if (record.type === "attributes") {
        if (activeHover?.video.closest("[hidden]")) activeHover.stop();
        return;
      }
      record.removedNodes.forEach((node) =>
        eachPreview(node, (video) => {
          if (video.isConnected) return;
          videoPreviews.get(video)?.cancel();
          videoPreviews.delete(video);
          hoverVideos.get(video)?.destroy();
          hoverVideos.delete(video);
        }),
      );
      record.addedNodes.forEach((node) => eachPreview(node, preparePreview));
    });
  }).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["hidden"],
  });
  document.querySelectorAll("[data-media-image]").forEach((image) => {
    const fail = () => {
      if (image.parentElement.querySelector(".media-unavailable")) return;
      const text = document.createElement("span");
      text.className = "media-unavailable";
      text.textContent = image.dataset.errorMessage;
      image.hidden = true;
      image.after(text);
    };
    image.addEventListener("error", fail);
    if (image.complete && !image.naturalWidth) fail();
  });
  document.addEventListener(
    "error",
    (event) => {
      const player = event.target.closest?.(".media-player");
      if (player && event.target.matches("video,audio,source")) {
        const notice = player.querySelector(".player-notice");
        if (notice) notice.hidden = false;
      }
    },
    true,
  );
  document.querySelectorAll("[data-avatar-fallback]").forEach((image) => {
    const fail = () => {
      const letter = document.createElement("span");
      letter.className = image.className;
      letter.textContent = image.dataset.avatarFallback;
      image.replaceWith(letter);
    };
    image.addEventListener("error", fail);
    if (image.complete && !image.naturalWidth) fail();
  });
  document.querySelectorAll("form[data-confirm-delete]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirmDelete)) event.preventDefault();
    });
  });
})();
