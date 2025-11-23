# This file holds the global configuration for the application,
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from graphite_styles import THEMES

# --- ASSET PATH CONFIGURATION ---
# Establish the base directory of the application to build portable paths.
BASE_DIR = Path(__file__).resolve().parent

def get_asset_path(asset_name: str) -> Path:
    """
    Constructs a full, OS-agnostic path to an asset in the 'assets' directory.

    Args:
        asset_name (str): The filename of the asset (e.g., "graphite.ico").

    Returns:
        pathlib.Path: A Path object pointing to the asset.
    """
    return BASE_DIR / "assets" / asset_name

# --- THEME CONFIGURATION ---
CURRENT_THEME = "dark"

def get_current_palette():
    """Returns the color palette object for the currently active theme."""
    return THEMES[CURRENT_THEME]["palette"]

def apply_theme(app: QApplication, theme_name: str):
    """
    Applies a theme stylesheet to the entire application and updates the global theme state.
    This function also notifies all top-level windows to update their theme-dependent styles.

    Args:
        app (QApplication): The main application instance.
        theme_name (str): The name of the theme to apply (e.g., "dark", "mono").
    """
    global CURRENT_THEME
    if theme_name in THEMES:
        CURRENT_THEME = theme_name
    else:
        print(f"Warning: Theme '{theme_name}' not found. Defaulting to 'dark'.")
        CURRENT_THEME = "dark"
    
    # Apply the global stylesheet.
    # The stylesheet can be a static string or a function that returns a string (for dynamic paths).
    stylesheet_or_func = THEMES[CURRENT_THEME]["stylesheet"]
    stylesheet = stylesheet_or_func() if callable(stylesheet_or_func) else stylesheet_or_func
    app.setStyleSheet(stylesheet)
    
    # Notify all top-level windows (e.g., ChatWindow, dialogs) that the theme has changed,
    # so they can update any custom-painted elements.
    for widget in app.topLevelWidgets():
        if hasattr(widget, 'on_theme_changed'):
            widget.on_theme_changed()

# --- MODEL CONFIGURATION ---

# Abstract task identifiers used throughout the application to request a specific
# type of model from the API provider. This allows for using different models
# for different tasks (e.g., a fast model for titles, a powerful model for chat).
TASK_TITLE = "task_title"
TASK_CHAT = "task_chat"
TASK_CHART = "task_chart"
TASK_IMAGE_GEN = "task_image_gen"
TASK_WEB_VALIDATE = "task_web_validate"
TASK_WEB_SUMMARIZE = "task_web_summarize"


# Constants for identifying the API provider type.
API_PROVIDER_GEMINI = "Google Gemini"