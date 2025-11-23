from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsProxyWidget, QWidget, QVBoxLayout,
    QLineEdit, QPushButton, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene
)
from PySide6.QtCore import QTimer, Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QTextDocument
import qtawesome as qta
import markdown
from graphite_config import get_current_palette
from graphite_widgets import HoverAnimationMixin

class ChatMessageBubbleItem(QGraphicsObject):
    """
    A QGraphicsObject that represents a single chat bubble within a ConversationNode.
    It handles rendering of Markdown-formatted text with a distinct background
    for user and AI messages.
    """
    PADDING = 10

    def __init__(self, text, is_user, parent=None):
        """
        Initializes the ChatMessageBubbleItem.

        Args:
            text (str): The raw Markdown text of the message.
            is_user (bool): True if the message is from the user, False otherwise.
            parent (QGraphicsItem, optional): The parent graphics item. Defaults to None.
        """
        super().__init__(parent)
        self.raw_text = text
        self.is_user = is_user
        self.is_search_match = False
        
        # Use a QTextDocument for rich text rendering (Markdown support).
        self.document = QTextDocument()
        
        # Basic stylesheet for the text content within the bubble.
        stylesheet = """
            p, ul, ol, li, blockquote {{ color: #e0e0e0; margin: 0; }}
            pre {{ background-color: #1e1e1e; padding: 8px; border-radius: 4px; white-space: pre-wrap; font-family: Consolas, monospace; }}
            a {{ color: #3498db; }}
        """
        self.document.setDefaultStyleSheet(stylesheet)
        
        # Convert Markdown to HTML and set it as the document's content.
        html_content = markdown.markdown(text, extensions=['fenced_code', 'tables'])
        self.document.setHtml(html_content)

        # Define max bubble and text widths
        MAX_BUBBLE_WIDTH = (ConversationNode.NODE_WIDTH - 80) * 0.75
        MAX_TEXT_WIDTH = MAX_BUBBLE_WIDTH - (2 * self.PADDING)

        # Determine the ideal width of the content
        ideal_text_width = self.document.idealWidth()

        # Clamp the text width to the maximum allowed
        final_text_width = min(ideal_text_width, MAX_TEXT_WIDTH)

        # Set the document's width, forcing it to wrap if necessary
        self.document.setTextWidth(final_text_width)

        # Now that the width is constrained, calculate the final bubble geometry
        # document.size().width() should now be equal to final_text_width
        self.width = self.document.size().width() + (2 * self.PADDING)
        self.height = self.document.size().height() + (2 * self.PADDING)

    def boundingRect(self):
        """
        Returns the bounding rectangle of the chat bubble.

        Returns:
            QRectF: The bounding rectangle.
        """
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the chat bubble's background and content.

        Args:
            painter (QPainter): The painter to use for drawing.
            option (QStyleOptionGraphicsItem): Provides style information.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(self.boundingRect(), 10, 10)
        
        # Use a neutral, subtle color scheme for bubbles, different for user and AI.
        user_bubble_color = QColor("#4f4f4f")
        ai_bubble_color = QColor("#3a3a3a")
        
        painter.setBrush(user_bubble_color if self.is_user else ai_bubble_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # Draw a highlight border if this bubble is a search match.
        if self.is_search_match:
            highlight_pen = QPen(QColor("#FFD700"), 2.5)
            highlight_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            
        # Draw the rich text content from the QTextDocument.
        painter.save()
        painter.translate(self.PADDING, self.PADDING)
        self.document.drawContents(painter)
        painter.restore()

class ConversationNode(QGraphicsObject, HoverAnimationMixin):
    """
    A self-contained node for linear, chat-style conversations on the canvas.
    It embeds its own QGraphicsView and QGraphicsScene to display individual
    message bubbles, providing a focused chat interface within the larger graph.
    """
    # Signal emitted when the user sends a message, requesting an AI response.
    ai_request_sent = Signal(object, list) # Emits self and the conversation history.

    # Node dimensions and connection dot properties.
    NODE_WIDTH = 550
    NODE_HEIGHT = 600
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0

    def __init__(self, parent_node, parent=None):
        """
        Initializes the ConversationNode.

        Args:
            parent_node (QGraphicsItem): The node from which this node branches.
            parent (QGraphicsItem, optional): The parent graphics item. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.parent_node = parent_node
        self.children = []
        self.conversation_history = [] # Stores the message history for this node.
        self.is_user = False # Considered an AI-generated node for history purposes.

        # Standard graphics item setup.
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False

        # Use a QGraphicsProxyWidget to embed standard Qt widgets.
        self.widget = QWidget()
        self.widget.setFixedSize(self.NODE_WIDTH, self.NODE_HEIGHT)
        self.widget.setStyleSheet("background-color: transparent;")

        # Internal state for managing message bubble layout.
        self._message_items = []
        self._next_message_y = 10

        self._setup_ui()

        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(self.widget)
        
    @property
    def text(self):
        """Returns the full transcript of the conversation."""
        transcript = []
        for msg in self.conversation_history:
            role = msg['role'].capitalize()
            content = msg['content']
            transcript.append(f"**{role}:** {content}")
        return "\n\n".join(transcript)

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
        node_color = QColor(palette.FRAME_COLORS["Purple"]["color"])

        # --- Header Section ---
        header_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(qta.icon('fa5s.comments', color=node_color).pixmap(18, 18))
        header_layout.addWidget(icon)
        title_label = QLabel("Conversation")
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {node_color.name()};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # --- Internal Scene and View for Chat Bubbles ---
        self.internal_scene = QGraphicsScene()
        self.internal_view = QGraphicsView(self.internal_scene)
        self.internal_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.internal_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.internal_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.internal_view.setStyleSheet("background-color: #252526; border: 1px solid #3f3f3f; border-radius: 4px;")
        main_layout.addWidget(self.internal_view)

        # --- Message Input Section ---
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.returnPressed.connect(self.send_message)
        
        self.send_button = QPushButton()
        self.send_button.setFixedSize(36, 36)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

        self.send_button.clicked.connect(self.send_message)
        self._update_button_style()

    def _update_button_style(self):
        """Applies theme-aware styling to the send button."""
        palette = get_current_palette()
        bg_color = palette.SELECTION
        # Determine icon color based on background brightness for contrast.
        brightness = (bg_color.red() * 299 + bg_color.green() * 587 + bg_color.blue() * 114) / 1000
        icon_color = "black" if brightness > 128 else "white"

        self.send_button.setIcon(qta.icon('fa5s.paper-plane', color=icon_color))
        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color.name()}; border: none; border-radius: 18px;
            }}
            QPushButton:hover {{ background-color: {bg_color.lighter(110).name()}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)

    def _add_bubble(self, text, is_user):
        """
        Creates and adds a new chat bubble to the internal scene.

        Args:
            text (str): The message content.
            is_user (bool): True if the message is from the user, False otherwise.
        """
        bubble_item = ChatMessageBubbleItem(text, is_user)
        
        # Position user bubbles on the right, AI bubbles on the left.
        if is_user:
            x_pos = self.internal_view.width() - bubble_item.width - 10
        else:
            x_pos = 10
            
        bubble_item.setPos(x_pos, self._next_message_y)
        self.internal_scene.addItem(bubble_item)
        self._message_items.append(bubble_item)
        
        # Increment the Y position for the next bubble.
        self._next_message_y += bubble_item.height + 10
        self.internal_scene.setSceneRect(self.internal_scene.itemsBoundingRect())
        
        # Use a QTimer to ensure the scroll happens after the scene rect has updated.
        QTimer.singleShot(0, lambda: self.internal_view.verticalScrollBar().setValue(self.internal_view.verticalScrollBar().maximum()))

    def send_message(self):
        """Handles the user sending a new message from the input field."""
        text = self.message_input.text().strip()
        if not text:
            return

        self.add_user_message(text)
        self.ai_request_sent.emit(self, self.conversation_history)
        self.message_input.clear()
        self.set_input_enabled(False) # Disable input while waiting for AI response.

    def add_user_message(self, text: str):
        """
        Adds a user message to the chat view and history.

        Args:
            text (str): The user's message text.
        """
        self._add_bubble(text, True)
        self.conversation_history.append({'role': 'user', 'content': text})

    def add_ai_message(self, text: str):
        """
        Adds an AI message to the chat view and history, and re-enables input.

        Args:
            text (str): The AI's message text.
        """
        self._add_bubble(text, False)
        self.conversation_history.append({'role': 'assistant', 'content': text})
        self.set_input_enabled(True)

    def set_input_enabled(self, enabled: bool):
        """
        Enables or disables the message input field and send button.

        Args:
            enabled (bool): True to enable input, False to disable.
        """
        self.message_input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        if enabled:
            self.message_input.setFocus()
            self.message_input.setPlaceholderText("Type a message...")
        else:
            self.message_input.setPlaceholderText("Waiting for response...")
    
    def set_history(self, history: list):
        """
        Reconstructs the chat view from a given message history list.

        Args:
            history (list[dict]): A list of message dictionaries.
        """
        self.internal_scene.clear()
        self._message_items.clear()
        self._next_message_y = 10
        self.conversation_history = []
        for message in history:
            role = message.get('role')
            content = message.get('content', '')
            if role == 'user':
                self.add_user_message(content)
            elif role == 'assistant':
                self.add_ai_message(content)
        
        # If the last message was from the assistant, pop it so the node can generate a new one.
        if self.conversation_history and self.conversation_history[-1]['role'] == 'assistant':
            self.conversation_history.pop()

    def update_search_highlight(self, search_text):
        """
        Updates the search highlight state for all message bubbles within this node.

        Args:
            search_text (str): The text to search for.
        """
        if not search_text:
            search_text = ""
        search_text = search_text.lower()
        found_item = None
        for item in self._message_items:
            is_match = search_text and search_text in item.raw_text.lower()
            if item.is_search_match != is_match:
                item.is_search_match = is_match
                item.update()
            if is_match and not found_item:
                found_item = item

        # If a match is found, scroll the internal view to make it visible.
        if found_item:
            self.internal_view.ensureVisible(found_item, 50, 50)
            
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
        """Handles the custom painting of the node's border, background, and connection dots."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        
        # Draw main node body.
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        # Determine outline color based on state.
        node_color = QColor(palette.FRAME_COLORS["Purple"]["color"])
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