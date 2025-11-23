from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsProxyWidget, QWidget, QVBoxLayout,
    QTextEdit, QPushButton, QLabel, QHBoxLayout, QSlider
)
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath
import qtawesome as qta
from graphite_config import get_current_palette
from graphite_widgets import HoverAnimationMixin

class ReasoningNode(QGraphicsObject, HoverAnimationMixin):
    """
    A specialized QGraphicsItem that provides a UI for a multi-step, iterative
    reasoning process to solve complex problems.

    This node allows the user to input a prompt, set a "thinking budget" (number of
    reasoning steps), and view the AI's thought process as it generates a plan,
    executes steps, critiques its own thoughts, and finally synthesizes an answer.
    """
    reasoning_requested = Signal(object) # Emits self when the run button is clicked

    NODE_WIDTH = 550
    NODE_HEIGHT = 700
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0

    def __init__(self, parent_node, parent=None):
        """
        Initializes the ReasoningNode.

        Args:
            parent_node (QGraphicsItem): The node from which this node branches.
            parent (QGraphicsItem, optional): The parent graphics item. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.parent_node = parent_node
        self.children = []
        self.is_user = False # Considered an AI-generated node.
        self.conversation_history = []

        # State attributes for the reasoning process.
        self.prompt = ""
        self.thinking_budget = 3 # Default number of reasoning steps.
        self.status = "Idle"
        self.thought_process = ""

        # Standard graphics item setup.
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False

        # Use a QGraphicsProxyWidget to embed standard widgets.
        self.widget = QWidget()
        self.widget.setFixedSize(self.NODE_WIDTH, self.NODE_HEIGHT)
        self.widget.setStyleSheet("background-color: transparent;")
        
        self._setup_ui()
        
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(self.widget)
    
    @property
    def text(self):
        """Returns the entire thought process and reasoning trace."""
        return self.thought_process

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
        node_color = QColor(palette.FRAME_COLORS["Blue"]["color"])
        
        # --- Header Section ---
        header_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.brain', color=node_color).pixmap(18, 18))
        header_layout.addWidget(icon)
        title_label = QLabel("Graphite-Reasoning")
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {node_color.name()};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # --- Prompt Input Section ---
        main_layout.addWidget(QLabel("Complex Prompt:"))
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Enter a complex problem or question that requires deep reasoning...")
        self.prompt_input.setFixedHeight(100)
        self.prompt_input.textChanged.connect(self._on_prompt_changed)
        main_layout.addWidget(self.prompt_input)

        # --- Thinking Budget Control ---
        budget_layout = QHBoxLayout()
        budget_layout.addWidget(QLabel("Thinking Budget:"))
        self.budget_slider = QSlider(Qt.Orientation.Horizontal)
        self.budget_slider.setMinimum(1)
        self.budget_slider.setMaximum(10)
        self.budget_slider.setValue(self.thinking_budget)
        self.budget_slider.setTickInterval(1)
        self.budget_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.budget_slider.valueChanged.connect(self._on_budget_changed)
        budget_layout.addWidget(self.budget_slider)
        self.budget_label = QLabel(str(self.thinking_budget))
        self.budget_label.setFixedWidth(25)
        budget_layout.addWidget(self.budget_label)
        main_layout.addLayout(budget_layout)

        # --- Run Button ---
        self.run_button = QPushButton("Start Reasoning")
        self.run_button.clicked.connect(lambda: self.reasoning_requested.emit(self))
        main_layout.addWidget(self.run_button)
        
        # --- Status Label ---
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        main_layout.addWidget(self.status_label)

        # --- Thought Process Display ---
        main_layout.addWidget(QLabel("Thought Process:"))
        self.thought_process_display = QTextEdit()
        self.thought_process_display.setReadOnly(True)
        self.thought_process_display.setPlaceholderText("The AI's step-by-step reasoning will appear here...")
        main_layout.addWidget(self.thought_process_display)

        # --- Apply Common Styles ---
        for widget in [self.prompt_input, self.thought_process_display]:
            widget.setStyleSheet("""
                QTextEdit {
                    background-color: #252526; border: 1px solid #3f3f3f;
                    color: #cccccc; border-radius: 4px; padding: 5px;
                    font-family: Segoe UI, sans-serif;
                }
            """)
        
        # Style the run button with a contrasting text color.
        brightness = (node_color.red() * 299 + node_color.green() * 587 + node_color.blue() * 114) / 1000
        text_color = "black" if brightness > 128 else "white"
        
        self.run_button.setIcon(qta.icon('fa5s.cogs', color=text_color))
        self.run_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {node_color.name()}; color: {text_color}; border: none;
                border-radius: 4px; padding: 8px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {node_color.lighter(110).name()}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)

    def _on_prompt_changed(self):
        """Updates the internal prompt state when the input text changes."""
        self.prompt = self.prompt_input.toPlainText()

    def _on_budget_changed(self, value):
        """Updates the thinking budget when the slider value changes."""
        self.thinking_budget = value
        self.budget_label.setText(str(value))

    def set_running_state(self, is_running: bool):
        """
        Enables or disables UI elements based on the reasoning process state.

        Args:
            is_running (bool): True if the process is active, False otherwise.
        """
        self.run_button.setEnabled(not is_running)
        self.prompt_input.setReadOnly(is_running)
        self.budget_slider.setEnabled(not is_running)
        self.run_button.setText("Reasoning..." if is_running else "Start Reasoning")
        if is_running:
            self.set_status("Thinking...")
        else:
            self.set_status("Completed")

    def set_status(self, status_text: str):
        """
        Updates the status label with feedback on the current step.

        Args:
            status_text (str): The new status message.
        """
        self.status = status_text
        self.status_label.setText(f"Status: {status_text}")
        if "Thinking" in status_text or "Step" in status_text:
            self.status_label.setStyleSheet("color: #3498db;")
        elif "Completed" in status_text:
            self.status_label.setStyleSheet("color: #2ecc71;")
        else:
            self.status_label.setStyleSheet("color: #888;")

    def clear_thoughts(self):
        """Clears the thought process display area."""
        self.thought_process = ""
        self.thought_process_display.clear()
        
    def append_thought(self, step_title: str, thought_text: str):
        """
        Appends a new step to the thought process display.

        Args:
            step_title (str): The title of the reasoning step (e.g., "The Plan").
            thought_text (str): The detailed text of the thought for this step.
        """
        formatted_step = f"## {step_title}\n\n{thought_text}\n\n---\n\n"
        self.thought_process += formatted_step
        self.thought_process_display.setMarkdown(self.thought_process)
        # Automatically scroll to the bottom to show the latest step.
        scrollbar = self.thought_process_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def set_final_answer(self, final_text: str):
        """
        Displays the final synthesized answer and updates conversation history.

        Args:
            final_text (str): The final answer from the reasoning agent.
        """
        # The final answer becomes the conversational context for any child nodes.
        self.conversation_history = self.parent_node.conversation_history if self.parent_node else []
        self.conversation_history.append({'role': 'assistant', 'content': final_text})
        self.append_thought("Final Answer", final_text)
        self.set_status("Completed")

    def set_error(self, error_message: str):
        """
        Displays an error message in the status and thought process areas.

        Args:
            error_message (str): The error message to display.
        """
        self.status = f"Error: {error_message}"
        self.status_label.setText(self.status)
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.append_thought("Error", f"An error occurred during the process:\n\n{error_message}")
        self.set_running_state(False)
        
    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        from graphite_node import PluginNodeContextMenu
        menu = PluginNodeContextMenu(self)
        menu.exec(event.screenPos())

    def boundingRect(self):
        """Returns the bounding rectangle of the node."""
        padding = self.CONNECTION_DOT_OFFSET + self.CONNECTION_DOT_RADIUS
        return QRectF(-padding, 0, self.NODE_WIDTH + 2 * padding, self.NODE_HEIGHT)

    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the node's border, background, and connection dots.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        node_color = QColor(palette.FRAME_COLORS["Blue"]["color"])
        pen = QPen(node_color, 1.5)

        if self.isSelected():
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Draw connection dots.
        dot_color = node_color
        if self.isSelected() or self.hovered:
            dot_color = pen.color().lighter(110)
        
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        dot_rect_left = QRectF(-self.CONNECTION_DOT_RADIUS, (self.NODE_HEIGHT / 2) - self.CONNECTION_DOT_RADIUS, self.CONNECTION_DOT_RADIUS * 2, self.CONNECTION_DOT_RADIUS * 2)
        painter.drawPie(dot_rect_left, 90 * 16, -180 * 16)
        
        dot_rect_right = QRectF(self.NODE_WIDTH - self.CONNECTION_DOT_RADIUS, (self.NODE_HEIGHT / 2) - self.CONNECTION_DOT_RADIUS, self.CONNECTION_DOT_RADIUS * 2, self.CONNECTION_DOT_RADIUS * 2)
        painter.drawPie(dot_rect_right, 90 * 16, 180 * 16)

    def mousePressEvent(self, event):
        """Handles mouse press to set the current context and initiate dragging."""
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
            if hasattr(self.scene(), 'window'):
                self.scene().window.setCurrentNode(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop dragging."""
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        """Handles item changes, applying snapping logic during movement."""
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged and self.scene():
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