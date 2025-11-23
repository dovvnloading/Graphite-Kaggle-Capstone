from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsProxyWidget, QWidget, QVBoxLayout,
    QTextEdit, QPushButton, QLabel, QFrame, QHBoxLayout
)
from PySide6.QtCore import QRectF, Qt, Property, QPropertyAnimation, QEasingCurve, QPointF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QIcon, QGuiApplication
import qtawesome as qta
from graphite_config import get_current_palette
from enum import Enum
from graphite_widgets import HoverAnimationMixin


class PyCoderMode(Enum):
    AI_DRIVEN = 1
    MANUAL = 2


class PyCoderStage(Enum):
    """
    Defines the distinct stages of the AI-driven PyCoder workflow.
    Used to update the status tracker UI in the PyCoderNode.
    """
    ANALYZE = 1
    GENERATE = 2
    EXECUTE = 3
    REPAIR = 3  # Merged with Execute for UI simplicity
    ANALYZE_RESULT = 4

class PyCoderStatus(Enum):
    """
    Defines the possible statuses for each stage in the PyCoder workflow.
    Used to control the appearance of the status icons in the PyCoderNode.
    """
    PENDING = 1
    RUNNING = 2
    SUCCESS = 3
    FAILURE = 4


class StatusIconWidget(QWidget):
    """A custom-painted widget for displaying crisp, vector-based status icons."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self._status = PyCoderStatus.PENDING
        self._angle = 0

        self.animation = QPropertyAnimation(self, b"angle")
        self.animation.setStartValue(0)
        self.animation.setEndValue(360)
        self.animation.setDuration(1200)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)

    def set_status(self, status):
        if self._status != status:
            self._status = status
            if self._status == PyCoderStatus.RUNNING:
                self.animation.start()
            else:
                self.animation.stop()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        palette = get_current_palette()

        if self._status == PyCoderStatus.PENDING:
            painter.setPen(QPen(QColor("#555555"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
        elif self._status == PyCoderStatus.RUNNING:
            pen = QPen(palette.AI_NODE, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, int(self._angle * 16), int(270 * 16))
        elif self._status == PyCoderStatus.SUCCESS:
            painter.setPen(QPen(palette.USER_NODE, 2))
            painter.setBrush(palette.USER_NODE)
            painter.drawEllipse(rect)
            
            check_path = QPainterPath()
            check_path.moveTo(rect.center().x() - 4, rect.center().y())
            check_path.lineTo(rect.center().x() - 1, rect.center().y() + 3)
            check_path.lineTo(rect.center().x() + 4, rect.center().y() - 2)
            
            pen = QPen(QColor("white"), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(check_path)
        elif self._status == PyCoderStatus.FAILURE:
            painter.setPen(QPen(QColor("#e74c3c"), 2))
            painter.setBrush(QColor("#e74c3c"))
            painter.drawEllipse(rect)

            pen = QPen(QColor("white"), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            center = rect.center()
            painter.drawLine(center.x() - 3, center.y() - 3, center.x() + 3, center.y() + 3)
            painter.drawLine(center.x() - 3, center.y() + 3, center.x() + 3, center.y() - 3)

    @Property(int)
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, value):
        self._angle = value
        self.update()


class StatusItemWidget(QWidget):
    """A widget representing a single step in the status tracker checklist."""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.icon_widget = StatusIconWidget()
        self.text_label = QLabel(text)
        self.text_label.setStyleSheet("color: #888888;")

        layout.addWidget(self.icon_widget)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self.set_status(PyCoderStatus.PENDING)

    def set_status(self, status):
        self.icon_widget.set_status(status)
        palette = get_current_palette()
        if status == PyCoderStatus.PENDING:
            self.text_label.setStyleSheet("color: #888888; font-style: italic;")
        elif status == PyCoderStatus.RUNNING:
            self.text_label.setStyleSheet(f"color: {palette.AI_NODE.name()}; font-style: normal;")
        elif status == PyCoderStatus.SUCCESS:
            self.text_label.setStyleSheet(f"color: {palette.USER_NODE.name()}; font-style: normal;")
        elif status == PyCoderStatus.FAILURE:
            self.text_label.setStyleSheet("color: #e74c3c; font-style: normal; font-weight: bold;")

class StatusTrackerWidget(QWidget):
    """The checklist widget that holds multiple StatusItemWidgets."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stages = {
            PyCoderStage.ANALYZE: StatusItemWidget("Analyze Prompt"),
            PyCoderStage.GENERATE: StatusItemWidget("Generate Code"),
            PyCoderStage.EXECUTE: StatusItemWidget("Execute & Repair"),
            PyCoderStage.ANALYZE_RESULT: StatusItemWidget("Final Analysis")
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)

        for stage_widget in self.stages.values():
            layout.addWidget(stage_widget)
            
        self.setStyleSheet("background-color: #252526; border-radius: 4px;")
        
    def update_status(self, stage, status):
        if stage in self.stages:
            self.stages[stage].set_status(status)

    def reset_statuses(self):
        for stage_widget in self.stages.values():
            stage_widget.set_status(PyCoderStatus.PENDING)

class PyCoderNode(QGraphicsItem, HoverAnimationMixin):
    """
    A specialized QGraphicsItem that provides a UI for both AI-driven code generation
    and manual code execution.
    """
    NODE_WIDTH = 500
    NODE_HEIGHT = 780
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0

    def __init__(self, parent_node, mode=PyCoderMode.AI_DRIVEN, parent=None):
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.parent_node = parent_node
        self.mode = mode
        self.children = []
        self.conversation_history = []
        self.is_user = False
        self.worker_thread = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False

        self.widget = QWidget()
        self.widget.setFixedSize(self.NODE_WIDTH, self.NODE_HEIGHT)
        self.widget.setStyleSheet("""
            QWidget {
                background-color: transparent;
                color: #e0e0e0;
                font-family: Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace;
            }
        """)

        self._setup_ui()

        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(self.widget)

        self._update_ui_for_mode()
        
    @property
    def text(self):
        """Returns the primary content of the node for chart generation and copying."""
        code = self.get_code()
        output = self.output_display.toPlainText()
        analysis = self.ai_analysis_display.toPlainText()
        
        content = []
        if analysis:
            content.append(f"--- Analysis ---\n{analysis}")
        if code:
            content.append(f"--- Code ---\n{code}")
        if output:
            content.append(f"--- Output ---\n{output}")
            
        return "\n\n".join(content)

    @property
    def width(self):
        return self.NODE_WIDTH

    @property
    def height(self):
        return self.NODE_HEIGHT

    def _setup_ui(self):
        main_layout = QVBoxLayout(self.widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        palette = get_current_palette()
        pycoder_color = QColor(palette.FRAME_COLORS["Purple Header"]["color"])

        # --- Header ---
        header_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.code', color=pycoder_color).pixmap(18, 18))
        header_layout.addWidget(icon)
        self.title_label = QLabel("Py-Coder (AI-Driven)")
        self.title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {pycoder_color.name()};")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.mode_toggle_button = QPushButton()
        self.mode_toggle_button.setFixedSize(28, 28)
        self.mode_toggle_button.clicked.connect(self._toggle_mode)
        self.mode_toggle_button.setStyleSheet("""
            QPushButton { border: 1px solid #555; border-radius: 14px; }
            QPushButton:hover { background-color: #4f4f4f; }
        """)
        header_layout.addWidget(self.mode_toggle_button)
        main_layout.addLayout(header_layout)

        # --- AI-Driven Widgets ---
        self.ai_driven_widgets = []
        self.ai_prompt_label = QLabel("Prompt:")
        main_layout.addWidget(self.ai_prompt_label)
        self.ai_driven_widgets.append(self.ai_prompt_label)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("e.g., 'Calculate the factorial of 15 and explain the result.'")
        self.prompt_input.setFixedHeight(60)
        self.prompt_input.setStyleSheet("QTextEdit { background-color: #252526; border: 1px solid #3f3f3f; border-radius: 4px; padding: 5px; }")
        main_layout.addWidget(self.prompt_input)
        self.ai_driven_widgets.append(self.prompt_input)
        
        self.generate_button = QPushButton("Generate & Execute")
        self.generate_button.clicked.connect(self._on_run_clicked)
        main_layout.addWidget(self.generate_button)
        self.ai_driven_widgets.append(self.generate_button)

        # --- Manual Widgets ---
        self.manual_widgets = []
        self.manual_code_label = QLabel("Manual Code Input:")
        main_layout.addWidget(self.manual_code_label)
        self.manual_widgets.append(self.manual_code_label)

        self.code_input = QTextEdit()
        self.code_input.setPlaceholderText("Enter Python code to execute...")
        self.code_input.setFixedHeight(120)
        main_layout.addWidget(self.code_input)
        self.manual_widgets.append(self.code_input)

        self.run_button = QPushButton("Run Code")
        self.run_button.clicked.connect(self._on_run_clicked)
        main_layout.addWidget(self.run_button)
        self.manual_widgets.append(self.run_button)

        # --- Shared Widgets (Code, Output, Analysis) ---
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(line)

        self.status_tracker = StatusTrackerWidget()
        main_layout.addWidget(self.status_tracker)

        generated_code_header_layout = QHBoxLayout()
        generated_code_header_layout.addWidget(QLabel("Generated Code:"))
        generated_code_header_layout.addStretch()
        self.copy_code_button = QPushButton()
        self.copy_code_button.setIcon(qta.icon('fa5s.copy', color='#ccc'))
        self.copy_code_button.setFixedSize(24, 24)
        self.copy_code_button.setToolTip("Copy Generated Code")
        self.copy_code_button.setStyleSheet("""
            QPushButton { border: 1px solid #444; border-radius: 4px; }
            QPushButton:hover { background-color: #4f4f4f; }
        """)
        self.copy_code_button.clicked.connect(self._copy_generated_code)
        generated_code_header_layout.addWidget(self.copy_code_button)
        main_layout.addLayout(generated_code_header_layout)
        
        self.generated_code_display = QTextEdit()
        self.generated_code_display.setReadOnly(True)
        self.generated_code_display.setPlaceholderText("Generated code will appear here...")
        main_layout.addWidget(self.generated_code_display)
        
        main_layout.addWidget(QLabel("Execution Output / Stderr:"))
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setPlaceholderText("Code output will appear here...")
        main_layout.addWidget(self.output_display)

        main_layout.addWidget(QLabel("AI Analysis:"))
        self.ai_analysis_display = QTextEdit()
        self.ai_analysis_display.setReadOnly(True)
        self.ai_analysis_display.setPlaceholderText("AI will analyze the output here...")
        main_layout.addWidget(self.ai_analysis_display)
        
        # Apply common styles
        for widget in [self.code_input, self.generated_code_display, self.output_display, self.ai_analysis_display]:
            widget.setStyleSheet("""
                QTextEdit {
                    background-color: #1e1e1e;
                    border: 1px solid #3f3f3f;
                    color: #cccccc;
                    border-radius: 4px;
                    padding: 5px;
                }
            """)
            
        selection_color = palette.SELECTION
        brightness = (selection_color.red() * 299 + selection_color.green() * 587 + selection_color.blue() * 114) / 1000
        text_color = "black" if brightness > 128 else "white"

        self.generate_button.setIcon(qta.icon('fa5s.cogs', color=text_color))
        self.run_button.setIcon(qta.icon('fa5s.play', color=text_color))

        for btn in [self.generate_button, self.run_button]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {selection_color.name()};
                    color: {text_color};
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {selection_color.lighter(110).name()}; }}
                QPushButton:disabled {{ background-color: #555; }}
            """)

    def _copy_generated_code(self):
        """Copies the text from the generated code display to the clipboard."""
        QGuiApplication.clipboard().setText(self.generated_code_display.toPlainText())

    def _toggle_mode(self):
        if self.mode == PyCoderMode.AI_DRIVEN:
            self.mode = PyCoderMode.MANUAL
        else:
            self.mode = PyCoderMode.AI_DRIVEN
        self._update_ui_for_mode()
    
    def _update_ui_for_mode(self):
        is_ai_mode = self.mode == PyCoderMode.AI_DRIVEN

        for widget in self.ai_driven_widgets:
            widget.setVisible(is_ai_mode)
        for widget in self.manual_widgets:
            widget.setVisible(not is_ai_mode)
            
        self.status_tracker.setVisible(is_ai_mode)

        if is_ai_mode:
            self.title_label.setText("Py-Coder (AI-Driven)")
            self.mode_toggle_button.setIcon(qta.icon('fa5s.user-edit', color='#ccc'))
            self.mode_toggle_button.setToolTip("Switch to Manual Mode")
            self.generated_code_display.setReadOnly(True)
        else:
            self.title_label.setText("Py-Coder (Manual)")
            self.mode_toggle_button.setIcon(qta.icon('fa5s.robot', color='#ccc'))
            self.mode_toggle_button.setToolTip("Switch to AI-Driven Mode")
            self.generated_code_display.setReadOnly(False) 

        self.code_input.setVisible(not is_ai_mode)
        self.manual_code_label.setVisible(not is_ai_mode)
        self.run_button.setVisible(not is_ai_mode)
        
        self.output_display.setReadOnly(is_ai_mode)
        self.ai_analysis_display.setReadOnly(is_ai_mode)

    def _on_run_clicked(self):
        """Handler for when either 'Run' or 'Generate & Execute' is clicked."""
        if self.mode == PyCoderMode.AI_DRIVEN:
            input_data = self.get_prompt()
        else:
            input_data = self.get_code()
        
        if not input_data.strip():
            if self.mode == PyCoderMode.AI_DRIVEN:
                self.set_ai_analysis("Please enter a prompt.")
            else:
                self.set_output("[No code to run]")
            return
            
        worker = self.run_as_tool(input_data)
        worker.start()

    def run_as_tool(self, input_data: str):
        """
        Programmatic entry point for the Orchestrator.
        It configures and returns a worker thread for the current mode.
        """
        from graphite_agents import CodeExecutionWorker, PyCoderExecutionWorker, PyCoderAgentWorker
        
        self.set_running_state(True)
        
        if self.mode == PyCoderMode.MANUAL:
            self.set_code(input_data)
            worker = CodeExecutionWorker(input_data, self)
            self.worker_thread = worker

        elif self.mode == PyCoderMode.AI_DRIVEN:
            self.prompt_input.setText(input_data)
            self.reset_statuses()
            self.set_code("")
            self.set_output("")
            self.set_ai_analysis("")
            
            from graphite_node import CodeNode
            context_node = self.parent_node
            if isinstance(context_node, CodeNode): 
                context_node = context_node.parent_content_node
            history = context_node.conversation_history if context_node and hasattr(context_node, 'conversation_history') else []

            worker = PyCoderExecutionWorker(input_data, history, self)
            worker.log_update.connect(self.update_status)
            worker.retry_feedback.connect(self.handle_retry_feedback) # Connect feedback signal
            self.worker_thread = worker
            
        return self.worker_thread

    def _handle_manual_execution_result(self, output: str):
        """Called when manual code execution finishes."""
        self.set_output(output)
        self.set_running_state(False)
        self.conversation_history = self.parent_node.conversation_history if self.parent_node else []
        self.conversation_history.append({'role': 'assistant', 'content': f"Executed code and got output:\n{output}"})

    def _handle_ai_execution_result(self, result: dict):
        """Called when the full AI-driven execution pipeline finishes."""
        analysis_text = result.get('analysis', '')
        parent_history = self.parent_node.conversation_history if self.parent_node else []
        self.conversation_history = parent_history + [{'role': 'assistant', 'content': analysis_text}]

        self.set_code(result.get('code', ''))
        self.set_output(result.get('output', ''))
        self.set_ai_analysis(analysis_text)
        self.set_running_state(False)

    def _handle_error(self, error_message: str):
        """Called if any worker thread emits an error."""
        self.set_ai_analysis(f"An error occurred: {error_message}")
        self.set_running_state(False)

    def handle_retry_feedback(self, message: str):
        """Appends retry status messages to the output display."""
        current_text = self.output_display.toPlainText()
        self.output_display.setText(current_text + message)
        # Auto-scroll to bottom
        scrollbar = self.output_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
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
        
        pycoder_color = QColor(palette.FRAME_COLORS["Purple Header"]["color"])
        pen = QPen(pycoder_color, 1.5)

        if self.isSelected():
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Draw connection dots
        dot_color = pycoder_color
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
        if change == QGraphicsItem.ItemSceneHasChanged and not self.scene():
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.quit()
                self.worker_thread.wait()

        if change == QGraphicsItem.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)

    def get_prompt(self):
        return self.prompt_input.toPlainText()

    def get_code(self):
        if self.mode == PyCoderMode.AI_DRIVEN:
            return self.generated_code_display.toPlainText()
        return self.code_input.toPlainText()

    def set_code(self, text):
        self.generated_code_display.setText(text)
        self.code_input.setText(text)

    def set_output(self, text):
        self.output_display.setText(text)

    def set_ai_analysis(self, text):
        self.ai_analysis_display.setText(text)
        
    def set_error(self, error_message: str):
        self.ai_analysis_display.setHtml(f'<p style="color: #e74c3c; font-weight: bold;">An error occurred:</p><pre style="color: #cccccc; white-space: pre-wrap;">{error_message}</pre>')

    def update_status(self, stage, status):
        self.status_tracker.update_status(stage, status)

    def reset_statuses(self):
        self.status_tracker.reset_statuses()

    def set_running_state(self, is_running):
        self.run_button.setEnabled(not is_running)
        self.generate_button.setEnabled(not is_running)
        self.code_input.setReadOnly(is_running)
        self.prompt_input.setReadOnly(is_running)
        
        if is_running:
            self.run_button.setText("Executing...")
            self.generate_button.setText("Processing...")
        else:
            self.run_button.setText("Run Code")
            self.generate_button.setText("Generate & Execute")