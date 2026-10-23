(function () {
    'use strict';

    const API_URL = '/api/media/';

    // DOM
    const viewList = document.getElementById('view-list');
    const viewDetail = document.getElementById('view-detail');
    const grid = document.getElementById('grid');
    const loading = document.getElementById('loading');
    const errorEl = document.getElementById('error');
    const detailBody = document.getElementById('detail-body');
    const refreshBtn = document.getElementById('refresh-btn');
    const backBtn = document.getElementById('back-btn');

    let cache = [];

    // ---------- Утилиты ----------
    function escapeHtml(s) {
        if (!s) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatDate(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' });
    }

    function showList() {
        viewDetail.hidden = true;
        viewList.hidden = false;
        window.scrollTo(0, 0);
    }

    function showDetail() {
        viewList.hidden = true;
        viewDetail.hidden = false;
        window.scrollTo(0, 0);
    }

    // ---------- Загрузка списка ----------
    async function loadList() {
        loading.hidden = false;
        errorEl.hidden = true;
        grid.hidden = true;
        grid.innerHTML = '';

        try {
            const resp = await fetch(API_URL, { headers: { 'Accept': 'application/json' } });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();

            cache = data.results || [];

            loading.hidden = true;

            if (cache.length === 0) {
                grid.hidden = false;
                grid.innerHTML = '<div class="state" style="grid-column: 1/-1;">Пока нет медиа.</div>';
                return;
            }

            grid.hidden = false;
            cache.forEach(item => {
                const card = document.createElement('div');
                card.className = 'card';
                card.dataset.id = item.id;
                card.innerHTML =
                    '<img class="card-image" src="' + item.image + '" alt="' + escapeHtml(item.title) + '" loading="lazy">' +
                    '<div class="card-body">' +
                        '<div class="card-title">' + escapeHtml(item.title) + '</div>' +
                        '<div class="card-date">' + formatDate(item.created_at) + '</div>' +
                    '</div>';
                card.addEventListener('click', () => openDetail(item.id));
                grid.appendChild(card);
            });

        } catch (err) {
            loading.hidden = true;
            errorEl.hidden = false;
            errorEl.textContent = 'Не удалось загрузить. Проверьте соединение.';
            console.error(err);
        }
    }

    // ---------- Открытие детали ----------
    function openDetail(id) {
        const item = cache.find(x => String(x.id) === String(id));
        if (!item) return;

        const authorName = item.author ? item.author.username : '—';

        detailBody.innerHTML =
            '<img class="detail-image" src="' + item.image + '" alt="' + escapeHtml(item.title) + '">' +
            '<h2 class="detail-title">' + escapeHtml(item.title) + '</h2>' +
            '<div class="detail-meta">' +
                '<span>' + escapeHtml(authorName) + '</span>' +
                '<span>' + formatDate(item.created_at) + '</span>' +
            '</div>' +
            '<div class="detail-description">' + escapeHtml(item.description || '') + '</div>';

        showDetail();
    }

    // ---------- Кнопки ----------
    refreshBtn.addEventListener('click', loadList);
    backBtn.addEventListener('click', showList);

    // Кнопка «назад» в браузере / телефоне
    window.addEventListener('popstate', () => {
        if (!viewDetail.hidden) {
            showList();
            history.pushState({ view: 'list' }, '');
        }
    });

    history.pushState({ view: 'list' }, '');

    // ---------- Service Worker (офлайн-кэш) ----------
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/hi/sw.js').catch(() => {});
        });
    }

    // ---------- Старт ----------
    loadList();
})();