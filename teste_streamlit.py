import io
import os
import base64
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from PyPDF2 import PageObject, PdfReader, PdfWriter


# Optional renderer for high-quality PDF previews.
try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None


@dataclass
class CropValues:
    left: float
    right: float
    top: float
    bottom: float


def clone_page(page: PageObject) -> PageObject:
    writer = PdfWriter()
    writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def pages_to_pdf_bytes(pages: List[PageObject]) -> bytes:
    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def pdf_bytes_to_pages(pdf_bytes: bytes) -> List[PageObject]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [clone_page(page) for page in reader.pages]


def image_file_to_page(uploaded_file) -> PageObject:
    with Image.open(uploaded_file) as img:
        rgb_img = img.convert("RGB")
        temp = io.BytesIO()
        rgb_img.save(temp, "PDF", resolution=100.0)
        temp.seek(0)
        return PdfReader(temp).pages[0]


def render_page_to_pil(page: PageObject, scale: float = 1.7) -> Optional[Image.Image]:
    if pdfium is None:
        return None

    try:
        writer = PdfWriter()
        writer.add_page(page)
        data = io.BytesIO()
        writer.write(data)
        data.seek(0)

        doc = pdfium.PdfDocument(data.getvalue())
        rendered = doc[0].render(scale=scale)
        return rendered.to_pil().convert("RGB")
    except Exception:
        return None


def pil_to_base64_png(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@st.cache_resource
def get_viewer_component():
    """Generates a robust Bidirectional Streamlit Component at runtime."""
    html_content = """<!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { margin: 0; padding: 0; overflow: hidden; background: transparent; }
            .crop-handle {
                position: absolute;
                width: 14px; height: 14px;
                background: #fff; border: 2px solid #4ec3ff;
                border-radius: 50%;
                box-shadow: 0 2px 4px rgba(0,0,0,0.5);
                pointer-events: auto;
                z-index: 10;
            }
            .h-nw { top: -7px; left: -7px; cursor: nwse-resize; }
            .h-n  { top: -7px; left: calc(50% - 7px); cursor: ns-resize; }
            .h-ne { top: -7px; right: -7px; cursor: nesw-resize; }
            .h-e  { top: calc(50% - 7px); right: -7px; cursor: ew-resize; }
            .h-se { bottom: -7px; right: -7px; cursor: nwse-resize; }
            .h-s  { bottom: -7px; left: calc(50% - 7px); cursor: ns-resize; }
            .h-sw { bottom: -7px; left: -7px; cursor: nesw-resize; }
            .h-w  { top: calc(50% - 7px); left: -7px; cursor: ew-resize; }
            
            #applyBtn {
                position: absolute;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: #61d7a4;
                color: #0a1020;
                border: none;
                border-radius: 20px;
                padding: 8px 24px;
                font-size: 14px;
                font-weight: bold;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(0,0,0,0.4);
                pointer-events: auto;
                z-index: 9999;
                transition: background 150ms ease;
            }
            #applyBtn:hover { background: #7eeabf; }
            
            #viewport {
                width: 100%;
                background: linear-gradient(180deg, #0d1424, #0a1020);
                border: 1px solid rgba(132, 169, 232, 0.28);
                border-radius: 14px;
                overflow: hidden;
                position: relative;
                user-select: none;
                touch-action: none;
            }
        </style>
    </head>
    <body>
        <div id="viewport">
            <img id="img_element" draggable="false" style="
                position: absolute;
                left: 0;
                top: 0;
                transform-origin: 0 0;
                cursor: grab;
                will-change: transform;
                user-drag: none;
                -webkit-user-drag: none;
            " />
            
            <div id="cropBox" style="
                position: absolute;
                border: 2px solid #4ec3ff;
                box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.65);
                pointer-events: auto;
                cursor: move;
                display: none;
            ">
                <div class="crop-handle h-nw" data-dir="nw"></div>
                <div class="crop-handle h-n" data-dir="n"></div>
                <div class="crop-handle h-ne" data-dir="ne"></div>
                <div class="crop-handle h-e" data-dir="e"></div>
                <div class="crop-handle h-se" data-dir="se"></div>
                <div class="crop-handle h-s" data-dir="s"></div>
                <div class="crop-handle h-sw" data-dir="sw"></div>
                <div class="crop-handle h-w" data-dir="w"></div>
            </div>
            
            <button id="applyBtn" style="display: none;">âœ” Apply Crop</button>

            <div id="hint" style="
                position: absolute;
                right: 10px;
                top: 8px;
                color: rgba(226, 236, 255, 0.72);
                font: 12px/1.2 Segoe UI, sans-serif;
                background: rgba(19, 28, 48, 0.55);
                border: 1px solid rgba(106, 143, 211, 0.32);
                border-radius: 8px;
                padding: 4px 7px;
                pointer-events: none;
                z-index: 999;
            "></div>
        </div>

        <script>
            // --- STREAMLIT COMPONENT API BRIDGE ---
            function sendMessageToStreamlitClient(type, data) {
                const outData = Object.assign({
                    isStreamlitMessage: true,
                    type: type,
                }, data);
                window.parent.postMessage(outData, "*");
            }
            function init() { sendMessageToStreamlitClient("streamlit:componentReady", {apiVersion: 1}); }
            function setFrameHeight(height) { sendMessageToStreamlitClient("streamlit:setFrameHeight", {height: height}); }
            function sendDataToPython(value) { sendMessageToStreamlitClient("streamlit:setComponentValue", {value: value}); }
            
            const viewport = document.getElementById('viewport');
            const img = document.getElementById('img_element');
            const cropBox = document.getElementById('cropBox');
            const applyBtn = document.getElementById('applyBtn');
            const hint = document.getElementById('hint');
            
            let scale = 1, minScale = 1, maxScale = 6;
            let tx = 0, ty = 0;
            let dragging = false, sx = 0, sy = 0;
            let cx = 0, cy = 0, cw = 0, ch = 0;
            let cnx0 = 0.0, cny0 = 0.0, cnx1 = 1.0, cny1 = 1.0;
            let isResizing = false, draggingBox = false, currentHandle = null;
            let cropMode = false;
            
            function clamp(v, a, b) { return Math.min(Math.max(v, a), b); }
            
            function fitImage() {
                const vw = viewport.clientWidth;
                const vh = viewport.clientHeight;
                const iw = img.naturalWidth;
                const ih = img.naturalHeight;
                if (!iw || !ih || !vw || !vh) return;

                const fit = Math.min(vw / iw, vh / ih);
                minScale = fit;
                scale = fit;
                tx = (vw - iw * scale) / 2;
                ty = (vh - ih * scale) / 2;
                applyTransform();

                if (cropMode) {
                    const r = getImageRect();
                    cx = r.left + r.width * cnx0;
                    cy = r.top + r.height * cny0;
                    cw = r.width * (cnx1 - cnx0);
                    ch = r.height * (cny1 - cny0);
                    
                    cropBox.style.display = 'block';
                    applyBtn.style.display = 'block';
                    updateCropDOM();
                } else {
                    cropBox.style.display = 'none';
                    applyBtn.style.display = 'none';
                }
            }
            
            function getImageRect() {
                const sw = img.naturalWidth * scale;
                const sh = img.naturalHeight * scale;
                return { left: tx, top: ty, right: tx + sw, bottom: ty + sh, width: sw, height: sh };
            }

            function updateCropDOM() {
                cropBox.style.left = cx + 'px';
                cropBox.style.top = cy + 'px';
                cropBox.style.width = cw + 'px';
                cropBox.style.height = ch + 'px';
            }
            
            function resizeCrop(dx, dy, dir) {
                const r = getImageRect();
                let ncx = cx, ncy = cy, ncw = cw, nch = ch;

                if (dir.includes('w')) {
                    ncx += dx; ncw -= dx;
                    if (ncw < 30) { ncx -= (30 - ncw); ncw = 30; }
                    if (ncx < r.left) { ncw -= (r.left - ncx); ncx = r.left; }
                }
                if (dir.includes('e')) {
                    ncw += dx;
                    if (ncw < 30) ncw = 30;
                    if (ncx + ncw > r.right) ncw = r.right - ncx;
                }
                if (dir.includes('n')) {
                    ncy += dy; nch -= dy;
                    if (nch < 30) { ncy -= (30 - nch); nch = 30; }
                    if (ncy < r.top) { nch -= (r.top - ncy); ncy = r.top; }
                }
                if (dir.includes('s')) {
                    nch += dy;
                    if (nch < 30) nch = 30;
                    if (ncy + nch > r.bottom) nch = r.bottom - ncy;
                }
                cx = ncx; cy = ncy; cw = ncw; ch = nch;
            }

            function moveCropBox(dx, dy) {
                const r = getImageRect();
                cx += dx; cy += dy;
                if (cx < r.left) cx = r.left;
                if (cy < r.top) cy = r.top;
                if (cx + cw > r.right) cx = r.right - cw;
                if (cy + ch > r.bottom) cy = r.bottom - ch;
            }
            
            function clampTranslate() {
                const vw = viewport.clientWidth;
                const vh = viewport.clientHeight;
                const sw = img.naturalWidth * scale;
                const sh = img.naturalHeight * scale;
                tx = clamp(tx, Math.min(0, vw - sw), Math.max(0, vw - sw));
                ty = clamp(ty, Math.min(0, vh - sh), Math.max(0, vh - sh));
            }

            function applyTransform() {
                clampTranslate();
                img.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
            }
            
            img.addEventListener('dragstart', e => e.preventDefault());
            img.addEventListener('dragend', e => e.preventDefault());
            img.addEventListener('load', fitImage);
            window.addEventListener('resize', fitImage);

            viewport.addEventListener('wheel', e => {
                if (cropMode) return;
                e.preventDefault();
                const rect = viewport.getBoundingClientRect();
                const mx = e.clientX - rect.left;
                const my = e.clientY - rect.top;

                const oldScale = scale;
                const factor = e.deltaY < 0 ? 1.09 : 0.92;
                scale = clamp(scale * factor, minScale, maxScale);

                tx = mx - (mx - tx) / oldScale * scale;
                ty = my - (my - ty) / oldScale * scale;
                applyTransform();
            }, { passive: false });

            viewport.addEventListener('mousedown', e => {
                if (cropMode) return;
                dragging = true;
                sx = e.clientX; sy = e.clientY;
                img.style.cursor = 'grabbing';
            });
            
            const handles = cropBox.querySelectorAll('.crop-handle');
            handles.forEach(h => {
                h.addEventListener('mousedown', e => {
                    if (!cropMode) return;
                    e.preventDefault(); e.stopPropagation();
                    isResizing = true;
                    currentHandle = e.target.getAttribute('data-dir');
                    sx = e.clientX; sy = e.clientY;
                });
            });

            cropBox.addEventListener('mousedown', e => {
                if (!cropMode) return;
                e.preventDefault(); e.stopPropagation();
                draggingBox = true;
                sx = e.clientX; sy = e.clientY;
            });

            applyBtn.addEventListener('click', e => {
                if (!cropMode) return;
                e.preventDefault(); e.stopPropagation();
                
                const r = getImageRect();
                if (r.width <= 0 || r.height <= 0) return;

                const nx0 = clamp((cx - r.left) / r.width, 0, 1);
                const ny0 = clamp((cy - r.top) / r.height, 0, 1);
                const nx1 = clamp((cx + cw - r.left) / r.width, 0, 1);
                const ny1 = clamp((cy + ch - r.top) / r.height, 0, 1);

                if ((nx1 - nx0) <= 0.001 || (ny1 - ny0) <= 0.001) return;
                
                sendDataToPython({
                    crop: [
                        Number(nx0.toFixed(6)),
                        Number(ny0.toFixed(6)),
                        Number(nx1.toFixed(6)),
                        Number(ny1.toFixed(6)),
                    ]
                });
            });
            
            window.addEventListener('mouseup', () => {
                if (cropMode) {
                    isResizing = false;
                    draggingBox = false;
                    const r = getImageRect();
                    cnx0 = (cx - r.left) / r.width;
                    cny0 = (cy - r.top) / r.height;
                    cnx1 = (cx + cw - r.left) / r.width;
                    cny1 = (cy + ch - r.top) / r.height;
                } else {
                    dragging = false;
                    img.style.cursor = 'grab';
                }
            });

            window.addEventListener('mousemove', e => {
                if (cropMode) {
                    if (isResizing) {
                        resizeCrop(e.clientX - sx, e.clientY - sy, currentHandle);
                        sx = e.clientX; sy = e.clientY;
                        updateCropDOM();
                    } else if (draggingBox) {
                        moveCropBox(e.clientX - sx, e.clientY - sy);
                        sx = e.clientX; sy = e.clientY;
                        updateCropDOM();
                    }
                    return;
                }
                
                if (!dragging) return;
                tx += e.clientX - sx;
                ty += e.clientY - sy;
                sx = e.clientX; sy = e.clientY;
                applyTransform();
            });

            // Streamlit props listener
            window.addEventListener("message", function(event) {
                if (event.data.type === "streamlit:render") {
                    const args = event.data.args;
                    
                    if (args.height) {
                        viewport.style.height = args.height + 'px';
                        setFrameHeight(args.height + 4);
                    }
                    if (args.img_b64) {
                        const newSrc = "data:image/png;base64," + args.img_b64;
                        if (img.src !== newSrc) {
                            img.src = newSrc;
                        }
                    }
                    
                    cropMode = args.crop_mode;
                    hint.innerText = cropMode ? 'Crop Mode: Adjust handles & Apply' : 'Wheel = Zoom | Drag = Pan';
                    
                    if (cropMode) {
                        cropBox.style.display = 'block';
                        applyBtn.style.display = 'block';
                        fitImage(); 
                    } else {
                        cropBox.style.display = 'none';
                        applyBtn.style.display = 'none';
                    }
                }
            });

            init();
        </script>
    </body>
    </html>
    """
    script_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    comp_dir = os.path.join(script_dir, ".pdf_viewer_comp")
    os.makedirs(comp_dir, exist_ok=True)
    with open(os.path.join(comp_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return components.declare_component("interactive_viewer_v2", path=comp_dir)


def apply_normalized_crop(page: PageObject, nx0: float, ny0: float, nx1: float, ny1: float) -> None:
    nx0, nx1 = sorted((max(0.0, min(1.0, nx0)), max(0.0, min(1.0, nx1))))
    ny0, ny1 = sorted((max(0.0, min(1.0, ny0)), max(0.0, min(1.0, ny1))))

    llx = float(page.cropbox.left)
    lly = float(page.cropbox.bottom)
    urx = float(page.cropbox.right)
    ury = float(page.cropbox.top)

    width = urx - llx
    height = ury - lly

    if width <= 0 or height <= 0:
        raise ValueError("Invalid page dimensions for crop.")

    new_llx = llx + width * nx0
    new_urx = llx + width * nx1
    new_ury = ury - height * ny0
    new_lly = ury - height * ny1

    if new_llx >= new_urx or new_lly >= new_ury:
        raise ValueError("Invalid crop area.")

    page.cropbox.lower_left = (new_llx, new_lly)
    page.cropbox.upper_right = (new_urx, new_ury)
    page.mediabox.lower_left = (new_llx, new_lly)
    page.mediabox.upper_right = (new_urx, new_ury)


def parse_crop_payload(payload: Any) -> Optional[Tuple[float, float, float, float]]:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("crop")
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        nx0, ny0, nx1, ny1 = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError):
        return None
    return nx0, ny0, nx1, ny1


def push_undo_state() -> None:
    pages = st.session_state.get("pages", [])
    snapshot = pages_to_pdf_bytes(pages)
    st.session_state.undo_stack.append(snapshot)
    if len(st.session_state.undo_stack) > 40:
        st.session_state.undo_stack.pop(0)


def mark_dirty() -> None:
    try:
        current = pages_to_pdf_bytes(st.session_state.get("pages", []))
        st.session_state.is_dirty = current != st.session_state.get("saved_pdf_bytes", b"")
    except Exception:
        st.session_state.is_dirty = True


def init_state() -> None:
    if "pages" not in st.session_state:
        st.session_state.pages = []
    if "thumbnails" not in st.session_state:
        st.session_state.thumbnails = []
    if "page_idx" not in st.session_state:
        st.session_state.page_idx = 0
    if "undo_stack" not in st.session_state:
        st.session_state.undo_stack = []
    if "saved_pdf_bytes" not in st.session_state:
        st.session_state.saved_pdf_bytes = b""
    if "is_dirty" not in st.session_state:
        st.session_state.is_dirty = False
    if "app_view" not in st.session_state:
        st.session_state.app_view = "upload"
    if "crop_drag_mode" not in st.session_state:
        st.session_state.crop_drag_mode = False
    if "update_counter" not in st.session_state:
        st.session_state.update_counter = 0


def build_from_uploads(pdf_files, image_files) -> Tuple[int, int, int]:
    pages: List[PageObject] = []
    skipped = 0
    ok_pdf = 0
    ok_img = 0

    for pdf_file in pdf_files:
        try:
            pdf_file.seek(0)
            reader = PdfReader(pdf_file)
            new_pages = [clone_page(p) for p in reader.pages]
            if new_pages:
                pages.extend(new_pages)
                ok_pdf += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    for img_file in image_files:
        try:
            img_file.seek(0)
            pages.append(clone_page(image_file_to_page(img_file)))
            ok_img += 1
        except Exception:
            skipped += 1

    if not pages:
        return 0, 0, skipped

    st.session_state.pages = pages
    st.session_state.thumbnails = [None] * len(pages)
    st.session_state.page_idx = 0
    st.session_state.undo_stack = []
    st.session_state.saved_pdf_bytes = pages_to_pdf_bytes(pages) if pages else b""
    st.session_state.is_dirty = False
    st.session_state.app_view = "editor"
    return ok_pdf, ok_img, skipped


def append_mixed_uploaded_files(uploaded_files) -> Tuple[int, int]:
    added = 0
    skipped = 0
    for up in uploaded_files:
        name = (up.name or "").lower()
        try:
            up.seek(0)
            if name.endswith(".pdf"):
                reader = PdfReader(up)
                new_pages = [clone_page(pg) for pg in reader.pages]
                if new_pages:
                    st.session_state.pages.extend(new_pages)
                    st.session_state.thumbnails.extend([None] * len(new_pages))
                    added += len(new_pages)
                else:
                    skipped += 1
            else:
                st.session_state.pages.append(clone_page(image_file_to_page(up)))
                st.session_state.thumbnails.append(None)
                added += 1
        except Exception:
            skipped += 1

    return added, skipped


def reset_to_upload_view() -> None:
    st.session_state.pages = []
    st.session_state.thumbnails = []
    st.session_state.page_idx = 0
    st.session_state.undo_stack = []
    st.session_state.saved_pdf_bytes = b""
    st.session_state.is_dirty = False
    st.session_state.app_view = "upload"


def go_to_page(idx: int) -> None:
    if 0 <= idx < len(st.session_state.pages):
        st.session_state.page_idx = idx


def theme_css() -> str:
    return """
    <style>
            html, body, [data-testid="stAppViewContainer"], .stApp {
                height: 100%;
                overflow: hidden;
            }

      :root {
        --bg0: #0b0f19;
        --bg1: #0f1628;
        --bg2: #131c33;
        --panel: rgba(18, 25, 45, 0.72);
        --panel-border: rgba(130, 160, 220, 0.22);
        --text: #f4f7ff;
        --muted: #b9c6e8;
        --accent: #4ec3ff;
        --accent2: #8a7dff;
        --ok: #61d7a4;
      }

      .stApp {
        background:
          radial-gradient(1300px 580px at 10% -10%, #1a2d54 0%, transparent 60%),
          radial-gradient(1100px 650px at 110% 10%, #2a1f57 0%, transparent 58%),
          linear-gradient(135deg, var(--bg0), var(--bg1) 50%, var(--bg2));
        color: var(--text);
      }

      .block-container {
                max-width: 1600px;
                height: 100vh;
                                padding-top: 0.15rem;
                                padding-bottom: 0.2rem;
                overflow: hidden;
      }

            [data-testid="stVerticalBlock"] {
                gap: 0.25rem;
            }

            .app-navbar {
                border: 1px solid var(--panel-border);
                background: rgba(18, 25, 45, 0.88);
                border-radius: 12px;
                padding: 0.35rem 0.55rem;
                margin-bottom: 0.2rem;
            }

            .app-navbar-title {
                color: var(--muted);
                font-size: 0.78rem;
                letter-spacing: 0.25px;
            }

      .panel {
        border: 1px solid var(--panel-border);
        background: var(--panel);
                border-radius: 14px;
                padding: 0.45rem;
        backdrop-filter: blur(8px);
        animation: fadeInUp 460ms ease-out;
      }

            h2, h3 {
                margin-top: 0.1rem !important;
                margin-bottom: 0.2rem !important;
            }

            h4 {
                margin-top: 0.08rem !important;
                margin-bottom: 0.14rem !important;
                font-size: 0.95rem !important;
            }

            p {
                margin-bottom: 0.12rem !important;
            }

            [data-testid="stMarkdownContainer"] p,
            [data-testid="stMarkdownContainer"] li,
            [data-testid="stCaptionContainer"] {
                font-size: 0.83rem;
            }

      div[data-testid="stButton"] > button {
                border-radius: 9px;
        border: 1px solid rgba(123, 163, 255, 0.44);
        background: linear-gradient(180deg, rgba(54, 77, 128, 0.64), rgba(31, 46, 82, 0.76));
        color: #f6f9ff;
        transition: all 180ms ease;
                                min-height: 1.72rem;
                                padding-top: 0.14rem;
                                padding-bottom: 0.14rem;
                                font-size: 0.76rem;
      }

            div[data-testid="stDownloadButton"] > button {
                min-height: 1.72rem;
                padding-top: 0.14rem;
                padding-bottom: 0.14rem;
                font-size: 0.76rem;
            }

            div[data-testid="stFileUploader"] {
                margin-bottom: 0.2rem;
            }

            div[data-testid="stFileUploader"] small,
            div[data-testid="stFileUploader"] label,
            div[data-testid="stNumberInput"] label,
            div[data-testid="stCaptionContainer"] {
                font-size: 0.76rem !important;
            }

            div[data-testid="stNumberInput"] {
                margin-bottom: 0.25rem;
            }

      div[data-testid="stButton"] > button:hover {
        transform: translateY(-1px);
        border-color: rgba(132, 199, 255, 0.82);
        box-shadow: 0 7px 16px rgba(25, 47, 95, 0.42);
      }

      div[data-testid="stDownloadButton"] > button {
        border-radius: 11px;
        border: 1px solid rgba(111, 233, 193, 0.45);
        background: linear-gradient(180deg, rgba(48, 114, 102, 0.6), rgba(28, 79, 72, 0.78));
      }

      .small-note {
        color: var(--muted);
        font-size: 0.84rem;
      }

            .pages-box-label {
                color: var(--muted);
                font-size: 0.74rem;
                margin-bottom: 0.2rem;
            }

      @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
      }

            @media (max-width: 1200px) {
        .block-container {
                    padding-left: 0.45rem;
                    padding-right: 0.45rem;
        }
      }
    </style>
    """


def main() -> None:
    st.set_page_config(
        page_title="PDF Forge Studio",
        page_icon="",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(theme_css(), unsafe_allow_html=True)

    hide_top_bar = """
        <style>
            header {visibility: hidden;}
            .block-container {
                padding-top: 1rem;
            }
        </style>
    """
    st.markdown(hide_top_bar, unsafe_allow_html=True)

    init_state()
    interactive_viewer = get_viewer_component()

    if st.session_state.app_view == "upload":
        with st.container(border=False):
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            col_u1, col_u2, col_u3 = st.columns([1.45, 1.45, 0.8])

            with col_u1:
                pdf_files = st.file_uploader(
                    "Upload PDFs",
                    type=["pdf"],
                    accept_multiple_files=True,
                    key="pdf_uploader",
                )

            with col_u2:
                image_files = st.file_uploader(
                    "Upload Images",
                    type=["png", "jpg", "jpeg", "bmp", "tiff", "webp"],
                    accept_multiple_files=True,
                    key="img_uploader",
                )

            with col_u3:
                st.write("")
                st.write("")
                if st.button("Create Working PDF", width="stretch"):
                    p = pdf_files or []
                    i = image_files or []
                    if not p and not i:
                        st.warning("Upload at least one PDF or image.")
                    else:
                        n_pdf, n_img, skipped = build_from_uploads(p, i)
                        if n_pdf == 0 and n_img == 0:
                            st.warning("No valid files were loaded. Check file integrity/format and try again.")
                        else:
                            st.success(f"Working document created from {n_pdf} PDF(s) and {n_img} image(s).")
                            if skipped:
                                st.warning(f"Skipped {skipped} invalid file(s).")
                            st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

        st.caption("Upload files and create a working PDF to enter the editor.")
        return

    if not st.session_state.pages:
        st.session_state.app_view = "upload"
        st.rerun()

    total_pages = len(st.session_state.pages)
    st.session_state.page_idx = max(0, min(st.session_state.page_idx, total_pages - 1))

    st.markdown('<div class="app-navbar"><div class="app-navbar-title">Editor Actions</div></div>', unsafe_allow_html=True)
    nav_c1, nav_c2, nav_c3 = st.columns([1.0, 1.0, 1.8], gap="small")
    with nav_c1:
        if st.button("New Working PDF", width="stretch", key="nav_new_working"):
            reset_to_upload_view()
            st.rerun()
    with nav_c2:
        if st.button("Save Snapshot", width="stretch", key="nav_save_snapshot"):
            st.session_state.saved_pdf_bytes = pages_to_pdf_bytes(st.session_state.pages)
            st.session_state.is_dirty = False
            st.rerun()
    with nav_c3:
        output_bytes = pages_to_pdf_bytes(st.session_state.pages)
        st.download_button(
            "Download Final PDF",
            data=output_bytes,
            file_name="0_streamlit_final.pdf",
            mime="application/pdf",
            width="stretch",
            key="nav_download_pdf",
        )

    preview_height = 510
    left, center, right = st.columns([1.05, 3.2, 1.0], gap="small")

    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Tools")
        st.caption(f"Pages: {total_pages}")

        nav_a, nav_b = st.columns(2)
        with nav_a:
            if st.button("Prev", width="stretch"):
                go_to_page(st.session_state.page_idx - 1)
                st.rerun()
        with nav_b:
            if st.button("Next", width="stretch"):
                go_to_page(st.session_state.page_idx + 1)
                st.rerun()

        selected = st.number_input(
            "Current page",
            min_value=1,
            max_value=total_pages,
            value=st.session_state.page_idx + 1,
            step=1,
        )
        if (int(selected) - 1) != st.session_state.page_idx:
            st.session_state.page_idx = int(selected) - 1
            st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Rotate Left", width="stretch"):
                push_undo_state()
                idx = st.session_state.page_idx
                st.session_state.pages[idx].rotate(-90)
                st.session_state.thumbnails[idx] = None
                mark_dirty()
                st.rerun()
        with c2:
            if st.button("Rotate Right", width="stretch"):
                push_undo_state()
                idx = st.session_state.page_idx
                st.session_state.pages[idx].rotate(90)
                st.session_state.thumbnails[idx] = None
                mark_dirty()
                st.rerun()

        c3, c4 = st.columns(2)
        with c3:
            if st.button("Move Up", width="stretch") and st.session_state.page_idx > 0:
                push_undo_state()
                idx = st.session_state.page_idx
                pages = st.session_state.pages
                thumbs = st.session_state.thumbnails
                pages[idx - 1], pages[idx] = pages[idx], pages[idx - 1]
                thumbs[idx - 1], thumbs[idx] = thumbs[idx], thumbs[idx - 1]
                st.session_state.page_idx -= 1
                mark_dirty()
                st.rerun()
        with c4:
            if st.button("Move Down", width="stretch") and st.session_state.page_idx < total_pages - 1:
                push_undo_state()
                idx = st.session_state.page_idx
                pages = st.session_state.pages
                thumbs = st.session_state.thumbnails
                pages[idx + 1], pages[idx] = pages[idx], pages[idx + 1]
                thumbs[idx + 1], thumbs[idx] = thumbs[idx], thumbs[idx + 1]
                st.session_state.page_idx += 1
                mark_dirty()
                st.rerun()

        c5, c6 = st.columns(2)
        with c5:
            if st.button("Duplicate", width="stretch"):
                push_undo_state()
                idx = st.session_state.page_idx
                clone = clone_page(st.session_state.pages[idx])
                st.session_state.pages.insert(idx + 1, clone)
                st.session_state.thumbnails.insert(idx + 1, None)
                st.session_state.page_idx = idx + 1
                mark_dirty()
                st.rerun()
        with c6:
            if st.button("Delete", width="stretch"):
                if len(st.session_state.pages) == 1:
                    st.warning("Cannot delete the only page.")
                else:
                    push_undo_state()
                    idx = st.session_state.page_idx
                    del st.session_state.pages[idx]
                    del st.session_state.thumbnails[idx]
                    st.session_state.page_idx = min(idx, len(st.session_state.pages) - 1)
                    mark_dirty()
                    st.rerun()

        if st.button("Undo", width="stretch"):
            if st.session_state.undo_stack:
                prev_state = st.session_state.undo_stack.pop()
                st.session_state.pages = pdf_bytes_to_pages(prev_state)
                st.session_state.thumbnails = [None] * len(st.session_state.pages)
                st.session_state.page_idx = min(st.session_state.page_idx, len(st.session_state.pages) - 1)
                mark_dirty()
                st.rerun()
            else:
                st.info("Nothing to undo.")

        st.markdown("#### Crop")
        crop_toggle_label = "Deactivate Crop Tool" if st.session_state.crop_drag_mode else "Activate Crop Tool"
        if st.button(crop_toggle_label, width="stretch"):
            st.session_state.crop_drag_mode = not st.session_state.crop_drag_mode
            st.rerun()
        st.caption("Adjust edges and corners on the preview.")

        st.markdown("#### Add More Pages")
        mixed_files = st.file_uploader(
            "Add PDFs or images",
            type=["pdf", "png", "jpg", "jpeg", "bmp", "tiff", "webp"],
            accept_multiple_files=True,
            key="extra_mixed_uploader",
        )

        if st.button("Append Uploaded Files", width="stretch"):
            selected_files = mixed_files or []
            if not selected_files:
                st.warning("No extra files selected.")
            else:
                before_append_snapshot = pages_to_pdf_bytes(st.session_state.pages)
                added, skipped = append_mixed_uploaded_files(selected_files)

                if added == 0:
                    st.warning("No pages were added from the selected files.")
                else:
                    st.session_state.undo_stack.append(before_append_snapshot)
                    if len(st.session_state.undo_stack) > 40:
                        st.session_state.undo_stack.pop(0)
                    mark_dirty()
                    st.success(f"Added {added} page(s).")
                if skipped:
                    st.warning(f"Skipped {skipped} invalid file(s).")
                st.rerun()

        status_text = "Unsaved changes" if st.session_state.is_dirty else "All changes saved"
        st.caption(status_text)

        st.markdown('</div>', unsafe_allow_html=True)

    with center:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Preview")
        st.caption(f"Page {st.session_state.page_idx + 1} of {total_pages}")

        current_page = st.session_state.pages[st.session_state.page_idx]
        preview_img = render_page_to_pil(current_page, scale=2.0)

        if preview_img is not None:
            
            uid = f"vp_{st.session_state.page_idx}_{st.session_state.update_counter}_{'c' if st.session_state.crop_drag_mode else 'p'}"
            
            # This calls our robust Custom Component 
            crop_result = interactive_viewer(
                img_b64=pil_to_base64_png(preview_img),
                crop_mode=st.session_state.crop_drag_mode,
                height=preview_height,
                key=uid
            )
            
            # Immediately process the crop payload from JavaScript
            parsed_crop = parse_crop_payload(crop_result)
            if parsed_crop is not None:
                nx0, ny0, nx1, ny1 = parsed_crop
                crop_applied = False
                try:
                    push_undo_state()
                    idx = st.session_state.page_idx
                    apply_normalized_crop(st.session_state.pages[idx], nx0, ny0, nx1, ny1)
                    st.session_state.thumbnails[idx] = None
                    mark_dirty()
                    crop_applied = True
                except Exception:
                    st.warning("Could not apply crop to this page.")

                if crop_applied:
                    # Automatically disable crop mode, force an ID change to avoid loops, and show result
                    st.session_state.crop_drag_mode = False
                    st.session_state.update_counter += 1
                    st.rerun()

        else:
            st.warning("Install pypdfium2 for high quality page preview.")

        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Pages")
        st.markdown('<div class="pages-box-label">Scrollable preview</div>', unsafe_allow_html=True)

        try:
            thumbs_container = st.container(height=preview_height + 10, border=False)
        except TypeError:
            try:
                thumbs_container = st.container(border=False)
            except TypeError:
                thumbs_container = st.container()

        with thumbs_container:
            if preview_img is not None:
                for i, page in enumerate(st.session_state.pages):
                    
                    if st.session_state.thumbnails[i] is None:
                        thumb = render_page_to_pil(page, scale=0.45)
                        if thumb is None:
                            thumb = Image.new("RGB", (120, 160), color=(235, 235, 235))
                        else:
                            thumb.thumbnail((145, 200))
                        st.session_state.thumbnails[i] = thumb
                        
                    thumb = st.session_state.thumbnails[i]
                    page_no = i + 1
                    is_active = (i == st.session_state.page_idx)
                    
                    with st.container(border=is_active):
                        st.image(thumb, width="stretch")
                        if st.button(
                            label=f"Page {page_no}", 
                            key=f"nav_thumb_{i}", 
                            width="stretch"
                        ):
                            st.session_state.page_idx = i
                            st.rerun()
            else:
                st.info("Thumbnail previews need pypdfium2.")

        st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
