/* Ubicación visual de los bloques de firma sobre el PDF.
 *
 * Idea central: cada bloque se guarda como FRACCIONES (0..1) del recuadro visible
 * de su página renderizada. Así la posición es independiente del zoom y del
 * tamaño de pantalla; el servidor la convierte a puntos PDF al firmar.
 *
 * Puede haber varios bloques (en la misma página o en páginas distintas), cada
 * uno con su propia firma. Todos se estampan a la vez al firmar.
 */
(function () {
    "use strict";

    const cfg = JSON.parse(document.getElementById("placement-config").textContent);
    const initial = JSON.parse(document.getElementById("placements-data").textContent);
    const pdfjsLib = window.pdfjsLib;
    pdfjsLib.GlobalWorkerOptions.workerSrc = cfg.workerSrc;

    const canvas = document.getElementById("pdf-canvas");
    const wrapper = document.getElementById("canvas-wrapper");
    const pageNumEl = document.getElementById("page-num");
    const prevBtn = document.getElementById("prev-page");
    const nextBtn = document.getElementById("next-page");
    const saveBtn = document.getElementById("save-btn");
    const saveStatus = document.getElementById("save-status");
    const addBtn = document.getElementById("add-block");
    const listEl = document.getElementById("block-list");
    const countEl = document.getElementById("block-count");
    const goSign = document.getElementById("go-sign");

    // Firmas disponibles (radios del panel lateral).
    const imageRadios = Array.from(document.getElementsByName("signature_image"));
    const images = {};
    for (const r of imageRadios) {
        images[r.value] = {
            url: r.dataset.url,
            name: r.closest("label").querySelector(".font-medium").textContent.trim(),
        };
    }
    function checkedImageId() {
        const r = imageRadios.find((r) => r.checked) || imageRadios[0];
        return r ? Number(r.value) : null;
    }
    function checkImage(id) {
        for (const r of imageRadios) r.checked = Number(r.value) === id;
    }

    // Modo del QR (URL de verificación vs. datos de la firma)
    const qrRadios = document.getElementsByName("qr_mode");
    if (cfg.qrMode) {
        for (const r of qrRadios) r.checked = r.value === cfg.qrMode;
    }
    function selectedQrMode() {
        for (const r of qrRadios) if (r.checked) return r.value;
        return "url";
    }

    let pdfDoc = null;
    let currentPage = initial.length ? initial[0].page : 1;
    let pageRotation = 0;
    let dirty = false;
    const MIN_PX = 36;

    // Estado: lista de bloques {page, x, y, w, h, rotation, image, el}.
    const blocks = initial.map((p) => ({
        page: p.page, x: p.x, y: p.y, w: p.w, h: p.h,
        rotation: p.rotation || 0,
        image: p.signature_image || checkedImageId(),
        el: null,
    }));
    let selected = blocks[0] || null;
    if (selected) checkImage(selected.image);

    function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }
    function markDirty() {
        dirty = true;
        saveStatus.textContent = "Cambios sin guardar";
        saveStatus.className = "text-sm text-center text-amber-600";
    }

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

        pageNumEl.textContent = num;
        prevBtn.disabled = num <= 1;
        nextBtn.disabled = num >= cfg.pageCount;
        drawBlocks();
    }

    // ---- Bloques en pantalla -------------------------------------------------
    function createBlockEl(b) {
        const el = document.createElement("div");
        el.className = "absolute cursor-move border-2 border-dashed bg-white/70";
        el.style.touchAction = "none";
        el.innerHTML =
            '<div class="h-full w-full bg-center bg-no-repeat bg-contain pointer-events-none"></div>' +
            '<button type="button" title="Quitar firma" class="absolute -top-2.5 -right-2.5 h-5 w-5 rounded-full bg-red-600 text-xs leading-5 text-white">×</button>' +
            '<div class="absolute -bottom-1.5 -right-1.5 h-3 w-3 cursor-se-resize rounded-sm bg-brand-600" style="touch-action:none"></div>';
        const removeBtn = el.querySelector("button");
        const handle = el.lastElementChild;

        removeBtn.addEventListener("pointerdown", (e) => e.stopPropagation());
        removeBtn.addEventListener("click", () => removeBlock(b));

        // Arrastrar
        let dragging = false, dx = 0, dy = 0;
        el.addEventListener("pointerdown", function (e) {
            if (e.target === handle) return;
            select(b);
            dragging = true;
            dx = e.clientX - el.offsetLeft;
            dy = e.clientY - el.offsetTop;
            el.setPointerCapture(e.pointerId);
        });
        el.addEventListener("pointermove", function (e) {
            if (!dragging) return;
            const W = wrapper.clientWidth, H = wrapper.clientHeight;
            el.style.left = clamp(e.clientX - dx, 0, W - el.offsetWidth) + "px";
            el.style.top = clamp(e.clientY - dy, 0, H - el.offsetHeight) + "px";
        });
        el.addEventListener("pointerup", function () {
            if (dragging) { dragging = false; readBlockFromEl(b); markDirty(); }
        });

        // Redimensionar
        let resizing = false, sx = 0, sy = 0, sw = 0, sh = 0;
        handle.addEventListener("pointerdown", function (e) {
            e.stopPropagation();
            select(b);
            resizing = true;
            sx = e.clientX; sy = e.clientY;
            sw = el.offsetWidth; sh = el.offsetHeight;
            handle.setPointerCapture(e.pointerId);
        });
        handle.addEventListener("pointermove", function (e) {
            if (!resizing) return;
            const W = wrapper.clientWidth, H = wrapper.clientHeight;
            el.style.width = clamp(sw + (e.clientX - sx), MIN_PX, W - el.offsetLeft) + "px";
            el.style.height = clamp(sh + (e.clientY - sy), MIN_PX, H - el.offsetTop) + "px";
        });
        handle.addEventListener("pointerup", function () {
            if (resizing) { resizing = false; readBlockFromEl(b); markDirty(); }
        });

        b.el = el;
        return el;
    }

    function readBlockFromEl(b) {
        const W = wrapper.clientWidth, H = wrapper.clientHeight;
        b.x = b.el.offsetLeft / W;
        b.y = b.el.offsetTop / H;
        b.w = b.el.offsetWidth / W;
        b.h = b.el.offsetHeight / H;
    }

    function drawBlocks() {
        for (const b of blocks) {
            if (b.el) b.el.remove();
            if (b.page !== currentPage) continue;
            const el = b.el || createBlockEl(b);
            const W = wrapper.clientWidth, H = wrapper.clientHeight;
            el.style.left = b.x * W + "px";
            el.style.top = b.y * H + "px";
            el.style.width = b.w * W + "px";
            el.style.height = b.h * H + "px";
            const img = images[b.image];
            el.firstElementChild.style.backgroundImage = img ? `url("${img.url}")` : "none";
            el.classList.toggle("border-brand-600", b === selected);
            el.classList.toggle("border-slate-400", b !== selected);
            el.style.zIndex = b === selected ? 2 : 1;
            wrapper.appendChild(el);
        }
        renderList();
    }

    function renderList() {
        listEl.innerHTML = "";
        countEl.textContent = blocks.length ? `${blocks.length}` : "";
        if (!blocks.length) {
            const li = document.createElement("li");
            li.className = "text-slate-400";
            li.textContent = "Aún no hay firmas. Agrega una.";
            listEl.appendChild(li);
        }
        blocks.forEach(function (b, i) {
            const li = document.createElement("li");
            li.className =
                "flex cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1 " +
                (b === selected ? "bg-brand-50 text-brand-700" : "hover:bg-slate-50 text-slate-700");
            const name = images[b.image] ? images[b.image].name : "Firma predeterminada";
            li.innerHTML = `<span class="truncate">${i + 1}. ${escapeHtml(name)}</span>` +
                `<span class="shrink-0 text-xs text-slate-400">pág. ${b.page}</span>`;
            li.addEventListener("click", function () {
                select(b);
                if (b.page !== currentPage) { currentPage = b.page; renderPage(currentPage); }
            });
            listEl.appendChild(li);
        });
    }

    function escapeHtml(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    function select(b) {
        selected = b;
        if (b) checkImage(b.image);
        drawBlocks();
    }

    function removeBlock(b) {
        const i = blocks.indexOf(b);
        if (i < 0) return;
        if (b.el) b.el.remove();
        blocks.splice(i, 1);
        selected = blocks[Math.min(i, blocks.length - 1)] || null;
        markDirty();
        drawBlocks();
    }

    function addBlock() {
        // Cada bloque nuevo aparece un poco desplazado para no tapar al anterior.
        const onPage = blocks.filter((b) => b.page === currentPage).length;
        const offset = (onPage % 5) * 0.04;
        const b = {
            page: currentPage,
            x: clamp(0.48 - offset, 0, 0.52), y: clamp(0.76 - offset, 0, 0.82),
            w: 0.48, h: 0.18,
            rotation: pageRotation,
            image: checkedImageId(),
            el: null,
        };
        blocks.push(b);
        markDirty();
        select(b);
    }

    addBtn.addEventListener("click", addBlock);

    // Cambiar la firma del bloque seleccionado.
    for (const r of imageRadios) {
        r.addEventListener("change", function () {
            if (selected && r.checked) {
                selected.image = Number(r.value);
                markDirty();
                drawBlocks();
            }
        });
    }
    for (const r of qrRadios) r.addEventListener("change", markDirty);

    // ---- Navegación de páginas ----------------------------------------------
    prevBtn.addEventListener("click", function () {
        if (currentPage > 1) { currentPage--; renderPage(currentPage); }
    });
    nextBtn.addEventListener("click", function () {
        if (currentPage < cfg.pageCount) { currentPage++; renderPage(currentPage); }
    });

    // ---- Guardar -------------------------------------------------------------
    async function save() {
        if (!blocks.length) {
            saveStatus.textContent = "Agrega al menos una firma.";
            saveStatus.className = "text-sm text-center text-red-600";
            return false;
        }
        saveStatus.textContent = "Guardando…";
        saveStatus.className = "text-sm text-center text-slate-500";
        try {
            const resp = await fetch(cfg.apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken },
                body: JSON.stringify({
                    qr_mode: selectedQrMode(),
                    placements: blocks.map((b) => ({
                        page: b.page, fx: b.x, fy: b.y, fw: b.w, fh: b.h,
                        rotation: b.rotation, signature_image: b.image,
                    })),
                }),
            });
            if (resp.ok) {
                dirty = false;
                const n = blocks.length;
                saveStatus.textContent = `${n} firma${n === 1 ? "" : "s"} guardada${n === 1 ? "" : "s"} ✓`;
                saveStatus.className = "text-sm text-center text-emerald-600";
                return true;
            }
            saveStatus.textContent = "Error: " + (await resp.text());
            saveStatus.className = "text-sm text-center text-red-600";
        } catch (err) {
            saveStatus.textContent = "Error de red al guardar.";
            saveStatus.className = "text-sm text-center text-red-600";
        }
        return false;
    }

    saveBtn.addEventListener("click", save);

    // "Ir a firmar" guarda primero si hay cambios pendientes.
    goSign.addEventListener("click", async function (e) {
        if (!dirty) return;
        e.preventDefault();
        if (await save()) window.location.href = goSign.href;
    });

    // ---- Arranque ------------------------------------------------------------
    pdfjsLib.getDocument({ url: cfg.pdfUrl, withCredentials: true }).promise
        .then(function (doc) {
            pdfDoc = doc;
            currentPage = Math.min(currentPage, doc.numPages);
            return renderPage(currentPage);
        })
        .then(function () {
            // Documento sin ubicaciones: se arranca con un bloque listo para mover.
            if (!blocks.length) addBlock();
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
