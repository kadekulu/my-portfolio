document.addEventListener('DOMContentLoaded', () => {
    const gallery = document.getElementById('gallery');
    const tagTabs = document.getElementById('tag-tabs');
    const monthTabs = document.getElementById('month-tabs');
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    const lightboxTitle = document.getElementById('lightbox-title');
    const lightboxDate = document.getElementById('lightbox-date');
    const lightboxClose = document.getElementById('lightbox-close');
    const lightboxPrev = document.getElementById('lightbox-prev');
    const lightboxNext = document.getElementById('lightbox-next');

    let allArtworks = [];
    let currentArtworks = []; // 現在表示中のリスト（フィルタリング対応）
    let currentIndex = 0;     // 現在拡大中のインデックス

    const CATEGORIES = {
        IDENTITY: ['Airi', 'Original'],
        HAIR: ['Pink Hair', 'Blue Hair', 'Blonde Hair', 'White Hair', 'Black Hair', 'Silver Hair', 'Brown Hair', 
               'Twin Tails', 'Wavy Hair', 'Straight Hair', 'Pony Tail', 'Short Hair', 'Long Hair', 'Medium Hair'],
        CLOTHING: ['School Uniform', 'Dress', 'Lingerie', 'Swimsuit', 'Casual', 'Gothic']
    };

    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        document.body.classList.toggle('sidebar-open');
    });

    function getCleanTitle(title) {
        const isSystemName = /\d{3,}/.test(title) || 
                             title.toLowerCase().includes('cleanup') || 
                             title.toLowerCase().includes('upscale') ||
                             title.length > 20;
        return isSystemName ? "Elite Art Piece" : title;
    }

    function loadGallery() {
        try {
            if (typeof ARTWORKS_DATA === 'undefined') {
                throw new Error('データが見つかりません');
            }
            allArtworks = ARTWORKS_DATA;
            
            const months = [...new Set(allArtworks.map(art => {
                const parts = art.date.split('.');
                return `${parts[0]}.${parts[1]}`;
            }))].sort().reverse();

            const allTags = [];
            allArtworks.forEach(art => {
                if (art.tags) allTags.push(...art.tags);
            });
            const uniqueTags = [...new Set(allTags)].sort();

            createTabs(months, uniqueTags);
            renderGallery(allArtworks);
        } catch (error) {
            console.error('Error loading gallery:', error);
            gallery.innerHTML = '<div class="glass-panel" style="padding: 40px; text-align: center; grid-column: 1/-1;">読み込みに失敗しました。</div>';
        }
    }

    function createTabs(months, tags) {
        tagTabs.innerHTML = '';
        tagTabs.appendChild(createLabel('Show All'));
        const allBtn = createTabBtn('All Works', () => renderGallery(allArtworks));
        allBtn.classList.add('active');
        tagTabs.appendChild(allBtn);

        const identityTags = tags.filter(t => CATEGORIES.IDENTITY.includes(t));
        if (identityTags.length > 0) {
            tagTabs.appendChild(createLabel('Characters'));
            identityTags.forEach(tag => tagTabs.appendChild(createTabBtn(tag, () => filterByTag(tag))));
        }

        const hairTags = tags.filter(t => CATEGORIES.HAIR.includes(t));
        if (hairTags.length > 0) {
            tagTabs.appendChild(createLabel('Hair Style & Color'));
            hairTags.forEach(tag => tagTabs.appendChild(createTabBtn(tag, () => filterByTag(tag))));
        }

        const clothingTags = tags.filter(t => CATEGORIES.CLOTHING.includes(t));
        if (clothingTags.length > 0) {
            tagTabs.appendChild(createLabel('Clothing'));
            clothingTags.forEach(tag => tagTabs.appendChild(createTabBtn(tag, () => filterByTag(tag))));
        }

        monthTabs.innerHTML = '';
        monthTabs.appendChild(createLabel('Timeline'));
        months.forEach(month => {
            const btn = createTabBtn(month, () => filterByMonth(month));
            monthTabs.appendChild(btn);
        });
    }

    function createLabel(text) {
        const label = document.createElement('div');
        label.className = 'nav-label';
        label.textContent = text;
        return label;
    }

    function createTabBtn(text, onClick) {
        const btn = document.createElement('button');
        btn.className = 'month-btn';
        btn.textContent = text;
        btn.setAttribute('data-tag', text);
        btn.addEventListener('click', () => {
            document.querySelectorAll('.month-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            onClick();
            if (window.innerWidth < 768) {
                sidebar.classList.remove('open');
                document.body.classList.remove('sidebar-open');
            }
        });
        return btn;
    }

    function filterByMonth(month) {
        const filtered = allArtworks.filter(art => art.date.startsWith(month));
        renderGallery(filtered);
    }

    function filterByTag(tag) {
        const filtered = allArtworks.filter(art => art.tags && art.tags.includes(tag));
        renderGallery(filtered);
    }

    function renderGallery(artworks) {
        gallery.innerHTML = '';
        currentArtworks = artworks; // 現在のリストを保持
        
        if (artworks.length === 0) {
            gallery.innerHTML = '<p style="text-align: center; grid-column: 1/-1;">イラストがありません。</p>';
            return;
        }

        artworks.forEach((art, index) => {
            const cleanTitle = getCleanTitle(art.title);
            const card = document.createElement('div');
            card.className = 'artwork-card glass-panel';
            
            const tagsHtml = art.tags ? art.tags.map(t => `<span style="font-size: 0.6rem; background: rgba(255, 255, 255, 0.05); padding: 2px 6px; border-radius: 4px; margin-right: 4px; color: rgba(255,255,255,0.4); border: 1px solid rgba(255,255,255,0.08);">${t}</span>`).join('') : '';

            card.innerHTML = `
                <img src="illustrations/${art.filename}" alt="${cleanTitle}" loading="lazy">
                <div class="artwork-info">
                    <p class="artwork-date">${art.date}</p>
                    <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px;">${tagsHtml}</div>
                </div>
            `;
            
            card.addEventListener('click', () => openLightbox(index));
            
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            gallery.appendChild(card);
            
            setTimeout(() => {
                card.style.transition = 'all 0.6s cubic-bezier(0.22, 1, 0.36, 1)';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, index * 30);
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
        document.body.style.overflow = 'auto';
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
    lightboxNext.addEventListener('click', (e) => { e.stopPropagation(); nextImage(); });
    lightboxPrev.addEventListener('click', (e) => { e.stopPropagation(); prevImage(); });
    document.querySelector('.lightbox-overlay').addEventListener('click', closeLightbox);

    document.addEventListener('keydown', (e) => {
        if (lightbox.classList.contains('hidden')) return;
        if (e.key === 'Escape') closeLightbox();
        if (e.key === 'ArrowRight') nextImage();
        if (e.key === 'ArrowLeft') prevImage();
    });

    async function loadNoteArticles() {
        const grid = document.getElementById('note-articles-grid');
        if (!grid) return;

        try {
            const res = await fetch('note_articles.json');
            if (!res.ok) throw new Error('Note articles could not be loaded');
            const articles = await res.json();

            if (articles.length === 0) {
                grid.innerHTML = '<p class="note-loading">現在、公開されている記事はありません。</p>';
                return;
            }

            grid.innerHTML = '';
            articles.forEach(art => {
                const cardLink = document.createElement('a');
                cardLink.href = art.link;
                cardLink.target = '_blank';
                cardLink.rel = 'noopener noreferrer';
                cardLink.className = 'note-card-link';

                // サムネイル画像がない場合のプレースホルダー（ガラスグラデーション）
                const eyecatchHtml = art.eyecatch 
                    ? `<img src="${art.eyecatch}" alt="${art.title}" class="note-thumb" loading="lazy">`
                    : `<div style="display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(244, 114, 182, 0.15)); height: 100%; width: 100%; font-size: 2.5rem; font-family: sans-serif; user-select: none;">📝</div>`;

                cardLink.innerHTML = `
                    <div class="note-card">
                        <div class="note-thumb-wrapper">
                            ${eyecatchHtml}
                        </div>
                        <div class="note-card-content">
                            <span class="note-date">${art.date}</span>
                            <h4 class="note-title">${art.title}</h4>
                        </div>
                    </div>
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
