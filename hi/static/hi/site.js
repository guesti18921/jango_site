(() => {
    'use strict';
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!reduced && 'IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => entries.forEach(entry => {
            if (entry.isIntersecting) { entry.target.classList.add('is-visible'); observer.unobserve(entry.target); }
        }), {threshold: 0.06});
        document.querySelectorAll('[data-reveal]').forEach(node => { node.classList.add('will-reveal'); observer.observe(node); });
    }
    document.querySelectorAll('.language-switch').forEach(form => form.addEventListener('submit', event => {
        const language = event.submitter?.value;
        if (!language || language === document.documentElement.lang) return;
        form.querySelector('.language-track').dataset.language = language;
        if (!reduced) {
            event.preventDefault();
            const hidden = document.createElement('input'); hidden.type = 'hidden'; hidden.name = 'language'; hidden.value = language;
            form.append(hidden);
            document.body.classList.add('language-changing');
            setTimeout(() => HTMLFormElement.prototype.submit.call(form), 160);
        }
    }));
    document.querySelectorAll('.rating-option input').forEach(input => input.addEventListener('change', () => {
        input.closest('.rating-options').classList.remove('rating-selected');
        requestAnimationFrame(() => input.closest('.rating-options').classList.add('rating-selected'));
    }));
    document.addEventListener('click', event => document.querySelectorAll('.account-menu[open]').forEach(menu => {
        if (!menu.contains(event.target)) menu.open = false;
    }));
    document.addEventListener('keydown', event => { if (event.key === 'Escape') document.querySelectorAll('.account-menu[open]').forEach(menu => menu.open = false); });
})();
