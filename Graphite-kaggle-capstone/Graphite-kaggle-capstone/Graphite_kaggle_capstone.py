# Graphite-kaggle-capstone.py

import sys
import os
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from graphite_window import ChatWindow
from graphite_config import apply_theme
import graphite_config as config
from graphite_dialogs import SettingsDialog
import api_provider

def main():
    """
    Initializes and runs the Graphite Competition Edition application.
    """
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    apply_theme(app, 'dark')

    # --- API Key Handling using Existing Dialog ---
    # The ApiSettingsWidget saves to environment variables for the session. We check if it's set.
    api_key = os.getenv('GRAPHITE_GEMINI_API_KEY')

    if not api_key:
        # If no key is set for this session, we must ask the user.
        # Create a temporary parent widget for proper dialog behavior.
        temp_parent = QWidget()
        
        dialog = SettingsDialog(parent=temp_parent)
        dialog.show_api_only() # Configure for first-time setup
        
        # The user must complete the dialog. If they cancel, we exit.
        if not dialog.exec():
            QMessageBox.critical(None, "API Key Required", "A Gemini API key is required to run. Exiting.")
            sys.exit(1)
            
        # After the dialog's save_settings is called, the key will be in the environment.
        api_key = os.getenv('GRAPHITE_GEMINI_API_KEY')
        if not api_key:
             QMessageBox.critical(None, "API Key Not Saved", "API key was not configured. Exiting.")
             sys.exit(1)

    # Now that we are sure a key exists, initialize the provider.
    try:
        api_provider.initialize_api(config.API_PROVIDER_GEMINI, api_key)
    except Exception as e:
        QMessageBox.critical(
            None, 
            "API Initialization Failed", 
            f"Failed to configure the Gemini API.\n\nError: {e}"
        )
        sys.exit(1)
    
    # The main application can now launch.
    main_window = ChatWindow() 
    main_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()