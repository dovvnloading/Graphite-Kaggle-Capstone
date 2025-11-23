from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsProxyWidget, QWidget, QVBoxLayout,
    QTextEdit, QPushButton, QLabel, QHBoxLayout, QProgressBar, QScrollArea,
    QFrame, QSizePolicy
)
from PySide6.QtCore import QRectF, Qt, Signal, QPointF, QSize, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath
import qtawesome as qta
import json
from graphite_config import get_current_palette
from graphite_widgets import HoverAnimationMixin
from graphite_connections import ConnectionItem
from graphite_agents import SynthesisWorkerThread, SynthesisAgent

class OrchestratorStepCard(QFrame):
    """
    A widget representing a single step in the Orchestrator's plan.
    It displays the tool, task, and status, and can expand to show input/output details.
    """
    def __init__(self, step_number, tool_name, task_description, input_data, parent=None):
        super().__init__(parent)
        self.step_number = step_number
        self.tool_name = tool_name
        self.task = task_description
        self.input_data = input_data
        self.output_data = ""
        self.status = "pending" # pending, running, success, error
        self.is_expanded = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            OrchestratorStepCard {
                background-color: #2d2d2d;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
            }
            QLabel { color: #e0e0e0; }
        """)
        
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # --- Header (Always Visible) ---
        header_layout = QHBoxLayout()
        
        # Tool Icon
        icon_label = QLabel()
        icon_name = self._get_tool_icon(self.tool_name)
        icon_color = self._get_tool_color(self.tool_name)
        icon_label.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(20, 20))
        header_layout.addWidget(icon_label)

        # Title
        title_text = f"<b>Step {self.step_number}:</b> {self.tool_name}"
        self.title_label = QLabel(title_text)
        self.title_label.setStyleSheet("font-size: 12px;")
        header_layout.addWidget(self.title_label, stretch=1)

        # Status Icon
        self.status_icon = QLabel()
        self.status_icon.setPixmap(qta.icon('fa5s.circle', color='#555555').pixmap(14, 14))
        header_layout.addWidget(self.status_icon)

        layout.addLayout(header_layout)

        # Task Description
        self.desc_label = QLabel(self.task)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #aaaaaa; font-size: 11px; font-style: italic;")
        layout.addWidget(self.desc_label)

        # --- Details (Expandable) ---
        self.details_widget = QWidget()
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(0, 5, 0, 0)
        details_layout.setSpacing(5)

        # Input
        details_layout.addWidget(QLabel("Input:", styleSheet="font-weight: bold; font-size: 10px; color: #888;"))
        self.input_label = QLabel(str(self.input_data))
        self.input_label.setWordWrap(True)
        self.input_label.setStyleSheet("background-color: #252526; padding: 5px; border-radius: 4px; font-family: Consolas; font-size: 10px; color: #ccc;")
        details_layout.addWidget(self.input_label)

        # Output
        self.output_header = QLabel("Output:", styleSheet="font-weight: bold; font-size: 10px; color: #888;")
        self.output_header.setVisible(False)
        details_layout.addWidget(self.output_header)
        
        self.output_label = QLabel("...")
        self.output_label.setWordWrap(True)
        self.output_label.setStyleSheet("background-color: #252526; padding: 5px; border-radius: 4px; font-family: Consolas; font-size: 10px; color: #2ecc71;")
        self.output_label.setVisible(False)
        details_layout.addWidget(self.output_label)

        self.details_widget.setVisible(False)
        layout.addWidget(self.details_widget)

    def _get_tool_icon(self, name):
        if "Web" in name: return "fa5s.globe-americas"
        if "Py-Coder" in name: return "fa5s.code"
        if "Memory" in name: return "fa5s.database"
        if "Synthesizer" in name: return "fa5s.pencil-ruler"
        return "fa5s.tools"

    def _get_tool_color(self, name):
        palette = get_current_palette()
        if "Web" in name: return palette.FRAME_COLORS["Orange"]["color"]
        if "Py-Coder" in name: return palette.FRAME_COLORS["Purple"]["color"]
        if "Memory" in name: return palette.FRAME_COLORS["Green"]["color"]
        if "Synthesizer" in name: return palette.FRAME_COLORS["Teal"]["color"]
        return "#cccccc"

    def set_status(self, status):
        self.status = status
        if status == "running":
            self.setStyleSheet("OrchestratorStepCard { background-color: #3a3a3a; border: 1px solid #3498db; border-radius: 6px; } QLabel { color: #e0e0e0; }")
            self.status_icon.setPixmap(qta.icon('fa5s.spinner', color='#3498db', animation=qta.Spin(self.status_icon)).pixmap(14, 14))
        elif status == "success":
            self.setStyleSheet("OrchestratorStepCard { background-color: #2d2d2d; border: 1px solid #2ecc71; border-radius: 6px; } QLabel { color: #e0e0e0; }")
            self.status_icon.setPixmap(qta.icon('fa5s.check-circle', color='#2ecc71').pixmap(14, 14))
        elif status == "error":
            self.setStyleSheet("OrchestratorStepCard { background-color: #3a2a2a; border: 1px solid #e74c3c; border-radius: 6px; } QLabel { color: #e0e0e0; }")
            self.status_icon.setPixmap(qta.icon('fa5s.exclamation-circle', color='#e74c3c').pixmap(14, 14))
        else:
            self.setStyleSheet("OrchestratorStepCard { background-color: #2d2d2d; border: 1px solid #3f3f3f; border-radius: 6px; } QLabel { color: #e0e0e0; }")
            self.status_icon.setPixmap(qta.icon('fa5s.circle', color='#555555').pixmap(14, 14))

    def set_output(self, output):
        self.output_data = output
        # Truncate for display if too long
        display_text = output if len(output) < 300 else output[:300] + "... (click to see full content in output node)"
        self.output_label.setText(display_text)
        self.output_header.setVisible(True)
        self.output_label.setVisible(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_details()
        super().mousePressEvent(event)

    def toggle_details(self):
        self.is_expanded = not self.is_expanded
        self.details_widget.setVisible(self.is_expanded)


class OrchestratorNode(QGraphicsObject, HoverAnimationMixin):
    """
    A specialized QGraphicsItem that acts as the "conductor" for a multi-agent workflow.

    This node allows a user to define a high-level goal. It will then generate a plan,
    execute a sequence of tasks by calling other "tool" nodes, and display the
    progress and final results.
    """
    orchestration_requested = Signal(object) 

    NODE_WIDTH = 500
    NODE_HEIGHT = 700
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0

    def __init__(self, parent_node, parent=None):
        """
        Initializes the OrchestratorNode.

        Args:
            parent_node (QGraphicsItem): The node from which this node branches.
            parent (QGraphicsItem, optional): The parent graphics item. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.parent_node = parent_node
        self.children = []
        self.is_user = False
        self.conversation_history = []
        self.goal = ""
        self.plan = ""
        self.step_cards = {} # Map step number to widget

        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False

        self.widget = QWidget()
        self.widget.setFixedSize(self.NODE_WIDTH, self.NODE_HEIGHT)
        self.widget.setStyleSheet("background-color: transparent;")
        
        self._setup_ui()
        
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(self.widget)
        
    @property
    def text(self):
        """Returns the plan and execution log."""
        return self.plan # Return raw plan text for export

    @property
    def width(self):
        return self.NODE_WIDTH

    @property
    def height(self):
        return self.NODE_HEIGHT

    def _setup_ui(self):
        main_layout = QVBoxLayout(self.widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Yellow"]["color"])
        
        # Header
        header_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.sitemap', color=node_color).pixmap(18, 18))
        header_layout.addWidget(icon)
        title_label = QLabel("Agent Orchestrator")
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {node_color.name()};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: #3f3f3f;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {node_color.name()};
                border-radius: 2px;
            }}
        """)
        main_layout.addWidget(self.progress_bar)

        # Goal Input
        main_layout.addWidget(QLabel("High-Level Goal:", styleSheet="font-weight: bold; color: #ccc;"))
        self.goal_input = QTextEdit()
        self.goal_input.setPlaceholderText("e.g., 'Research the current price of Bitcoin, calculate the moving average, and write a summary.'")
        self.goal_input.setFixedHeight(80)
        self.goal_input.textChanged.connect(self._on_goal_changed)
        self.goal_input.setStyleSheet("""
            QTextEdit {
                background-color: #252526; border: 1px solid #3f3f3f;
                color: #cccccc; border-radius: 4px; padding: 5px;
                font-family: Segoe UI, sans-serif;
            }
        """)
        main_layout.addWidget(self.goal_input)

        # Run Button
        self.run_button = QPushButton("Start Orchestration")
        self.run_button.clicked.connect(self._on_run_clicked)
        brightness = (node_color.red() * 299 + node_color.green() * 587 + node_color.blue() * 114) / 1000
        text_color = "black" if brightness > 128 else "white"
        self.run_button.setIcon(qta.icon('fa5s.cogs', color=text_color))
        self.run_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {node_color.name()}; color: {text_color}; border: none;
                border-radius: 4px; padding: 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {node_color.lighter(110).name()}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)
        main_layout.addWidget(self.run_button)
        
        # Status Label
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        main_layout.addWidget(self.status_label)

        # Plan Display (Scroll Area for Step Cards)
        main_layout.addWidget(QLabel("Execution Plan:", styleSheet="font-weight: bold; color: #ccc;"))
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #3f3f3f; background-color: #252526; border-radius: 4px; }")
        
        self.steps_container = QWidget()
        self.steps_container.setStyleSheet("background-color: transparent;")
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(10, 10, 10, 10)
        self.steps_layout.setSpacing(8)
        self.steps_layout.addStretch() # Push items to top
        
        self.scroll_area.setWidget(self.steps_container)
        main_layout.addWidget(self.scroll_area)

    def _on_run_clicked(self):
        """Handles the run button click and emits the orchestration_requested signal."""
        self.orchestration_requested.emit(self)

    def _on_goal_changed(self):
        """Updates the internal goal state when the input text changes."""
        self.goal = self.goal_input.toPlainText()

    def set_running_state(self, is_running: bool):
        """Enables or disables UI elements based on the running state."""
        self.run_button.setEnabled(not is_running)
        self.goal_input.setReadOnly(is_running)
        self.run_button.setText("Processing..." if is_running else "Start Orchestration")
        if is_running:
            self.progress_bar.setValue(0)

    def set_status(self, status_text: str):
        self.status_label.setText(f"Status: {status_text}")
        self.status_label.setStyleSheet("color: #3498db;")

    def set_plan(self, plan_text: str):
        """Parses the JSON plan text and creates visual step cards."""
        if not plan_text:
            return

        self.plan = plan_text
        
        try:
            plan_data = json.loads(plan_text)
            if isinstance(plan_data, list):
                # Recreate the cards from the loaded data
                self.create_step_cards_from_json(plan_data)
        except json.JSONDecodeError:
            # If parsing fails (e.g. legacy text plan), handle gracefully or log
            print("Warning: Could not parse plan text as JSON for visual restoration.")
        except Exception as e:
            print(f"Error setting plan cards: {e}")

    def create_step_cards_from_json(self, plan_list):
        """
        Creates the visual step cards from the parsed JSON plan list.
        Called by the window logic.
        """
        # Update self.plan so it can be properly serialized later
        self.plan = json.dumps(plan_list)

        # Clear existing cards
        while self.steps_layout.count() > 1:
            item = self.steps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.step_cards = {}
        
        self.progress_bar.setMaximum(len(plan_list) + 1) # Steps + Final

        for step in plan_list:
            step_num = step['step']
            card = OrchestratorStepCard(
                step_number=step_num,
                tool_name=step['tool'],
                task_description=step['task'],
                input_data=step['input']
            )
            self.steps_layout.insertWidget(self.steps_layout.count() - 1, card)
            self.step_cards[step_num] = card

    def append_log(self, log_text: str):
        """
        Previously appended to a text box. Now we can perhaps update the status bar
        or just ignore generic logs if we have specific step updates.
        """
        # For now, we can just update the status label with the latest log line
        lines = log_text.strip().split('\n')
        if lines:
            self.set_status(lines[-1][:50] + "...")

    def update_step_output(self, step_num: int, output: str):
        """Updates the specific card with the result."""
        if step_num in self.step_cards:
            card = self.step_cards[step_num]
            card.set_output(output)
            card.set_status("success")
            self.progress_bar.setValue(step_num)

    def set_current_step(self, step_num: int):
        """ highlights the active card. """
        self.set_status(f"Executing step {step_num}...")
        if step_num in self.step_cards:
            self.step_cards[step_num].set_status("running")
            
            # Mark previous as success if not already
            if step_num > 1 and (step_num - 1) in self.step_cards:
                self.step_cards[step_num - 1].set_status("success")

    def set_final_answer(self, result: str):
        self.set_status("Completed Successfully")
        self.status_label.setStyleSheet("color: #2ecc71;")
        self.progress_bar.setValue(self.progress_bar.maximum())
        
        # Ensure all cards are marked success
        for card in self.step_cards.values():
            if card.status != "success":
                card.set_status("success")
        
        self.conversation_history = self.parent_node.conversation_history if self.parent_node else []
        self.conversation_history.append({'role': 'assistant', 'content': result})
        self.set_running_state(False)

    def set_error(self, error_message: str):
        self.status_label.setText(f"Error: {error_message}")
        self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        
        # Find the currently running card and mark it as error
        for card in self.step_cards.values():
            if card.status == "running":
                card.set_status("error")
                card.set_output(f"Error: {error_message}")
                
        self.set_running_state(False)

    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        from graphite_node import PluginNodeContextMenu
        menu = PluginNodeContextMenu(self)
        menu.exec(event.screenPos())

    def boundingRect(self):
        padding = self.CONNECTION_DOT_OFFSET + self.CONNECTION_DOT_RADIUS
        return QRectF(-padding, 0, self.NODE_WIDTH + 2 * padding, self.NODE_HEIGHT)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        node_color = QColor(palette.FRAME_COLORS["Yellow"]["color"])
        pen = QPen(node_color, 1.5)

        if self.isSelected():
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        
        painter.setPen(pen)
        painter.drawPath(path)
        
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
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
            if hasattr(self.scene(), 'window'):
                self.scene().window.setCurrentNode(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)


class MemoryBankNode(QGraphicsObject, HoverAnimationMixin):
    """
    A simple node that acts as a key-value store for an agentic workflow.
    It allows one node to save its output and another to retrieve it, demonstrating
    session memory visually.
    """
    NODE_WIDTH = 350
    NODE_HEIGHT = 400
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0

    def __init__(self, parent_node, parent=None):
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.parent_node = parent_node
        self.children = []
        self.is_user = False
        self.conversation_history = []
        self._memory = {}

        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False

        self.widget = QWidget()
        self.widget.setFixedSize(self.NODE_WIDTH, self.NODE_HEIGHT)
        self.widget.setStyleSheet("background-color: transparent;")
        
        self._setup_ui()
        
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(self.widget)

    @property
    def text(self):
        """Returns the visible content of the memory bank."""
        return self.memory_display.toPlainText()

    @property
    def width(self):
        return self.NODE_WIDTH

    @property
    def height(self):
        return self.NODE_HEIGHT

    def _setup_ui(self):
        main_layout = QVBoxLayout(self.widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Green"]["color"])
        
        header_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.database', color=node_color).pixmap(18, 18))
        header_layout.addWidget(icon)
        title_label = QLabel("Memory Bank")
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {node_color.name()};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        main_layout.addWidget(QLabel("Stored Values:"))
        self.memory_display = QTextEdit()
        self.memory_display.setReadOnly(True)
        self.memory_display.setPlaceholderText("[Empty]")
        main_layout.addWidget(self.memory_display)

        self.memory_display.setStyleSheet("""
            QTextEdit {
                background-color: #252526; border: 1px solid #3f3f3f;
                color: #cccccc; border-radius: 4px; padding: 8px;
                font-family: Consolas, monospace; font-size: 12px;
            }
        """)

    def set_value(self, key: str, value: str):
        """Stores or updates a key-value pair in memory."""
        self._memory[key] = value
        self._update_display()

    def get_value(self, key: str) -> str:
        """Retrieves a value from memory by its key."""
        return self._memory.get(key, "")

    def _update_display(self):
        """Updates the read-only text display to reflect the current memory state without truncation."""
        if not self._memory:
            self.memory_display.clear()
            return

        # Use Markdown to format the memory dump clearly for user inspection
        markdown_content = ""
        for key, value in self._memory.items():
            val_str = str(value)
            # Use bold for key and display full value body
            markdown_content += f"**Key:** `{key}`\n\n"
            markdown_content += f"{val_str}\n\n"
            markdown_content += "---\n\n" # Visual separator
        
        self.memory_display.setMarkdown(markdown_content)
        
    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        from graphite_node import PluginNodeContextMenu
        menu = PluginNodeContextMenu(self)
        menu.exec(event.screenPos())

    def boundingRect(self):
        padding = self.CONNECTION_DOT_OFFSET + self.CONNECTION_DOT_RADIUS
        return QRectF(-padding, 0, self.NODE_WIDTH + 2 * padding, self.NODE_HEIGHT)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        node_color = QColor(palette.FRAME_COLORS["Green"]["color"])
        pen = QPen(node_color, 1.5)

        if self.isSelected():
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        
        painter.setPen(pen)
        painter.drawPath(path)
        
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
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
            if hasattr(self.scene(), 'window'):
                self.scene().window.setCurrentNode(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)

class SynthesisNode(QGraphicsObject, HoverAnimationMixin):
    """
    A node that uses an AI agent to synthesize, summarize, or reformat text based
    on a given instruction and source text. This is a key tool for the Orchestrator.
    """
    NODE_WIDTH = 500
    NODE_HEIGHT = 550
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0

    def __init__(self, parent_node, parent=None):
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.parent_node = parent_node
        self.children = []
        self.is_user = False
        self.conversation_history = []
        self.worker_thread = None

        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False

        self.widget = QWidget()
        self.widget.setFixedSize(self.NODE_WIDTH, self.NODE_HEIGHT)
        self.widget.setStyleSheet("background-color: transparent;")
        
        self._setup_ui()
        
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(self.widget)
        
    @property
    def text(self):
        """Returns the synthesized output text."""
        return self.output_display.toPlainText()

    @property
    def width(self):
        return self.NODE_WIDTH

    @property
    def height(self):
        return self.NODE_HEIGHT

    def _setup_ui(self):
        main_layout = QVBoxLayout(self.widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Teal"]["color"])
        
        header_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.pencil-ruler', color=node_color).pixmap(18, 18))
        header_layout.addWidget(icon)
        title_label = QLabel("Text Synthesizer")
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {node_color.name()};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        main_layout.addWidget(QLabel("Instruction & Source Text:"))
        self.instruction_input = QTextEdit()
        self.instruction_input.setPlaceholderText("Enter instructions and the text to process. For example: 'Summarize the following report: ...'")
        main_layout.addWidget(self.instruction_input)
        
        main_layout.addWidget(QLabel("Synthesized Output:"))
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        main_layout.addWidget(self.output_display)

        for widget in [self.instruction_input, self.output_display]:
            widget.setStyleSheet("""
                QTextEdit {
                    background-color: #252526; border: 1px solid #3f3f3f;
                    color: #cccccc; border-radius: 4px; padding: 5px;
                    font-family: Segoe UI, sans-serif;
                }
            """)

    def run_as_tool(self, input_data: str):
        """Programmatic entry point for the Orchestrator."""
        self.instruction_input.setText(input_data)
        
        self.worker_thread = SynthesisWorkerThread(SynthesisAgent(), input_data, self)
        return self.worker_thread

    def set_output(self, text: str):
        """Displays the result from the SynthesisAgent."""
        self.output_display.setMarkdown(text)
        self.conversation_history = self.parent_node.conversation_history if self.parent_node else []
        self.conversation_history.append({'role': 'assistant', 'content': text})
        
    def set_error(self, error_message: str):
        self.output_display.setMarkdown(f"### Error\n\nAn error occurred during synthesis:\n\n```\n{error_message}\n```")
        
    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        from graphite_node import PluginNodeContextMenu
        menu = PluginNodeContextMenu(self)
        menu.exec(event.screenPos())

    def boundingRect(self):
        padding = self.CONNECTION_DOT_OFFSET + self.CONNECTION_DOT_RADIUS
        return QRectF(-padding, 0, self.NODE_WIDTH + 2 * padding, self.NODE_HEIGHT)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        node_color = QColor(palette.FRAME_COLORS["Teal"]["color"])
        pen = QPen(node_color, 1.5)

        if self.isSelected():
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        
        painter.setPen(pen)
        painter.drawPath(path)
        
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
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
            if hasattr(self.scene(), 'window'):
                self.scene().window.setCurrentNode(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)