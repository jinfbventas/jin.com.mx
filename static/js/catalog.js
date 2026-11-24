/**
 * catalog.js - JIN.COM.MX
 * Motor del Catálogo: Sincronización en vivo con Mercado Libre México (/api/productos-ml),
 * Búsqueda reactiva, Mosaico responsivo, Slider de escala, Tarjetas 3D Flip y Filtros.
 */

(function () {
    'use strict';

    window.addEventListener('DOMContentLoaded', function () {
        const slider = document.getElementById('cardSizeSlider');
        const gallery = document.querySelector('.gallery');
        const searchInput = document.getElementById('searchInput');
        const filterButtons = document.querySelectorAll('.filter-btn');
        const activeFilterLabel = document.getElementById('activeFilterIndicator');

        let cards = Array.from(document.querySelectorAll('.product-card'));
        let filters = {
            category: 'all',
            brand: '',
            special: '',
            search: ''
        };

        // 1. Control dinámico de escala del mosaico
        if (slider && gallery) {
            slider.addEventListener('input', function () {
                gallery.style.setProperty('--card-size', this.value + 'px');
            });
        }

        // 2. Rotación 3D (Flip Card) táctil y por clic
        function bindCardFlipEvents() {
            cards = Array.from(document.querySelectorAll('.product-card'));
            cards.forEach(card => {
                // Eliminar listener previo para evitar duplicación
                card.onclick = null;
                card.addEventListener('click', function (e) {
                    if (e.target.closest('a') || e.target.closest('.return-btn')) {
                        if (e.target.closest('.return-btn')) {
                            this.classList.remove('flipped');
                            e.stopPropagation();
                        }
                        return;
                    }
                    this.classList.toggle('flipped');
                });
            });
        }

        bindCardFlipEvents();

        // 3. Motor de Filtrado
        function applyFilters() {
            const explicitlyShowingBatteries =
                filters.category === 'battery' ||
                filters.category === 'refacciones' ||
                filters.brand === 'lth';

            if (explicitlyShowingBatteries) {
                document.body.classList.add('force-show-batteries');
            } else {
                document.body.classList.remove('force-show-batteries');
            }

            const isNational = document.body.classList.contains('is-national') && !explicitlyShowingBatteries;
            let visibleCount = 0;

            const hasSpecificBazar = cards.some(c => (c.getAttribute('data-type') || '').toLowerCase() === 'bazar');

            cards.forEach(card => {
                const title = (card.getAttribute('data-title') || '').toLowerCase();
                const id = (card.getAttribute('data-id') || '').toLowerCase();
                const type = (card.getAttribute('data-type') || '').toLowerCase();

                const hasOffer = card.querySelector('.discount-badge') !== null;
                const isLastPiece = card.querySelector('.last-piece') !== null;
                const hasInstallments = card.querySelector('.installments') !== null;

                let match = true;

                // Filtro por categoría general y nodos orbitales
                if (filters.category !== 'all') {
                    if (filters.category === 'toy') {
                        match = (type === 'toy' || type === 'colecciones');
                    } else if (filters.category === 'colecciones') {
                        match = (type === 'colecciones' || type === 'toy');
                    } else if (filters.category === 'battery') {
                        match = (type === 'battery');
                    } else if (filters.category === 'refacciones') {
                        match = (type === 'refacciones' || type === 'battery');
                    } else if (filters.category === 'bazar') {
                        match = hasSpecificBazar ? (type === 'bazar') : (type !== 'battery');
                    } else if (type !== filters.category) {
                        match = false;
                    }
                }

                // Regla nacional (baterías no elegibles para paquetería estándar nacional salvo filtro explícito)
                if (isNational && type === 'battery') {
                    match = false;
                }

                // Filtro por marca / franquicia
                if (filters.brand && !title.includes(filters.brand.toLowerCase())) {
                    match = false;
                }

                // Filtros especiales (oferta, últimas piezas, MSI)
                if (filters.special === 'offer' && !hasOffer) match = false;
                if (filters.special === 'last' && !isLastPiece) match = false;
                if (filters.special === 'installments' && !hasInstallments) match = false;

                // Filtro de búsqueda por texto o ID
                if (filters.search) {
                    const terms = filters.search.split(' ');
                    const matchesTerms = terms.every(term => title.includes(term) || id.includes(term));
                    if (!matchesTerms) match = false;
                }

                if (match) {
                    showCard(card);
                    visibleCount++;
                } else {
                    hideCard(card);
                }
            });

            // Mensaje de resultados vacíos
            const emptyMsg = document.getElementById('noResultsMsg');
            if (emptyMsg) {
                emptyMsg.style.display = visibleCount === 0 ? 'block' : 'none';
            }

            // Indicador visual de filtro activo
            if (activeFilterLabel) {
                let label = 'Todos los productos';
                if (filters.brand) label = `Marca: ${filters.brand.toUpperCase()}`;
                else if (filters.category === 'toy') label = 'Outlet Juguetes';
                else if (filters.category === 'colecciones') label = 'Juguetes Colecciones';
                else if (filters.category === 'battery') label = 'Baterías para auto LTH';
                else if (filters.category === 'refacciones') label = 'Refa en Línea';
                else if (filters.category === 'bazar') label = 'Bazar';
                else if (filters.special === 'offer') label = 'Ofertas Especiales';
                else if (filters.special === 'last') label = 'Últimas Piezas';
                else if (filters.special === 'installments') label = 'Meses sin Intereses';

                if (filters.search) label += ` | Búsqueda: "${filters.search}"`;
                activeFilterLabel.textContent = `${label} (${visibleCount})`;
            }
        }

        function hideCard(card) {
            card.classList.add('fade-out');
            clearTimeout(card._hideTimeout);
            card._hideTimeout = setTimeout(() => {
                card.classList.remove('flipped');
                card.style.display = 'none';
            }, 250);
        }

        function showCard(card) {
            clearTimeout(card._hideTimeout);
            if (card.style.display === 'none') {
                card.style.display = '';
            }
            requestAnimationFrame(() => {
                card.classList.remove('fade-out');
            });
        }

        // 4. Búsqueda en tiempo real
        if (searchInput) {
            searchInput.addEventListener('input', function (e) {
                filters.search = e.target.value.toLowerCase().trim();
                applyFilters();
            });
        }

        // 5. Botones de filtro de la barra superior
        filterButtons.forEach(btn => {
            btn.addEventListener('click', function (e) {
                e.preventDefault();

                filterButtons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');

                const filterType = this.getAttribute('data-type');
                const filterValue = this.getAttribute('data-val');

                filters.brand = '';
                filters.special = '';

                if (filterType === 'category') {
                    filters.category = filterValue;
                } else if (filterType === 'brand') {
                    filters.category = 'all';
                    filters.brand = filterValue;
                } else if (filterType === 'special') {
                    filters.category = 'all';
                    filters.special = filterValue;
                }

                applyFilters();

                const galleryTop = gallery.getBoundingClientRect().top + window.scrollY;
                if (window.scrollY < galleryTop - 150) {
                    window.scrollTo({ top: galleryTop - 90, behavior: 'smooth' });
                }
            });
        });

        // 6. Motor del Banner Horizontal Slider (Publicaciones Más Recientes de Mercado Libre)
        const recentTrack = document.getElementById('recentSliderTrack');
        const recentDotsContainer = document.getElementById('recentSliderDots');
        const recentPrevBtn = document.getElementById('recentSliderPrev');
        const recentNextBtn = document.getElementById('recentSliderNext');
        const recentBannerBox = document.getElementById('recentBannerContainer');
        let currentSlideIndex = 0;
        let recentSlideTimer = null;

        function initRecentSlider() {
            if (!recentTrack) return;
            const slides = Array.from(recentTrack.querySelectorAll('.recent-slide'));
            const totalSlides = slides.length;
            if (totalSlides === 0) return;

            if (currentSlideIndex >= totalSlides) currentSlideIndex = 0;

            // Generar puntos indicadores inferiores
            if (recentDotsContainer) {
                recentDotsContainer.innerHTML = '';
                slides.forEach((_, idx) => {
                    const dot = document.createElement('button');
                    dot.type = 'button';
                    dot.className = `recent-slider-dot ${idx === currentSlideIndex ? 'active' : ''}`;
                    dot.setAttribute('aria-label', `Ir a publicación reciente ${idx + 1}`);
                    dot.addEventListener('click', function () {
                        goToRecentSlide(idx);
                        restartRecentTimer();
                    });
                    recentDotsContainer.appendChild(dot);
                });
            }

            updateRecentSlidePosition();
            restartRecentTimer();
        }

        function updateRecentSlidePosition() {
            if (!recentTrack) return;
            const slides = Array.from(recentTrack.querySelectorAll('.recent-slide'));
            if (slides.length === 0) return;

            recentTrack.style.transform = `translate3d(-${currentSlideIndex * 100}%, 0, 0)`;
            slides.forEach((s, idx) => {
                s.classList.toggle('is-active', idx === currentSlideIndex);
            });

            if (recentDotsContainer) {
                const dots = recentDotsContainer.querySelectorAll('.recent-slider-dot');
                dots.forEach((d, idx) => {
                    d.classList.toggle('active', idx === currentSlideIndex);
                });
            }
        }

        function goToRecentSlide(index) {
            if (!recentTrack) return;
            const total = recentTrack.querySelectorAll('.recent-slide').length;
            if (total === 0) return;
            currentSlideIndex = (index + total) % total;
            updateRecentSlidePosition();
        }

        function stopRecentTimer() {
            if (recentSlideTimer) {
                clearInterval(recentSlideTimer);
                recentSlideTimer = null;
            }
        }

        function restartRecentTimer() {
            stopRecentTimer();
            recentSlideTimer = setInterval(function () {
                goToRecentSlide(currentSlideIndex + 1);
            }, 4500);
        }

        if (recentPrevBtn) {
            recentPrevBtn.addEventListener('click', function () {
                goToRecentSlide(currentSlideIndex - 1);
                restartRecentTimer();
            });
        }

        if (recentNextBtn) {
            recentNextBtn.addEventListener('click', function () {
                goToRecentSlide(currentSlideIndex + 1);
                restartRecentTimer();
            });
        }

        if (recentBannerBox) {
            recentBannerBox.addEventListener('mouseenter', stopRecentTimer);
            recentBannerBox.addEventListener('mouseleave', restartRecentTimer);
            recentBannerBox.addEventListener('touchstart', stopRecentTimer, { passive: true });
            recentBannerBox.addEventListener('touchend', restartRecentTimer, { passive: true });
        }

        function renderRecentSlider(recentProducts) {
            if (!recentTrack || !recentProducts || recentProducts.length === 0) return;

            recentTrack.innerHTML = '';
            recentProducts.slice(0, 5).forEach((p, idx) => {
                const priceFormatted = Number(p.price || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                const tagLabel = idx % 2 === 0 ? 'RECIÉN PUBLICADO' : 'NUEVO INGRESO';
                let extraBadge = '';
                if (p.is_last) {
                    extraBadge = '<span class="recent-slide-pill pill-alert">¡ÚLTIMA PIEZA!</span>';
                } else if (p.discount) {
                    extraBadge = `<span class="recent-slide-pill pill-discount">${p.discount} OFF</span>`;
                }
                const origHtml = (p.original_price && Number(p.original_price) > Number(p.price))
                    ? `<span class="recent-orig-price">$${Number(p.original_price).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MXN</span>`
                    : '';
                const installmentsText = p.installments || 'Compra 100% Protegida';
                const permalink = p.permalink || 'https://listado.mercadolibre.com.mx/_CustId_491131225';
                const waMsg = encodeURIComponent(`Hola JIN.COM.MX, vi en Nuevos Artículos el producto: ${p.title} (Ref: ${p.id}) de $${priceFormatted} MXN`);
                const thumbFallback = p.thumbnail_url || (p.image_url || '').replace('-O.jpg', '-I.jpg');

                const slideEl = document.createElement('div');
                slideEl.className = `recent-slide ${idx === 0 ? 'is-active' : ''}`;
                slideEl.setAttribute('data-slide-index', String(idx));
                slideEl.innerHTML = `
                    <a href="${permalink}" target="_blank" rel="noopener noreferrer" class="recent-slide-media" title="Ver publicación en Mercado Libre">
                        <img src="${p.image_url}"
                             data-fallback="${thumbFallback}"
                             alt="${p.title}"
                             loading="lazy"
                             onerror="if(this.dataset.fallback && this.src !== this.dataset.fallback){this.src=this.dataset.fallback;}else{this.onerror=null;this.src='static/img/logo_jin_3d.png';}">
                    </a>
                    <div class="recent-slide-content">
                        <div class="recent-slide-badges">
                            <span class="recent-slide-pill pill-new">${tagLabel}</span>
                            ${extraBadge}
                            <span class="recent-slide-ref">REF: ${p.id}</span>
                        </div>
                        <h3 class="recent-slide-title">
                            <a href="${permalink}" target="_blank" rel="noopener noreferrer" class="recent-title-link">${p.title}</a>
                        </h3>
                        <div class="recent-slide-pricing">
                            <div class="front-price recent-lcd-price">$${priceFormatted} MXN</div>
                            ${origHtml}
                            <span class="recent-slide-msi">${installmentsText}</span>
                        </div>
                        <div class="recent-slide-actions">
                            <a href="${permalink}" target="_blank" rel="noopener noreferrer" class="glass-btn ml-btn recent-cta-btn">
                                Ver / Comprar en Mercado Libre
                            </a>
                            <a href="https://wa.me/524771230000?text=${waMsg}" target="_blank" rel="noopener noreferrer" class="glass-btn wa-btn recent-cta-btn">
                                Pedir por WhatsApp
                            </a>
                        </div>
                    </div>
                `;
                recentTrack.appendChild(slideEl);
            });

            currentSlideIndex = 0;
            initRecentSlider();
        }

        // Inicializar slider con los slides precargados
        initRecentSlider();

        // 7. Sincronización en Vivo de Publicaciones de Mercado Libre México (/api/productos-ml)
        async function fetchLiveMLProducts() {
            try {
                const response = await fetch('/api/productos-ml');
                if (!response.ok) return;

                const data = await response.json();
                if (data && data.body_class) {
                    document.body.classList.remove('is-local', 'is-national');
                    document.body.classList.add(data.body_class);
                }
                if (data && data.products && data.products.length > 0) {
                    renderLiveProducts(data.products);
                    const recents = (data.recent_products && data.recent_products.length > 0)
                        ? data.recent_products.slice(0, 5)
                        : data.products.slice(0, 5);
                    renderRecentSlider(recents);
                }
            } catch (err) {
                // Modo estático o fuera de línea: mantiene los productos precargados
                console.info("Catálogo operando con productos precargados optimizados.");
            }
        }

        function renderLiveProducts(products) {
            if (!gallery) return;

            // Limpiamos los productos existentes y renderizamos los productos actualizados de Mercado Libre
            gallery.innerHTML = '';

            products.forEach(p => {
                const isBattery = p.category === 'battery';
                const cardEl = document.createElement('div');
                cardEl.className = `product-card flip-card ${isBattery ? 'battery-link' : ''}`;
                cardEl.setAttribute('data-id', p.id || '');
                cardEl.setAttribute('data-title', p.title || '');
                cardEl.setAttribute('data-type', p.category || 'toy');

                const priceFormatted = Number(p.price || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                const origPriceHtml = (p.original_price && Number(p.original_price) > Number(p.price))
                    ? `<div style="font-size: 11px; text-decoration: line-through; color: #888; font-weight: 700;">$${Number(p.original_price).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MXN</div>`
                    : '';
                const stockBadge = p.is_last 
                    ? '<span class="stock-badge last-piece">⚡ ¡ÚLTIMA PIEZA!</span>' 
                    : `<span class="stock-badge">Stock: ${p.stock || 'Disponible'}</span>`;
                const discountBadge = p.discount ? `<span class="discount-badge">${p.discount}</span>` : '';
                const installmentsBadge = p.installments ? `<div class="installments">${p.installments}</div>` : '';

                const mlButton = p.permalink ? `
                    <a href="${p.permalink}" target="_blank" rel="noopener" class="glass-btn ml-btn">
                        🛒 Comprar en Mercado Libre
                    </a>` : '';

                const waMessage = encodeURIComponent(`Hola JIN.COM.MX, me interesa el producto: ${p.title} (Ref: ${p.id})`);
                const waButton = `
                    <a href="https://wa.me/524771230000?text=${waMessage}" target="_blank" rel="noopener" class="glass-btn wa-btn">
                        💬 Pedir por WhatsApp
                    </a>`;

                const thumbFallback = p.thumbnail_url || (p.image_url || '').replace('-O.jpg', '-I.jpg');

                cardEl.innerHTML = `
                    <div class="flip-card-inner">
                        <div class="flip-card-front">
                            ${stockBadge}
                            ${discountBadge}
                            <div class="card-image-area">
                                <img src="${p.image_url}" 
                                     data-fallback="${thumbFallback}"
                                     alt="${p.title}" 
                                     loading="lazy"
                                     onerror="if(this.dataset.fallback && this.src !== this.dataset.fallback){this.src=this.dataset.fallback;}else{this.onerror=null;this.src='static/img/logo_jin_3d.png';}">
                            </div>
                            <div class="card-info-area">
                                <h3 class="card-title">${p.title}</h3>
                                <div class="ref-id">REF: ${p.id}</div>
                                ${origPriceHtml}
                                <div class="front-price">$${priceFormatted} MXN</div>
                                ${installmentsBadge}
                                <div class="tap-hint">👆 Toca para ver opciones</div>
                            </div>
                        </div>
                        <div class="flip-card-back">
                            <div class="back-content">
                                <img src="static/img/logo_jin_3d.png" alt="JIN.COM.MX" class="back-logo-img">
                                <h4 class="back-title">${p.title}</h4>
                                <div class="back-price">$${priceFormatted} MXN</div>
                                <p style="font-size: 11px; color: #555; font-weight: 600;">${p.description || 'Publicación oficial en Mercado Libre México con garantía y envío protegido.'}</p>
                                <div class="action-buttons-group">
                                    ${mlButton}
                                    ${waButton}
                                    <button class="return-btn" type="button">Volver al frente ↩</button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;

                gallery.appendChild(cardEl);
            });

            // Re-vincular eventos y aplicar filtros vigentes
            bindCardFlipEvents();
            applyFilters();
        }

        // Ejecución de sincronización en vivo
        fetchLiveMLProducts();

        // 7. API Global para interacción desde el menú orbital
        window.JinCatalog = {
            setCategory: function (cat) {
                filters.category = cat;
                filters.brand = '';
                filters.special = '';
                updateButtonStates('category', cat);
                applyFilters();
            },
            setBrand: function (brand) {
                filters.category = 'all';
                filters.brand = brand;
                filters.special = '';
                updateButtonStates('brand', brand);
                applyFilters();
            },
            setSpecial: function (special) {
                filters.category = 'all';
                filters.brand = '';
                filters.special = special;
                updateButtonStates('special', special);
                applyFilters();
            },
            reset: function () {
                filters = { category: 'all', brand: '', special: '', search: '' };
                if (searchInput) searchInput.value = '';
                updateButtonStates('category', 'all');
                applyFilters();
            }
        };

        function updateButtonStates(type, val) {
            filterButtons.forEach(btn => {
                if (btn.getAttribute('data-type') === type && btn.getAttribute('data-val') === val) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }

        // Ejecución inicial de filtros
        applyFilters();
    });
})();
