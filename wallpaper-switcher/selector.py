import os
import json
import subprocess
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QGraphicsDropShadowEffect, QPushButton, QScrollArea
from PyQt6.QtCore import Qt, QSize, QVariantAnimation, QEasingCurve, pyqtSignal, QFileSystemWatcher, QRunnable, QObject, QThreadPool, QTimer, QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QPixmap, QKeyEvent, QWheelEvent, QBrush

# Importaciones del proyecto:
from wallpaper import get_wallpapers, apply_wallpaper
from thumbnail_cache import create_thumbnail

def update_starship_toml():
    """Inyecta los colores de pywal directamente en la paleta del starship.toml."""
    cache_json = os.path.expanduser("~/.cache/wal/colors.json")
    starship_path = os.path.expanduser("~/.config/starship.toml")
    
    if not os.path.exists(cache_json) or not os.path.exists(starship_path):
        return
        
    try:
        with open(cache_json, "r") as f:
            data = json.load(f)
            colors_dict = data.get("colors", {})
            
        with open(starship_path, "r") as f:
            content = f.read()
            
        # Generar la nueva sección [palettes.wal]
        new_palette_lines = ["[palettes.wal]"]
        for i in range(16):
            hex_val = colors_dict.get(f"color{i}", "#ffffff")
            new_palette_lines.append(f'color{i} = "{hex_val}"')
        new_palette_str = "\n".join(new_palette_lines)
        
        # Reemplazar la sección en el archivo toml
        if "[palettes.wal]" in content:
            parts = content.split("[palettes.wal]")
            updated_content = parts[0] + new_palette_str
        else:
            updated_content = content + "\n\n" + new_palette_str
            
        with open(starship_path, "w") as f:
            f.write(updated_content)
    except Exception as e:
        print(f"Error actualizando starship.toml: {e}")

class LoaderSignals(QObject):
    thumbLoaded = pyqtSignal(str, str, QObject)

class ThumbnailWorker(QRunnable):
    def __init__(self, target_item, filepath):
        super().__init__()
        self.target_item = target_item
        self.filepath = filepath
        self.signals = LoaderSignals()

    def run(self):
        thumb_path = create_thumbnail(self.filepath)
        self.signals.thumbLoaded.emit(thumb_path, self.filepath, self.target_item)


class ArrowButton(QPushButton):
    """Botón circular minimalista adaptado para navegación horizontal."""
    def __init__(self, direction="left", parent=None):
        super().__init__(parent)
        self.direction = direction
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)

        if self.isDown():
            bg = QColor(255, 255, 255, 30)
        elif self._hover:
            bg = QColor(255, 255, 255, 22)
        else:
            bg = QColor(255, 255, 255, 10)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawEllipse(rect)

        pen = QPen(QColor(255, 255, 255, 180 if self._hover else 130), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        path = QPainterPath()
        if self.direction == "left":
            path.moveTo(cx + 3, cy - 7)
            path.lineTo(cx - 4, cy)
            path.lineTo(cx + 3, cy + 7)
        else:
            path.moveTo(cx - 4, cy - 7)
            path.lineTo(cx + 3, cy)
            path.lineTo(cx - 4, cy + 7)
        painter.drawPath(path)


class ThumbnailItem(QWidget):
    """Miniatura individual con redimensionamiento reactivo y bordes atenuados."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filepath = ""
        self.is_selected = False
        self.virtual_index = 0
        
        self.base_w = 170
        self.base_h = 100
        self.setFixedSize(self.base_w, self.base_h)
        
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._hover = False
        self.current_scale = 1.0
        self.glow_progress = 0.0
        self.pixmap = QPixmap()

        self.anim = QVariantAnimation(self)
        self.anim.setDuration(160)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._animate_properties)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def update_content(self, filepath, is_selected, thread_pool):
        if self.filepath != filepath:
            self.filepath = filepath
            self.pixmap = QPixmap()
            if filepath:
                worker = ThumbnailWorker(self, filepath)
                worker.signals.thumbLoaded.connect(self.on_thumb_ready)
                thread_pool.start(worker)

        if self.is_selected != is_selected:
            self.is_selected = is_selected
            target_glow = 1.0 if is_selected else 0.0
            self.anim.stop()
            self.anim.setStartValue(self.glow_progress)
            self.anim.setEndValue(target_glow)
            self.anim.start()

    def on_thumb_ready(self, thumb_path, origin_path, target_item):
        if target_item == self and self.filepath == origin_path:
            self.pixmap = QPixmap(thumb_path)
            self.update()

    def _animate_properties(self, val):
        self.glow_progress = val
        self.current_scale = 1.0 + (0.35 * val)
        
        dynamic_w = int(self.base_w * self.current_scale)
        dynamic_h = int(self.base_h * self.current_scale)
        self.setFixedSize(dynamic_w, dynamic_h)
        self.updateGeometry()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.filepath:
            self.window().set_index_by_virtual_idx(self.virtual_index)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.filepath:
            self.window().confirm_selection()

    def paintEvent(self, event):
        if not self.filepath or self.pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()

        padding = 2.0
        rect = QRectF(padding, padding, w - (padding * 2), h - (padding * 2))
        radius = 12.0
        
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        painter.save()
        painter.setClipPath(path)
        scaled_pix = self.pixmap.scaled(
            QSize(w, h),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        painter.drawPixmap(0, 0, scaled_pix)
        painter.restore()

        painter.save()
        painter.setClipPath(path)
        overlay = QColor(0, 0, 0, int(20 if self.glow_progress > 0 else 65))
        painter.fillPath(path, QBrush(overlay))
        painter.restore()

        if self.glow_progress > 0.0:
            alpha = int(170 * self.glow_progress)
            pen = QPen(QColor(255, 255, 255, alpha), 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif self._hover:
            pen = QPen(QColor(255, 255, 255, 135), 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        else:
            pen = QPen(QColor(255, 255, 255, 25), 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)


class ColorPaletteBar(QWidget):
    """Barra flotante que muestra los círculos de colores extraídos por pywal."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(300, 45)
        self.colors = []

    def set_colors(self, hex_colors):
        self.colors = hex_colors[:6]
        self.update()

    def paintEvent(self, event):
        if not self.colors:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)
        painter.fillPath(bg_path, QBrush(QColor(15, 15, 15, 190)))
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawPath(bg_path)

        diameter = 24
        spacing = 10
        total_w = len(self.colors) * diameter + (len(self.colors) - 1) * spacing
        start_x = (self.width() - total_w) / 2.0
        y = (self.height() - diameter) / 2.0

        for i, hex_color in enumerate(self.colors):
            x = start_x + i * (diameter + spacing)
            c = QColor(hex_color)
            painter.setBrush(QBrush(c))
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1.5))
            painter.drawEllipse(QRectF(x, y, diameter, diameter))


class HUDPanel(QWidget):
    """Panel contenedor rectangular plano gris oscuro."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(840, 170)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        path = QPainterPath()
        path.addRect(QRectF(0, 0, w, h))

        painter.save()
        painter.setClipPath(path)
        bg = QColor(15, 15, 15, 190)
        painter.fillPath(path, QBrush(bg))
        painter.restore()

        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawPath(path)
        painter.restore()


class SelectorWindow(QWidget):
    def __init__(self, wallpaper_dir):
        super().__init__()
        self.wallpaper_dir = wallpaper_dir
        self.wallpapers = get_wallpapers(wallpaper_dir)
        self.current_idx = 0
        self.repeat_factor = 3
        self.virtual_wallpapers = []
        self.virtual_current_idx = 0

        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(2)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.dim_overlay = QWidget(self)
        self.dim_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.32);")

        self.hud = HUDPanel(self)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(50)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 8)
        self.hud.setGraphicsEffect(shadow)

        self.hud_layout = QHBoxLayout(self.hud)
        self.hud_layout.setContentsMargins(15, 10, 15, 10)
        self.hud_layout.setSpacing(10)
        self.hud_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_left = ArrowButton("left", self.hud)
        self.btn_left.clicked.connect(self.retreat)
        self.hud_layout.addWidget(self.btn_left, 0, Qt.AlignmentFlag.AlignCenter)

        self.scroll_area = QScrollArea(self.hud)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.hud_layout.addWidget(self.scroll_area)

        self.scroll_container = QWidget()
        self.scroll_container.setStyleSheet("background: transparent;")
        self.slots_layout = QHBoxLayout(self.scroll_container)
        
        self.slots_layout.setContentsMargins(255, 0, 255, 0)
        self.slots_layout.setSpacing(0)
        self.slots_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.scroll_area.setWidget(self.scroll_container)

        self.btn_right = ArrowButton("right", self.hud)
        self.btn_right.clicked.connect(self.advance)
        self.hud_layout.addWidget(self.btn_right, 0, Qt.AlignmentFlag.AlignCenter)

        # Restaurar la barra de paleta de colores debajo del HUD
        self.palette_bar = ColorPaletteBar(self)
        shadow_palette = QGraphicsDropShadowEffect(self)
        shadow_palette.setBlurRadius(30)
        shadow_palette.setColor(QColor(0, 0, 0, 180))
        shadow_palette.setOffset(0, 5)
        self.palette_bar.setGraphicsEffect(shadow_palette)

        self.scroll_anim = QVariantAnimation(self)
        self.scroll_anim.setDuration(240)
        self.scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scroll_anim.valueChanged.connect(self._animate_scroll)
        self.scroll_anim.finished.connect(self.normalize_virtual_index)

        self.visible_slots = []
        self.init_virtual_carousel()

        if self.wallpapers:
            base_offset = (self.repeat_factor // 2) * len(self.wallpapers)
            self.virtual_current_idx = base_offset + self.current_idx

        screen = self.screen()
        if screen:
            self.setGeometry(screen.geometry())
            self.dim_overlay.setGeometry(self.rect())

        self.position_hud()
        self.update_focused_view(animate_scroll=False)

        self.watcher = QFileSystemWatcher(self)
        if os.path.exists(self.wallpaper_dir):
            self.watcher.addPath(self.wallpaper_dir)
        self.watcher.directoryChanged.connect(self.handle_directory_mutations)

        self.watch_timer = QTimer(self)
        self.watch_timer.setInterval(3000)
        self.watch_timer.timeout.connect(self.ensure_watcher_resilience)
        self.watch_timer.start()

        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def fetch_pywal_preview(self, image_path):
        """Genera temporalmente la paleta con pywal para los círculos de colores en tiempo real."""
        try:
            cache_file = os.path.expanduser("~/.cache/wal/colors.json")
            subprocess.run(["wal", "-i", image_path, "-n", "-q"], check=True)
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    colors_dict = data.get("colors", {})
                    hex_list = [colors_dict.get(f"color{i}", "#ffffff") for i in range(1, 8)]
                    self.palette_bar.set_colors(hex_list)
        except Exception as e:
            print(f"Error cargando previsualización de pywal: {e}")

    def ensure_watcher_resilience(self):
        if os.path.exists(self.wallpaper_dir):
            if self.wallpaper_dir not in self.watcher.directories():
                self.watcher.addPath(self.wallpaper_dir)
                self.handle_directory_mutations()

    def init_virtual_carousel(self):
        self.clear_carousel_layout()
        if not self.wallpapers:
            empty = QLabel("Vacío")
            empty.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 13px; font-weight: 300;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.slots_layout.addWidget(empty)
            return

        self.repeat_factor = 5 if len(self.wallpapers) < 5 else 3
        self.virtual_wallpapers = self.wallpapers * self.repeat_factor

        self.visible_slots = []
        for i, path in enumerate(self.virtual_wallpapers):
            thumb = ThumbnailItem(self)
            thumb.virtual_index = i
            self.slots_layout.addWidget(thumb)
            self.visible_slots.append(thumb)

    def clear_carousel_layout(self):
        while self.slots_layout.count():
            item = self.slots_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.visible_slots = []

    def handle_directory_mutations(self):
        current = self.wallpapers[self.current_idx] if self.wallpapers else None
        self.wallpapers = get_wallpapers(self.wallpaper_dir)
        self.init_virtual_carousel()
        if not self.wallpapers:
            self.current_idx = 0
            self.virtual_current_idx = 0
            return
        if current in self.wallpapers:
            self.current_idx = self.wallpapers.index(current)
        else:
            self.current_idx = min(self.current_idx, len(self.wallpapers) - 1)
        
        base_offset = (self.repeat_factor // 2) * len(self.wallpapers)
        self.virtual_current_idx = base_offset + self.current_idx
        self.update_focused_view(animate_scroll=False)

    def position_hud(self):
        x_pos = (self.width() - self.hud.width()) // 2
        y_pos = (self.height() - self.hud.height()) // 2
        self.hud.move(x_pos, y_pos)
        
        # Posicionar la barra de colores debajo del HUD
        px_pos = (self.width() - self.palette_bar.width()) // 2
        py_pos = y_pos + self.hud.height() + 15
        self.palette_bar.move(px_pos, py_pos)

    def update_focused_view(self, animate_scroll=True):
        if not self.wallpapers or not self.visible_slots:
            return
            
        target_virtual_idx = self.virtual_current_idx
        
        for i, slot in enumerate(self.visible_slots):
            is_active = (i == target_virtual_idx)
            slot.update_content(self.virtual_wallpapers[i], is_active, self.threadpool)
            
        active_path = self.virtual_wallpapers[target_virtual_idx]
        if active_path:
            self.fetch_pywal_preview(active_path)
            
        QTimer.singleShot(25, lambda: self.center_active_item(target_virtual_idx, animate_scroll))

    def center_active_item(self, target_idx, animate=True):
        if target_idx >= len(self.visible_slots):
            return
        target_widget = self.visible_slots[target_idx]
        
        widget_center = target_widget.x() + (target_widget.width() // 2)
        area_width = self.scroll_area.width()
        target_scroll = widget_center - (area_width // 2)
        
        max_scroll = self.scroll_area.horizontalScrollBar().maximum()
        target_scroll = max(0, min(target_scroll, max_scroll))
        
        self.scroll_anim.stop()
        if animate:
            self.scroll_anim.setStartValue(self.scroll_area.horizontalScrollBar().value())
            self.scroll_anim.setEndValue(target_scroll)
            self.scroll_anim.start()
        else:
            self.scroll_area.horizontalScrollBar().setValue(target_scroll)

    def _animate_scroll(self, val):
        self.scroll_area.horizontalScrollBar().setValue(val)

    def normalize_virtual_index(self):
        if not self.wallpapers:
            return
        N = len(self.wallpapers)
        base_offset = (self.repeat_factor // 2) * N
        
        if self.virtual_current_idx < base_offset or self.virtual_current_idx >= base_offset + N:
            self.virtual_current_idx = base_offset + self.current_idx
            self.update_focused_view(animate_scroll=False)

    def set_index_by_virtual_idx(self, virtual_idx):
        if self.wallpapers:
            self.virtual_current_idx = virtual_idx
            self.current_idx = virtual_idx % len(self.wallpapers)
            self.update_focused_view()
            self.setFocus()

    def advance(self):
        if not self.wallpapers:
            return
        N = len(self.wallpapers)
        base_offset = (self.repeat_factor // 2) * N
        
        if self.current_idx == N - 1:
            self.virtual_current_idx = base_offset - 1
            self.update_focused_view(animate_scroll=False)
            
        self.virtual_current_idx += 1
        self.current_idx = self.virtual_current_idx % N
        self.update_focused_view(animate_scroll=True)

    def retreat(self):
        if not self.wallpapers:
            return
        N = len(self.wallpapers)
        base_offset = (self.repeat_factor // 2) * N
        
        if self.current_idx == 0:
            self.virtual_current_idx = base_offset + N
            self.update_focused_view(animate_scroll=False)
            
        self.virtual_current_idx -= 1
        self.current_idx = self.virtual_current_idx % N
        self.update_focused_view(animate_scroll=True)

    def confirm_selection(self):
        if self.wallpapers:
            selected_path = self.wallpapers[self.current_idx]
            apply_wallpaper(selected_path)
            subprocess.run(["wal", "-i", selected_path, "-q"], check=True)
            update_starship_toml()
            self.close()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_D, Qt.Key.Key_Down, Qt.Key.Key_S):
            self.advance()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_A, Qt.Key.Key_Up, Qt.Key.Key_W):
            self.retreat()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.confirm_selection()

    def wheelEvent(self, event: QWheelEvent):
        if event.angleDelta().y() > 0:
            self.retreat()
        elif event.angleDelta().y() < 0:
            self.advance()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.dim_overlay.setGeometry(self.rect())
        self.position_hud()

    def closeEvent(self, event):
        self.watch_timer.stop()
        try:
            self.watcher.blockSignals(True)
            if self.watcher.directories():
                self.watcher.removePaths(self.watcher.directories())
        except Exception:
            pass
        self.threadpool.clear()
        self.threadpool.waitForDone(100)
        super().closeEvent(event)