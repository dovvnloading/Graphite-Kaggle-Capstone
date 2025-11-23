import os
import webbrowser
from datetime import datetime

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QWidget, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QMessageBox, QGraphicsDropShadowEffect,
    QInputDialog, QTextEdit, QTabWidget, QFormLayout, QComboBox, QGridLayout, QApplication,
    QCheckBox, QScrollArea, QRadioButton, QButtonGroup, QFrame
)

import api_provider
import graphite_config as config
from graphite_styles import THEMES
from graphite_config import apply_theme, get_current_palette

# A consistent path for the application icon
# NOTE: For a real distributable app, this should be a relative path.
ICON_PATH = r"C:\Users\Admin\source\repos\graphite_app\assets\graphite.ico"


class ChatLibraryDialog(QDialog):
    """
    A dialog for managing saved chat sessions. It allows users to view, search,
    load, rename, and delete past conversations.
    """
    def __init__(self, session_manager, parent=None):
        super().__init__(parent)
        self.session_manager = session_manager

        self.setWindowTitle("Chat Library")
        self.setWindowIcon(QIcon(ICON_PATH)) # FIX: Add window icon
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.resize(500, 600)
        self.on_theme_changed()

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search chats...")
        self.search_input.textChanged.connect(self.filter_chats)
        main_layout.addWidget(self.search_input)
        
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        
        new_chat_btn = QPushButton(qta.icon('fa5s.plus', color='white'), "New Chat")
        new_chat_btn.clicked.connect(self.new_chat)
        toolbar.addWidget(new_chat_btn)
        
        delete_btn = QPushButton(qta.icon('fa5s.trash', color='white'), "Delete")
        delete_btn.clicked.connect(self.delete_selected)
        toolbar.addWidget(delete_btn)
        
        rename_btn = QPushButton(qta.icon('fa5s.edit', color='white'), "Rename")
        rename_btn.clicked.connect(self.rename_selected)
        toolbar.addWidget(rename_btn)
        
        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        main_layout.addWidget(toolbar_widget)
        
        self.chat_list = QListWidget()
        self.chat_list.setAlternatingRowColors(True)
        self.chat_list.itemDoubleClicked.connect(self.load_chat)
        self.chat_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d; border: 1px solid #3f3f3f; border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px; border-bottom: 1px solid #3f3f3f;
            }
            QListWidget::item:alternate { background-color: #333333; }
            QListWidget::item:selected { background-color: #2ecc71; color: white; }
            QListWidget::item:hover { background-color: #3f3f3f; }
        """)
        main_layout.addWidget(self.chat_list)
        
        self.status_label = QLabel()
        main_layout.addWidget(self.status_label)
        
        self.refresh_chat_list()
        
        if parent:
            parent_center = parent.geometry().center()
            self.move(parent_center.x() - self.width() // 2,
                     parent_center.y() - self.height() // 2)

    def on_theme_changed(self):
        self.setStyleSheet(THEMES[config.CURRENT_THEME]["stylesheet"])

    def closeEvent(self, event):
        event.accept()
        
    def refresh_chat_list(self):
        self.chat_list.clear()
        chats = self.session_manager.db.get_all_chats()
        for chat_id, title, created_at, updated_at in chats:
            item = QListWidgetItem()
            created_dt = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            updated_dt = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
            display_text = f"{title}\nCreated: {created_dt.strftime('%Y-%m-%d %H:%M')}\nUpdated: {updated_dt.strftime('%Y-%m-%d %H:%M')}"
            item.setText(display_text)
            item.setData(Qt.ItemDataRole.UserRole, chat_id)
            self.chat_list.addItem(item)
        self.update_status()
            
    def update_status(self):
        count = self.chat_list.count()
        self.status_label.setText(f"Total chats: {count}")
        
    def filter_chats(self, text):
        text = text.lower()
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            item.setHidden(text not in item.text().lower())
                
    def new_chat(self):
        if self.parent() and hasattr(self.parent(), 'new_chat'):
            if self.parent().new_chat(parent_for_dialog=self):
                self.close()
                
    def delete_selected(self):
        current_item = self.chat_list.currentItem()
        if current_item:
            chat_id = current_item.data(Qt.ItemDataRole.UserRole)
            reply = QMessageBox.question(self, 'Delete Chat', 'Are you sure you want to delete this chat?\nThis action cannot be undone.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.session_manager.db.delete_chat(chat_id)
                self.refresh_chat_list()
                
    def rename_selected(self):
        current_item = self.chat_list.currentItem()
        if current_item:
            chat_id = current_item.data(Qt.ItemDataRole.UserRole)
            current_title = current_item.text().split('\n')[0]
            new_title, ok = QInputDialog.getText(self, 'Rename Chat', 'Enter new title:', text=current_title)
            if ok and new_title:
                self.session_manager.db.rename_chat(chat_id, new_title)
                self.refresh_chat_list()
                
    def load_chat(self, item):
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.session_manager.load_chat(chat_id)
            if self.session_manager.window:
                chat_info = self.session_manager.db.load_chat(chat_id)
                if chat_info and 'title' in chat_info:
                    self.session_manager.window.setWindowTitle(f"Graphite - {chat_info['title']}")
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load chat: {str(e)}")

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Graphite")
        self.setWindowIcon(QIcon(ICON_PATH)) # FIX: Add window icon
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(True)
        self.resize(400, 250)
        self.on_theme_changed()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        app_title = QLabel("Graphite - Competition Edition")
        app_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2ecc71;")
        main_layout.addWidget(app_title, alignment=Qt.AlignmentFlag.AlignCenter)
        dev_label = QLabel("Developed by: Matthew Wesney")
        dev_label.setStyleSheet("font-size: 14px;")
        main_layout.addWidget(dev_label, alignment=Qt.AlignmentFlag.AlignCenter)
        contact_label = QLabel("Contact: dev.graphite@gmail.com")
        contact_label.setStyleSheet("font-size: 12px;")
        main_layout.addWidget(contact_label, alignment=Qt.AlignmentFlag.AlignCenter)
        github_link = QLabel('<a href="https://github.com/dovvnloading/Graphite" style="color: #3498db; text-decoration: none;">View on GitHub</a>')
        github_link.setOpenExternalLinks(False)
        github_link.linkActivated.connect(lambda url: webbrowser.open(url))
        main_layout.addWidget(github_link, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addStretch()
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

    def on_theme_changed(self):
        self.setStyleSheet(THEMES[config.CURRENT_THEME]["stylesheet"])

class ColorPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(15, 15, 15, 15)
        self.container = QWidget(self)
        self.container.setObjectName("colorPickerContainer")
        dialog_layout.addWidget(self.container)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 2)
        self.container.setGraphicsEffect(shadow)
        main_layout = QVBoxLayout(self.container)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        default_btn = QPushButton("Reset to Default")
        default_btn.setIcon(qta.icon('fa5s.undo', color='white'))
        default_btn.clicked.connect(lambda: self.color_selected(None, "default"))
        main_layout.addWidget(default_btn)
        def create_section(title, color_type, names_list):
            label = QLabel(title)
            label.setStyleSheet("color: #cccccc; font-size: 10px; margin-top: 5px;")
            main_layout.addWidget(label)
            grid_layout = QGridLayout()
            grid_layout.setSpacing(8)
            col, row = 0, 0
            frame_colors = get_current_palette().FRAME_COLORS
            for name in names_list:
                color_data = frame_colors[name]
                btn = QPushButton()
                btn.setFixedSize(28, 28)
                btn.setToolTip(name)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                style = f"""
                    QPushButton {{ background-color: {color_data["color"]}; border: 2px solid #3f3f3f; border-radius: 14px; }}
                    QPushButton:hover {{ border: 2px solid #ffffff; }}
                """
                if color_type == "header":
                    style = f"""
                        QPushButton {{
                            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {color_data["color"]}, stop:0.4 {color_data["color"]},
                                stop:0.41 #3f3f3f, stop:1 #3f3f3f);
                            border: 2px solid #3f3f3f; border-radius: 14px;
                        }}
                        QPushButton:hover {{ border: 2px solid #ffffff; }}
                    """
                btn.setStyleSheet(style)
                btn.clicked.connect(lambda checked, c=color_data: self.color_selected(c["color"], c["type"]))
                grid_layout.addWidget(btn, row, col)
                col = (col + 1) % 5
                if col == 0: row += 1
            main_layout.addLayout(grid_layout)
        frame_colors = get_current_palette().FRAME_COLORS
        full_color_names = [k for k, v in frame_colors.items() if v['type'] == 'full' and 'Gray' not in k]
        header_color_names = [k for k, v in frame_colors.items() if v['type'] == 'header']
        mono_color_names = [k for k, v in frame_colors.items() if 'Gray' in k]
        create_section("Frame Colors", "full", full_color_names)
        create_section("Header Colors Only", "header", header_color_names)
        create_section("Monochrome", "full", mono_color_names)
        main_layout.addStretch()
        self.setStyleSheet("""
            QDialog { background: transparent; }
            QWidget#colorPickerContainer { background-color: #252526; border-radius: 8px; }
            QPushButton { background-color: #3f3f3f; border-radius: 5px; padding: 8px; }
            QPushButton:hover { background-color: #555555; }
        """)
        self.selected_color = None
        self.selected_type = None
        
    def showEvent(self, event):
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            if not self.container.geometry().contains(self.mapFromGlobal(event.globalPos())):
                self.close()
                return True
        return super().eventFilter(watched, event)
        
    def color_selected(self, color, color_type):
        self.selected_color = color
        self.selected_type = color_type
        self.accept()
        
    def get_selected_color(self):
        return self.selected_color, self.selected_type

class PinEditDialog(QDialog):
    def __init__(self, title="", note="", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.resize(300, 200)
        self.container = QWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.container)
        container_layout = QVBoxLayout(self.container)
        container_layout.setSpacing(10)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.addWidget(QLabel("Pin Title"))
        self.title_input = QLineEdit(title)
        self.title_input.setPlaceholderText("Enter pin title...")
        container_layout.addWidget(self.title_input)
        container_layout.addWidget(QLabel("Note"))
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("Add a note...")
        self.note_input.setText(note)
        self.note_input.setMaximumHeight(80)
        container_layout.addWidget(self.note_input)
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        container_layout.addLayout(button_layout)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 0)
        self.container.setGraphicsEffect(shadow)
        self.container.setStyleSheet("""
            QWidget { background-color: #2d2d2d; border-radius: 10px; }
            QLabel { color: white; font-size: 12px; }
            QLineEdit, QTextEdit { background-color: #3f3f3f; border: none; border-radius: 5px; padding: 5px; color: white; }
            QPushButton { background-color: #2ecc71; border: none; border-radius: 5px; padding: 8px 16px; color: white; }
            QPushButton:hover { background-color: #27ae60; }
        """)

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Graphite Help")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.setMinimumSize(1100, 750)
        self.resize(900, 700)
        self.on_theme_changed()
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3f3f3f; background: #2d2d2d; border-radius: 4px; }
            QTabBar::tab { background: #252526; color: #ffffff; padding: 8px 16px; border: 1px solid #3f3f3f; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; min-width: 100px; }
            QTabBar::tab:selected { background: #2d2d2d; border-bottom: 2px solid #2ecc71; }
            QTabBar::tab:hover { background: #333333; }
        """)
        
        def create_scrollable_tab(sections):
            tab_content = QWidget()
            tab_layout = QVBoxLayout(tab_content)
            tab_layout.setSpacing(15)
            for title, items in sections:
                tab_layout.addWidget(self._create_section(title, items))
            tab_layout.addStretch()
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(tab_content)
            scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
            return scroll_area

        # 1. Navigation Tab
        nav_tab = create_scrollable_tab([
            ("Mouse Navigation", [
                ("Pan View", "Hold Middle Mouse Button and drag.", "fa5s.hand-paper"),
                ("Zoom", "Hold Ctrl + Mouse Wheel, or use Q/E keys.", "fa5s.search-plus"),
                ("Zoom to Selection", "Hold Shift + drag to draw a box.", "fa5s.search"),
                ("Select Items", "Click to select. Drag on canvas to box select.", "fa5s.mouse-pointer"),
                ("Move Items", "Drag selected items to reposition.", "fa5s.arrows-alt"),
            ]),
            ("View Controls", [
                ("Reset View", "Restores default zoom and position.", "fa5s.undo"),
                ("Fit All", "Zooms to show all items on canvas.", "fa5s.expand"),
                ("Minimap", "Use the minimap on the right to jump to nodes.", "fa5s.map")
            ])
        ])
        tab_widget.addTab(nav_tab, "Navigation")

        # 2. Node Types Tab (New)
        nodes_tab = create_scrollable_tab([
            ("Standard Nodes", [
                ("Chat Node", "The core building block. Green for User, Blue for AI. Contains the conversation text.", "fa5s.comment"),
                ("Code Node", "A specialized node for displaying syntax-highlighted code blocks. Created automatically by the AI.", "fa5s.code"),
                ("Image Node", "Displays images generated by the AI or attached by the user.", "fa5s.image"),
                ("Document Node", "Displays the text content of an attached file (.txt, .pdf, .docx).", "fa5s.file-alt"),
                ("Thinking Node", "Contains the AI's internal reasoning process (Chain of Thought). Can be docked.", "fa5s.brain"),
                ("Note", "A floating sticky note for annotations or system prompts. (Ctrl+N)", "fa5s.sticky-note"),
                ("Navigation Pin", "A bookmark for quick navigation to specific areas of the graph.", "fa5s.map-pin"),
            ])
        ])
        tab_widget.addTab(nodes_tab, "Node Types")

        # 3. Chat Features Tab
        chat_tab = create_scrollable_tab([
            ("Interaction", [
                ("Send Message", "Type in the bar and press Enter. Branches off the selected node.", "fa5s.paper-plane"),
                ("Context Selection", "Click any node to make it the active context for your next message.", "fa5s.comment"),
                ("Attach Files", "Click the paperclip to attach images or documents for the AI to analyze.", "fa5s.paperclip"),
            ]),
            ("Management", [
                ("Export", "Right-click a node to export content to PDF, Word, HTML, etc.", "fa5s.file-export"),
                ("Chat Library", "Open the Library (Ctrl+L) to manage saved sessions.", "fa5s.folder-open"),
                ("Search", "Use Ctrl+F to find text within nodes.", "fa5s.search")
            ])
        ])
        tab_widget.addTab(chat_tab, "Chat Features")

        # 4. Agent Orchestrator Tab (New)
        orchestrator_tab = create_scrollable_tab([
            ("The Workflow", [
                ("Orchestrator Node", "The manager. Give it a high-level goal, and it generates a multi-step plan.", "fa5s.sitemap"),
                ("Execution", "The Orchestrator automatically creates and controls other tool nodes to execute the plan.", "fa5s.cogs"),
            ]),
            ("Orchestrator Tools", [
                ("Memory Bank", "A shared storage node. Allows agents to save and pass data between steps.", "fa5s.database"),
                ("Synthesizer", "The writer. Takes raw data (from Memory) and instructions to compose final reports.", "fa5s.pencil-ruler"),
                ("Web Researcher", "Searches the internet, validates sources, and summarizes findings.", "fa5s.globe-americas"),
                ("Py-Coder", "Writes and executes Python code to solve computational tasks.", "fa5s.code"),
            ])
        ])
        tab_widget.addTab(orchestrator_tab, "Agent Orchestrator")

        # 5. Specialized Agents (Plugins) Tab
        plugins_tab = create_scrollable_tab([
            ("Specialized Agents", [
                ("Py-Coder", "A dual-mode coding environment. AI Mode generates/fixes code; Manual Mode runs your code.", "fa5s.code"),
                ("Graphite-Web", "A manual web search node. Enter a query to get a synthesized answer with sources.", "fa5s.globe-americas"),
                ("Graphite-Reasoning", "A 'System 2' thinker. Uses a 'Plan -> Reason -> Critique' loop for complex logic.", "fa5s.brain"),
                ("Conversation Node", "A linear, self-contained chat detached from the main graph.", "fa5s.comments"),
                ("HTML Renderer", "Renders HTML/CSS/JS code in a live preview window.", "fa5s.code"),
                ("System Prompt", "Overrides the default AI personality for a branch. Connect a Note to a root node.", "fa5s.cog"),
            ]),
            ("AI Actions (Right-Click)", [
                ("Generate Takeaway", "Creates a note with a concise summary of the selected node.", "fa5s.lightbulb"),
                ("Generate Explainer", "Creates a note with a simplified explanation of complex topics.", "fa5s.question-circle"),
                ("Generate Chart", "Creates a visualization (Bar, Line, Pie, etc.) from data in the node.", "fa5s.chart-bar"),
            ])
        ])
        tab_widget.addTab(plugins_tab, "Specialized Agents")

        # 6. Organization Tab
        org_tab = create_scrollable_tab([
            ("Grouping", [
                ("Frames", "Ctrl+G to group items in a resizable background frame.", "fa5s.object-group"),
                ("Containers", "Ctrl+Shift+G to group items in a movable container that can collapse.", "fa5s.box-open"),
            ]),
            ("Layout", [
                ("Auto-Organize", "Click 'Organize' in toolbar to arrange nodes in a tree layout.", "fa5s.sitemap"),
                ("Color Coding", "Use the header button on Frames/Containers/Notes to change colors.", "fa5s.palette"),
            ])
        ])
        tab_widget.addTab(org_tab, "Organization")

        # 7. Shortcuts Tab
        shortcuts_tab = create_scrollable_tab([
            ("General", [
                ("Ctrl + K", "Open Command Palette", "fa5s.terminal"),
                ("Ctrl + T", "New Chat", "fa5s.plus-square"),
                ("Ctrl + L", "Open Library", "fa5s.book"),
                ("Ctrl + S", "Save Chat", "fa5s.save"),
                ("Ctrl + F", "Find", "fa5s.search"),
            ]),
            ("Canvas", [
                ("Ctrl + N", "New Note", "fa5s.sticky-note"),
                ("Ctrl + G", "Create Frame", "fa5s.object-group"),
                ("Ctrl + Shift + G", "Create Container", "fa5s.box-open"),
                ("Delete", "Delete Selection", "fa5s.trash-alt"),
                ("Ctrl + Click (Line)", "Add Pin", "fa5s.dot-circle"),
            ]),
            ("Navigation", [
                ("W, A, S, D", "Pan View", "fa5s.arrows-alt"),
                ("Q / E", "Zoom Out / In", "fa5s.search"),
                ("Ctrl + Arrows", "Navigate Nodes", "fa5s.project-diagram"),
            ])
        ])
        tab_widget.addTab(shortcuts_tab, "Shortcuts")
        
        main_layout.addWidget(tab_widget)

    def on_theme_changed(self):
        self.setStyleSheet(THEMES[config.CURRENT_THEME]["stylesheet"])

    def _create_section(self, title, items):
        section = QFrame()
        section.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
        """)
        layout = QVBoxLayout(section)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("QLabel { color: #2ecc71; font-size: 15px; font-weight: bold; border: none; background: transparent; }")
        layout.addWidget(title_label)
        
        for action, description, icon_name in items:
            item_widget = QWidget()
            item_widget.setStyleSheet("background: transparent; border: none;")
            item_layout = QHBoxLayout(item_widget)
            item_layout.setSpacing(15)
            item_layout.setContentsMargins(0,0,0,0)
            
            icon_label = QLabel()
            icon = qta.icon(icon_name, color='#2ecc71')
            icon_label.setPixmap(icon.pixmap(24, 24))
            icon_label.setFixedWidth(30)
            icon_label.setStyleSheet("background: transparent; border: none;")
            item_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignTop)
            
            text_widget = QWidget()
            text_widget.setStyleSheet("background: transparent; border: none;")
            text_layout = QVBoxLayout(text_widget)
            text_layout.setSpacing(4)
            text_layout.setContentsMargins(0,0,0,0)
            
            action_label = QLabel(action)
            action_label.setStyleSheet("color: white; font-weight: bold; background: transparent; border: none;")
            text_layout.addWidget(action_label)
            
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #aaaaaa; background: transparent; border: none;")
            text_layout.addWidget(desc_label)
            
            item_layout.addWidget(text_widget)
            layout.addWidget(item_widget)
            
        return section

class ApiSettingsWidget(QWidget):
    """A settings widget for configuring API-based providers."""
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        
        info = QLabel("Configure your Google Gemini API endpoint. This key will be saved for the current session.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #d4d4d4; margin-bottom: 15px;")
        layout.addWidget(info)

        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setVerticalSpacing(10)
        
        self.api_key_input = QLineEdit(os.getenv('GRAPHITE_GEMINI_API_KEY', ''), echoMode=QLineEdit.Password, placeholderText="Enter your Gemini API key...")
        form_layout.addRow(QLabel("API Key:", styleSheet="color: #ffffff; font-weight: bold;"), self.api_key_input)
        
        self.smart_model_combo = QComboBox()
        self.fast_model_combo = QComboBox()

        for combo in [self.smart_model_combo, self.fast_model_combo]:
            combo.addItems(api_provider.GEMINI_MODELS_STATIC)

        self.smart_model_combo.setCurrentText("gemini-1.5-pro-latest")
        self.fast_model_combo.setCurrentText("gemini-1.5-flash-latest")

        form_layout.addRow(QLabel("Smart Model:", styleSheet="color: #ffffff; font-weight: bold;"), self.smart_model_combo)
        form_layout.addRow(QLabel("Fast Model:", styleSheet="color: #ffffff; font-weight: bold;"), self.fast_model_combo)

        layout.addLayout(form_layout)
        layout.addStretch()

    def save_settings(self):
        """Saves the configured API settings as environment variables for the session."""
        api_key = self.api_key_input.text().strip()

        if not api_key:
            QMessageBox.warning(self, "Missing API Key", "Please enter your API Key.")
            return False

        os.environ['GRAPHITE_GEMINI_API_KEY'] = api_key

        smart_model = self.smart_model_combo.currentText()
        fast_model = self.fast_model_combo.currentText()

        # Map the simplified model choices to the specific tasks
        api_provider.set_task_model(config.TASK_CHAT, smart_model)
        api_provider.set_task_model(config.TASK_WEB_SUMMARIZE, smart_model)
        api_provider.set_task_model(config.TASK_CHART, smart_model)
        
        api_provider.set_task_model(config.TASK_TITLE, fast_model)
        api_provider.set_task_model(config.TASK_WEB_VALIDATE, fast_model)
        
        QMessageBox.information(self, "Configuration Saved", "API settings for Google Gemini have been saved for this session.")
        return True

class SettingsDialog(QDialog):
    """
    A simplified dialog for API settings, for the competition.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setWindowIcon(QIcon(ICON_PATH)) # FIX: Add window icon
        self.setMinimumWidth(550)
        self.setMinimumHeight(350)
        self.on_theme_changed()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.api_tab = ApiSettingsWidget()
        main_layout.addWidget(self.api_tab)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.save_and_close_button = QPushButton("Save and Close")
        self.save_and_close_button.clicked.connect(self.save_and_close)
        button_layout.addWidget(self.save_and_close_button)
        main_layout.addLayout(button_layout)
        
    def show_api_only(self):
        """ Configures the dialog for the initial API key setup. """
        self.setWindowTitle("API Configuration Required")
        pass

    def save_and_close(self):
        if self.api_tab.save_settings():
            self.accept()

    def on_theme_changed(self):
        self.setStyleSheet(THEMES[config.CURRENT_THEME]["stylesheet"])