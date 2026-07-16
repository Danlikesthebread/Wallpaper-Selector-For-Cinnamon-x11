import os
import subprocess
from PyQt6.QtGui import QImageReader

def get_supported_extensions():
    formats = QImageReader.supportedImageFormats()
    exts = set()
    for fmt in formats:
        exts.add(f".{fmt.data().decode().lower()}")
    exts.update(['.jpg', '.jpeg', '.png', '.webp', '.gif'])
    return tuple(exts)

def get_wallpapers(directory):
    if not directory or not os.path.isdir(directory):
        return []
    wallpapers = []
    valid_exts = get_supported_extensions()
    try:
        for file in os.listdir(directory):
            if file.lower().endswith(valid_exts):
                wallpapers.append(os.path.join(directory, file))
    except Exception:
        return []
    return sorted(wallpapers)

def sync_gtk_theme(image_path):
    """Sincronizar el tema GTK con el wallpaper usando el script de Andromeda"""
    script_path = os.path.expanduser("~/.local/bin/sync-andromeda.sh")
    if os.path.exists(script_path):
        try:
            subprocess.run([script_path, image_path], check=False, capture_output=True)
        except Exception as e:
            print(f"Error sincronizando tema: {e}")

def apply_wallpaper(image_path):
    if not os.path.exists(image_path):
        return
    file_uri = f"file://{image_path}"
    subprocess.run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", file_uri], check=False)
    subprocess.run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri-dark", file_uri], check=False)
    
    # NUEVO: Sincronizar el tema GTK
    sync_gtk_theme(image_path)
