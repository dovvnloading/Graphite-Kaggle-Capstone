from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsProxyWidget, QWidget, QVBoxLayout,
    QTextEdit, QPushButton, QLabel, QHBoxLayout, QGraphicsObject
)
from PySide6.QtCore import QRectF, Qt, QPointF, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QFont
import qtawesome as qta
from graphite_config import get_current_palette
from graphite_connections import ConnectionItem
from graphite_widgets import HoverAnimationMixin
from graphite_agents import WebWorkerThread


class WebConnectionItem(ConnectionItem):
    """
    A specialized ConnectionItem with a distinct visual style (orange dash-dot line)
    to represent the link to a WebNode.
    """
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the connection line.

        Args:
            painter (QPainter): The painter to use.
            option (QStyleOptionGraphicsItem): Provides style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        if not (self.start_node and self.end_node):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        web_color = QColor(palette.FRAME_COLORS["Orange"]["color"])

        # Use a dash-dot line style to distinguish it from other connection types.
        pen = QPen(web_color, 2, Qt.PenStyle.DashDotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.hover:
            pen.setWidth(3)
        
        painter.setPen(pen)
        painter.drawPath(self.path)

        # Draw animated arrows if the animation is active.
        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], web_color)

    def drawArrow(self, painter, pos, color):
        """
        Draws a single animated arrow along the connection path.

        Args:
            painter (QPainter): The painter to use.
            pos (float): The position along the path (0.0 to 1.0).
            color (QColor): The color of the arrow.
        """
        if pos < 0 or pos > 1:
            return
        point = self.path.pointAtPercent(pos)
        angle = self.path.angleAtPercent(pos)
        
        arrow = QPainterPath()
        arrow.moveTo(-self.arrow_size, -self.arrow_size/2)
        arrow.lineTo(0, 0)
        arrow.lineTo(-self.arrow_size, self.arrow_size/2)
        
        painter.save()
        painter.translate(point)
        painter.rotate(-angle)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(arrow)
        painter.restore()


class WebNode(QGraphicsObject, HoverAnimationMixin):
    """
    A QGraphicsItem representing a web search plugin node on the canvas.

    This node provides a user interface for entering a search query, initiating a
    web search via a worker thread, and displaying the status and summarized
    results of that search.
    """
    run_button_clicked = Signal(object) 
    
    NODE_WIDTH = 450
    NODE_HEIGHT = 400
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0

    def __init__(self, parent_node, parent=None):
        """
        Initializes the WebNode.

        Args:
            parent_node (QGraphicsItem): The node from which this WebNode branches.
            parent (QGraphicsItem, optional): The parent graphics item. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.parent_node = parent_node
        self.children = []
        self.is_user = False # Considered an AI-generated node for history purposes.
        self.conversation_history = []
        
        self.worker_thread = None

        # State attributes for the web search process.
        self.query = ""
        self.status = "Idle"
        self.summary = ""
        self.sources = []

        # Standard graphics item setup.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False

        # Use a QGraphicsProxyWidget to embed standard Qt widgets into the graphics item.
        self.widget = QWidget()
        self.widget.setFixedSize(self.NODE_WIDTH, self.NODE_HEIGHT)
        self.widget.setStyleSheet("background-color: transparent;")
        
        self._setup_ui()
        
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(self.widget)
        
    @property
    def text(self):
        """Returns the primary content of the node for chart generation and copying."""
        return self.summary if self.summary else self.query

    @property
    def width(self):
        """Returns the fixed width of the node."""
        return self.NODE_WIDTH

    @property
    def height(self):
        """Returns the fixed height of the node."""
        return self.NODE_HEIGHT

    def _setup_ui(self):
        """Constructs the internal widget layout and components of the node."""
        main_layout = QVBoxLayout(self.widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        palette = get_current_palette()
        web_color = QColor(palette.FRAME_COLORS["Orange"]["color"])
        
        # --- Header Section ---
        header_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.globe-americas', color=web_color).pixmap(18, 18))
        header_layout.addWidget(icon)
        title_label = QLabel("Web Search")
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {web_color.name()};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # --- Query Input Section ---
        main_layout.addWidget(QLabel("Search Query:"))
        self.query_input = QTextEdit()
        self.query_input.setPlaceholderText("Enter a search query, e.g., 'Best Italian restaurants in NYC'")
        self.query_input.setFixedHeight(60)
        self.query_input.textChanged.connect(self._on_query_changed)
        main_layout.addWidget(self.query_input)

        # --- Run Button ---
        self.run_button = QPushButton("Fetch Information")
        self.run_button.clicked.connect(lambda: self.run_button_clicked.emit(self))
        main_layout.addWidget(self.run_button)

        # --- Status Label ---
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        main_layout.addWidget(self.status_label)

        # --- Result Display Section ---
        main_layout.addWidget(QLabel("Summary:"))
        self.summary_display = QTextEdit()
        self.summary_display.setReadOnly(True)
        self.summary_display.setPlaceholderText("Web search results will be summarized here...")
        main_layout.addWidget(self.summary_display)

        # Apply common styles to text edit widgets.
        for widget in [self.query_input, self.summary_display]:
            widget.setStyleSheet("""
                QTextEdit {
                    background-color: #252526; border: 1px solid #3f3f3f;
                    color: #cccccc; border-radius: 4px; padding: 5px;
                    font-family: Segoe UI, sans-serif;
                }
            """)

        # Style the run button with a contrasting text color based on background brightness.
        brightness = (web_color.red() * 299 + web_color.green() * 587 + web_color.blue() * 114) / 1000
        text_color = "black" if brightness > 128 else "white"
        
        self.run_button.setIcon(qta.icon('fa5s.search', color=text_color))
        self.run_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {web_color.name()}; color: {text_color}; border: none;
                border-radius: 4px; padding: 8px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {web_color.lighter(110).name()}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)

    def run_as_tool(self, query: str) -> WebWorkerThread:
        """
        Executes the web search as a tool. This method is designed to be called
        programmatically by another agent (like the Orchestrator).

        It sets up and returns a configured worker thread. The calling agent is
        responsible for connecting to the thread's signals and starting it.

        Args:
            query (str): The search query to execute.

        Returns:
            WebWorkerThread: The configured (but not started) worker thread.
        """
        self.set_query(query)
        self.set_running_state(True)
        self.set_status("Initializing...")

        parent_node = self.parent_node
        history = parent_node.conversation_history[:] if parent_node else []

        self.worker_thread = WebWorkerThread(query, history, self)
        
        self.worker_thread.update_status.connect(self.set_status)
        
        return self.worker_thread

    def _on_query_changed(self):
        """Slot to update the internal query state when the input text changes."""
        self.query = self.query_input.toPlainText()

    def set_query(self, text: str):
        """Programmatically sets the query text in the input widget."""
        self.query_input.setText(text)
        self.query = text

    def set_status(self, status_text: str):
        """
        Updates the status label to provide feedback on the search process.

        Args:
            status_text (str): The new status message to display.
        """
        self.status = status_text
        self.status_label.setText(f"Status: {status_text}")
        self.status_label.setStyleSheet("color: #3498db;")

    def set_running_state(self, is_running: bool):
        """
        Enables or disables UI elements based on the running state.

        Args:
            is_running (bool): True if the search is active, False otherwise.
        """
        self.run_button.setEnabled(not is_running)
        self.query_input.setReadOnly(is_running)
        self.run_button.setText("Processing..." if is_running else "Fetch Information")

    def set_result(self, summary: str, sources: list):
        """
        Displays the final summary and source links in the result area.

        Args:
            summary (str): The summarized text from the web search.
            sources (list[str]): A list of source URLs.
        """
        self.summary = summary
        self.sources = sources
        
        # Format sources as clickable Markdown links.
        source_links = "\n".join([f"- [{src}]({src})" for src in sources])
        full_text = f"{summary}\n\n---\n\n**Sources:**\n{source_links}"
        
        self.summary_display.setMarkdown(full_text)
        self.set_status("Completed")
        self.status_label.setStyleSheet("color: #2ecc71;")
        
        # Update conversation history for potential child nodes.
        self.conversation_history = self.parent_node.conversation_history if self.parent_node else []
        self.conversation_history.append({'role': 'assistant', 'content': full_text})

    def set_error(self, error_message: str):
        """
        Displays an error message in the status and result areas.

        Args:
            error_message (str): The error message to display.
        """
        self.status = f"Error: {error_message}"
        self.status_label.setText(self.status)
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.summary_display.setText(f"An error occurred during the process:\n\n{error_message}")
        
    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        from graphite_node import PluginNodeContextMenu
        menu = PluginNodeContextMenu(self)
        menu.exec(event.screenPos())

    def boundingRect(self):
        """Returns the bounding rectangle of the node, including padding for connection dots."""
        padding = self.CONNECTION_DOT_OFFSET + self.CONNECTION_DOT_RADIUS
        return QRectF(-padding, 0, self.NODE_WIDTH + 2 * padding, self.NODE_HEIGHT)
        
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the node's border, background, and connection dots.

        Args:
            painter (QPainter): The painter to use.
            option (QStyleOptionGraphicsItem): Provides style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        web_color = QColor(palette.FRAME_COLORS["Orange"]["color"])
        pen = QPen(web_color, 1.5)

        if self.isSelected():
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Draw connection dots for linking.
        dot_color = web_color
        if self.isSelected() or self.hovered:
            dot_color = pen.color().lighter(110)
        
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        dot_rect_left = QRectF(-self.CONNECTION_DOT_RADIUS, (self.NODE_HEIGHT / 2) - self.CONNECTION_DOT_RADIUS, self.CONNECTION_DOT_RADIUS * 2, self.CONNECTION_DOT_RADIUS * 2)
        painter.drawPie(dot_rect_left, 90 * 16, -180 * 16)
        
        dot_rect_right = QRectF(self.NODE_WIDTH - self.CONNECTION_DOT_RADIUS, (self.NODE_HEIGHT / 2) - self.CONNECTION_DOT_RADIUS, self.CONNECTION_DOT_RADIUS * 2, self.CONNECTION_DOT_RADIUS * 2)
        painter.drawPie(dot_rect_right, 90 * 16, 180 * 16)
        
    def mousePressEvent(self, event):
        """Handles mouse press to set the current node context and start dragging."""
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
            if hasattr(self.scene(), 'window'):
                self.scene().window.setCurrentNode(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop dragging and clear smart guides."""
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        """
        Handles item changes, applying snapping logic during position changes.

        Args:
            change (QGraphicsItem.GraphicsItemChange): The type of change.
            value: The new value for the changed attribute.

        Returns:
            The modified value or the result of the superclass implementation.
        """
        if change == QGraphicsItem.ItemSceneHasChanged and not self.scene():
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.stop()
                self.worker_thread.quit()
                self.worker_thread.wait()

        if change == QGraphicsItem.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        """Handles hover enter event using the mixin."""
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles hover leave event using the mixin."""
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)