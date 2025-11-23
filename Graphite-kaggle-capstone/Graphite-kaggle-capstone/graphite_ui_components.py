from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, QRect, Qt, Signal
from PySide6.QtGui import QPixmap, QIcon
import markdown
import qtawesome as qta
from graphite_config import get_current_palette, get_asset_path

class CustomTitleBar(QWidget):
    """
    A custom title bar widget to replace the native window frame.
    
    This class provides a styled title bar with a custom icon, title, and window
    control buttons (minimize, maximize, close). It also implements the logic
    for moving the window by clicking and dragging the title bar.
    """
    def __init__(self, parent=None):
        """
        Initializes the CustomTitleBar.

        Args:
            parent (QWidget, optional): The parent widget, typically the main window. 
                                        Defaults to None.
        """
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("titleBar")
        
        icon_path = get_asset_path("graphite.ico")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)

        # Application icon in the title bar.
        icon_label = QLabel()
        icon_pixmap = QPixmap(str(icon_path)).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        icon_label.setPixmap(icon_pixmap)
        layout.addWidget(icon_label)
        
        # Window title label.
        self.title = QLabel("Graphite")
        layout.addWidget(self.title)
        layout.addStretch()
        
        # Window control buttons (minimize, maximize, close).
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(0)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        
        self.minimize_btn = QPushButton("🗕")
        self.maximize_btn = QPushButton("🗖")
        self.close_btn = QPushButton("✕")
        
        for btn in (self.minimize_btn, self.maximize_btn, self.close_btn):
            btn.setFixedSize(34, 26)
            btn.setObjectName("titleBarButton")
            btn_layout.addWidget(btn)
        
        # Special object name for the close button for unique styling (e.g., red hover).
        self.close_btn.setObjectName("closeButton")
        
        # Connect button signals to the parent window's slots.
        self.minimize_btn.clicked.connect(self.parent.showMinimized)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.parent.close)
        
        button_widget = QWidget()
        button_widget.setObjectName("titleBarButtons")
        button_widget.setLayout(btn_layout)
        layout.addWidget(button_widget)
        
        # Attributes for handling window dragging.
        self.pressing = False
        self.start_pos = None

    def setTitle(self, title):
        """
        Sets the text of the title label.

        Args:
            title (str): The new title to display.
        """
        self.title.setText(title)
        
    def toggle_maximize(self):
        """Toggles the main window between maximized and normal states."""
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.maximize_btn.setText("🗖") # Restore icon
        else:
            self.parent.showMaximized()
            self.maximize_btn.setText("🗗") # Maximized icon
            
    def mousePressEvent(self, event):
        """
        Captures mouse press events to initiate window dragging.

        Args:
            event (QMouseEvent): The mouse press event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressing = True
            self.start_pos = event.globalPosition().toPoint()
            
    def mouseMoveEvent(self, event):
        """
        Moves the parent window when the title bar is dragged.

        Args:
            event (QMouseEvent): The mouse move event.
        """
        if self.pressing:
            # If the window is maximized, dragging should restore it to normal size.
            if self.parent.isMaximized():
                self.parent.showNormal()
            
            # Calculate the window's new position based on the mouse movement.
            delta = event.globalPosition().toPoint() - self.start_pos
            self.parent.move(self.parent.x() + delta.x(), self.parent.y() + delta.y())
            self.start_pos = event.globalPosition().toPoint()
            
    def mouseReleaseEvent(self, event):
        """Stops the dragging operation on mouse release."""
        self.pressing = False

class NotificationBanner(QWidget):
    """
    A banner widget that slides up from the bottom of its parent to display
    temporary messages (e.g., errors, confirmations).
    """
    def __init__(self, parent=None):
        """
        Initializes the NotificationBanner.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setObjectName("notificationBanner")
        self.setFixedHeight(40)
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)

        self.message_label = QLabel()
        self.message_label.setObjectName("notificationLabel")
        layout.addWidget(self.message_label)

        layout.addStretch()

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("notificationCloseButton")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.hide_banner)
        layout.addWidget(self.close_button)

        self.setStyleSheet("""
            QWidget#notificationBanner {
                background-color: #e67e22;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QLabel#notificationLabel {
                color: #ffffff;
                font-weight: bold;
                background-color: transparent;
            }
            QPushButton#notificationCloseButton {
                background-color: transparent;
                border: none;
                color: #ffffff;
                font-size: 14px;
                border-radius: 12px;
            }
            QPushButton#notificationCloseButton:hover {
                background-color: rgba(0, 0, 0, 0.2);
            }
        """)

        # Timer to automatically hide the banner after a duration.
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_banner)

        # Animation for the slide-in and slide-out effect.
        self.animation = QPropertyAnimation(self, b"geometry", self)

    def show_message(self, message, duration_ms=5000):
        """
        Displays a message on the banner with a slide-in animation.

        Args:
            message (str): The message to display.
            duration_ms (int): The duration in milliseconds before the banner
                               auto-hides. If 0, it stays visible.
        """
        self.message_label.setText(message)
        
        parent_width = self.parent().width()
        # Start the banner off-screen at the bottom.
        self.setGeometry(0, self.parent().height(), parent_width, self.height())
        self.setVisible(True)

        # Configure and start the slide-in animation.
        self.animation.setDuration(300)
        self.animation.setStartValue(QRect(0, self.parent().height(), parent_width, self.height()))
        self.animation.setEndValue(QRect(0, self.parent().height() - self.height(), parent_width, self.height()))
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.start()

        if duration_ms > 0:
            self.hide_timer.start(duration_ms)

    def hide_banner(self):
        """Hides the banner with a slide-out animation."""
        if not self.isVisible():
            return
            
        self.hide_timer.stop()
        
        # Configure and start the slide-out animation.
        parent_width = self.parent().width()
        self.animation.setDuration(300)
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(QRect(0, self.parent().height(), parent_width, self.height()))
        self.animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.animation.finished.connect(lambda: self.setVisible(False))
        self.animation.start()

class DocumentViewerPanel(QWidget):
    """
    A side panel designed to display formatted text content from a node,
    such as Markdown with code blocks and tables.
    """
    close_requested = Signal()

    def __init__(self, parent=None):
        """
        Initializes the DocumentViewerPanel.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setFixedWidth(500)
        self.setObjectName("documentViewerPanel")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Header section with icon, title, and close button.
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.book-open', color='white').pixmap(16, 16))
        header_layout.addWidget(icon_label)

        title_label = QLabel("Document View")
        title_label.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        close_button = QPushButton(qta.icon('fa5s.times', color='white'), "")
        close_button.setFixedSize(24, 24)
        close_button.setToolTip("Close Panel")
        close_button.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(close_button)
        main_layout.addWidget(header_widget)

        # Read-only text edit to display the formatted content.
        self.content_viewer = QTextEdit()
        self.content_viewer.setReadOnly(True)
        main_layout.addWidget(self.content_viewer)

        self.on_theme_changed()

    def set_document_content(self, markdown_text):
        """
        Sets the content of the viewer by converting Markdown text to HTML.

        Args:
            markdown_text (str): The Markdown-formatted text to display.
        """
        # Use the markdown library to convert the text to rich HTML.
        html = markdown.markdown(markdown_text, extensions=['fenced_code', 'tables'])
        self.content_viewer.setHtml(html)

    def on_theme_changed(self):
        """Updates the widget's stylesheet when the application theme changes."""
        palette = get_current_palette()
        self.setStyleSheet(f"""
            QWidget#documentViewerPanel {{
                background-color: #252526;
                border-right: 1px solid #3f3f3f;
            }}
            QTextEdit {{
                background-color: #2d2d2d;
                border: 1px solid #3f3f3f;
                color: #e0e0e0;
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #3f3f3f;
            }}
        """)