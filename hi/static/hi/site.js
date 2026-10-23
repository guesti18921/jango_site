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
  document.addEventListener(
    "play",
    (event) => {
      if (!event.target.matches("video,audio")) return;
      document.querySelectorAll("video,audio").forEach((media) => {
        if (media !== event.target) media.pause();
      });
    },
    true,
  );
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
