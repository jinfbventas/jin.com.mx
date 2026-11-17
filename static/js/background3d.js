/**
 * background3d.js - Jin.com.mx
 * Motor de Fondo Dinámico 3D Glossy / Y2K
 * Recrea los aros líquidos cristalinos, burbujas translúcidas con brillo especular
 * y profundidad multicapa con aceleración por GPU a 60 FPS.
 */

(function () {
    'use strict';

    const canvas = document.createElement('canvas');
    canvas.id = 'bg-canvas';
    canvas.style.position = 'fixed';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.width = '100vw';
    canvas.style.height = '100vh';
    canvas.style.zIndex = '-1';
    canvas.style.pointerEvents = 'none';
    document.body.prepend(canvas);

    const ctx = canvas.getContext('2d');
    let width = 0;
    let height = 0;
    let dpr = 1;

    // Estado del cursor para interacción y parallax
    let mouse = { x: 0.5, y: 0.5, targetX: 0.5, targetY: 0.5 };
    let isTouch = false;

    function resize() {
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        ctx.scale(dpr, dpr);
    }

    window.addEventListener('resize', resize);
    resize();

    window.addEventListener('mousemove', function (e) {
        if (!isTouch) {
            mouse.targetX = e.clientX / width;
            mouse.targetY = e.clientY / height;
        }
    });

    window.addEventListener('touchstart', function () {
        isTouch = true;
    }, { passive: true });

    // Configuración de burbujas flotantes 3D
    const BUBBLE_COUNT = width < 768 ? 16 : 28;
    const bubbles = [];

    for (let i = 0; i < BUBBLE_COUNT; i++) {
        bubbles.push({
            x: Math.random() * width,
            y: Math.random() * height,
            radius: 8 + Math.random() * (width < 768 ? 22 : 36),
            speedY: 0.2 + Math.random() * 0.5,
            speedX: (Math.random() - 0.5) * 0.3,
            phase: Math.random() * Math.PI * 2,
            wobbleSpeed: 0.015 + Math.random() * 0.02,
            depth: 0.3 + Math.random() * 0.7, // Parallax depth factor
            colorType: Math.random() > 0.4 ? 'magenta' : (Math.random() > 0.5 ? 'cyan' : 'purple'),
            opacity: 0.25 + Math.random() * 0.45
        });
    }

    // Configuración de aros líquidos 3D
    const rings = [
        {
            centerXRatio: 0.5,
            centerYRatio: 0.42,
            radiusXRatio: 0.42,
            radiusYRatio: 0.26,
            angle: -0.22,
            rotSpeed: 0.0006,
            thickness: 24,
            hueStart: '#4F6BFF',
            hueMid: '#9D4EDD',
            hueEnd: '#FF56B2',
            depth: 0.5
        },
        {
            centerXRatio: 0.48,
            centerYRatio: 0.48,
            radiusXRatio: 0.55,
            radiusYRatio: 0.34,
            angle: 0.35,
            rotSpeed: -0.00045,
            thickness: 18,
            hueStart: '#00F5D4',
            hueMid: '#4F6BFF',
            hueEnd: '#FF007F',
            depth: 0.8
        },
        {
            centerXRatio: 0.52,
            centerYRatio: 0.45,
            radiusXRatio: 0.32,
            radiusYRatio: 0.18,
            angle: -0.65,
            rotSpeed: 0.0008,
            thickness: 14,
            hueStart: '#FF56B2',
            hueMid: '#00F5D4',
            hueEnd: '#4F6BFF',
            depth: 0.3
        }
    ];

    let time = 0;

    function drawDeepGradient() {
        // Fondo base con gradiente cósmico índigo a magenta neón
        const grad = ctx.createLinearGradient(
            width * 0.1 + (mouse.x - 0.5) * 60,
            0,
            width * 0.9 + (mouse.x - 0.5) * -60,
            height
        );
        grad.addColorStop(0.0, '#100c2a');
        grad.addColorStop(0.25, '#1e1b4b');
        grad.addColorStop(0.55, '#3b1259');
        grad.addColorStop(0.85, '#5b1046');
        grad.addColorStop(1.0, '#2b0728');

        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, width, height);

        // Brillo ambiental central detrás del logo
        const auraGrad = ctx.createRadialGradient(
            width * 0.5 + (mouse.x - 0.5) * 40,
            height * 0.42 + (mouse.y - 0.5) * 40,
            20,
            width * 0.5,
            height * 0.42,
            Math.max(width, height) * 0.55
        );
        auraGrad.addColorStop(0, 'rgba(157, 78, 221, 0.35)');
        auraGrad.addColorStop(0.35, 'rgba(79, 107, 255, 0.22)');
        auraGrad.addColorStop(0.7, 'rgba(255, 86, 178, 0.12)');
        auraGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');

        ctx.fillStyle = auraGrad;
        ctx.fillRect(0, 0, width, height);
    }

    function drawLiquidRing(ring) {
        ctx.save();

        const pX = (mouse.x - 0.5) * 35 * ring.depth;
        const pY = (mouse.y - 0.5) * 25 * ring.depth;
        const cx = width * ring.centerXRatio + pX;
        const cy = height * ring.centerYRatio + pY;
        const rx = width * ring.radiusXRatio;
        const ry = height * ring.radiusYRatio;

        const currentAngle = ring.angle + time * ring.rotSpeed;

        ctx.translate(cx, cy);
        ctx.rotate(currentAngle);

        // Creamos la cinta 3D con gradiente glossy
        const ringGrad = ctx.createLinearGradient(-rx, -ry, rx, ry);
        ringGrad.addColorStop(0.0, ring.hueStart);
        ringGrad.addColorStop(0.45, ring.hueMid);
        ringGrad.addColorStop(0.85, ring.hueEnd);
        ringGrad.addColorStop(1.0, ring.hueStart);

        ctx.lineWidth = ring.thickness;
        ctx.strokeStyle = ringGrad;
        ctx.shadowColor = ring.hueEnd;
        ctx.shadowBlur = 18;
        ctx.globalAlpha = 0.55;

        ctx.beginPath();
        ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
        ctx.stroke();

        // Reflejo especular blanco fino sobre el borde superior del aro
        ctx.lineWidth = Math.max(2, ring.thickness * 0.22);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
        ctx.shadowColor = '#ffffff';
        ctx.shadowBlur = 10;
        ctx.globalAlpha = 0.7;

        ctx.beginPath();
        ctx.ellipse(0, -ring.thickness * 0.2, rx * 0.99, ry * 0.98, 0, Math.PI * 0.2, Math.PI * 0.85);
        ctx.stroke();

        ctx.restore();
    }

    function drawBubble(b) {
        ctx.save();

        const pX = (mouse.x - 0.5) * 50 * b.depth;
        const pY = (mouse.y - 0.5) * 40 * b.depth;
        const bx = b.x + pX;
        const by = b.y + pY;
        const r = b.radius;

        // Cuerpo translúcido de la burbuja
        const grad = ctx.createRadialGradient(
            bx - r * 0.35, by - r * 0.35, r * 0.1,
            bx, by, r
        );

        if (b.colorType === 'magenta') {
            grad.addColorStop(0, 'rgba(255, 255, 255, 0.9)');
            grad.addColorStop(0.25, 'rgba(255, 86, 178, 0.55)');
            grad.addColorStop(0.7, 'rgba(157, 78, 221, 0.35)');
            grad.addColorStop(1, 'rgba(79, 107, 255, 0.7)');
        } else if (b.colorType === 'cyan') {
            grad.addColorStop(0, 'rgba(255, 255, 255, 0.9)');
            grad.addColorStop(0.25, 'rgba(0, 245, 212, 0.55)');
            grad.addColorStop(0.7, 'rgba(79, 107, 255, 0.35)');
            grad.addColorStop(1, 'rgba(157, 78, 221, 0.7)');
        } else {
            grad.addColorStop(0, 'rgba(255, 255, 255, 0.9)');
            grad.addColorStop(0.3, 'rgba(157, 78, 221, 0.6)');
            grad.addColorStop(0.8, 'rgba(255, 86, 178, 0.35)');
            grad.addColorStop(1, 'rgba(0, 245, 212, 0.65)');
        }

        ctx.globalAlpha = b.opacity;
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(bx, by, r, 0, Math.PI * 2);
        ctx.fill();

        // Borde exterior tipo cristal 3D
        ctx.lineWidth = Math.max(1, r * 0.08);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.75)';
        ctx.shadowColor = '#ffffff';
        ctx.shadowBlur = 6;
        ctx.stroke();

        // Destello especular secundario inferior (efecto líquido Y2K)
        ctx.beginPath();
        ctx.arc(bx + r * 0.3, by + r * 0.3, r * 0.22, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
        ctx.fill();

        ctx.restore();
    }

    function animate() {
        time++;

        // Interpolación suave del cursor (amortiguación / damping)
        mouse.x += (mouse.targetX - mouse.x) * 0.05;
        mouse.y += (mouse.targetY - mouse.y) * 0.05;

        ctx.clearRect(0, 0, width, height);

        // 1. Capa de Fondo
        drawDeepGradient();

        // 2. Aros 3D de fondo
        rings.forEach(ring => drawLiquidRing(ring));

        // 3. Burbujas flotantes en movimiento
        for (let i = 0; i < bubbles.length; i++) {
            const b = bubbles[i];
            b.y -= b.speedY;
            b.x += Math.sin(time * b.wobbleSpeed + b.phase) * b.speedX;

            // Reciclado cuando sale de la pantalla
            if (b.y < -b.radius * 2) {
                b.y = height + b.radius * 2;
                b.x = Math.random() * width;
            }
            if (b.x < -b.radius * 2) b.x = width + b.radius * 2;
            if (b.x > width + b.radius * 2) b.x = -b.radius * 2;

            drawBubble(b);
        }

        requestAnimationFrame(animate);
    }

    animate();
})();
