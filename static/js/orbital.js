/**
 * orbital.js - Jin.com.mx
 * Menú Orbital Interactivo y Animación Perpetua 3D del Logotipo Central
 */

(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const heroSection = document.querySelector('.hero-orbital-section');
        const centralCore = document.querySelector('.orbital-core');
        const logo3d = document.querySelector('.logo-3d-floating');
        const orbitContainer = document.querySelector('.orbit-track');
        const orbitNodes = document.querySelectorAll('.orbit-node');

        if (!centralCore || !logo3d) return;

        // Variables de física de levitación e inclinación
        let mouseX = 0;
        let mouseY = 0;
        let targetRotX = 0;
        let targetRotY = 0;
        let currentRotX = 0;
        let currentRotY = 0;
        let levitateAngle = 0;

        // Sensibilidad del mouse
        window.addEventListener('mousemove', function (e) {
            const rect = centralCore.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;

            const dx = (e.clientX - centerX) / (window.innerWidth / 2);
            const dy = (e.clientY - centerY) / (window.innerHeight / 2);

            targetRotY = Math.max(-18, Math.min(18, dx * 18));
            targetRotX = Math.max(-14, Math.min(14, -dy * 14));
        });

        // Bucle de animación perpetua del logo central (60 FPS)
        function renderLogoPhysics() {
            levitateAngle += 0.035;

            // Interpolación de rotación con amortiguación
            currentRotX += (targetRotX - currentRotX) * 0.08;
            currentRotY += (targetRotY - currentRotY) * 0.08;

            const levitateY = Math.sin(levitateAngle) * 12; // Oscilación de 12px
            const levitateZ = Math.cos(levitateAngle * 0.7) * 8;
            const tiltZ = Math.sin(levitateAngle * 0.5) * 2; // Ligero bamboleo

            logo3d.style.transform = `perspective(1000px) translateY(${levitateY}px) translateZ(${levitateZ}px) rotateX(${currentRotX}deg) rotateY(${currentRotY}deg) rotateZ(${tiltZ}deg)`;

            requestAnimationFrame(renderLogoPhysics);
        }

        renderLogoPhysics();

        // Posicionamiento dinámico de los nodos orbitales en Desktop
        function layoutOrbitalNodes() {
            const isDesktop = window.innerWidth >= 992;
            if (!isDesktop || !orbitContainer) {
                // En móviles o pantallas estrechas se usa el CSS Grid adaptable
                orbitNodes.forEach(node => {
                    node.style.transform = '';
                    node.style.left = '';
                    node.style.top = '';
                });
                return;
            }

            const totalNodes = orbitNodes.length;
            const radiusX = Math.min(window.innerWidth * 0.42, 440); // Radio horizontal de la elipse
            const radiusY = Math.min(window.innerHeight * 0.32, 250); // Radio vertical de la elipse
            const centerOffsetX = orbitContainer.offsetWidth / 2;
            const centerOffsetY = orbitContainer.offsetHeight / 2;

            // Offset angular para ubicar los nodos de forma armónica (evitando solaparse con el centro)
            const angleStep = (Math.PI * 2) / totalNodes;
            const startAngle = -Math.PI / 2; // Empezar arriba a las 12 en punto

            orbitNodes.forEach((node, index) => {
                const angle = startAngle + index * angleStep;
                const x = centerOffsetX + Math.cos(angle) * radiusX - (node.offsetWidth / 2);
                const y = centerOffsetY + Math.sin(angle) * radiusY - (node.offsetHeight / 2);

                node.style.position = 'absolute';
                node.style.left = `${x}px`;
                node.style.top = `${y}px`;
                node.style.transition = 'transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), opacity 0.35s ease, box-shadow 0.35s ease';
            });
        }

        window.addEventListener('resize', layoutOrbitalNodes);
        window.addEventListener('load', layoutOrbitalNodes);
        // Inicializar posicionamiento orbital con leve delay para medición precisa del DOM
        setTimeout(layoutOrbitalNodes, 100);

        // Interacciones de los Nodos Orbitales (Click / Tap / Navegación y Filtros)
        orbitNodes.forEach(node => {
            node.addEventListener('mouseenter', function () {
                this.classList.add('is-active');
            });

            node.addEventListener('mouseleave', function () {
                this.classList.remove('is-active');
            });

            node.addEventListener('click', function (e) {
                const targetHref = this.getAttribute('data-href');
                const targetFilter = this.getAttribute('data-filter');
                const targetBrand = this.getAttribute('data-brand');
                const targetSpecial = this.getAttribute('data-special');
                const scrollTarget = this.getAttribute('data-scroll');

                if (targetHref && !targetFilter) {
                    window.location.href = targetHref;
                    return;
                }

                // Si tiene scroll a sección (ej. vitrina de productos o contacto)
                if (scrollTarget) {
                    const targetEl = document.querySelector(scrollTarget);
                    if (targetEl) {
                        e.preventDefault();
                        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }

                // Disparar filtrado automático en el catálogo si aplica
                if (window.JinCatalog) {
                    if (targetFilter) {
                        window.JinCatalog.setCategory(targetFilter);
                    } else if (targetBrand) {
                        window.JinCatalog.setBrand(targetBrand);
                    } else if (targetSpecial) {
                        window.JinCatalog.setSpecial(targetSpecial);
                    }
                }
            });
        });
    });
})();
