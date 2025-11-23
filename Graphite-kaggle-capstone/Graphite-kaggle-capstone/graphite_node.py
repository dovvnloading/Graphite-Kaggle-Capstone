import qtawesome as qta
from PySide6.QtWidgets import (
    QDialog, QGraphicsItem, QMenu, QMessageBox, QApplication, QFileDialog
)
from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QVariantAnimation,
    QSizeF
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPainterPath, QImage, QTextLayout, QTextOption,
    QLinearGradient, QConicalGradient, QFontMetrics, QAction, QPainterPathStroker,
    QTextDocument, QAbstractTextDocumentLayout, QPalette
)
from graphite_canvas_items import Frame, Container
from graphite_widgets import ScrollBar, HoverAnimationMixin
from graphite_connections import ConnectionItem
import markdown
from graphite_config import get_current_palette
from graphite_exporter import Exporter

# --- Start of new code for syntax highlighting ---
# Conditional import for Pygments library for syntax highlighting
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False

class CodeHighlighter:
    """A wrapper for the Pygments library to provide syntax highlighting."""
    def __init__(self, style='monokai'):
        """
        Initializes the CodeHighlighter.

        Args:
            style (str, optional): The Pygments style to use for highlighting.
                                   Defaults to 'monokai', which is suitable for dark themes.
        """
        if not PYGMENTS_AVAILABLE:
            return
        # Using a style that fits a dark theme
        self.formatter = HtmlFormatter(style=style, nobackground=True, cssclass="code")

    def highlight(self, code, language):
        """
        Highlights a block of code using the specified language.

        Args:
            code (str): The source code to highlight.
            language (str): The name of the programming language. If empty, Pygments will try to guess.

        Returns:
            str: The HTML-formatted, highlighted code.
        """
        if not PYGMENTS_AVAILABLE:
            # Fallback to simple preformatted text if Pygments is not installed
            return f'<pre style="color: #ffffff; white-space: pre-wrap;">{code}</pre>'
        try:
            # If no language is specified, pygments can often guess
            if not language:
                 lexer = guess_lexer(code)
            else:
                lexer = get_lexer_by_name(language)
        except:
            # Fallback to plain text if lexer not found or guess fails
            lexer = get_lexer_by_name('text')
        
        return highlight(code, lexer, self.formatter)

    def get_stylesheet(self):
        """
        Generates the CSS stylesheet required for the selected Pygments style.

        Returns:
            str: A CSS string that can be applied to a QTextDocument.
        """
        if not PYGMENTS_AVAILABLE:
            return ""
        # Generate CSS for the chosen pygments style
        return self.formatter.get_style_defs('.code')
# --- End of new code for syntax highlighting ---


class ChatNode(QGraphicsItem, HoverAnimationMixin):
    """
    A graphical node representing a single message in the chat conversation.
    It supports Markdown rendering, scrolling for long content, and collapsing.
    """
    # Constants for node geometry and appearance
    MAX_HEIGHT = 600
    PADDING = 15
    BLOCK_PADDING = 10
    BLOCK_SPACING = 8
    COLLAPSED_WIDTH = 250
    COLLAPSED_HEIGHT = 40
    SCROLLBAR_PADDING = 5
    CONTROL_GUTTER = 30 # Reserved space for button and scrollbar
    CONNECTION_DOT_RADIUS = 5
    CONNECTION_DOT_OFFSET = 0
    
    def __init__(self, text, is_user=True, parent=None):
        """
        Initializes the ChatNode.

        Args:
            text (str or list): The raw content for the node. Can be a simple string or
                                a list of content parts for multi-modal messages.
            is_user (bool, optional): True if this is a user message, False for an AI message.
                                      Defaults to True.
            parent (QGraphicsItem, optional): The parent item in the graphics scene.
                                              Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.raw_content = text # Can be string or list of text parts
        self.is_user = is_user
        self.children = [] # List of direct child nodes in the conversation graph
        self.parent_node = None # The parent node this node branches from
        self.conversation_history = [] # Full message history leading up to this node
        self.docked_thinking_nodes = []
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.hovered = False
        
        # Node dimensions and content height
        self.width = 400
        self.height = 100
        self.content_height = 0
        
        # State flags
        self.is_collapsed = False
        self.collapse_button_rect = QRectF()
        
        # Scrolling mechanism
        self.scroll_value = 0
        self.scrollbar = ScrollBar(self)
        self.scrollbar.width = 8
        self.scrollbar.valueChanged.connect(self.update_scroll_position)
        
        # QTextDocument is used for efficient rendering of rich text (Markdown/HTML)
        self.document = QTextDocument()
        self._setup_document()
        
        # State flags for visual feedback
        self.is_dimmed = False
        self.is_search_match = False
        self.is_last_navigated = False

    @property
    def text(self):
        """
        Returns the purely textual content of the node, stripping out any
        non-text parts from multi-modal content.
        
        Returns:
            str: The plain text content of the node.
        """
        if isinstance(self.raw_content, str):
            return self.raw_content
        
        # If content is a list of parts, extract and join the text parts
        text_parts = []
        if isinstance(self.raw_content, list):
            for part in self.raw_content:
                if isinstance(part, dict) and part.get('type') == 'text':
                    text_parts.append(part.get('text', ''))
                elif isinstance(part, str): # Handle legacy or simple cases
                    text_parts.append(part)
        
        return "\n".join(text_parts)

    def boundingRect(self):
        """
        Returns the bounding rectangle of the item, including padding for connection dots.

        Returns:
            QRectF: The bounding rectangle.
        """
        padding = self.CONNECTION_DOT_OFFSET + self.CONNECTION_DOT_RADIUS
        if self.is_collapsed:
            return QRectF(-padding, -5, self.COLLAPSED_WIDTH + 10 + 2 * padding, self.COLLAPSED_HEIGHT + 10)
        return QRectF(-padding, -5, self.width + 10 + 2 * padding, self.height + 10)

    def _update_geometry_for_state(self):
        """Updates the node's dimensions based on its collapsed/expanded state."""
        self.prepareGeometryChange()
        if self.is_collapsed:
            self.width = self.COLLAPSED_WIDTH
            self.height = self.COLLAPSED_HEIGHT
            self.scrollbar.setVisible(False)
        else:
            self.width = 400 # Restore default width
            self._recalculate_geometry()

        # Notify the scene to update connections and parent frame geometry
        if self.scene():
            self.scene().update_connections()
            if self.parentItem() and isinstance(self.parentItem(), Frame):
                self.parentItem().updateGeometry()
        self.update()

    def set_collapsed(self, collapsed):
        """
        Sets the collapsed state of the node.

        Args:
            collapsed (bool): True to collapse the node, False to expand it.
        """
        if self.is_collapsed != collapsed:
            self.is_collapsed = collapsed
            self._update_geometry_for_state()

    def toggle_collapse(self):
        """Toggles the node's collapsed state."""
        self.set_collapsed(not self.is_collapsed)

    def _get_default_stylesheet(self, color, font_family, font_size):
        """
        Generates a default CSS stylesheet for the QTextDocument based on scene settings.
        
        Args:
            color (str): The hex color code for the text.
            font_family (str): The name of the font family.
            font_size (int): The point size of the font.

        Returns:
            str: A CSS stylesheet string.
        """
        return f"""
            p, ul, ol, li, blockquote {{
                color: {color};
                font-family: '{font_family}';
                font-size: {font_size}pt;
            }}
            h1, h2, h3, h4, h5, h6 {{
                color: #ffffff;
                font-family: '{font_family}';
                font-weight: bold;
                margin-top: 10px;
                margin-bottom: 5px;
            }}
            h1 {{ font-size: {font_size + 4}pt; }}
            h2 {{ font-size: {font_size + 3}pt; }}
            h3 {{ font-size: {font_size + 2}pt; }}
            hr {{
                border: none;
                border-top: 1px solid #444444;
                height: 1px;
                margin: 10px 0;
            }}
            blockquote {{
                border-left: 3px solid #555555;
                padding-left: 10px;
                margin-left: 5px;
                color: #aaaaaa;
            }}
        """

    def _setup_document(self):
        """Sets up the QTextDocument for rendering, applying styles and content."""
        # Get font settings from the scene if available
        font_family = "Segoe UI"
        font_size = 10
        color = "#dddddd"
        
        if self.scene():
            font_family = self.scene().font_family
            font_size = self.scene().font_size
            color = self.scene().font_color.name()

        # Apply stylesheet and convert Markdown content to HTML
        self.document.setDefaultStyleSheet(self._get_default_stylesheet(color, font_family, font_size))
        text_content = self.text
        html = markdown.markdown(text_content, extensions=['fenced_code', 'tables'])
        self.document.setHtml(html)

        # Recalculate geometry after content change
        self._recalculate_geometry()

    def _recalculate_geometry(self):
        """
        Recalculates the node's height based on its content and determines if a
        scrollbar is needed.
        """
        # Determine the available width for text rendering
        available_width = self.width - (self.PADDING * 2) - self.CONTROL_GUTTER
        self.document.setTextWidth(available_width)
        
        # Calculate the ideal height of the content and clamp it to MAX_HEIGHT
        self.content_height = self.document.size().height() + (self.PADDING * 2)
        self.height = min(self.MAX_HEIGHT, self.content_height)

        # Show scrollbar if content overflows
        is_scrollable = self.content_height > self.height
        self.scrollbar.setVisible(is_scrollable)
        
        # Position and configure the scrollbar
        self.scrollbar.height = self.height - (self.SCROLLBAR_PADDING * 2)
        self.scrollbar.setPos(self.width - self.scrollbar.width - self.SCROLLBAR_PADDING, self.SCROLLBAR_PADDING)
        
        # Set the scrollbar's handle size based on the visible content ratio
        visible_ratio = self.height / self.content_height if self.content_height > 0 else 1
        self.scrollbar.set_range(visible_ratio)
        
        self.prepareGeometryChange()
        self.update()

    def update_font_settings(self, font_family, font_size, color):
        """
        Applies new font settings from the scene and re-renders the document.

        Args:
            font_family (str): The new font family name.
            font_size (int): The new font size.
            color (QColor): The new font color.
        """
        self._setup_document()
        
    def contextMenuEvent(self, event):
        """
        Shows a context menu when the node is right-clicked.

        Args:
            event (QGraphicsSceneContextMenuEvent): The context menu event.
        """
        menu = ChatNodeContextMenu(self)
        menu.exec(event.screenPos())

    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the node.

        Args:
            painter (QPainter): The painter to use for drawing.
            option (QStyleOptionGraphicsItem): Provides style information.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # Determine current dimensions based on collapsed state
        current_width = self.COLLAPSED_WIDTH if self.is_collapsed else self.width
        current_height = self.COLLAPSED_HEIGHT if self.is_collapsed else self.height

        # Draw a subtle drop shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 30))
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(3, 3, current_width, current_height, 10, 10)
        painter.drawPath(shadow_path)
    
        # Draw the main node body
        path = QPainterPath()
        path.addRoundedRect(0, 0, current_width, current_height, 10, 10)
    
        gradient = QLinearGradient(QPointF(0, 0), QPointF(0, current_height))
        gradient.setColorAt(0, QColor("#4a4a4a"))
        gradient.setColorAt(1, QColor("#2d2d2d"))
        painter.setBrush(QBrush(gradient))
    
        # Check if a rubber band selection is active to avoid conflicting highlights
        is_dragging = self.scene() and getattr(self.scene(), 'is_rubber_band_dragging', False)
        
        # Determine outline color based on node type and state
        outline_color = palette.USER_NODE if self.is_user else palette.AI_NODE
        pen = QPen(outline_color, 1.5)

        if self.isSelected() and not is_dragging:
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        
        painter.setPen(pen)
        painter.drawPath(path)

        # Draw connection dots on the left and right edges
        dot_color = outline_color
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        dot_rect_left = QRectF(-self.CONNECTION_DOT_RADIUS, (current_height / 2) - self.CONNECTION_DOT_RADIUS, self.CONNECTION_DOT_RADIUS * 2, self.CONNECTION_DOT_RADIUS * 2)
        painter.drawPie(dot_rect_left, 90 * 16, -180 * 16) # Draws a half-circle
        
        dot_rect_right = QRectF(current_width - self.CONNECTION_DOT_RADIUS, (current_height / 2) - self.CONNECTION_DOT_RADIUS, self.CONNECTION_DOT_RADIUS * 2, self.CONNECTION_DOT_RADIUS * 2)
        painter.drawPie(dot_rect_right, 90 * 16, 180 * 16) # Draws a half-circle

        # Draw indicator for docked thinking node
        if self.docked_thinking_nodes:
            indicator_color = QColor("#95a5a6").lighter(130)
            painter.setBrush(indicator_color)
            painter.setPen(Qt.PenStyle.NoPen)
            indicator_rect = QRectF((current_width / 2) - 4, 4, 8, 8)
            painter.drawEllipse(indicator_rect)


        # Draw special highlight for last navigated node
        if self.is_last_navigated:
            highlight_pen = QPen(palette.NAV_HIGHLIGHT, 2.5, Qt.PenStyle.DashLine)
            highlight_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # Draw search match highlight
        if self.is_search_match:
            highlight_pen = QPen(QColor("#00FFFF"), 2.5)
            highlight_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        
        if self.is_collapsed:
            # Draw UI for collapsed state (elided text and expand button)
            if self.hovered:
                self.collapse_button_rect = QRectF(current_width - 24, 6, 18, 18)
                painter.setBrush(QColor(255, 255, 255, 30))
                painter.setPen(QColor(255, 255, 255, 150))
                painter.drawRoundedRect(self.collapse_button_rect, 4, 4)
                
                # Draw a '+' icon for expansion
                icon_pen = QPen(QColor("#ffffff"), 2)
                painter.setPen(icon_pen)
                center = self.collapse_button_rect.center()
                painter.drawLine(int(center.x()), int(center.y() - 4), int(center.x()), int(center.y() + 4))
                painter.drawLine(int(center.x() - 4), int(center.y()), int(center.x() + 4), int(center.y()))

            painter.setPen(QColor("#ffffff"))
            font = QFont('Segoe UI', 10)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            
            # Show the first line of text or a placeholder
            text_to_show = self.text.split('\n')[0]
            if not text_to_show:
                text_to_show = "[Empty]"

            elided_text = metrics.elidedText(text_to_show, Qt.TextElideMode.ElideRight, current_width - 40)
            painter.drawText(QRectF(10, 0, current_width - 30, current_height), Qt.AlignmentFlag.AlignVCenter, elided_text)
        else:
            # Draw UI for expanded state (rendered content and collapse button)
            painter.save()

            # Clip the content area to prevent drawing over controls
            clip_rect = QRectF(0, 0, self.width - self.CONTROL_GUTTER, self.height)
            painter.setClipRect(clip_rect)

            # Apply scroll offset by translating the painter
            scroll_offset = (self.content_height - self.height) * self.scroll_value
            painter.translate(self.PADDING, self.PADDING - scroll_offset)
            
            # Draw a subtle background for the content area
            content_area_width = self.width - (self.PADDING * 2) - self.CONTROL_GUTTER
            container_path = QPainterPath()
            container_path.addRoundedRect(0, 0, content_area_width, self.content_height - (self.PADDING * 2), 10, 10)
            painter.setBrush(QColor(0, 0, 0, 25))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(container_path)

            # Draw the rich text content
            self.document.drawContents(painter)

            painter.restore()

            # Draw collapse button on hover
            if self.hovered:
                button_x = 0
                if self.scrollbar.isVisible():                   
                    button_x = self.scrollbar.pos().x() - 18 - 5 
                else:
                    button_x = self.width - 24
                
                self.collapse_button_rect = QRectF(button_x, 6, 18, 18)
                painter.setBrush(QColor(255, 255, 255, 30))
                painter.setPen(QColor(255, 255, 255, 150))
                painter.drawRoundedRect(self.collapse_button_rect, 4, 4)
                
                # Draw a '-' icon for collapsing
                icon_pen = QPen(QColor("#ffffff"), 2)
                painter.setPen(icon_pen)
                center = self.collapse_button_rect.center()
                painter.drawLine(int(center.x() - 4), int(center.y()), int(center.x() + 4), int(center.y()))

        # Draw a dimming overlay if the node is part of an inactive branch
        if self.is_dimmed:
            painter.setPen(Qt.PenStyle.NoPen)
            dim_color = QColor(0, 0, 0, 100)
            painter.setBrush(dim_color)
            painter.drawRoundedRect(0, 0, current_width, current_height, 10, 10)


    def wheelEvent(self, event):
        """
        Handles mouse wheel events for scrolling the node's content.

        Args:
            event (QGraphicsSceneWheelEvent): The wheel event.
        """
        if self.is_collapsed or not self.scrollbar.isVisible():
            event.ignore()
            return
            
        # Calculate scroll delta based on wheel rotation
        delta = event.delta() / 120
        scroll_delta = -delta * 0.1 # Adjust sensitivity
        
        # Update scroll value and clamp between 0 and 1
        new_value = max(0, min(1, self.scroll_value + scroll_delta))
        self.scroll_value = new_value
        self.scrollbar.set_value(new_value)
        self.update()
        
        event.accept()

    def update_scroll_position(self, value):
        """
        Slot to update the scroll position when the scrollbar is moved.

        Args:
            value (float): The new scroll value (0.0 to 1.0).
        """
        self.scroll_value = value
        self.update()

    def mousePressEvent(self, event):
        """
        Handles mouse press events for collapsing/expanding or initiating a drag.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse press event.
        """
        # Check if the collapse button was clicked
        if self.hovered and self.collapse_button_rect.contains(event.pos()):
            self.toggle_collapse()
            event.accept()
            return

        # Handle left-click for dragging and context setting
        if event.button() == Qt.MouseButton.LeftButton:
            scene = self.scene()
            if scene:
                if hasattr(scene, 'window'):
                    scene.window.setCurrentNode(self)
                scene.is_dragging_item = True
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        """
        Handles mouse release events to stop dragging.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse release event.
        """
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides() # Clear any smart guides
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        """Handles hover enter events using the mixin."""
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles hover leave events using the mixin."""
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        """
        Handles item changes, such as position changes or being added to a scene.

        Args:
            change (QGraphicsItem.GraphicsItemChange): The type of change.
            value: The new value for the changed attribute.

        Returns:
            The modified value or the result of the superclass implementation.
        """
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene():
            # Re-setup document when added to a scene to get scene-wide font settings
            self._setup_document()
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # Notify scene of movement for connection updates and smart guides
            self.scene().nodeMoved(self)
            
            parent = self.parentItem()
            if parent and isinstance(parent, Container):
                parent.updateGeometry()

            # Apply snapping if enabled
            if self.scene().is_dragging_item:
                return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def update_content(self, new_content):
        """
        Updates the node's content, re-processes text blocks, and recalculates geometry.

        Args:
            new_content (str or list): The new raw content for the node.
        """
        self.raw_content = new_content
        self._setup_document()
        self.update()

class CodeNode(QGraphicsItem, HoverAnimationMixin):
    """A graphical node for displaying formatted code with syntax highlighting."""
    PADDING = 15
    HEADER_HEIGHT = 30
    MAX_HEIGHT = 800

    def __init__(self, code, language, parent_content_node, parent=None):
        """
        Initializes the CodeNode.

        Args:
            code (str): The source code to display.
            language (str): The programming language for syntax highlighting.
            parent_content_node (ChatNode): The ChatNode this code block belongs to.
            parent (QGraphicsItem, optional): The parent item in the scene. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.code = code
        self.language = language
        self.parent_content_node = parent_content_node
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False
        self.is_search_match = False

        # Use CodeHighlighter for syntax highlighting
        self.highlighter = CodeHighlighter()
        self.document = QTextDocument()
        self.document.setDefaultStyleSheet(self.highlighter.get_stylesheet())
        self.document.setHtml(self.highlighter.highlight(self.code, self.language))

        # Calculate geometry based on content
        self.width = 600
        doc_width = self.width - (self.PADDING * 2)
        self.document.setTextWidth(doc_width)
        
        content_height = self.document.size().height()
        self.height = min(self.MAX_HEIGHT, content_height + self.HEADER_HEIGHT + self.PADDING)

    def boundingRect(self):
        """
        Returns the bounding rectangle of the item, including a small margin.

        Returns:
            QRectF: The bounding rectangle.
        """
        return QRectF(-5, -5, self.width + 10, self.height + 10)

    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the code node.

        Args:
            painter (QPainter): The painter to use for drawing.
            option (QStyleOptionGraphicsItem): Provides style information.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Draw main body
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)

        painter.setBrush(QColor("#1e1e1e"))
        
        is_dragging = self.scene() and getattr(self.scene(), 'is_rubber_band_dragging', False)

        # Determine outline color based on state
        if self.isSelected() and not is_dragging:
            painter.setPen(QPen(palette.SELECTION, 2))
        elif self.hovered:
            painter.setPen(QPen(QColor("#ffffff"), 2))
        else:
            painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawPath(path)

        # Draw search match highlight
        if self.is_search_match:
            highlight_pen = QPen(QColor("#FFD700"), 2.5)
            highlight_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        
        # Draw header area
        header_path = QPainterPath()
        header_rect = QRectF(0, 0, self.width, self.HEADER_HEIGHT)
        header_path.addRoundedRect(header_rect, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        painter.drawPath(header_path)

        # Draw header text (language) and copy icon
        painter.setPen(QColor("#cccccc"))
        font = QFont('Consolas', 9)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, f"Language: {self.language or 'auto-detected'}")
        
        copy_icon = qta.icon('fa5s.copy', color='#cccccc')
        copy_icon.paint(painter, QRectF(self.width - 28, 7, 16, 16).toRect())

        # Draw the highlighted code content
        painter.save()
        painter.translate(self.PADDING, self.HEADER_HEIGHT)
        clip_rect = QRectF(0, 0, self.width - (self.PADDING * 2), self.height - self.HEADER_HEIGHT - self.PADDING)
        painter.setClipRect(clip_rect)
        self.document.drawContents(painter)
        painter.restore()

    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        menu = CodeNodeContextMenu(self)
        menu.exec(event.screenPos())

    def mousePressEvent(self, event):
        """
        Handles mouse press events, specifically for the copy button.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse press event.
        """
        copy_rect = QRectF(self.width - 32, 4, 24, 24)
        if copy_rect.contains(event.pos()):
            QApplication.clipboard().setText(self.code)
            # TODO: Add some user feedback, maybe an animation
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop dragging."""
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)
    
    def hoverEnterEvent(self, event):
        """Handles hover enter events using the mixin."""
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles hover leave events using the mixin."""
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)
    
    def itemChange(self, change, value):
        """Handles item changes, applying snapping during movement."""
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            self.scene().nodeMoved(self)
            
            parent = self.parentItem()
            if parent and isinstance(parent, Container):
                parent.updateGeometry()

            if self.scene().is_dragging_item:
                return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

class ThinkingNode(QGraphicsItem, HoverAnimationMixin):
    """A graphical node for displaying the AI's reasoning or 'Chain of Thought' text."""
    PADDING = 15
    HEADER_HEIGHT = 30
    MAX_HEIGHT = 600
    SCROLLBAR_PADDING = 5
    
    def __init__(self, thinking_text, parent_content_node, parent=None):
        """
        Initializes the ThinkingNode.

        Args:
            thinking_text (str): The reasoning text from the AI.
            parent_content_node (ChatNode): The ChatNode this reasoning block belongs to.
            parent (QGraphicsItem, optional): The parent item in the scene. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.thinking_text = thinking_text
        self.parent_content_node = parent_content_node
        self.is_docked = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False
        self.is_search_match = False
        self.dock_button_rect = QRectF()
        self.dock_button_hovered = False
        
        self.width = 500
        
        # Setup QTextDocument for content rendering
        self.document = QTextDocument()
        self._setup_document()
        
        # Setup ScrollBar for overflowing content
        self.scroll_value = 0
        self.scrollbar = ScrollBar(self)
        self.scrollbar.width = 8
        self.scrollbar.valueChanged.connect(self.update_scroll_position)
        self._recalculate_geometry()

    def _setup_document(self):
        """Sets up the QTextDocument with the correct styles and content."""
        font_family = "Segoe UI"
        font_size = 9 
        color = "#b0b0b0"

        if self.scene():
            font_family = self.scene().font_family
            font_size = self.scene().font_size - 1
            color = self.scene().font_color.lighter(120).name()
        
        stylesheet = f"p {{ color: {color}; font-family: '{font_family}'; font-size: {font_size}pt; font-style: italic; }}"
        self.document.setDefaultStyleSheet(stylesheet)
        html = markdown.markdown(self.thinking_text, extensions=['fenced_code'])
        self.document.setHtml(html)

    def _recalculate_geometry(self):
        """Recalculates the node's height based on its content."""
        self.prepareGeometryChange()

        doc_width = self.width - (self.PADDING * 2)
        self.document.setTextWidth(doc_width)
        
        self.content_height = self.document.size().height()
        self.height = min(self.MAX_HEIGHT, self.content_height + self.HEADER_HEIGHT + self.PADDING)
        
        is_scrollable = self.content_height + self.HEADER_HEIGHT + self.PADDING > self.height
        self.scrollbar.setVisible(is_scrollable)
        
        if is_scrollable:
            self.scrollbar.height = self.height - (self.SCROLLBAR_PADDING * 2)
            self.scrollbar.setPos(self.width - self.scrollbar.width - self.SCROLLBAR_PADDING, self.SCROLLBAR_PADDING)
            visible_ratio = (self.height - self.HEADER_HEIGHT - self.PADDING) / self.content_height
            self.scrollbar.set_range(visible_ratio)
        
        self.prepareGeometryChange()
        self.update()

    def update_font_settings(self, font_family, font_size, color):
        """Applies new font settings from the scene."""
        self._setup_document()

    def boundingRect(self):
        """Returns the bounding rectangle of the item."""
        return QRectF(-5, -5, self.width + 10, self.height + 10)

    def dock(self):
        """Hides the node and registers it as docked with its parent."""
        self.is_docked = True
        self.hide()
        if self.parent_content_node:
            if self not in self.parent_content_node.docked_thinking_nodes:
                self.parent_content_node.docked_thinking_nodes.append(self)
            self.parent_content_node.update()
        if self.scene():
            self.scene().update_connections()

    def undock(self):
        """Shows the node and unregisters it from its parent's docked list."""
        self.is_docked = False
        self.show()
        if self.parent_content_node:
            if self in self.parent_content_node.docked_thinking_nodes:
                self.parent_content_node.docked_thinking_nodes.remove(self)
            self.parent_content_node.update()
        if self.scene():
            self.scene().update_connections()

    def paint(self, painter, option, widget=None):
        """Handles the custom painting of the thinking node."""
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        is_dragging = self.scene() and getattr(self.scene(), 'is_rubber_band_dragging', False)

        pen_color = QColor("#95a5a6")
        if self.isSelected() and not is_dragging:
            pen = QPen(palette.SELECTION, 2)
        elif self.hovered:
            pen = QPen(QColor("#ffffff"), 2)
        else:
            pen = QPen(pen_color, 1)
        painter.setPen(pen)
        painter.drawPath(path)

        header_path = QPainterPath()
        header_rect = QRectF(0, 0, self.width, self.HEADER_HEIGHT)
        header_path.addRoundedRect(header_rect, 10, 10)
        painter.setBrush(QColor("#3f3f3f"))
        painter.drawPath(header_path)
        
        icon = qta.icon('fa5s.brain', color='#cccccc')
        icon.paint(painter, QRectF(10, 7, 16, 16).toRect())

        painter.setPen(QColor("#cccccc"))
        font = QFont('Segoe UI', 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(55, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, "Assistant's Thoughts")

        self.dock_button_rect = QRectF(self.width - 28, 6, 18, 18)
        button_bg_color = QColor("#555") if self.dock_button_hovered else QColor("#444")
        painter.setBrush(button_bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.dock_button_rect, 4, 4)
        dock_icon_color = "#ffffff" if self.dock_button_hovered else "#aaaaaa"
        dock_icon = qta.icon('fa5s.arrow-up', color=dock_icon_color)
        dock_icon.paint(painter, self.dock_button_rect.adjusted(3,3,-3,-3).toRect())
        
        painter.save()
        painter.translate(self.PADDING, self.HEADER_HEIGHT + 5)
        clip_rect = QRectF(0, 0, self.width - (self.PADDING * 2), self.height - self.HEADER_HEIGHT - self.PADDING)
        painter.setClipRect(clip_rect)
        
        scroll_offset = (self.content_height - (self.height - self.HEADER_HEIGHT - self.PADDING)) * self.scroll_value
        painter.translate(0, -scroll_offset)
        
        self.document.drawContents(painter)
        painter.restore()

    def wheelEvent(self, event):
        """Handles mouse wheel events for scrolling."""
        if not self.scrollbar.isVisible():
            event.ignore()
            return
        
        delta = event.delta() / 120
        scroll_range = self.content_height - (self.height - self.HEADER_HEIGHT)
        if scroll_range <= 0: return

        scroll_delta = -(delta * 50) / scroll_range 
        
        new_value = max(0, min(1, self.scroll_value + scroll_delta))
        self.scroll_value = new_value
        self.scrollbar.set_value(new_value)
        self.update()
        event.accept()

    def update_scroll_position(self, value):
        """Updates scroll position based on scrollbar movement."""
        self.scroll_value = value
        self.update()

    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        menu = ThinkingNodeContextMenu(self)
        menu.exec(event.screenPos())

    def mousePressEvent(self, event):
        """Handles mouse press to initiate dragging."""
        if self.dock_button_hovered and self.dock_button_rect.contains(event.pos()):
            self.dock()
            event.accept()
            return
            
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop dragging."""
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        """Handles hover move events to update button hover states."""
        was_hovered = self.dock_button_hovered
        self.dock_button_hovered = self.dock_button_rect.contains(event.pos())
        if was_hovered != self.dock_button_hovered:
            self.update()
        super().hoverMoveEvent(event)
    
    def hoverEnterEvent(self, event):
        """Handles hover enter using the mixin."""
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles hover leave using the mixin."""
        self.dock_button_hovered = False
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)
    
    def itemChange(self, change, value):
        """Handles item changes, applying snapping during movement."""
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene():
            self._setup_document()
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            self.scene().nodeMoved(self)
            parent = self.parentItem()
            if parent and isinstance(parent, Container):
                parent.updateGeometry()
            if self.scene().is_dragging_item:
                return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

class ImageNode(QGraphicsItem, HoverAnimationMixin):
    """A graphical node for displaying an image."""
    PADDING = 15
    HEADER_HEIGHT = 30

    def __init__(self, image_bytes, parent_content_node, prompt="", parent=None):
        """
        Initializes the ImageNode.

        Args:
            image_bytes (bytes): The raw byte data of the image.
            parent_content_node (ChatNode): The ChatNode this image is associated with.
            prompt (str, optional): The prompt used to generate the image. Defaults to "".
            parent (QGraphicsItem, optional): The parent item in the scene. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.image_bytes = image_bytes
        self.parent_content_node = parent_content_node
        self.prompt = prompt
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False
        self.is_search_match = False
        
        # Load image data and calculate geometry
        self.image = QImage.fromData(self.image_bytes)
        self.width = 512 + (self.PADDING * 2) # Default width for a standard-sized image
        
        if not self.image.isNull():
            # Calculate height based on aspect ratio
            aspect_ratio = self.image.height() / self.image.width() if self.image.width() > 0 else 1
            content_width = self.width - (self.PADDING * 2)
            content_height = content_width * aspect_ratio
            self.height = content_height + self.HEADER_HEIGHT + (self.PADDING * 2)
        else:
            self.height = 400 # Fallback height if image is invalid

    def boundingRect(self):
        """Returns the bounding rectangle of the item."""
        return QRectF(-5, -5, self.width + 10, self.height + 10)

    def paint(self, painter, option, widget=None):
        """Handles the custom painting of the image node."""
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Draw main body
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)
        
        painter.setBrush(QColor("#2d2d2d"))
        
        is_dragging = self.scene() and getattr(self.scene(), 'is_rubber_band_dragging', False)

        # Determine outline color
        if self.isSelected() and not is_dragging:
            painter.setPen(QPen(palette.SELECTION, 2))
        elif self.hovered:
            painter.setPen(QPen(QColor("#ffffff"), 2))
        else:
            painter.setPen(QPen(QColor("#7f8c8d"), 1))
        painter.drawPath(path)

        # Draw header
        header_path = QPainterPath()
        header_rect = QRectF(0, 0, self.width, self.HEADER_HEIGHT)
        header_path.addRoundedRect(header_rect, 10, 10)
        painter.setBrush(QColor("#3f3f3f"))
        painter.drawPath(header_path)
        
        # Draw header icon and elided prompt text
        icon = qta.icon('fa5s.image', color='#cccccc')
        icon.paint(painter, QRectF(10, 7, 16, 16).toRect())

        painter.setPen(QColor("#cccccc"))
        font = QFont('Segoe UI', 9)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        elided_prompt = metrics.elidedText(f"Image: {self.prompt}", Qt.TextElideMode.ElideRight, self.width - 50)
        painter.drawText(header_rect.adjusted(35, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, elided_prompt)

        # Draw the image itself
        if not self.image.isNull():
            image_rect = QRectF(
                self.PADDING,
                self.HEADER_HEIGHT + self.PADDING,
                self.width - (self.PADDING * 2),
                self.height - self.HEADER_HEIGHT - (self.PADDING * 2)
            )
            painter.drawImage(image_rect, self.image)

    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        menu = ImageNodeContextMenu(self)
        menu.exec(event.screenPos())
        
    def mousePressEvent(self, event):
        """Handles mouse press to initiate dragging."""
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop dragging."""
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)
    
    def hoverEnterEvent(self, event):
        """Handles hover enter using the mixin."""
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles hover leave using the mixin."""
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        """Handles item changes, applying snapping during movement."""
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            self.scene().nodeMoved(self)
            
            parent = self.parentItem()
            if parent and isinstance(parent, Container):
                parent.updateGeometry()

            if self.scene().is_dragging_item:
                return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

class DocumentNode(QGraphicsItem, HoverAnimationMixin):
    """A graphical node for displaying the content of a text-based document."""
    PADDING = 15
    HEADER_HEIGHT = 30
    MAX_HEIGHT = 600
    SCROLLBAR_PADDING = 5
    
    def __init__(self, title, content, parent_content_node, parent=None):
        """
        Initializes the DocumentNode.

        Args:
            title (str): The title of the document (e.g., filename).
            content (str): The text content of the document.
            parent_content_node (ChatNode): The ChatNode this document is associated with.
            parent (QGraphicsItem, optional): The parent item in the scene. Defaults to None.
        """
        super().__init__(parent)
        HoverAnimationMixin.__init__(self)
        self.title = title
        self.content = content
        self.parent_content_node = parent_content_node
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hovered = False
        self.is_search_match = False
        
        self.width = 500
        
        # Setup QTextDocument for content rendering
        self.document = QTextDocument()
        self._setup_document()
        
        # Setup ScrollBar for overflowing content
        self.scroll_value = 0
        self.scrollbar = ScrollBar(self)
        self.scrollbar.width = 8
        self.scrollbar.valueChanged.connect(self.update_scroll_position)
        self._recalculate_geometry()

    def _setup_document(self):
        """Sets up the QTextDocument with the correct styles and content."""
        font_family = "Segoe UI"
        font_size = 10
        color = "#dddddd"

        # Inherit font settings from the scene
        if self.scene():
            font_family = self.scene().font_family
            font_size = self.scene().font_size
            color = self.scene().font_color.name()
        
        stylesheet = f"p {{ color: {color}; font-family: '{font_family}'; font-size: {font_size}pt; }}"
        self.document.setDefaultStyleSheet(stylesheet)
        self.document.setPlainText(self.content)

    def _recalculate_geometry(self):
        """Recalculates the node's height based on its content."""
        doc_width = self.width - (self.PADDING * 2)
        self.document.setTextWidth(doc_width)
        
        self.content_height = self.document.size().height()
        self.height = min(self.MAX_HEIGHT, self.content_height + self.HEADER_HEIGHT + self.PADDING)
        
        # Determine if a scrollbar is necessary
        is_scrollable = self.content_height + self.HEADER_HEIGHT + self.PADDING > self.height
        self.scrollbar.setVisible(is_scrollable)
        
        if is_scrollable:
            self.scrollbar.height = self.height - (self.SCROLLBAR_PADDING * 2)
            self.scrollbar.setPos(self.width - self.scrollbar.width - self.SCROLLBAR_PADDING, self.SCROLLBAR_PADDING)
            visible_ratio = (self.height - self.HEADER_HEIGHT - self.PADDING) / self.content_height
            self.scrollbar.set_range(visible_ratio)
        
        self.prepareGeometryChange()
        self.update()

    def update_font_settings(self, font_family, font_size, color):
        """Applies new font settings from the scene."""
        self._setup_document()

    def boundingRect(self):
        """Returns the bounding rectangle of the item."""
        return QRectF(-5, -5, self.width + 10, self.height + 10)

    def paint(self, painter, option, widget=None):
        """Handles the custom painting of the document node."""
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Draw main body
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)
        painter.setBrush(QColor("#2d2d2d"))
        
        is_dragging = self.scene() and getattr(self.scene(), 'is_rubber_band_dragging', False)

        # Determine outline color
        if self.isSelected() and not is_dragging:
            painter.setPen(QPen(palette.SELECTION, 2))
        elif self.hovered:
            painter.setPen(QPen(QColor("#ffffff"), 2))
        else:
            painter.setPen(QPen(QColor("#7f8c8d"), 1))
        painter.drawPath(path)

        # Draw header
        header_path = QPainterPath()
        header_rect = QRectF(0, 0, self.width, self.HEADER_HEIGHT)
        header_path.addRoundedRect(header_rect, 10, 10)
        painter.setBrush(QColor("#3f3f3f"))
        painter.drawPath(header_path)
        
        # Draw header text and icon
        file_icon = qta.icon('fa5s.file-alt', color='#cccccc')
        file_icon.paint(painter, QRectF(10, 7, 16, 16).toRect())

        painter.setPen(QColor("#cccccc"))
        font = QFont('Segoe UI', 9, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        elided_title = metrics.elidedText(self.title, Qt.TextElideMode.ElideRight, self.width - 50)
        painter.drawText(header_rect.adjusted(35, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, elided_title)
        
        # Draw content, applying scroll offset
        painter.save()
        painter.translate(self.PADDING, self.HEADER_HEIGHT + 5)
        clip_rect = QRectF(0, 0, self.width - (self.PADDING * 2), self.height - self.HEADER_HEIGHT - self.PADDING)
        painter.setClipRect(clip_rect)
        
        scroll_offset = (self.content_height - (self.height - self.HEADER_HEIGHT - self.PADDING)) * self.scroll_value
        painter.translate(0, -scroll_offset)
        
        self.document.drawContents(painter)
        painter.restore()

    def wheelEvent(self, event):
        """Handles mouse wheel events for scrolling."""
        if not self.scrollbar.isVisible():
            event.ignore()
            return
        
        delta = event.delta() / 120
        scroll_range = self.content_height - (self.height - self.HEADER_HEIGHT)
        if scroll_range <= 0: return

        scroll_delta = -(delta * 50) / scroll_range # 50 pixels per wheel tick
        
        new_value = max(0, min(1, self.scroll_value + scroll_delta))
        self.scroll_value = new_value
        self.scrollbar.set_value(new_value)
        self.update()
        event.accept()

    def update_scroll_position(self, value):
        """Updates scroll position based on scrollbar movement."""
        self.scroll_value = value
        self.update()

    def contextMenuEvent(self, event):
        """Shows a context menu on right-click."""
        menu = DocumentNodeContextMenu(self)
        menu.exec(event.screenPos())

    def mousePressEvent(self, event):
        """Handles mouse press to initiate dragging."""
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop dragging."""
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)
    
    def hoverEnterEvent(self, event):
        """Handles hover enter using the mixin."""
        self._handle_hover_enter(event)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles hover leave using the mixin."""
        self._handle_hover_leave(event)
        super().hoverLeaveEvent(event)
    
    def itemChange(self, change, value):
        """Handles item changes, applying snapping during movement."""
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene():
            self._setup_document()
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            self.scene().nodeMoved(self)

            parent = self.parentItem()
            if parent and isinstance(parent, Container):
                parent.updateGeometry()

            if self.scene().is_dragging_item:
                return self.scene().snap_position(self, value)
        
        # Crucial for responsive connections: Notify scene immediately on position change
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

class ThinkingNodeContextMenu(QMenu):
    """Context menu for ThinkingNode, providing copy and delete actions."""
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        palette = get_current_palette()
        
        self.setStyleSheet(f"""
            QMenu {{ background-color: #2d2d2d; border: 1px solid #3f3f3f; border-radius: 4px; padding: 4px; }}
            QMenu::item {{ background-color: transparent; padding: 8px 20px; border-radius: 4px; color: white; }}
            QMenu::item:selected {{ background-color: {palette.SELECTION.name()}; }}
        """)

        copy_action = QAction("Copy Content", self)
        copy_action.setIcon(qta.icon('fa5s.copy', color='white'))
        copy_action.triggered.connect(self.copy_content)
        self.addAction(copy_action)
        
        dock_action = QAction("Dock to Parent Node", self)
        dock_action.setIcon(qta.icon('fa5s.compress-arrows-alt', color='white'))
        dock_action.triggered.connect(self.node.dock)
        self.addAction(dock_action)
        
        delete_action = QAction("Delete Node", self)
        delete_action.setIcon(qta.icon('fa5s.trash', color='white'))
        delete_action.triggered.connect(self.delete_node)
        self.addAction(delete_action)

    def copy_content(self):
        """Copies the node's content to the clipboard."""
        QApplication.clipboard().setText(self.node.thinking_text)

    def delete_node(self):
        """Deletes the node from the scene."""
        scene = self.node.scene()
        if scene and hasattr(scene, 'deleteSelectedItems'):
            scene.clearSelection()
            self.node.setSelected(True)
            scene.deleteSelectedItems()

class DocumentNodeContextMenu(QMenu):
    """Context menu for DocumentNode, providing export and delete actions."""
    def __init__(self, node, parent=None):
        """
        Initializes the DocumentNodeContextMenu.

        Args:
            node (DocumentNode): The node this menu is for.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.node = node
        palette = get_current_palette()
        
        self.setStyleSheet(f"""
            QMenu {{ background-color: #2d2d2d; border: 1px solid #3f3f3f; border-radius: 4px; padding: 4px; }}
            QMenu::item {{ background-color: transparent; padding: 8px 20px; border-radius: 4px; color: white; }}
            QMenu::item:selected {{ background-color: {palette.SELECTION.name()}; }}
            QMenu::separator {{ height: 1px; background-color: #3f3f3f; margin: 4px 0px; }}
        """)

        copy_action = QAction("Copy Content", self)
        copy_action.setIcon(qta.icon('fa5s.copy', color='white'))
        copy_action.triggered.connect(self.copy_content)
        self.addAction(copy_action)
        
        self.addSeparator()
        
        export_menu = self.create_export_menu()
        self.addMenu(export_menu)

        delete_action = QAction("Delete Document", self)
        delete_action.setIcon(qta.icon('fa5s.trash', color='white'))
        delete_action.triggered.connect(self.delete_node)
        self.addAction(delete_action)

    def create_export_menu(self):
        """Creates the 'Export to Doc' submenu."""
        export_menu = QMenu("Export to Doc", self)
        export_menu.setIcon(qta.icon('fa5s.file-export', color='white'))
        
        txt_action = QAction("Text File (.txt)", self)
        txt_action.triggered.connect(lambda: self._handle_export('txt'))
        export_menu.addAction(txt_action)
        
        md_action = QAction("Markdown File (.md)", self)
        md_action.triggered.connect(lambda: self._handle_export('md'))
        export_menu.addAction(md_action)

        html_action = QAction("HTML Document (.html)", self)
        html_action.triggered.connect(lambda: self._handle_export('html'))
        export_menu.addAction(html_action)

        docx_action = QAction("Word Document (.docx)", self)
        docx_action.triggered.connect(lambda: self._handle_export('docx'))
        export_menu.addAction(docx_action)
        
        pdf_action = QAction("PDF Document (.pdf)", self)
        pdf_action.triggered.connect(lambda: self._handle_export('pdf'))
        export_menu.addAction(pdf_action)
        
        return export_menu

    def _handle_export(self, file_format):
        """
        Handles the export logic for a given file format.

        Args:
            file_format (str): The target file format (e.g., 'txt', 'pdf').
        """
        exporter = Exporter()
        content = self.node.content
        default_filename = f"{self.node.title.split('.')[0]}.{file_format}"

        filters = {
            'txt': "Text Files (*.txt)",
            'pdf': "PDF Documents (*.pdf)",
            'docx': "Word Documents (*.docx)",
            'html': "HTML Files (*.html)",
            'md': "Markdown Files (*.md)"
        }
        
        main_window = self.node.scene().window
        file_path, _ = QFileDialog.getSaveFileName(main_window, "Export Node Content", default_filename, filters[file_format])

        if not file_path:
            return

        success, error_msg = False, "Unknown format"
        try:
            if file_format == 'txt':
                success, error_msg = exporter.export_to_txt(content, file_path)
            elif file_format == 'pdf':
                success, error_msg = exporter.export_to_pdf(content, file_path, is_code=False)
            elif file_format == 'docx':
                success, error_msg = exporter.export_to_docx(content, file_path)
            elif file_format == 'html':
                success, error_msg = exporter.export_to_html(content, file_path)
            elif file_format == 'md':
                success, error_msg = exporter.export_to_md(content, file_path)
        except ImportError as e:
            QMessageBox.warning(main_window, "Dependency Missing", str(e))
            return
        
        if success:
            msg_box = QMessageBox(QMessageBox.Icon.Information, "Export Successful", f"Node content exported to:\n{file_path}", parent=main_window)
            msg_box.setWindowIcon(main_window.windowIcon())
            msg_box.exec()
        else:
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Export Failed", f"An error occurred during export:\n{error_msg}", parent=main_window)
            msg_box.setWindowIcon(main_window.windowIcon())
            msg_box.exec()

    def copy_content(self):
        """Copies the node's content to the clipboard."""
        QApplication.clipboard().setText(self.node.content)

    def delete_node(self):
        """Deletes the node from the scene."""
        scene = self.node.scene()
        if scene and hasattr(scene, 'deleteSelectedItems'):
            scene.clearSelection()
            self.node.setSelected(True)
            scene.deleteSelectedItems()

class CodeNodeContextMenu(QMenu):
    """Context menu for CodeNode, providing copy, export, and regenerate actions."""
    def __init__(self, node, parent=None):
        """
        Initializes the CodeNodeContextMenu.

        Args:
            node (CodeNode): The node this menu is for.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.node = node # This is a CodeNode
        palette = get_current_palette()
        
        self.setStyleSheet(f"""
            QMenu {{
                background-color: #2d2d2d;
                border: 1px solid #3f3f3f;
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 8px 20px;
                border-radius: 4px;
                color: white;
            }}
            QMenu::item:selected {{
                background-color: {palette.SELECTION.name()};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #3f3f3f;
                margin: 4px 0px;
            }}
        """)

        copy_action = QAction("Copy Code", self)
        copy_action.setIcon(qta.icon('fa5s.copy', color='white'))
        copy_action.triggered.connect(self.copy_code)
        self.addAction(copy_action)
        
        self.addSeparator()
        
        export_menu = self.create_export_menu()
        self.addMenu(export_menu)

        if self.node.parent_content_node:
            regenerate_action = QAction("Regenerate Response", self)
            regenerate_action.setIcon(qta.icon('fa5s.sync', color='white'))
            regenerate_action.triggered.connect(self.regenerate_response)
            self.addAction(regenerate_action)

        delete_action = QAction("Delete Code Block", self)
        delete_action.setIcon(qta.icon('fa5s.trash', color='white'))
        delete_action.triggered.connect(self.delete_node)
        self.addAction(delete_action)

    def create_export_menu(self):
        """Creates the 'Export to Doc' submenu."""
        export_menu = QMenu("Export to Doc", self)
        export_menu.setIcon(qta.icon('fa5s.file-export', color='white'))
        
        py_action = QAction("Python Script (.py)", self)
        py_action.triggered.connect(lambda: self._handle_export('py'))
        export_menu.addAction(py_action)
        
        txt_action = QAction("Text File (.txt)", self)
        txt_action.triggered.connect(lambda: self._handle_export('txt'))
        export_menu.addAction(txt_action)
        
        md_action = QAction("Markdown File (.md)", self)
        md_action.triggered.connect(lambda: self._handle_export('md'))
        export_menu.addAction(md_action)

        html_action = QAction("HTML Document (.html)", self)
        html_action.triggered.connect(lambda: self._handle_export('html'))
        export_menu.addAction(html_action)
        
        pdf_action = QAction("PDF Document (.pdf)", self)
        pdf_action.triggered.connect(lambda: self._handle_export('pdf'))
        export_menu.addAction(pdf_action)
        
        return export_menu

    def _handle_export(self, file_format):
        """
        Handles the export logic for a given file format.

        Args:
            file_format (str): The target file format (e.g., 'py', 'pdf').
        """
        exporter = Exporter()
        content = self.node.code
        default_filename = f"code_snippet.{file_format}"

        filters = {
            'py': "Python Files (*.py)",
            'txt': "Text Files (*.txt)",
            'pdf': "PDF Documents (*.pdf)",
            'html': "HTML Files (*.html)",
            'md': "Markdown Files (*.md)"
        }
        
        main_window = self.node.scene().window
        file_path, _ = QFileDialog.getSaveFileName(main_window, "Export Code Content", default_filename, filters[file_format])

        if not file_path:
            return

        success, error_msg = False, "Unknown format"
        try:
            if file_format == 'txt':
                success, error_msg = exporter.export_to_txt(content, file_path)
            elif file_format == 'py':
                success, error_msg = exporter.export_to_py(content, file_path)
            elif file_format == 'pdf':
                success, error_msg = exporter.export_to_pdf(content, file_path, is_code=True)
            elif file_format == 'html':
                success, error_msg = exporter.export_to_html(content, file_path, title="Code Snippet")
            elif file_format == 'md':
                success, error_msg = exporter.export_to_md(f"```{self.node.language}\n{content}\n```", file_path)
        except ImportError as e:
            QMessageBox.warning(main_window, "Dependency Missing", str(e))
            return
        
        if success:
            msg_box = QMessageBox(QMessageBox.Icon.Information, "Export Successful", f"Code exported to:\n{file_path}", parent=main_window)
            msg_box.setWindowIcon(main_window.windowIcon())
            msg_box.exec()
        else:
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Export Failed", f"An error occurred during export:\n{error_msg}", parent=main_window)
            msg_box.setWindowIcon(main_window.windowIcon())
            msg_box.exec()

    def copy_code(self):
        """Copies the code to the clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.node.code)

    def regenerate_response(self):
        """Triggers a regeneration of the parent ChatNode's response."""
        # The key logic: we trigger regeneration on the PARENT ChatNode
        parent_chat_node = self.node.parent_content_node
        if parent_chat_node and parent_chat_node.scene():
            main_window = parent_chat_node.scene().window
            if main_window and hasattr(main_window, 'regenerate_node'):
                main_window.regenerate_node(parent_chat_node)

    def delete_node(self):
        """Deletes the code node from the scene."""
        scene = self.node.scene()
        if scene and hasattr(scene, 'deleteSelectedItems'):
            # A simple way is to select this node and call the scene's delete function
            scene.clearSelection()
            self.node.setSelected(True)
            scene.deleteSelectedItems()

class ImageNodeContextMenu(QMenu):
    """Context menu for ImageNode, providing copy, save, and regenerate actions."""
    def __init__(self, node, parent=None):
        """
        Initializes the ImageNodeContextMenu.

        Args:
            node (ImageNode): The node this menu is for.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.node = node # This is an ImageNode
        palette = get_current_palette()
        
        self.setStyleSheet(f"""
            QMenu {{
                background-color: #2d2d2d; border: 1px solid #3f3f3f;
                border-radius: 4px; padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent; padding: 8px 20px;
                border-radius: 4px; color: white;
            }}
            QMenu::item:selected {{ background-color: {palette.SELECTION.name()}; }}
            QMenu::separator {{ height: 1px; background-color: #3f3f3f; margin: 4px 0px; }}
        """)

        copy_image_action = QAction("Copy Image", self)
        copy_image_action.setIcon(qta.icon('fa5s.copy', color='white'))
        copy_image_action.triggered.connect(self.copy_image)
        self.addAction(copy_image_action)
        
        save_image_action = QAction("Export Image (.png/.jpg)", self)
        save_image_action.setIcon(qta.icon('fa5s.save', color='white'))
        save_image_action.triggered.connect(self.save_image)
        self.addAction(save_image_action)
        
        self.addSeparator()

        if self.node.parent_content_node and self.node.prompt:
            regenerate_action = QAction("Regenerate Image", self)
            regenerate_action.setIcon(qta.icon('fa5s.sync', color='white'))
            regenerate_action.triggered.connect(self.regenerate_image)
            self.addAction(regenerate_action)

        delete_action = QAction("Delete Image", self)
        delete_action.setIcon(qta.icon('fa5s.trash', color='white'))
        delete_action.triggered.connect(self.delete_node)
        self.addAction(delete_action)

    def copy_image(self):
        """Copies the image to the clipboard."""
        QApplication.clipboard().setImage(self.node.image)

    def save_image(self):
        """Opens a file dialog to save the image."""
        file_path, _ = QFileDialog.getSaveFileName(
            None, "Save Image", "", "PNG Images (*.png);;JPEG Images (*.jpg)"
        )
        if file_path:
            self.node.image.save(file_path)

    def regenerate_image(self):
        """Triggers a new image generation using the same prompt."""
        parent_chat_node = self.node.parent_content_node
        if parent_chat_node and parent_chat_node.scene():
            main_window = parent_chat_node.scene().window
            if main_window and hasattr(main_window, 'generate_image'):
                # We can't regenerate from the AI node directly, so we trigger
                # a new generation from the user node that holds the prompt.
                # Here we assume the parent_content_node's text is the prompt.
                main_window.generate_image(parent_chat_node)

    def delete_node(self):
        """Deletes the image node from the scene."""
        scene = self.node.scene()
        if scene and hasattr(scene, 'deleteSelectedItems'):
            scene.clearSelection()
            self.node.setSelected(True)
            scene.deleteSelectedItems()

class ChatNodeContextMenu(QMenu):
    """
    A comprehensive context menu for ChatNode, providing access to text manipulation,
    AI actions (summaries, explainers, charts), and organizational tools.
    """
    def __init__(self, node, parent=None):
        """
        Initializes the ChatNodeContextMenu.

        Args:
            node (ChatNode): The node this menu is for.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.node = node
        self.takeaway_thread = None
        palette = get_current_palette()
        
        self.setStyleSheet(f"""
            QMenu {{
                background-color: #2d2d2d;
                border: 1px solid #3f3f3f;
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 8px 20px;
                border-radius: 4px;
                color: white;
            }}
            QMenu::item:selected {{
                background-color: {palette.SELECTION.name()};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #3f3f3f;
                margin: 4px 0px;
            }}
        """)
        
        copy_action = QAction("Copy Text", self)
        copy_action.setIcon(qta.icon('fa5s.copy', color='white'))
        copy_action.triggered.connect(self.copy_text)
        self.addAction(copy_action)
        
        collapse_text = "Expand Node" if self.node.is_collapsed else "Collapse Node"
        collapse_icon = 'fa5s.expand-arrows-alt' if self.node.is_collapsed else 'fa5s.compress-arrows-alt'
        collapse_action = QAction(collapse_text, self)
        collapse_action.setIcon(qta.icon(collapse_icon, color='white'))
        collapse_action.triggered.connect(self.node.toggle_collapse)
        self.addAction(collapse_action)
        
        self.addSeparator()
        
        export_menu = self.create_export_menu()
        self.addMenu(export_menu)

        scene = self.node.scene()
        is_branch_hidden = getattr(scene, 'is_branch_hidden', False)
        
        visibility_text = "Show All Branches" if is_branch_hidden else "Hide Other Branches"
        visibility_icon = 'fa5s.eye' if is_branch_hidden else 'fa5s.eye-slash'
        visibility_action = QAction(visibility_text, self)
        visibility_action.setIcon(qta.icon(visibility_icon, color='white'))
        visibility_action.triggered.connect(self.toggle_branch_visibility)
        self.addAction(visibility_action)

        if self.node.docked_thinking_nodes:
            self.addSeparator()
            undock_action = QAction("Undock Thinking Node", self)
            undock_action.setIcon(qta.icon('fa5s.expand-arrows-alt', color='white'))
            undock_action.triggered.connect(self.undock_thinking_node)
            self.addAction(undock_action)

        self.addSeparator()

        # Context-aware actions: different options for single vs. multiple selection
        selected_chat_nodes = [item for item in self.node.scene().selectedItems() if isinstance(item, ChatNode)]

        if len(selected_chat_nodes) > 1:
            group_summary_action = QAction("Generate Group Summary", self)
            group_summary_action.setIcon(qta.icon('fa5s.object-group', color='white'))
            group_summary_action.triggered.connect(self.generate_group_summary)
            self.addAction(group_summary_action)
        else:
            doc_view_action = QAction("Open Document View", self)
            doc_view_action.setIcon(qta.icon('fa5s.book-open', color='white'))
            doc_view_action.triggered.connect(self.open_document_view)
            self.addAction(doc_view_action)
            self.addSeparator()

            takeaway_action = QAction("Generate Key Takeaway", self)
            takeaway_action.setIcon(qta.icon('fa5s.lightbulb', color='white'))
            takeaway_action.triggered.connect(self.generate_takeaway)
            self.addAction(takeaway_action)
            
            explainer_action = QAction("Generate Explainer Note", self)
            explainer_action.setIcon(qta.icon('fa5s.question', color='white'))
            explainer_action.triggered.connect(self.generate_explainer)
            self.addAction(explainer_action)
            
            chart_menu = QMenu("Generate Chart", self)
            chart_menu.setIcon(qta.icon('fa5s.chart-bar', color='white'))
            chart_menu.setStyleSheet(self.styleSheet())
            
            chart_types = [
                ("Bar Chart", "bar", 'fa5s.chart-bar'),
                ("Line Graph", "line", 'fa5s.chart-line'),
                ("Histogram", "histogram", 'fa5s.chart-area'),
                ("Pie Chart", "pie", 'fa5s.chart-pie'),
                ("Sankey Diagram", "sankey", 'fa5s.project-diagram')
            ]
            
            for title, chart_type, icon in chart_types:
                action = QAction(title, chart_menu)
                action.setIcon(qta.icon(icon, color='white'))
                action.triggered.connect(lambda checked, t=chart_type: self.generate_chart(t))
                chart_menu.addAction(action)
                
            self.addMenu(chart_menu)
            
            image_gen_action = QAction("Generate Image", self)
            image_gen_action.setIcon(qta.icon('fa5s.image', color='white'))
            image_gen_action.triggered.connect(self.generate_image)
            self.addAction(image_gen_action)
        
        self.addSeparator()
        
        delete_action = QAction("Delete Node", self)
        delete_action.setIcon(qta.icon('fa5s.trash', color='white'))
        delete_action.triggered.connect(self.delete_node)
        self.addAction(delete_action)
        
        # Add regenerate option only for AI nodes
        if not self.node.is_user:
            self.addSeparator()
            
            regenerate_action = QAction("Regenerate Response", self)
            regenerate_action.setIcon(qta.icon('fa5s.sync', color='white'))
            regenerate_action.triggered.connect(self.regenerate_response)
            self.addAction(regenerate_action)
            
        self.destroyed.connect(self.cleanup_thread)

    def undock_thinking_node(self):
        """Undocks the first available thinking node from the parent."""
        if self.node.docked_thinking_nodes:
            # Undock the last-docked node, which is a simple LIFO approach
            node_to_undock = self.node.docked_thinking_nodes.pop(0)
            node_to_undock.undock()
            self.node.update()

    def create_export_menu(self):
        """Creates the 'Export to Doc' submenu."""
        export_menu = QMenu("Export to Doc", self)
        export_menu.setIcon(qta.icon('fa5s.file-export', color='white'))
        
        txt_action = QAction("Text File (.txt)", self)
        txt_action.triggered.connect(lambda: self._handle_export('txt'))
        export_menu.addAction(txt_action)
        
        md_action = QAction("Markdown File (.md)", self)
        md_action.triggered.connect(lambda: self._handle_export('md'))
        export_menu.addAction(md_action)

        html_action = QAction("HTML Document (.html)", self)
        html_action.triggered.connect(lambda: self._handle_export('html'))
        export_menu.addAction(html_action)

        docx_action = QAction("Word Document (.docx)", self)
        docx_action.triggered.connect(lambda: self._handle_export('docx'))
        export_menu.addAction(docx_action)

        pdf_action = QAction("PDF Document (.pdf)", self)
        pdf_action.triggered.connect(lambda: self._handle_export('pdf'))
        export_menu.addAction(pdf_action)
        
        return export_menu

    def _handle_export(self, file_format):
        """
        Handles the export logic for a given file format.

        Args:
            file_format (str): The target file format (e.g., 'txt', 'pdf').
        """
        exporter = Exporter()
        content = self.node.text
        default_filename = f"chat_node_export.{file_format}"

        filters = {
            'txt': "Text Files (*.txt)",
            'pdf': "PDF Documents (*.pdf)",
            'docx': "Word Documents (*.docx)",
            'html': "HTML Files (*.html)",
            'md': "Markdown Files (*.md)"
        }
        
        main_window = self.node.scene().window
        file_path, _ = QFileDialog.getSaveFileName(main_window, "Export Node Content", default_filename, filters[file_format])

        if not file_path:
            return

        success, error_msg = False, "Unknown format"
        try:
            if file_format == 'txt':
                success, error_msg = exporter.export_to_txt(content, file_path)
            elif file_format == 'pdf':
                success, error_msg = exporter.export_to_pdf(content, file_path, is_code=False)
            elif file_format == 'docx':
                success, error_msg = exporter.export_to_docx(content, file_path)
            elif file_format == 'html':
                success, error_msg = exporter.export_to_html(content, file_path)
            elif file_format == 'md':
                success, error_msg = exporter.export_to_md(content, file_path)
        except ImportError as e:
            QMessageBox.warning(main_window, "Dependency Missing", str(e))
            return
        
        if success:
            msg_box = QMessageBox(QMessageBox.Icon.Information, "Export Successful", f"Node content exported to:\n{file_path}", parent=main_window)
            msg_box.setWindowIcon(main_window.windowIcon())
            msg_box.exec()
        else:
            msg_box = QMessageBox(QMessageBox.Icon.Critical, "Export Failed", f"An error occurred during export:\n{error_msg}", parent=main_window)
            msg_box.setWindowIcon(main_window.windowIcon())
            msg_box.exec()

    def toggle_branch_visibility(self):
        """Toggles the visibility of other conversation branches."""
        scene = self.node.scene()
        if scene and hasattr(scene, 'toggle_branch_visibility'):
            scene.toggle_branch_visibility(self.node)
    
    def copy_text(self):
        """Copies the node's text content to the clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.node.text)
    
    def delete_node(self):
        """Deletes the node from the scene."""
        scene = self.node.scene()
        if scene and hasattr(scene, 'delete_chat_node'):
            scene.delete_chat_node(self.node)
    
    def regenerate_response(self):
        """Triggers regeneration of the AI response for this node."""
        main_window = self.node.scene().window
        if not main_window:
            return
        
        if hasattr(main_window, 'regenerate_node'):
            main_window.regenerate_node(self.node)
                
    def cleanup_thread(self):
        """Cleans up any running background threads associated with this menu."""
        if self.takeaway_thread is not None:
            self.takeaway_thread.finished.disconnect()
            self.takeaway_thread.error.disconnect()
            self.takeaway_thread.quit()
            self.takeaway_thread.wait()
            self.takeaway_thread = None
            
    def generate_takeaway(self):
        """Initiates the key takeaway generation process."""
        scene = self.node.scene()
        if scene and scene.window:
            scene.window.generate_takeaway(self.node)

    def generate_group_summary(self):
        """Initiates the group summary generation process."""
        scene = self.node.scene()
        if scene and scene.window:
            scene.window.generate_group_summary()
                
    def handle_takeaway_response(self, response, node_pos):
        """
        Handles the response from the takeaway agent by creating a new note.

        Args:
            response (str): The takeaway summary text.
            node_pos (QPointF): The position of the original node.
        """
        try:
            scene = self.node.scene()
            if not scene:
                return
                
            note_pos = QPointF(node_pos.x() + self.node.width + 50, node_pos.y())
            
            note = scene.add_note(note_pos)
            note.content = response
            note.color = "#2d2d2d"
            note.header_color = "#2ecc71"
            
            if scene.window:
                scene.window.loading_overlay.hide()
                
            self.cleanup_thread()
                
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error creating takeaway note: {str(e)}")
            if scene and scene.window:
                scene.window.loading_overlay.hide()
                
    def handle_takeaway_error(self, error_message):
        """Handles errors from the takeaway agent."""
        QMessageBox.critical(None, "Error", f"Error generating takeaway: {error_message}")
        scene = self.node.scene()
        if scene and scene.window:
            scene.window.loading_overlay.hide()
            
        self.cleanup_thread()
        
    def generate_explainer(self):
        """Initiates the explainer note generation process."""
        scene = self.node.scene()
        if scene and scene.window:
            scene.window.generate_explainer(self.node)
            
    def generate_chart(self, chart_type):
        """
        Initiates the chart generation process.

        Args:
            chart_type (str): The type of chart to generate (e.g., 'bar', 'line').
        """
        scene = self.node.scene()
        if scene and scene.window:
            scene.window.generate_chart(self.node, chart_type)
            
    def generate_image(self):
        """Initiates the image generation process."""
        scene = self.node.scene()
        if scene and scene.window:
            scene.window.generate_image(self.node)

    def open_document_view(self):
        """Opens the document view side panel for this node."""
        scene = self.node.scene()
        if scene and scene.window:
            scene.window.show_document_view(self.node)

class PluginNodeContextMenu(QMenu):
    """
    A context menu for Plugin Nodes (Web, PyCoder, Reasoning, etc.).
    Provides generic actions like Copy Content, Generate Chart, and Delete.
    """
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        palette = get_current_palette()
        
        self.setStyleSheet(f"""
            QMenu {{
                background-color: #2d2d2d;
                border: 1px solid #3f3f3f;
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 8px 20px;
                border-radius: 4px;
                color: white;
            }}
            QMenu::item:selected {{
                background-color: {palette.SELECTION.name()};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #3f3f3f;
                margin: 4px 0px;
            }}
        """)
        
        copy_action = QAction("Copy Content", self)
        copy_action.setIcon(qta.icon('fa5s.copy', color='white'))
        copy_action.triggered.connect(self.copy_content)
        self.addAction(copy_action)

        self.addSeparator()
        
        chart_menu = QMenu("Generate Chart", self)
        chart_menu.setIcon(qta.icon('fa5s.chart-bar', color='white'))
        chart_menu.setStyleSheet(self.styleSheet()) # Inherit style
        
        chart_types = [
            ("Bar Chart", "bar", 'fa5s.chart-bar'),
            ("Line Graph", "line", 'fa5s.chart-line'),
            ("Histogram", "histogram", 'fa5s.chart-area'),
            ("Pie Chart", "pie", 'fa5s.chart-pie'),
            ("Sankey Diagram", "sankey", 'fa5s.project-diagram')
        ]
        
        for title, chart_type, icon in chart_types:
            action = QAction(title, chart_menu)
            action.setIcon(qta.icon(icon, color='white'))
            action.triggered.connect(lambda checked, t=chart_type: self.generate_chart(t))
            chart_menu.addAction(action)
            
        self.addMenu(chart_menu)
        
        self.addSeparator()
        
        delete_action = QAction("Delete Node", self)
        delete_action.setIcon(qta.icon('fa5s.trash', color='white'))
        delete_action.triggered.connect(self.delete_node)
        self.addAction(delete_action)

    def copy_content(self):
        QApplication.clipboard().setText(self.node.text)

    def generate_chart(self, chart_type):
        scene = self.node.scene()
        if scene and hasattr(scene, 'window'):
            scene.window.generate_chart(self.node, chart_type)

    def delete_node(self):
        scene = self.node.scene()
        if scene and hasattr(scene, 'deleteSelectedItems'):
            scene.clearSelection()
            self.node.setSelected(True)
            scene.deleteSelectedItems()