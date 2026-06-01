document.addEventListener('DOMContentLoaded', () => {
    const gallery = document.getElementById('gallery');
    const gallerySummary = document.getElementById('gallery-summary');
    const tagTabs = document.getElementById('tag-tabs');
    const monthTabs = document.getElementById('month-tabs');
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const inlineFilterToggle = document.getElementById('inline-filter-toggle');
    const sidebarClose = document.getElementById('sidebar-close');

    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxTitle = document.getElementById('lightbox-title');
    const lightboxDate = document.getElementById('lightbox-date');
    const lightboxClose = document.getElementById('lightbox-close');
    const lightboxPrev = document.getElementById('lightbox-prev');
    const lightboxNext = document.getElementById('lightbox-next');

    const statArtworks = document.getElementById('stat-artworks');
    const statMonths = document.getElementById('stat-months');
    const statNotes = document.getElementById('stat-notes');

    let allArtworks = [];
    let currentArtworks = [];
    let currentIndex = 0;
    let currentFilterLabel = 'All Works';

    const CATEGORIES = {
        IDENTITY: ['Airi', 'Original'],
        HAIR: ['Pink Hair', 'Blue Hair', 'Blonde Hair', 'White Hair', 'Black Hair', 'Silver Hair', 'Brown Hair',
               'Twin Tails', 'Wavy Hair', 'Straight Hair', 'Pony Tail', 'Short Hair', 'Long Hair', 'Medium Hair'],
        CLOTHING: ['School Uniform', 'Dress', 'Lingerie', 'Swimsuit', 'Casual', 'Gothic']
    };

    const LABELS = {
        'All Works': 'すべて',
        'Airi': '愛依莉',
        'Original': 'オリジナル',
        'Pink Hair': 'ピンク髪',
        'Blue Hair': '青髪',
        'Blonde Hair': '金髪',
        'White Hair': '白髪',
        'Black Hair': '黒髪',
        'Silver Hair': '銀髪',
        'Brown Hair': '茶髪',
        'Twin Tails': 'ツインテール',
        'Wavy Hair': 'ウェーブ',
        'Straight Hair': 'ストレート',
        'Pony Tail': 'ポニーテール',
        'Short Hair': 'ショート',
        'Long Hair': 'ロング',
        'Medium Hair': 'ミディアム',
        'School Uniform': '制服',
        'Dress': 'ドレス',
        'Lingerie': 'ランジェリー',
        'Swimsuit': '水着',
        'Casual': 'カジュアル',
        'Gothic': 'ゴシック',
        'Other': 'その他'
    };

    function labelFor(value) {
        return LABELS[value] || value;
    }

    function openSidebar() {
        sidebar.classList.add('open');
        document.body.classList.add('sidebar-open');
        sidebarToggle.setAttribute('aria-expanded', 'true');
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        document.body.classList.remove('sidebar-open');
        sidebarToggle.setAttribute('aria-expanded', 'false');
    }

    function toggleSidebar() {
        if (sidebar.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    }

    sidebarToggle.addEventListener('click', toggleSidebar);
    inlineFilterToggle.addEventListener('click', openSidebar);
    sidebarClose.addEventListener('click', closeSidebar);
    sidebar.addEventListener('click', (event) => {
        if (event.target === sidebar) closeSidebar();
    });

    function getCleanTitle(title) {
        if (!title) return 'Artwork';
        const isSystemName = /\d{3,}/.test(title) ||
            title.toLowerCase().includes('cleanup') ||
            title.toLowerCase().includes('upscale') ||
            title.length > 20;
        return isSystemName ? 'Artwork' : title;
    }

    function updateGallerySummary(count = currentArtworks.length) {
        if (!gallerySummary) return;
        const label = currentFilterLabel === 'All Works' ? 'すべての作品' : `「${labelFor(currentFilterLabel)}」`;
        gallerySummary.textContent = `${label}を ${count} 件表示中`;
    }

    function updateStats(months) {
        if (statArtworks) statArtworks.textContent = allArtworks.length.toString();
        if (statMonths) statMonths.textContent = months[0] || '-';
    }

    function loadGallery() {
        try {
            if (typeof ARTWORKS_DATA === 'undefined') {
                throw new Error('作品データが見つかりません');
            }

            allArtworks = ARTWORKS_DATA;
            const months = [...new Set(allArtworks.map(art => art.date.split('.').slice(0, 2).join('.')))].sort().reverse();
            const uniqueTags = [...new Set(allArtworks.flatMap(art => art.tags || []))].sort();

            updateStats(months);
            createTabs(months, uniqueTags);
            renderGallery(allArtworks, 'All Works');
        } catch (error) {
            console.error('Error loading gallery:', error);
            gallery.innerHTML = '<div class="loading">作品データの読み込みに失敗しました。</div>';
        }
    }

    function createTabs(months, tags) {
        tagTabs.innerHTML = '';
        tagTabs.appendChild(createLabel('表示'));
        const allBtn = createTabBtn('All Works', () => renderGallery(allArtworks, 'All Works'));
        allBtn.classList.add('active');
        tagTabs.appendChild(allBtn);

        addCategory('キャラクター', tags, CATEGORIES.IDENTITY);
        addCategory('髪色・髪型', tags, CATEGORIES.HAIR);
        addCategory('衣装', tags, CATEGORIES.CLOTHING);

        monthTabs.innerHTML = '';
        monthTabs.appendChild(createLabel('月別'));
        months.forEach(month => {
            monthTabs.appendChild(createTabBtn(month, () => filterByMonth(month)));
        });
    }

    function addCategory(label, tags, categoryTags) {
        const filtered = tags.filter(t => categoryTags.includes(t));
        if (filtered.length === 0) return;

        tagTabs.appendChild(createLabel(label));
        filtered.forEach(tag => tagTabs.appendChild(createTabBtn(tag, () => filterByTag(tag))));
    }

    function createLabel(text) {
        const label = document.createElement('div');
        label.className = 'nav-label';
        label.textContent = text;
        return label;
    }

    function createTabBtn(value, onClick) {
        const btn = document.createElement('button');
        btn.className = 'month-btn';
        btn.textContent = labelFor(value);
        btn.setAttribute('data-tag', value);
        btn.type = 'button';
        btn.addEventListener('click', () => {
            document.querySelectorAll('.month-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            onClick();
            if (window.innerWidth < 768) closeSidebar();
        });
        return btn;
    }

    function filterByMonth(month) {
        const filtered = allArtworks.filter(art => art.date.startsWith(month));
        renderGallery(filtered, month);
    }

    function filterByTag(tag) {
        const filtered = allArtworks.filter(art => art.tags && art.tags.includes(tag));
        renderGallery(filtered, tag);
    }

    function renderGallery(artworks, filterLabel = currentFilterLabel) {
        gallery.innerHTML = '';
        currentArtworks = artworks;
        currentFilterLabel = filterLabel;
        updateGallerySummary(artworks.length);

        if (artworks.length === 0) {
            gallery.innerHTML = '<p class="loading">該当する作品がありません。</p>';
            return;
        }

        artworks.forEach((art, index) => {
            const cleanTitle = getCleanTitle(art.title);
            const card = document.createElement('article');
            card.className = 'artwork-card';
            card.tabIndex = 0;

            const tagsHtml = (art.tags || [])
                .filter(tag => tag !== 'Other')
                .slice(0, 4)
                .map(tag => `<span class="tag-pill">${labelFor(tag)}</span>`)
                .join('');

            card.innerHTML = `
                <img src="illustrations/${art.filename}" alt="${cleanTitle}" loading="lazy">
                <div class="artwork-info">
                    <p class="artwork-date">${art.date}</p>
                    <div class="tag-list">${tagsHtml}</div>
                </div>
            `;

            card.addEventListener('click', () => openLightbox(index));
            card.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') openLightbox(index);
            });

            gallery.appendChild(card);
        });
    }

    function openLightbox(index) {
        currentIndex = index;
        const art = currentArtworks[currentIndex];
        const cleanTitle = getCleanTitle(art.title);

        lightboxImg.src = `illustrations/${art.filename}`;
        lightboxTitle.textContent = cleanTitle;
        lightboxDate.textContent = art.date;
        lightbox.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    function closeLightbox() {
        lightbox.classList.add('hidden');
        document.body.style.overflow = '';
    }

    function nextImage() {
        currentIndex = (currentIndex + 1) % currentArtworks.length;
        openLightbox(currentIndex);
    }

    function prevImage() {
        currentIndex = (currentIndex - 1 + currentArtworks.length) % currentArtworks.length;
        openLightbox(currentIndex);
    }

    lightboxClose.addEventListener('click', closeLightbox);
    lightboxNext.addEventListener('click', (event) => { event.stopPropagation(); nextImage(); });
    lightboxPrev.addEventListener('click', (event) => { event.stopPropagation(); prevImage(); });
    document.querySelector('.lightbox-overlay').addEventListener('click', closeLightbox);

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeLightbox();
            closeSidebar();
        }
        if (lightbox.classList.contains('hidden')) return;
        if (event.key === 'ArrowRight') nextImage();
        if (event.key === 'ArrowLeft') prevImage();
    });

    async function loadNoteArticles() {
        const grid = document.getElementById('note-articles-grid');
        if (!grid) return;

        try {
            const res = await fetch('note_articles.json');
            if (!res.ok) throw new Error('Note articles could not be loaded');
            const articles = await res.json();
            if (statNotes) statNotes.textContent = articles.length.toString();

            if (articles.length === 0) {
                grid.innerHTML = '<p class="note-loading">現在、公開中の記事はありません。</p>';
                return;
            }

            grid.innerHTML = '';
            articles.forEach(art => {
                const cardLink = document.createElement('a');
                cardLink.href = art.link;
                cardLink.target = '_blank';
                cardLink.rel = 'noopener noreferrer';
                cardLink.className = 'note-card-link';

                const eyecatchHtml = art.eyecatch
                    ? `<img src="${art.eyecatch}" alt="${art.title}" class="note-thumb" loading="lazy">`
                    : '<div class="note-thumb"></div>';

                cardLink.innerHTML = `
                    <article class="note-card">
                        <div class="note-thumb-wrapper">
                            ${eyecatchHtml}
                        </div>
                        <div class="note-card-content">
                            <span class="note-date">${art.date}</span>
                            <h3 class="note-title">${art.title}</h3>
                        </div>
                    </article>
                `;
                grid.appendChild(cardLink);
            });
        } catch (error) {
            console.error('Error loading Note articles:', error);
            grid.innerHTML = '<p class="note-loading">Note記事の読み込みに失敗しました。</p>';
        }
    }

    loadGallery();
    loadNoteArticles();
});
