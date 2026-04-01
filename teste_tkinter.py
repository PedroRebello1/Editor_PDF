import io
import os
from typing import List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:
    tk = None
    filedialog = None
    messagebox = None
    ttk = None

from PIL import Image
from PIL import ImageTk
from PyPDF2 import PdfReader, PdfWriter, PdfMerger, PageObject
from PyPDF2.errors import PdfReadError
from reportlab.lib.pagesizes import A4


def list_source_pdfs(input_dir: str, output_name: str) -> List[str]:
    """
    Lista PDFs de entrada elegiveis para edicao e juncao.
    """
    generated_prefix = "0_standardized_joined"
    return sorted(
        [
            f
            for f in os.listdir(input_dir)
            if f.lower().endswith('.pdf')
            and f.lower() != output_name.lower()
            and not f.lower().startswith(generated_prefix)
        ]
    )


def converter_imagens_para_pdf(diretorio: str) -> None:
    """
    Busca imagens suportadas no diretorio especificado e as converte para PDF.
    """
    extensoes_suportadas = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
    sucessos = 0

    print(f"Buscando imagens em: {diretorio}\n" + "-" * 30)

    try:
        arquivos = os.listdir(diretorio)
    except OSError as e:
        print(f"Erro ao acessar o diretorio: {e}")
        return

    for arquivo in arquivos:
        if arquivo.lower().endswith(extensoes_suportadas):
            try:
                caminho_imagem = os.path.join(diretorio, arquivo)
                nome_base = os.path.splitext(arquivo)[0]
                nome_pdf = os.path.join(diretorio, f"{nome_base}.pdf")

                # Evita sobrescrever PDFs que ja existam com o mesmo nome
                if os.path.exists(nome_pdf):
                    print(f"Aviso: '{nome_pdf}' ja existe. Ignorando conversao de '{arquivo}'.")
                    continue

                with Image.open(caminho_imagem) as img:
                    img_rgb = img.convert('RGB')
                    img_rgb.save(nome_pdf, "PDF", resolution=100.0)

                print(f"Convertido: {arquivo} -> {nome_base}.pdf")
                sucessos += 1

            except Exception as e:
                print(f"Erro ao converter {arquivo}: {e}")

    print("-" * 30)
    print(f"Conversao finalizada! {sucessos} imagens convertidas para PDF.\n")


def scale_and_center_page(page: PageObject, target_w: float, target_h: float) -> PageObject:
    """
    Escala e centraliza a pagina manipulando as caixas originais,
    evitando bugs de rotacao de scanners e corte de merge_page.
    """
    rotation = page.get('/Rotate', 0)
    if hasattr(rotation, 'get_object'):
        rotation = rotation.get_object()
    rotation = int(rotation) % 360

    raw_w = float(page.cropbox.width)
    raw_h = float(page.cropbox.height)

    if rotation in [90, 270]:
        vis_w, vis_h = raw_h, raw_w
        target_raw_w, target_raw_h = target_h, target_w
    else:
        vis_w, vis_h = raw_w, raw_h
        target_raw_w, target_raw_h = target_w, target_h

    if vis_w == 0 or vis_h == 0:
        return page

    scale = min(target_w / vis_w, target_h / vis_h)
    page.scale_by(scale)

    new_llx = float(page.cropbox.left)
    new_lly = float(page.cropbox.bottom)
    new_urx = float(page.cropbox.right)
    new_ury = float(page.cropbox.top)

    new_raw_w = new_urx - new_llx
    new_raw_h = new_ury - new_lly

    diff_x = (target_raw_w - new_raw_w) / 2.0
    diff_y = (target_raw_h - new_raw_h) / 2.0

    lower_left = (new_llx - diff_x, new_lly - diff_y)
    upper_right = (new_urx + diff_x, new_ury + diff_y)

    page.mediabox.lower_left = lower_left
    page.mediabox.upper_right = upper_right

    page.cropbox.lower_left = lower_left
    page.cropbox.upper_right = upper_right

    page.trimbox.lower_left = lower_left
    page.trimbox.upper_right = upper_right
    page.bleedbox.lower_left = lower_left
    page.bleedbox.upper_right = upper_right

    return page




def _load_pdf_renderer():
    """
    Carrega pypdfium2 sob demanda para renderizacao de preview no editor manual.
    """
    try:
        import importlib
        return importlib.import_module("pypdfium2")
    except Exception:
        return None


def _standardize_pdf_in_isolation(
    file_path: str,
    target_w: float,
    target_h: float,
) -> io.BytesIO:
    """
    Padroniza um unico PDF e retorna o resultado em memoria.
    Isso evita que objetos de recurso (imagens) de PDFs diferentes sejam
    reutilizados indevidamente ao adicionar tudo em um unico PdfWriter.
    """
    reader = PdfReader(file_path)
    isolated_writer = PdfWriter()

    for page in reader.pages:
        standardized = scale_and_center_page(page, target_w, target_h)
        isolated_writer.add_page(standardized)

    buffer = io.BytesIO()
    isolated_writer.write(buffer)
    buffer.seek(0)
    return buffer


def standardize_and_merge(
    input_dir: str,
    output_name: str,
) -> None:
    """
    Localiza todos os PDFs, padroniza para o tamanho A4 e os une em um unico arquivo.
    """
    target_w, target_h = A4
    merger = PdfMerger()

    try:
        arquivos = list_source_pdfs(input_dir, output_name)
    except OSError as e:
        print(f"Erro ao acessar o diretorio para juncao: {e}")
        return

    if not arquivos:
        print("Nenhum arquivo PDF encontrado para unir.")
        return

    print("Iniciando a padronizacao e uniao dos PDFs...")
    in_memory_parts = []

    for pdf_nome in arquivos:
        print(f"Processando: {pdf_nome}...")
        file_path = os.path.join(input_dir, pdf_nome)

        try:
            standardized_part = _standardize_pdf_in_isolation(
                file_path,
                target_w,
                target_h,
            )
            in_memory_parts.append(standardized_part)
            merger.append(standardized_part)
        except (PdfReadError, OSError) as e:
            print(f"Erro ao processar {pdf_nome}: {e}")
            continue

    output_path = os.path.join(input_dir, output_name)
    try:
        with open(output_path, "wb") as f:
            merger.write(f)
        print(f"\nConcluido! Todas as paginas estao no tamanho A4 no arquivo: {output_name}")
    except IOError as e:
        print(f"Erro ao salvar o arquivo final: {e}")
    finally:
        merger.close()
        for part in in_memory_parts:
            part.close()


class ManualPDFEditor:
    def __init__(self, pdf_path: str):
        if tk is None:
            raise RuntimeError("Tkinter nao esta disponivel neste ambiente.")

        self.pdf_path = pdf_path
        self.backup_path = f"{pdf_path}.bak"
        self.renderer = _load_pdf_renderer()

        self.pages: List[PageObject] = []
        self.page_index = 0
        self.is_dirty = False
        self.saved_state: Optional[bytes] = None
        self.undo_stack: List[bytes] = []
        self.max_undo = 30

        self.current_photo = None
        self.thumbnail_refs: List[ImageTk.PhotoImage] = []
        self.display_bounds: Optional[Tuple[int, int, int, int]] = None

        self.crop_mode = False
        self.crop_start: Optional[Tuple[int, int]] = None
        self.crop_rect_id: Optional[int] = None
        self.is_dark_theme = True

        self.root = tk.Tk()
        self.root.title("Editor Manual do PDF Final")
        self.root.geometry("1450x920")
        self.root.minsize(1024, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Control-z>", self.undo_last_action)
        self.root.bind("<Control-Z>", self.undo_last_action)

        self.file_label = tk.StringVar(value="")
        self.page_label = tk.StringVar(value="")
        self.status_label = tk.StringVar(value="")
        self.theme_toggle_var = tk.StringVar(value="☀")

        self._load_pages()
        self._configure_theme()
        self._build_ui()
        self._refresh_all()

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        top = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        top.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=0)

        ttk.Label(top, textvariable=self.file_label, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.page_label).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.theme_button = ttk.Button(top, textvariable=self.theme_toggle_var, width=3, command=self.toggle_theme)
        self.theme_button.grid(row=0, column=1, rowspan=2, sticky="e")

        body = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        left_panel = ttk.Frame(body, width=250)
        left_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        left_panel.grid_propagate(False)

        center_panel = ttk.Frame(body)
        center_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        center_panel.grid_rowconfigure(0, weight=1)
        center_panel.grid_columnconfigure(0, weight=1)

        right_panel = ttk.Frame(body, width=220)
        right_panel.grid(row=0, column=2, sticky="nse", padx=(0, 0))
        right_panel.grid_propagate(False)
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(center_panel, bg="#1f1f1f", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _e: self._render_current_page())
        self.canvas.bind("<ButtonPress-1>", self._on_crop_press)
        self.canvas.bind("<B1-Motion>", self._on_crop_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_crop_release)

        nav = ttk.LabelFrame(left_panel, text="Navegacao", padding=8)
        nav.pack(fill="x", pady=(0, 8))
        ttk.Button(nav, text="Pagina Anterior", command=self.prev_page).pack(fill="x")
        ttk.Button(nav, text="Proxima Pagina", command=self.next_page).pack(fill="x", pady=(6, 0))

        edit = ttk.LabelFrame(left_panel, text="Edicao", padding=8)
        edit.pack(fill="x", pady=(0, 8))
        ttk.Button(edit, text="Girar Esquerda", command=self.rotate_left).pack(fill="x")
        ttk.Button(edit, text="Girar Direita", command=self.rotate_right).pack(fill="x", pady=(6, 0))
        ttk.Button(edit, text="Apagar Pagina", command=self.delete_page).pack(fill="x", pady=(6, 0))
        ttk.Button(edit, text="Duplicar Pagina", command=self.duplicate_page).pack(fill="x", pady=(6, 0))
        ttk.Button(edit, text="Mover Pagina Acima", command=self.move_page_up).pack(fill="x", pady=(6, 0))
        ttk.Button(edit, text="Mover Pagina Abaixo", command=self.move_page_down).pack(fill="x", pady=(6, 0))

        crop = ttk.LabelFrame(left_panel, text="Crop", padding=8)
        crop.pack(fill="x", pady=(0, 8))
        self.crop_button = ttk.Button(crop, text="Ativar Crop por Arraste", command=self.toggle_crop_mode)
        self.crop_button.pack(fill="x")

        add = ttk.LabelFrame(left_panel, text="Adicionar", padding=8)
        add.pack(fill="x", pady=(0, 8))
        ttk.Button(add, text="Adicionar Paginas de PDF", command=self.add_pages_from_pdf).pack(fill="x")
        ttk.Button(add, text="Adicionar Imagem como Pagina", command=self.add_page_from_image).pack(fill="x", pady=(6, 0))

        help_box = ttk.LabelFrame(left_panel, text="Atalhos", padding=8)
        help_box.pack(fill="x")
        ttk.Label(help_box, text="Ctrl+Z: desfazer ultima acao").pack(anchor="w")
        ttk.Label(help_box, text="Clique miniatura: ir para pagina").pack(anchor="w")

        ttk.Label(right_panel, text="Paginas", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")

        self.thumb_canvas = tk.Canvas(right_panel, highlightthickness=0)
        self.thumb_scroll = ttk.Scrollbar(right_panel, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scroll.set)

        self.thumb_canvas.grid(row=1, column=0, sticky="nsew")
        self.thumb_scroll.grid(row=1, column=1, sticky="ns")

        self.thumb_container = ttk.Frame(self.thumb_canvas)
        self.thumb_window = self.thumb_canvas.create_window((0, 0), window=self.thumb_container, anchor="nw")
        self.thumb_container.bind("<Configure>", self._on_thumb_container_configure)
        self.thumb_canvas.bind("<Configure>", self._on_thumb_canvas_configure)
        self._bind_thumbnail_scroll_events()

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.grid(row=2, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=1)

        ttk.Label(bottom, textvariable=self.status_label).grid(row=0, column=0, sticky="w")
        action_bar = ttk.Frame(bottom)
        action_bar.grid(row=0, column=1, sticky="e")
        ttk.Button(action_bar, text="Desfazer (Ctrl+Z)", command=self.undo_last_action).pack(side="left", padx=(0, 6))
        ttk.Button(action_bar, text="Salvar", command=self.save_pdf).pack(side="left", padx=(0, 6))
        ttk.Button(action_bar, text="Salvar e Fechar", command=self.save_and_close).pack(side="left")

    def _configure_theme(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        if self.is_dark_theme:
            bg = "#1a1d22"
            panel = "#252a31"
            text = "#e8ebf0"
            accent = "#4fa3ff"
            canvas_bg = "#15181d"
            thumb_bg = "#20252c"
            selected_thumb = "#2b3440"
            self.theme_toggle_var.set("☀")
        else:
            bg = "#f2f4f7"
            panel = "#ffffff"
            text = "#23262b"
            accent = "#2d74da"
            canvas_bg = "#dfe4ea"
            thumb_bg = "#eef2f7"
            selected_thumb = "#d9e8ff"
            self.theme_toggle_var.set("☾")

        self.root.configure(bg=bg)

        style.configure(".", background=bg, foreground=text)
        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=panel, foreground=text)
        style.configure("TLabelframe.Label", background=panel, foreground=text)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("TButton", background=panel, foreground=text, bordercolor=accent, focusthickness=1)
        style.map("TButton", background=[("active", accent)], foreground=[("active", "#ffffff")])
        style.configure("SelectedThumb.TFrame", background=selected_thumb)

        if hasattr(self, "canvas"):
            self.canvas.configure(bg=canvas_bg)
        if hasattr(self, "thumb_canvas"):
            self.thumb_canvas.configure(bg=thumb_bg)

    def toggle_theme(self) -> None:
        self.is_dark_theme = not self.is_dark_theme
        self._configure_theme()
        self._refresh_all()

    def _bind_thumbnail_scroll_events(self) -> None:
        self.thumb_canvas.bind("<Enter>", self._activate_thumb_scroll)
        self.thumb_canvas.bind("<Leave>", self._deactivate_thumb_scroll)
        self.thumb_container.bind("<Enter>", self._activate_thumb_scroll)
        self.thumb_container.bind("<Leave>", self._deactivate_thumb_scroll)

    def _activate_thumb_scroll(self, _event=None) -> None:
        self.thumb_canvas.bind_all("<MouseWheel>", self._on_thumb_mousewheel)
        self.thumb_canvas.bind_all("<Button-4>", self._on_thumb_mousewheel)
        self.thumb_canvas.bind_all("<Button-5>", self._on_thumb_mousewheel)

    def _deactivate_thumb_scroll(self, _event=None) -> None:
        self.thumb_canvas.unbind_all("<MouseWheel>")
        self.thumb_canvas.unbind_all("<Button-4>")
        self.thumb_canvas.unbind_all("<Button-5>")

    def _on_thumb_mousewheel(self, event) -> None:
        if hasattr(event, "delta") and event.delta:
            direction = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            direction = -1
        else:
            direction = 1
        self.thumb_canvas.yview_scroll(direction * 3, "units")

    def _on_thumb_container_configure(self, _event=None) -> None:
        self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))

    def _on_thumb_canvas_configure(self, event=None) -> None:
        if event is not None:
            self.thumb_canvas.itemconfigure(self.thumb_window, width=event.width)

    def _set_status(self, text: str) -> None:
        self.status_label.set(text)

    def _clone_page(self, page: PageObject) -> PageObject:
        writer = PdfWriter()
        writer.add_page(page)
        temp = io.BytesIO()
        writer.write(temp)
        temp.seek(0)
        return PdfReader(temp).pages[0]

    def _load_pages(self) -> None:
        reader = PdfReader(self.pdf_path)
        self.pages = [self._clone_page(page) for page in reader.pages]
        self.saved_state = self._snapshot_state()
        self.is_dirty = False

    def _snapshot_state(self) -> bytes:
        writer = PdfWriter()
        for page in self.pages:
            writer.add_page(page)
        temp = io.BytesIO()
        writer.write(temp)
        return temp.getvalue()

    def _push_undo_state(self) -> None:
        self.undo_stack.append(self._snapshot_state())
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)

    def _restore_from_state(self, state_bytes: bytes) -> None:
        reader = PdfReader(io.BytesIO(state_bytes))
        self.pages = [self._clone_page(page) for page in reader.pages]
        if self.pages:
            self.page_index = min(self.page_index, len(self.pages) - 1)
        else:
            self.page_index = 0

    def _mark_changed(self, status_text: str) -> None:
        self.is_dirty = self._snapshot_state() != self.saved_state
        self._set_status(status_text)
        self._refresh_all()

    def _refresh_all(self) -> None:
        name = os.path.basename(self.pdf_path)
        dirty_mark = "*" if self.is_dirty else ""
        self.file_label.set(f"Arquivo: {name}{dirty_mark}")
        total = len(self.pages)
        page_text = f"Pagina: {self.page_index + 1 if total else 0} / {total}"
        self.page_label.set(page_text)
        self._render_current_page()
        self._render_thumbnails()
        crop_text = "Desativar Crop por Arraste" if self.crop_mode else "Ativar Crop por Arraste"
        self.crop_button.configure(text=crop_text)

    def _render_page_to_pil(self, page: PageObject, scale: float = 1.5) -> Optional[Image.Image]:
        if self.renderer is None:
            return None
        try:
            writer = PdfWriter()
            writer.add_page(page)
            temp = io.BytesIO()
            writer.write(temp)
            temp.seek(0)
            doc = self.renderer.PdfDocument(temp.getvalue())
            rendered = doc[0].render(scale=scale)
            return rendered.to_pil().convert("RGB")
        except Exception:
            return None

    def _render_current_page(self) -> None:
        self.canvas.delete("all")
        self.display_bounds = None

        if not self.pages:
            self.canvas.create_text(20, 20, anchor="nw", fill="white", text="PDF sem paginas.")
            return

        if ImageTk is None:
            self.canvas.create_text(20, 20, anchor="nw", fill="white", text="ImageTk indisponivel.")
            return

        pil_image = self._render_page_to_pil(self.pages[self.page_index], scale=2.0)
        if pil_image is None:
            self.canvas.create_text(
                20,
                20,
                anchor="nw",
                fill="white",
                text="Preview indisponivel. Instale pypdfium2 para visualizar o PDF.",
                width=max(300, self.canvas.winfo_width() - 40),
            )
            return

        canvas_w = max(320, self.canvas.winfo_width())
        canvas_h = max(320, self.canvas.winfo_height())

        pil_image.thumbnail((canvas_w - 20, canvas_h - 20))
        self.current_photo = ImageTk.PhotoImage(pil_image)

        img_w = self.current_photo.width()
        img_h = self.current_photo.height()
        x = (canvas_w - img_w) // 2
        y = (canvas_h - img_h) // 2

        self.display_bounds = (x, y, x + img_w, y + img_h)
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=self.current_photo, anchor="center")

        if self.crop_mode:
            self.canvas.create_text(
                14,
                14,
                anchor="nw",
                fill="#f5f5f5" if self.is_dark_theme else "#202020",
                text="Crop: arraste sobre a pagina para recortar.",
            )

    def _render_thumbnails(self) -> None:
        for child in self.thumb_container.winfo_children():
            child.destroy()

        self.thumbnail_refs = []
        if not self.pages:
            return

        for idx, page in enumerate(self.pages):
            item = ttk.Frame(self.thumb_container, padding=(4, 4, 4, 6))
            item.pack(fill="x", padx=2, pady=2)

            selected = idx == self.page_index
            if selected:
                item.configure(style="SelectedThumb.TFrame")

            pil_thumb = self._render_page_to_pil(page, scale=0.55)
            if pil_thumb is None:
                pil_thumb = Image.new("RGB", (120, 160), color=(220, 220, 220))

            pil_thumb.thumbnail((140, 190))
            img = ImageTk.PhotoImage(pil_thumb) if ImageTk else None
            if img is not None:
                self.thumbnail_refs.append(img)

            btn = ttk.Button(
                item,
                image=img,
                text=f"Pagina {idx + 1}",
                compound="top",
                command=lambda i=idx: self.go_to_page(i),
            )
            btn.pack(fill="x")

        self._on_thumb_container_configure()

    def go_to_page(self, page_idx: int) -> None:
        if page_idx < 0 or page_idx >= len(self.pages):
            return
        self.page_index = page_idx
        self._refresh_all()

    def prev_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._refresh_all()

    def next_page(self) -> None:
        if self.page_index < len(self.pages) - 1:
            self.page_index += 1
            self._refresh_all()

    def rotate_left(self) -> None:
        if not self.pages:
            return
        self._push_undo_state()
        self.pages[self.page_index].rotate(-90)
        self._mark_changed("Pagina girada para esquerda.")

    def rotate_right(self) -> None:
        if not self.pages:
            return
        self._push_undo_state()
        self.pages[self.page_index].rotate(90)
        self._mark_changed("Pagina girada para direita.")

    def delete_page(self) -> None:
        if not self.pages:
            return
        if len(self.pages) == 1:
            messagebox.showwarning("Operacao bloqueada", "Nao e possivel remover a unica pagina.")
            return
        self._push_undo_state()
        del self.pages[self.page_index]
        self.page_index = min(self.page_index, len(self.pages) - 1)
        self._mark_changed("Pagina removida.")

    def duplicate_page(self) -> None:
        if not self.pages:
            return
        self._push_undo_state()
        clone = self._clone_page(self.pages[self.page_index])
        self.pages.insert(self.page_index + 1, clone)
        self.page_index += 1
        self._mark_changed("Pagina duplicada.")

    def move_page_up(self) -> None:
        if not self.pages or self.page_index <= 0:
            return
        self._push_undo_state()
        self.pages[self.page_index - 1], self.pages[self.page_index] = self.pages[self.page_index], self.pages[self.page_index - 1]
        self.page_index -= 1
        self._mark_changed("Pagina movida para cima.")

    def move_page_down(self) -> None:
        if not self.pages or self.page_index >= len(self.pages) - 1:
            return
        self._push_undo_state()
        self.pages[self.page_index + 1], self.pages[self.page_index] = self.pages[self.page_index], self.pages[self.page_index + 1]
        self.page_index += 1
        self._mark_changed("Pagina movida para baixo.")

    def toggle_crop_mode(self) -> None:
        self.crop_mode = not self.crop_mode
        self._set_status("Modo crop ativado. Arraste na imagem." if self.crop_mode else "Modo crop desativado.")
        self._refresh_all()

    def _clamp_to_display(self, x: int, y: int) -> Tuple[int, int]:
        if self.display_bounds is None:
            return x, y
        x0, y0, x1, y1 = self.display_bounds
        return min(max(x, x0), x1), min(max(y, y0), y1)

    def _on_crop_press(self, event) -> None:
        if not self.crop_mode or self.display_bounds is None:
            return
        x0, y0, x1, y1 = self.display_bounds
        if not (x0 <= event.x <= x1 and y0 <= event.y <= y1):
            return

        sx, sy = self._clamp_to_display(event.x, event.y)
        self.crop_start = (sx, sy)
        if self.crop_rect_id is not None:
            self.canvas.delete(self.crop_rect_id)
        self.crop_rect_id = self.canvas.create_rectangle(sx, sy, sx, sy, outline="#35d07f", width=2, dash=(5, 3))

    def _on_crop_drag(self, event) -> None:
        if not self.crop_mode or self.crop_start is None or self.crop_rect_id is None:
            return
        ex, ey = self._clamp_to_display(event.x, event.y)
        sx, sy = self.crop_start
        self.canvas.coords(self.crop_rect_id, sx, sy, ex, ey)

    def _on_crop_release(self, event) -> None:
        if not self.crop_mode or self.crop_start is None or self.crop_rect_id is None or self.display_bounds is None:
            return

        ex, ey = self._clamp_to_display(event.x, event.y)
        sx, sy = self.crop_start
        x_min, x_max = sorted((sx, ex))
        y_min, y_max = sorted((sy, ey))

        self.canvas.delete(self.crop_rect_id)
        self.crop_rect_id = None
        self.crop_start = None

        if (x_max - x_min) < 8 or (y_max - y_min) < 8:
            self._set_status("Crop cancelado: selecione uma area maior.")
            return

        dx0, dy0, dx1, dy1 = self.display_bounds
        disp_w = dx1 - dx0
        disp_h = dy1 - dy0
        if disp_w <= 0 or disp_h <= 0:
            return

        nx0 = (x_min - dx0) / disp_w
        nx1 = (x_max - dx0) / disp_w
        ny0 = (y_min - dy0) / disp_h
        ny1 = (y_max - dy0) / disp_h

        page = self.pages[self.page_index]
        llx = float(page.cropbox.left)
        lly = float(page.cropbox.bottom)
        urx = float(page.cropbox.right)
        ury = float(page.cropbox.top)
        width = urx - llx
        height = ury - lly

        new_llx = llx + (width * nx0)
        new_urx = llx + (width * nx1)
        new_ury = ury - (height * ny0)
        new_lly = ury - (height * ny1)

        if new_llx >= new_urx or new_lly >= new_ury:
            self._set_status("Crop invalido.")
            return

        self._push_undo_state()
        page.cropbox.lower_left = (new_llx, new_lly)
        page.cropbox.upper_right = (new_urx, new_ury)
        page.mediabox.lower_left = (new_llx, new_lly)
        page.mediabox.upper_right = (new_urx, new_ury)
        self._mark_changed("Crop aplicado por arraste.")

    def add_pages_from_pdf(self) -> None:
        if filedialog is None:
            return

        selected_path = filedialog.askopenfilename(
            title="Selecionar PDF para adicionar paginas",
            filetypes=[("PDF", "*.pdf")],
        )
        if not selected_path:
            return

        try:
            reader = PdfReader(selected_path)
            new_pages = [self._clone_page(page) for page in reader.pages]
        except Exception as e:
            messagebox.showerror("Falha ao adicionar", f"Nao foi possivel abrir o PDF: {e}")
            return

        if not new_pages:
            messagebox.showwarning("Sem paginas", "O PDF selecionado nao possui paginas.")
            return

        self._push_undo_state()
        insert_at = self.page_index + 1 if self.pages else 0
        for offset, page in enumerate(new_pages):
            self.pages.insert(insert_at + offset, page)
        self.page_index = insert_at
        self._mark_changed(f"{len(new_pages)} pagina(s) adicionada(s).")

    def add_page_from_image(self) -> None:
        if filedialog is None:
            return

        selected_path = filedialog.askopenfilename(
            title="Selecionar imagem para adicionar",
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp")],
        )
        if not selected_path:
            return

        try:
            with Image.open(selected_path) as image:
                rgb_image = image.convert("RGB")
                temp = io.BytesIO()
                rgb_image.save(temp, "PDF", resolution=100.0)
                temp.seek(0)
                image_page = PdfReader(temp).pages[0]
        except Exception as e:
            messagebox.showerror("Falha ao adicionar", f"Nao foi possivel converter a imagem: {e}")
            return

        self._push_undo_state()
        insert_at = self.page_index + 1 if self.pages else 0
        self.pages.insert(insert_at, self._clone_page(image_page))
        self.page_index = insert_at
        self._mark_changed("Pagina adicionada da imagem.")

    def undo_last_action(self, _event=None) -> None:
        if not self.undo_stack:
            self._set_status("Nada para desfazer.")
            return

        state = self.undo_stack.pop()
        self._restore_from_state(state)
        self.is_dirty = self._snapshot_state() != self.saved_state
        self._set_status("Ultima acao desfeita.")
        self._refresh_all()

    def save_pdf(self) -> bool:
        if not self.pages:
            messagebox.showwarning("Salvar bloqueado", "Nao e possivel salvar PDF vazio.")
            return False

        try:
            if not os.path.exists(self.backup_path) and os.path.exists(self.pdf_path):
                with open(self.pdf_path, "rb") as original, open(self.backup_path, "wb") as backup:
                    backup.write(original.read())

            writer = PdfWriter()
            for page in self.pages:
                writer.add_page(page)

            with open(self.pdf_path, "wb") as output:
                writer.write(output)
        except Exception as e:
            messagebox.showerror("Erro ao salvar", f"Falha ao salvar o PDF: {e}")
            return False

        self.saved_state = self._snapshot_state()
        self.is_dirty = False
        self._set_status("PDF salvo com sucesso.")
        self._refresh_all()
        return True

    def save_and_close(self) -> None:
        if self.save_pdf():
            self.root.destroy()

    def on_close(self) -> None:
        if not self.is_dirty:
            self.root.destroy()
            return

        choice = messagebox.askyesnocancel("Salvar alteracoes", "Deseja salvar alteracoes antes de fechar?")
        if choice is None:
            return
        if choice:
            if self.save_pdf():
                self.root.destroy()
            return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_manual_editor(pdf_path: str) -> bool:
    """
    Executa o editor manual para um unico PDF final.
    """
    if tk is None or messagebox is None or ttk is None:
        print("Erro: modo manual requer Tkinter instalado no Python atual.")
        return False

    if not os.path.exists(pdf_path):
        print(f"Erro: arquivo para edicao manual nao encontrado: {pdf_path}")
        return False

    editor = ManualPDFEditor(pdf_path)
    editor.run()
    return True


if __name__ == "__main__":
    try:
        pasta_atual = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pasta_atual = os.getcwd()

    nome_saida = "0_standardized_joined.pdf"

    # 1. Converte as imagens encontradas para PDF
    converter_imagens_para_pdf(pasta_atual)

    # 2. Une tudo em um unico PDF final
    print("Gerando PDF final unico...")
    standardize_and_merge(pasta_atual, nome_saida)

    # 3. Abre editor manual do PDF final
    print("Abrindo editor manual do PDF final...")
    manual_ok = launch_manual_editor(os.path.join(pasta_atual, nome_saida))
    if not manual_ok:
        print("Editor manual indisponivel. O PDF final foi gerado com sucesso.")
