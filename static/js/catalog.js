/**
 * catalog.js - JIN.COM.MX
 * Motor del Catálogo: Sincronización en vivo con Mercado Libre México (/api/productos-ml),
 * Búsqueda reactiva, Mosaico responsivo, Slider de escala, Tarjetas 3D Flip y Filtros.
 */

(function () {
    'use strict';

    window.addEventListener('DOMContentLoaded', function () {
        const slider = document.getElementById('cardSizeSlider');
        const gallery = document.querySelector('#catalogArea > .gallery') || document.querySelector('.gallery');
        const recommendedGallery = document.getElementById('recommendedGallery');
        const searchInput = document.getElementById('searchInput');
        const filterButtons = document.querySelectorAll('.filter-btn');
        const activeFilterLabel = document.getElementById('activeFilterIndicator');

        let cards = Array.from(gallery ? gallery.querySelectorAll('.product-card') : document.querySelectorAll('.product-card'));
        let filters = {
            category: 'all',
            sub: '',
            brand: '',
            special: '',
            search: ''
        };

        const SUB_LABELS = {
            col_all: 'Todo en Juguetes y Colecciones',
            col_star_wars: 'Star Wars',
            col_marvel_dc: 'Marvel / DC',
            col_pokemon: 'Pokémon',
            col_trolls_mattel_hasbro: 'Trolls / Mattel / Hasbro',
            col_figuras_accion: 'Figuras de Acción y Coleccionables',
            outlet_baratos: 'Outlet del Juguete: Súper Económicos (Menor Precio)',
            outlet_menos_300: 'Outlet del Juguete: Menos de $300',
            outlet_300_600: 'Outlet del Juguete: De $300 a $600',
            outlet_remates: 'Outlet del Juguete: Remates de Juguetería',
            refa_all: 'Refa en Línea: Todas las Refacciones',
            refa_bujias: 'Refa en Línea: Bujías y Encendido',
            refa_bandas: 'Refa en Línea: Bandas y Poleas',
            refa_filtros_sensores: 'Refa en Línea: Filtros y Sensores',
            refa_suspension_frenos: 'Refa en Línea: Suspensión y Frenos',
            refa_otras: 'Refa en Línea: Otras Refacciones',
            bat_all: 'Baterías para Auto LTH',
            bat_convencional: 'Baterías LTH Convencional',
            bat_hitec_agm: 'Baterías LTH Hi-Tec / AGM',
            bat_aplicacion: 'Acumuladores LTH por Aplicación',
            bazar_usados_all: 'Bazar: Todo en Usados y Segunda Mano',
            bazar_usados_juguetes: 'Bazar: Juguetes y Coleccionables Usados',
            bazar_usados_electronica_hogar: 'Bazar: Electrónica y Hogar Usados',
            bazar_usados_otros: 'Bazar: Otros Artículos Usados',
            bazar2_all: 'Bazar 2: Variedades y Miscelánea',
            bazar2_hogar: 'Bazar 2: Hogar y Oficina',
            bazar2_herramientas: 'Bazar 2: Herramientas y Accesorios',
            bazar2_electronica: 'Bazar 2: Electrónica y Gadgets',
            bazar2_variedades: 'Bazar 2: Variedades',
            oferta_mayores: 'Ofertas Especiales: Mayores Descuentos (%)',
            oferta_relampago: 'Ofertas Especiales: Ofertas Relámpago',
            oferta_msi: 'Ofertas Especiales: Meses Sin Intereses',
            oferta_ultimas: 'Ofertas Especiales: Últimas Piezas en Oferta'
        };

        // 1. Control dinámico de escala del mosaico
        if (slider && gallery) {
            slider.addEventListener('input', function () {
                gallery.style.setProperty('--card-size', this.value + 'px');
                if (recommendedGallery) {
                    recommendedGallery.style.setProperty('--card-size', this.value + 'px');
                }
            });
        }

        // Enriquecimiento automático de metadatos multi-etiqueta en tarjetas del DOM
        function enrichCardMetadata(card, idx) {
            if (!card.hasAttribute('data-orig-index')) {
                card.setAttribute('data-orig-index', String(idx));
            }
            const title = (card.getAttribute('data-title') || '').toLowerCase();
            const type = (card.getAttribute('data-type') || 'toy').toLowerCase();

            // Extraer precio numérico si no existe data-price
            if (!card.hasAttribute('data-price')) {
                const priceEl = card.querySelector('.front-price');
                const rawPrice = priceEl ? priceEl.textContent.replace(/[^0-9.]/g, '') : '0';
                card.setAttribute('data-price', String(parseFloat(rawPrice) || 0));
            }

            // Extraer porcentaje de descuento si no existe data-discount-pct
            if (!card.hasAttribute('data-discount-pct')) {
                const discEl = card.querySelector('.discount-badge');
                let pct = 0;
                if (discEl) {
                    const m = discEl.textContent.match(/(\d+)\s*%/);
                    if (m) pct = parseInt(m[1], 10);
                    else if (discEl.textContent.trim().length > 0) pct = 5;
                }
                card.setAttribute('data-discount-pct', String(pct));
            }

            // Clasificar multi-etiqueta si la tarjeta viene del HTML estático
            if (!card.hasAttribute('data-cats') || !card.hasAttribute('data-subs')) {
                const price = parseFloat(card.getAttribute('data-price') || '0');
                const discPct = parseInt(card.getAttribute('data-discount-pct') || '0', 10);
                const isLast = card.querySelector('.last-piece') !== null;
                const hasMsi = card.querySelector('.installments') !== null;

                const isUsed = ['usado', 'usada', 'segunda mano', 'exhibición', 'exhibicion', 'seminuevo'].some(w => title.includes(w));
                const isBattery = type === 'battery' || ['bateria', 'batería', 'acumulador', 'lth'].some(w => title.includes(w));
                const isRefa = !isBattery && (type === 'refacciones' || ['refaccion', 'refacción', 'bujia', 'bujía', 'bobina', 'banda', 'polea', 'filtro', 'sensor', 'amortiguador', 'balata', 'freno', 'suspensión', 'suspension', 'alternador'].some(w => title.includes(w)));
                const isToy = !isBattery && !isRefa && (type === 'toy' || type === 'colecciones' || ['juguete', 'figura', 'colección', 'coleccion', 'marvel', 'spider', 'avengers', 'capitán', 'capitan', 'batman', 'dc', 'star wars', 'mandalorian', 'grogu', 'hot wheels', 'mattel', 'hasbro', 'pokemon', 'pokémon', 'trolls', 'funko', 'lego', 'barbie'].some(w => title.includes(w)));

                const cats = [];
                const subs = [];

                if (isBattery) {
                    cats.push('battery');
                    subs.push('bat_all', 'bat_aplicacion');
                    if (['hi-tec', 'hitec', 'agm', 'evolution'].some(w => title.includes(w))) subs.push('bat_hitec_agm');
                    else subs.push('bat_convencional');
                }
                if (isRefa) {
                    cats.push('refacciones');
                    subs.push('refa_all');
                    let matchedRefa = false;
                    if (['bujia', 'bujía', 'bobina', 'encendido'].some(w => title.includes(w))) { subs.push('refa_bujias'); matchedRefa = true; }
                    if (['banda', 'polea', 'tensor', 'alternador'].some(w => title.includes(w))) { subs.push('refa_bandas'); matchedRefa = true; }
                    if (['filtro', 'sensor', 'inyector', 'valvula'].some(w => title.includes(w))) { subs.push('refa_filtros_sensores'); matchedRefa = true; }
                    if (['amortiguador', 'balata', 'freno', 'rotula', 'horquilla', 'suspension', 'suspensión'].some(w => title.includes(w))) { subs.push('refa_suspension_frenos'); matchedRefa = true; }
                    if (!matchedRefa) subs.push('refa_otras');
                }
                if (isToy) {
                    cats.push('toy', 'colecciones');
                    subs.push('col_all', 'outlet_baratos');
                    if (price < 300) subs.push('outlet_menos_300');
                    if (price >= 300 && price <= 600) subs.push('outlet_300_600');
                    if (discPct > 0 || price <= 220 || isLast) subs.push('outlet_remates');

                    if (['star wars', 'mandalorian', 'grogu', 'yoda', 'vader', 'jedi'].some(w => title.includes(w))) subs.push('col_star_wars');
                    if (['marvel', 'spider', 'avengers', 'capitán', 'capitan', 'iron man', 'hulk', 'batman', 'superman', 'dc', 'joker'].some(w => title.includes(w))) subs.push('col_marvel_dc');
                    if (['pokemon', 'pokémon', 'pikachu', 'charizard'].some(w => title.includes(w))) subs.push('col_pokemon');
                    if (['trolls', 'mattel', 'hasbro', 'hot wheels', 'barbie', 'transformers', 'nerf'].some(w => title.includes(w))) subs.push('col_trolls_mattel_hasbro');
                    if (['figura', 'colección', 'coleccion', 'escala', 'funko', 'lego', 'missions', 'titan hero'].some(w => title.includes(w))) subs.push('col_figuras_accion');
                }
                if (isUsed) {
                    cats.push('bazar');
                    subs.push('bazar_usados_all');
                    if (isToy) subs.push('bazar_usados_juguetes');
                    else if (['electr', 'hogar', 'cocina', 'audio', 'bocina', 'tv'].some(w => title.includes(w))) subs.push('bazar_usados_electronica_hogar');
                    else subs.push('bazar_usados_otros');
                }
                if (!isToy && !isBattery && !isRefa) {
                    cats.push('bazar_2');
                    subs.push('bazar2_all');
                    let matchedB2 = false;
                    if (['hogar', 'oficina', 'cocina', 'decoracion', 'organizador'].some(w => title.includes(w))) { subs.push('bazar2_hogar'); matchedB2 = true; }
                    if (['herramienta', 'llave', 'pinza', 'desarmador', 'accesorio'].some(w => title.includes(w))) { subs.push('bazar2_herramientas'); matchedB2 = true; }
                    if (['electr', 'gadget', 'cable', 'bocina', 'audifono', 'usb', 'led'].some(w => title.includes(w))) { subs.push('bazar2_electronica'); matchedB2 = true; }
                    if (!matchedB2) subs.push('bazar2_variedades');
                }

                if (discPct > 0) subs.push('oferta_mayores');
                if (discPct >= 15) subs.push('oferta_relampago');
                if (hasMsi) subs.push('oferta_msi');
                if (isLast) subs.push('oferta_ultimas');

                card.setAttribute('data-cats', cats.join(','));
                card.setAttribute('data-subs', subs.join(','));
                card.setAttribute('data-condition', isUsed ? 'used' : 'new');
            }
        }

        // 2. Rotación 3D (Flip Card) táctil y por clic
        function attachFlipListener(card) {
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
        }

        function bindCardFlipEvents() {
            cards = Array.from(gallery ? gallery.querySelectorAll('.product-card') : document.querySelectorAll('.product-card'));
            cards.forEach((card, idx) => {
                enrichCardMetadata(card, idx);
                attachFlipListener(card);
            });
        }

        bindCardFlipEvents();

        // Ordenamiento dinámico del contenedor .gallery según la sección activa
        function sortGalleryCards() {
            if (!gallery || cards.length === 0) return;

            const isOutletSort =
                filters.category === 'toy' ||
                (filters.sub && filters.sub.indexOf('outlet_') === 0);

            const isOfferSort =
                filters.special === 'offer' ||
                (filters.sub && filters.sub.indexOf('oferta_') === 0);

            const sorted = cards.slice().sort((a, b) => {
                if (isOutletSort) {
                    const pa = parseFloat(a.getAttribute('data-price') || '0');
                    const pb = parseFloat(b.getAttribute('data-price') || '0');
                    return pa - pb;
                }
                if (isOfferSort) {
                    const da = parseInt(a.getAttribute('data-discount-pct') || '0', 10);
                    const db = parseInt(b.getAttribute('data-discount-pct') || '0', 10);
                    if (db !== da) return db - da;
                    const pa = parseFloat(a.getAttribute('data-price') || '0');
                    const pb = parseFloat(b.getAttribute('data-price') || '0');
                    return pa - pb;
                }
                const ia = parseInt(a.getAttribute('data-orig-index') || '0', 10);
                const ib = parseInt(b.getAttribute('data-orig-index') || '0', 10);
                return ia - ib;
            });

            sorted.forEach(c => gallery.appendChild(c));
            cards = sorted;
        }

        // Generador de recomendaciones inteligentes cuando visibleCount === 0
        function renderRecommendations(isNational) {
            if (!recommendedGallery) return;
            recommendedGallery.innerHTML = '';

            const eligiblePool = cards.filter(c => {
                const type = (c.getAttribute('data-type') || '').toLowerCase();
                if (isNational && type === 'battery') return false;
                return true;
            });
            const basePool = eligiblePool.length > 0 ? eligiblePool : cards.slice();
            if (basePool.length === 0) return;

            let similarCards = [];

            // Prioridad 1: Coincidencias parciales de palabras clave sueltas o categoría padre relacionada
            if (filters.search) {
                const rawTokens = filters.search
                    .toLowerCase()
                    .split(/\s+/)
                    .filter(t => t.length >= 2);
                const stems = rawTokens.map(t => (t.length >= 4 ? t.slice(0, 4) : t));

                similarCards = basePool.filter(c => {
                    const haystack = (
                        (c.getAttribute('data-title') || '') + ' ' +
                        (c.getAttribute('data-brand') || '') + ' ' +
                        (c.getAttribute('data-cats') || '') + ' ' +
                        (c.getAttribute('data-subs') || '')
                    ).toLowerCase();
                    return stems.some(st => haystack.includes(st));
                });
            } else if (filters.sub || (filters.category && filters.category !== 'all')) {
                const sub = filters.sub || '';
                let relatedCat = '';
                if (sub.indexOf('col_') === 0 || sub.indexOf('outlet_') === 0 || filters.category === 'toy' || filters.category === 'colecciones') {
                    relatedCat = 'toy';
                } else if (sub.indexOf('refa_') === 0 || sub.indexOf('bat_') === 0 || filters.category === 'refacciones' || filters.category === 'battery') {
                    relatedCat = 'battery';
                }

                if (relatedCat) {
                    similarCards = basePool.filter(c => {
                        const cats = (c.getAttribute('data-cats') || '').split(',');
                        const type = (c.getAttribute('data-type') || '').toLowerCase();
                        return cats.includes(relatedCat) || type === relatedCat || (relatedCat === 'toy' && cats.includes('colecciones'));
                    });
                }
            }

            const recSubtitle = document.getElementById('recommendedSubtitle');
            let finalSelection = [];

            if (similarCards.length > 0) {
                finalSelection = similarCards.slice(0, 4);
                if (recSubtitle) {
                    recSubtitle.textContent = 'Artículos similares y relacionados con tu selección';
                }
            }

            // Prioridad 2 (Fallback): Productos aleatorios dentro del grupo con mayor porcentaje de descuento
            if (finalSelection.length < 4) {
                const usedIds = new Set(finalSelection.map(c => c.getAttribute('data-id')));
                const remainingByDiscount = basePool
                    .filter(c => !usedIds.has(c.getAttribute('data-id')))
                    .sort((a, b) => {
                        const da = parseInt(a.getAttribute('data-discount-pct') || '0', 10);
                        const db = parseInt(b.getAttribute('data-discount-pct') || '0', 10);
                        return db - da;
                    });

                // Tomar el grupo top de mayores descuentos y mezclar aleatoriamente
                const topPoolSize = Math.min(Math.max(remainingByDiscount.length, 4), 8);
                const topDiscountGroup = remainingByDiscount.slice(0, topPoolSize);
                for (let i = topDiscountGroup.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    const tmp = topDiscountGroup[i];
                    topDiscountGroup[i] = topDiscountGroup[j];
                    topDiscountGroup[j] = tmp;
                }

                // Ordenar los seleccionados de mayor a menor % de descuento
                const needed = 4 - finalSelection.length;
                const pickedFallback = topDiscountGroup.slice(0, needed).sort((a, b) => {
                    const da = parseInt(a.getAttribute('data-discount-pct') || '0', 10);
                    const db = parseInt(b.getAttribute('data-discount-pct') || '0', 10);
                    return db - da;
                });

                if (finalSelection.length === 0 && recSubtitle) {
                    recSubtitle.textContent = 'Seleccionados automáticamente entre las ofertas con mayor porcentaje de descuento';
                }
                finalSelection = finalSelection.concat(pickedFallback);
            }

            finalSelection.forEach(origCard => {
                const clone = origCard.cloneNode(true);
                clone.classList.remove('fade-out', 'flipped', 'battery-link');
                clone.style.display = '';
                attachFlipListener(clone);
                recommendedGallery.appendChild(clone);
            });
        }

        // 3. Motor de Filtrado Inteligente Multi-Etiqueta
        function applyFilters() {
            const explicitlyShowingBatteries =
                filters.category === 'battery' ||
                filters.category === 'refacciones' ||
                filters.brand === 'lth' ||
                (filters.sub && (filters.sub.indexOf('bat_') === 0 || filters.sub.indexOf('refa_') === 0));

            if (explicitlyShowingBatteries) {
                document.body.classList.add('force-show-batteries');
            } else {
                document.body.classList.remove('force-show-batteries');
            }

            sortGalleryCards();

            const isNational = document.body.classList.contains('is-national') && !explicitlyShowingBatteries;
            let visibleCount = 0;

            cards.forEach(card => {
                const title = (card.getAttribute('data-title') || '').toLowerCase();
                const id = (card.getAttribute('data-id') || '').toLowerCase();
                const type = (card.getAttribute('data-type') || '').toLowerCase();
                const cats = (card.getAttribute('data-cats') || type).toLowerCase().split(',');
                const subs = (card.getAttribute('data-subs') || '').toLowerCase().split(',');
                const condition = (card.getAttribute('data-condition') || 'new').toLowerCase();
                const discPct = parseInt(card.getAttribute('data-discount-pct') || '0', 10);

                const hasOffer = discPct > 0 || card.querySelector('.discount-badge') !== null;
                const isLastPiece = card.querySelector('.last-piece') !== null;
                const hasInstallments = card.querySelector('.installments') !== null;

                let match = true;

                // 1) Filtro por Submenú específico
                if (filters.sub) {
                    if (!subs.includes(filters.sub.toLowerCase())) {
                        match = false;
                    }
                }

                // 2) Filtro por Categoría Principal / Nodo Orbital
                if (match && filters.category !== 'all') {
                    if (filters.category === 'toy') {
                        match = cats.includes('toy') || type === 'toy' || type === 'colecciones';
                    } else if (filters.category === 'colecciones') {
                        match = cats.includes('colecciones') || cats.includes('toy') || type === 'colecciones' || type === 'toy';
                    } else if (filters.category === 'battery') {
                        match = cats.includes('battery') || type === 'battery';
                    } else if (filters.category === 'refacciones') {
                        match = cats.includes('refacciones') || type === 'refacciones';
                    } else if (filters.category === 'bazar') {
                        match = cats.includes('bazar') || condition === 'used' || type === 'bazar';
                    } else if (filters.category === 'bazar_2') {
                        match = cats.includes('bazar_2') || type === 'bazar_2';
                    } else if (!cats.includes(filters.category) && type !== filters.category) {
                        match = false;
                    }
                }

                // 3) Regla nacional (baterías no elegibles para paquetería estándar nacional salvo filtro explícito)
                if (isNational && (type === 'battery' || cats.includes('battery'))) {
                    match = false;
                }

                // 4) Filtro por marca / franquicia
                if (filters.brand && !title.includes(filters.brand.toLowerCase())) {
                    match = false;
                }

                // 5) Filtros especiales (oferta, últimas piezas, MSI)
                if (filters.special === 'offer' && !hasOffer) match = false;
                if (filters.special === 'last' && !isLastPiece) match = false;
                if (filters.special === 'installments' && !hasInstallments) match = false;

                // 6) Filtro de búsqueda por texto o ID
                if (filters.search) {
                    const terms = filters.search.split(/\s+/).filter(Boolean);
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

            // Mostrar u ocultar estado vacío con /images/no_disponible.gif y "Productos que te podrían interesar"
            const emptyMsg = document.getElementById('noResultsMsg');
            const noResultsTitle = document.getElementById('noResultsTitle');
            if (emptyMsg) {
                if (visibleCount === 0) {
                    if (gallery) gallery.style.display = 'none';
                    emptyMsg.style.display = 'block';
                    if (noResultsTitle) {
                        if (filters.search) {
                            noResultsTitle.textContent = `Por el momento no encontramos coincidencias exactas para "${filters.search}"`;
                        } else {
                            noResultsTitle.textContent = 'Por el momento esta categoría no tiene artículos activos disponibles';
                        }
                    }
                    renderRecommendations(isNational);
                } else {
                    if (gallery) gallery.style.display = '';
                    emptyMsg.style.display = 'none';
                }
            }

            // Indicador visual de filtro activo
            if (activeFilterLabel) {
                let label = 'Todos los productos';
                if (filters.sub && SUB_LABELS[filters.sub]) {
                    label = SUB_LABELS[filters.sub];
                } else if (filters.brand) {
                    label = `Marca: ${filters.brand.toUpperCase()}`;
                } else if (filters.category === 'toy') {
                    label = 'Outlet del Juguete (Ordenados de Menor a Mayor Precio)';
                } else if (filters.category === 'colecciones') {
                    label = 'Juguetes y Colecciones';
                } else if (filters.category === 'battery') {
                    label = 'Baterías para Auto LTH';
                } else if (filters.category === 'refacciones') {
                    label = 'Refa en Línea (Refacciones Automotrices)';
                } else if (filters.category === 'bazar') {
                    label = 'Bazar (Usados y Segunda Mano)';
                } else if (filters.category === 'bazar_2') {
                    label = 'Bazar 2 (Variedades y Miscelánea)';
                } else if (filters.special === 'offer') {
                    label = 'Ofertas Especiales (Mayor % de Descuento)';
                } else if (filters.special === 'last') {
                    label = 'Últimas Piezas';
                } else if (filters.special === 'installments') {
                    label = 'Meses sin Intereses';
                }

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
            }, 220);
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

        // 5. Botones de filtro y submenús de la barra superior
        filterButtons.forEach(btn => {
            btn.addEventListener('click', function (e) {
                e.preventDefault();

                filterButtons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');

                const filterType = this.getAttribute('data-type');
                const filterValue = this.getAttribute('data-val');

                filters.brand = '';
                filters.special = '';
                filters.sub = '';

                if (filterType === 'category') {
                    filters.category = filterValue;
                } else if (filterType === 'sub') {
                    filters.category = 'all';
                    filters.sub = filterValue;
                } else if (filterType === 'brand') {
                    filters.category = 'all';
                    filters.brand = filterValue;
                } else if (filterType === 'special') {
                    filters.category = 'all';
                    filters.special = filterValue;
                }

                applyFilters();

                const catalogSection = document.getElementById('catalogArea');
                if (catalogSection) {
                    const topPos = catalogSection.getBoundingClientRect().top + window.scrollY;
                    if (window.scrollY < topPos - 140) {
                        window.scrollTo({ top: topPos - 90, behavior: 'smooth' });
                    }
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

            products.forEach((p, idx) => {
                const isBattery = p.category === 'battery' || Boolean(p.is_battery);
                const cardEl = document.createElement('div');
                cardEl.className = `product-card flip-card ${isBattery ? 'battery-link' : ''}`;
                cardEl.setAttribute('data-id', p.id || '');
                cardEl.setAttribute('data-title', p.title || '');
                cardEl.setAttribute('data-type', p.category || 'toy');
                cardEl.setAttribute('data-orig-index', String(idx));
                cardEl.setAttribute('data-price', String(Number(p.price || 0)));
                cardEl.setAttribute('data-discount-pct', String(Number(p.discount_pct || 0)));
                cardEl.setAttribute('data-condition', p.condition || 'new');
                cardEl.setAttribute('data-brand', p.brand || '');
                if (Array.isArray(p.cats) && p.cats.length > 0) {
                    cardEl.setAttribute('data-cats', p.cats.join(','));
                }
                if (Array.isArray(p.subs) && p.subs.length > 0) {
                    cardEl.setAttribute('data-subs', p.subs.join(','));
                }

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

        // 8. API Global para interacción desde el menú orbital y submenús
        window.JinCatalog = {
            setCategory: function (cat) {
                filters.category = cat;
                filters.sub = '';
                filters.brand = '';
                filters.special = '';
                updateButtonStates('category', cat);
                applyFilters();
            },
            setSub: function (sub) {
                filters.category = 'all';
                filters.sub = sub;
                filters.brand = '';
                filters.special = '';
                updateButtonStates('sub', sub);
                applyFilters();
            },
            setBrand: function (brand) {
                filters.category = 'all';
                filters.sub = '';
                filters.brand = brand;
                filters.special = '';
                updateButtonStates('brand', brand);
                applyFilters();
            },
            setSpecial: function (special) {
                filters.category = 'all';
                filters.sub = '';
                filters.brand = '';
                filters.special = special;
                updateButtonStates('special', special);
                applyFilters();
            },
            reset: function () {
                filters = { category: 'all', sub: '', brand: '', special: '', search: '' };
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
