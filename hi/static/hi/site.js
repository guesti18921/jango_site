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
  const connection = navigator.connection;
  const restrainedNetwork = () =>
    connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType || "");
  function prepareHover(video) {
    if (hoverVideos.has(video)) return;
    const surface =
      video.closest(".video-preview") ||
      (video.closest(".media-card") ? video : null);
    if (!surface) return;
    let timer,
      limit,
      saved = null;
    const stop = (keepPosition = false) => {
      clearTimeout(timer);
      clearTimeout(limit);
      if (!saved) return;
      const previous = saved;
      saved = null;
      video.pause();
      video.muted = previous.muted;
      video.loop = previous.loop;
      video.controls = previous.controls;
      video.classList.remove("is-hover-preview");
      if (!keepPosition && video.readyState >= 1) {
        video.classList.add("is-preview-restoring");
        const reveal = () => video.classList.remove("is-preview-restoring");
        video.addEventListener("seeked", reveal, { once: true });
        setTimeout(reveal, 250);
        try {
          if (previous.time === 0 && video.hasAttribute("poster")) {
            // Reset the native poster flag without preloading the movie again.
            video.preload = "none";
            video.load();
          } else video.currentTime = previous.time;
        } catch (_) {}
      }
      if (activeHover?.video === video) activeHover = null;
    };
    const enter = (event) => {
      if (
        event.pointerType !== "mouse" ||
        !canHover.matches ||
        reduced ||
        restrainedNetwork()
      )
        return;
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
        video.loop = false;
        video.classList.remove("is-preview-restoring");
        video.classList.add("is-hover-preview");
        // A frame click starts normal playback; native controls return then.
        // Otherwise a click on the temporary preview's Pause control can get
        // swallowed inside the browser's media-control shadow tree.
        video.controls = false;
        limit = setTimeout(() => stop(), 4000);
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
    video.addEventListener("ended", leave);
    hoverVideos.set(video, {
      destroy: () => {
        stop();
        surface.removeEventListener("pointerenter", enter);
        surface.removeEventListener("pointerleave", leave);
        surface.removeEventListener("pointerdown", interact, true);
        surface.removeEventListener("keydown", key, true);
        surface.removeEventListener("click", activate, true);
        video.removeEventListener("error", leave);
        video.removeEventListener("ended", leave);
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
  const previewQueue = [];
  let previewJobs = 0;
  function pumpPreviews() {
    const capacity = restrainedNetwork() ? 1 : 2;
    while (previewJobs < capacity && previewQueue.length) {
      const job = previewQueue.shift();
      if (job.cancelled) continue;
      previewJobs++;
      job.run(() => {
        previewJobs--;
        pumpPreviews();
      });
    }
  }
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
      timer,
      release,
      job,
      sampled = false;
    const events = [];
    const listen = (name, handler) => {
      video.addEventListener(name, handler);
      events.push([name, handler]);
    };
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (video.paused && video.closest(".media-card,.video-preview"))
        video.preload = "none";
      if (job) job.cancelled = true;
      if (release) {
        const done = release;
        release = null;
        done();
      }
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
        video.currentTime = Math.min(3, video.duration * 0.12);
      } catch (_) {
        finish();
      }
    };
    const frameReady = () => {
      // Avoid an opening black frame, with only one additional bounded seek.
      if (
        !sampled &&
        !restrainedNetwork() &&
        video.paused &&
        video.videoWidth
      ) {
        sampled = true;
        try {
          const canvas = document.createElement("canvas");
          canvas.width = 16;
          canvas.height = 9;
          const ctx = canvas.getContext("2d", { willReadFrequently: true });
          ctx.drawImage(video, 0, 0, 16, 9);
          const pixels = ctx.getImageData(0, 0, 16, 9).data;
          let brightness = 0;
          for (let i = 0; i < pixels.length; i += 4)
            brightness += Math.max(pixels[i], pixels[i + 1], pixels[i + 2]);
          if (brightness / 144 < 10) {
            video.currentTime = Math.min(6, video.duration * 0.3);
            return;
          }
        } catch (_) {
          /* A cross-origin decoder still provides its first frame. */
        }
      }
      finish();
    };
    const load = () => {
      if (started || finished || !video.isConnected) return;
      started = true;
      job = {
        cancelled: false,
        run: (done) => {
          release = done;
          if (finished || !video.isConnected || !video.paused) {
            finish();
            return;
          }
          const box = video.getBoundingClientRect();
          if (
            previewObserver &&
            (video.closest("[hidden]") ||
              !box.width ||
              !box.height ||
              box.bottom < -240 ||
              box.top > innerHeight + 240)
          ) {
            // A queued card may have scrolled away while another was decoding.
            // Keep observing it so returning to the card can try again.
            job.cancelled = true;
            release = null;
            started = false;
            done();
            return;
          }
          timer = setTimeout(finish, 20000);
          listen("loadedmetadata", seek);
          listen("seeked", frameReady);
          listen("error", finish);
          if (video.readyState >= 1) seek();
          else {
            video.preload = "metadata";
          }
        },
      };
      previewQueue.push(job);
      pumpPreviews();
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
  const visualMedia = new WeakSet();
  function prepareVisual(media) {
    if (
      visualMedia.has(media) ||
      !media.matches(".post-media-image,.card-image,.detail-image,video")
    )
      return;
    visualMedia.add(media);
    const isImage = media.tagName === "IMG";
    if (!isImage && media.hasAttribute("poster")) return;
    const ready = () => media.classList.remove("media-is-loading");
    const fail = () => {
      ready();
      media.classList.add("media-is-failed");
      if (
        isImage &&
        media.isConnected &&
        !media.parentElement.querySelector(".media-unavailable")
      ) {
        const notice = document.createElement("span");
        notice.className = "media-unavailable";
        notice.textContent =
          media.dataset.errorMessage ||
          (window.gettext || ((v) => v))("Изображение недоступно.");
        media.hidden = true;
        media.after(notice);
      }
    };
    if (isImage ? media.complete : media.readyState >= 2) {
      if (isImage && !media.naturalWidth) fail();
      return;
    }
    media.classList.add("media-is-loading");
    media.addEventListener(isImage ? "load" : "loadeddata", ready, {
      once: true,
    });
    media.addEventListener("error", fail, { once: true });
    // Keep native controls usable even on a stalled connection.
    if (!isImage) setTimeout(ready, 20000);
  }
  function eachVisual(root) {
    if (root.nodeType !== 1) return;
    if (root.matches("img,video")) prepareVisual(root);
    root.querySelectorAll("img,video").forEach(prepareVisual);
  }
  eachVisual(document.documentElement);
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
      record.addedNodes.forEach((node) => {
        eachPreview(node, preparePreview);
        eachVisual(node);
      });
    });
  }).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["hidden"],
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
