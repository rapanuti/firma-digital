/* Ubicación visual del bloque de firma sobre el PDF (Fase 4).
 *
 * Idea central: el bloque se guarda como FRACCIONES (0..1) del recuadro visible
 * de la página renderizada. Así la posición es independiente del zoom y del
 * tamaño de pantalla; el servidor la convierte a puntos PDF al firmar.
 */
(function () {
    "use strict";

    const cfg = JSON.parse(document.getElementById("placement-config").textContent);
    const pdfjsLib = window.pdfjsLib;
    pdfjsLib.GlobalWorkerOptions.workerSrc = cfg.workerSrc;

    const canvas = document.getElementById("pdf-canvas");
    const wrapper = document.getElementById("canvas-wrapper");
    const block = document.getElementById("sign-block");
    const blockImg = document.getElementById("sign-block-img");
    const handle = document.getElementById("resize-handle");
    const pageNumEl = document.getElementById("page-num");
    const prevBtn = document.getElementById("prev-page");
    const nextBtn = document.getElementById("next-page");
    const saveBtn = document.getElementById("save-btn");
    const saveStatus = document.getElementById("save-status");

    blockImg.style.backgroundImage = `url("${cfg.signatureImageUrl}")`;

    let pdfDoc = null;
    let currentPage = (cfg.placement && cfg.placement.page) || 1;
    let pageRotation = 0;
    const MIN_PX = 36;

    // Posición del bloque como fracciones (0..1). Por defecto, abajo a la derecha.
    let frac = cfg.placement
        ? { x: cfg.placement.x, y: cfg.placement.y, w: cfg.placement.w, h: cfg.placement.h }
        : { x: 0.48, y: 0.76, w: 0.48, h: 0.18 };

    // ---- Render de la página ------------------------------------------------
    async function renderPage(num) {
        const page = await pdfDoc.getPage(num);
        pageRotation = page.rotate || 0;

        const unscaled = page.getViewport({ scale: 1 });
        const avail = wrapper.parentElement.clientWidth - 32; // padding del contenedor
        const scale = Math.max(0.2, Math.min(2.0, avail / unscaled.width));
        const viewport = page.getViewport({ scale });

        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * dpr);
        canvas.height = Math.floor(viewport.height * dpr);
        canvas.style.width = viewport.width + "px";
        canvas.style.height = viewport.height + "px";
        wrapper.style.width = viewport.width + "px";
        wrapper.style.height = viewport.height + "px";

        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        await page.render({ canvasContext: ctx, viewport }).promise;

        applyFracToBlock();
        pageNumEl.textContent = num;
        prevBtn.disabled = num <= 1;
        nextBtn.disabled = num >= cfg.pageCount;
    }

    // ---- Conversión fracciones <-> píxeles -----------------------------------
    function applyFracToBlock() {
        const W = wrapper.clientWidth, H = wrapper.clientHeight;
        block.style.left = frac.x * W + "px";
        block.style.top = frac.y * H + "px";
        block.style.width = frac.w * W + "px";
        block.style.height = frac.h * H + "px";
    }

    function updateFracFromBlock() {
        const W = wrapper.clientWidth, H = wrapper.clientHeight;
        frac = {
            x: block.offsetLeft / W,
            y: block.offsetTop / H,
            w: block.offsetWidth / W,
            h: block.offsetHeight / H,
        };
    }

    function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }

    // ---- Arrastrar el bloque -------------------------------------------------
    let dragging = false, dragDX = 0, dragDY = 0;
    block.addEventListener("pointerdown", function (e) {
        if (e.target === handle) return; // el handle gestiona el resize
        dragging = true;
        dragDX = e.clientX - block.offsetLeft;
        dragDY = e.clientY - block.offsetTop;
        block.setPointerCapture(e.pointerId);
    });
    block.addEventListener("pointermove", function (e) {
        if (!dragging) return;
        const W = wrapper.clientWidth, H = wrapper.clientHeight;
        block.style.left = clamp(e.clientX - dragDX, 0, W - block.offsetWidth) + "px";
        block.style.top = clamp(e.clientY - dragDY, 0, H - block.offsetHeight) + "px";
    });
    block.addEventListener("pointerup", function () {
        if (dragging) { dragging = false; updateFracFromBlock(); }
    });

    // ---- Redimensionar -------------------------------------------------------
    let resizing = false, startX = 0, startY = 0, startW = 0, startH = 0;
    handle.addEventListener("pointerdown", function (e) {
        e.stopPropagation();
        resizing = true;
        startX = e.clientX; startY = e.clientY;
        startW = block.offsetWidth; startH = block.offsetHeight;
        handle.setPointerCapture(e.pointerId);
    });
    handle.addEventListener("pointermove", function (e) {
        if (!resizing) return;
        const W = wrapper.clientWidth, H = wrapper.clientHeight;
        const newW = clamp(startW + (e.clientX - startX), MIN_PX, W - block.offsetLeft);
        const newH = clamp(startH + (e.clientY - startY), MIN_PX, H - block.offsetTop);
        block.style.width = newW + "px";
        block.style.height = newH + "px";
    });
    handle.addEventListener("pointerup", function () {
        if (resizing) { resizing = false; updateFracFromBlock(); }
    });

    // ---- Navegación de páginas ----------------------------------------------
    prevBtn.addEventListener("click", function () {
        if (currentPage > 1) { currentPage--; renderPage(currentPage); }
    });
    nextBtn.addEventListener("click", function () {
        if (currentPage < cfg.pageCount) { currentPage++; renderPage(currentPage); }
    });

    // ---- Guardar posición ----------------------------------------------------
    saveBtn.addEventListener("click", async function () {
        updateFracFromBlock();
        saveStatus.textContent = "Guardando…";
        saveStatus.className = "text-sm text-center text-slate-500";
        try {
            const resp = await fetch(cfg.apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken },
                body: JSON.stringify({
                    page: currentPage,
                    fx: frac.x, fy: frac.y, fw: frac.w, fh: frac.h,
                    rotation: pageRotation,
                }),
            });
            if (resp.ok) {
                saveStatus.textContent = "Posición guardada ✓ (página " + currentPage + ")";
                saveStatus.className = "text-sm text-center text-emerald-600";
            } else {
                const txt = await resp.text();
                saveStatus.textContent = "Error: " + txt;
                saveStatus.className = "text-sm text-center text-red-600";
            }
        } catch (err) {
            saveStatus.textContent = "Error de red al guardar.";
            saveStatus.className = "text-sm text-center text-red-600";
        }
    });

    // ---- Arranque ------------------------------------------------------------
    pdfjsLib.getDocument({ url: cfg.pdfUrl, withCredentials: true }).promise
        .then(function (doc) {
            pdfDoc = doc;
            currentPage = Math.min(currentPage, doc.numPages);
            return renderPage(currentPage);
        })
        .catch(function (err) {
            saveStatus.textContent = "No se pudo cargar el PDF.";
            saveStatus.className = "text-sm text-center text-red-600";
            console.error(err);
        });

    window.addEventListener("resize", function () {
        if (pdfDoc) renderPage(currentPage);
    });
})();
