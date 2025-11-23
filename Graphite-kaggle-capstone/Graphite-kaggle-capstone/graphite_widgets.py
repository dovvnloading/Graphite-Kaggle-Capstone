import qtawesome as qta
from PySide6.QtWidgets import (
    QApplication, QGraphicsDropShadowEffect, QStyle, QStyleOptionSlider, QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QFrame, QGridLayout,
    QSizePolicy, QScrollArea, QSlider, QLineEdit, QGraphicsObject, QCheckBox, QMenu, QComboBox, QMainWindow,
    QGraphicsItem, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, QTimer, QPointF, Property, QParallelAnimationGroup, QPropertyAnimation, QEasingCurve, QRectF, QSize, QRect, QPoint, QEvent
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QPainterPath, QBrush, QLinearGradient, QPen, QShortcut, QKeySequence, QFont, QAction, QGuiApplication
import re
from graphite_config import get_current_palette, get_asset_path

# Conditional import for spellchecker
try:
    from spellchecker import SpellChecker
    SPELLCHECK_AVAILABLE = True
except ImportError:
    SPELLCHECK_AVAILABLE = False


class HoverAnimationMixin:
    """
    A mixin class that provides functionality for triggering an animated effect
    on ancestor connections after a long hover.

    When a node is hovered over for a set duration, this mixin traces back
    through its parent connections, activating an animated arrow flow to visualize
    the conversational path leading to the hovered node.
    """
    def __init__(self):
        """Initializes the HoverAnimationMixin."""
        self.incoming_connection = None # The connection leading *to* this node.
        # A single-shot timer to detect a "long hover".
        self.long_hover_timer = QTimer()
        self.long_hover_timer.setSingleShot(True)
        self.long_hover_timer.setInterval(750) # 750ms delay before triggering.
        self.long_hover_timer.timeout.connect(self.trigger_ancestor_animation)

    def trigger_ancestor_animation(self):
        """
        Starts the arrow animation on the incoming connection and recursively
        calls this method on its parent node to animate the entire ancestral path.
        """
        if self.incoming_connection:
            self.incoming_connection.startArrowAnimation()
        
        parent = getattr(self, 'parent_node', None)
        if parent and hasattr(parent, 'trigger_ancestor_animation'):
            parent.trigger_ancestor_animation()

    def stop_ancestor_animation(self):
        """
        Stops the arrow animation on the incoming connection and recursively
        calls this method on its parent node to stop all animations in the path.
        """
        if self.incoming_connection:
            self.incoming_connection.stopArrowAnimation()
            
        parent = getattr(self, 'parent_node', None)
        if parent and hasattr(parent, 'stop_ancestor_animation'):
            parent.stop_ancestor_animation()

    def _handle_hover_enter(self, event):
        """
        A standardized hover enter handler for any QGraphicsItem using this mixin.
        It sets the hover state and starts the long-hover timer.
        """
        self.hovered = True
        self.long_hover_timer.start()
        self.update()

    def _handle_hover_leave(self, event):
        """
        A standardized hover leave handler. It clears the hover state, stops the
        timer, and stops any active ancestor animations.
        """
        self.hovered = False
        self.long_hover_timer.stop()
        self.stop_ancestor_animation()
        self.update()


class CustomTooltip(QLabel):
    """A custom styled tooltip widget that appears frameless and translucent."""
    def __init__(self, parent=None):
        """
        Initializes the CustomTooltip.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 30, 30, 0.9);
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
            }
        """)

class NavigationPin:
    """
    A dummy class representing a navigation pin for type hinting or mocking purposes.
    The actual implementation is in `graphite_canvas_items.py`.
    """
    def __init__(self):
        """Initializes a dummy NavigationPin."""
        self.title = "Dummy Pin"
        self.note = ""
        self.scene = lambda: None # Mock scene method

class CustomScrollBar(QWidget):
    """
    A custom-painted scrollbar widget with a modern, minimalist look.
    """
    valueChanged = Signal(float)
    
    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        """
        Initializes the CustomScrollBar.

        Args:
            orientation (Qt.Orientation, optional): The orientation of the scrollbar.
                                                    Defaults to Qt.Orientation.Vertical.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.orientation = orientation
        self.value = 0
        self.handle_position = 0
        self.handle_pressed = False
        self.hover = False
        
        self.min_val = 0
        self.max_val = 99
        self.page_step = 10
        
        if orientation == Qt.Orientation.Vertical:
            self.setFixedWidth(8)
        else:
            self.setFixedHeight(8)
            
        self.setMouseTracking(True)
        
    def setRange(self, min_val, max_val):
        """
        Sets the minimum and maximum values for the scrollbar.

        Args:
            min_val (float): The minimum scroll value.
            max_val (float): The maximum scroll value.
        """
        self.min_val = min_val
        self.max_val = max(min_val + 0.1, max_val) # Ensure max is always greater than min
        self.value = max(min_val, min(self.value, max_val))
        self.update()
        
    def setValue(self, value):
        """
        Sets the current value of the scrollbar.

        Args:
            value (float): The new value to set.
        """
        old_value = self.value
        self.value = max(self.min_val, min(self.max_val, value))
        if self.value != old_value:
            self.valueChanged.emit(self.value)
            self.update()
        
    def paintEvent(self, event):
        """
        Handles the custom painting of the scrollbar track and handle.

        Args:
            event (QPaintEvent): The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw the track
        track_color = QColor("#2A2A2A")
        track_color.setAlpha(100)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        
        if self.orientation == Qt.Orientation.Vertical:
            painter.drawRoundedRect(1, 0, self.width() - 2, self.height(), 4, 4)
        else:
            painter.drawRoundedRect(0, 1, self.width(), self.height() - 2, 4, 4)
            
        range_size = self.max_val - self.min_val
        if range_size <= 0:
            return
            
        # Calculate handle size based on the visible ratio (page step vs total range)
        visible_ratio = min(1.0, self.page_step / (range_size + self.page_step))
        
        if self.orientation == Qt.Orientation.Vertical:
            handle_size = max(20, int(self.height() * visible_ratio))
            available_space = max(0, self.height() - handle_size)
            if range_size > 0:
                handle_position = int(available_space * 
                    ((self.value - self.min_val) / range_size))
            else:
                handle_position = 0
        else:
            handle_size = max(20, int(self.width() * visible_ratio))
            available_space = max(0, self.width() - handle_size)
            if range_size > 0:
                handle_position = int(available_space * 
                    ((self.value - self.min_val) / range_size))
            else:
                handle_position = 0
            
        # Draw the handle
        handle_color = QColor("#6a6a6a") if self.hover else QColor("#555555")
        painter.setBrush(handle_color)
        
        if self.orientation == Qt.Orientation.Vertical:
            painter.drawRoundedRect(1, handle_position, self.width() - 2, handle_size, 3, 3)
        else:
            painter.drawRoundedRect(handle_position, 1, handle_size, self.height() - 2, 3, 3)
            
    def mousePressEvent(self, event):
        """
        Handles mouse press events to initiate dragging the handle.

        Args:
            event (QMouseEvent): The mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.handle_pressed = True
            self.mouse_start_pos = event.position().toPoint()
            self.start_value = self.value
            
    def mouseMoveEvent(self, event):
        """
        Handles mouse move events to update hover state and drag the handle.

        Args:
            event (QMouseEvent): The mouse event.
        """
        self.hover = True
        self.update()
        
        if self.handle_pressed:
            if self.orientation == Qt.Orientation.Vertical:
                delta = event.position().toPoint().y() - self.mouse_start_pos.y()
                available_space = max(1, self.height() - 20)
                delta_ratio = delta / available_space
            else:
                delta = event.position().toPoint().x() - self.mouse_start_pos.x()
                available_space = max(1, self.width() - 20)
                delta_ratio = delta / available_space
                
            range_size = self.max_val - self.min_val
            new_value = self.start_value + delta_ratio * range_size
            self.setValue(new_value)
            
    def mouseReleaseEvent(self, event):
        """
        Handles mouse release events to stop dragging the handle.

        Args:
            event (QMouseEvent): The mouse event.
        """
        self.handle_pressed = False
        
    def enterEvent(self, event):
        """
        Handles the mouse entering the widget area to update hover state.

        Args:
            event (QEnterEvent): The enter event.
        """
        self.hover = True
        self.update()
        
    def leaveEvent(self, event):
        """
        Handles the mouse leaving the widget area to update hover state.

        Args:
            event (QEvent): The leave event.
        """
        self.hover = False
        self.update()

class CustomScrollArea(QWidget):
    """A container widget that uses CustomScrollBar widgets for its scrollbars."""
    def __init__(self, widget):
        """
        Initializes the CustomScrollArea.

        Args:
            widget (QWidget): The content widget to be placed inside the scroll area.
        """
        super().__init__()
        self.widget = widget
        
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # The viewport holds the content widget.
        self.viewport = QWidget()
        self.viewport.setLayout(QVBoxLayout())
        self.viewport.layout().setContentsMargins(0, 0, 0, 0)
        self.viewport.layout().addWidget(widget)
        
        self.v_scrollbar = CustomScrollBar(Qt.Orientation.Vertical)
        self.h_scrollbar = CustomScrollBar(Qt.Orientation.Horizontal)
        
        layout.addWidget(self.viewport, 0, 0)
        layout.addWidget(self.v_scrollbar, 0, 1)
        layout.addWidget(self.h_scrollbar, 1, 0)
        
        self.v_scrollbar.valueChanged.connect(self.updateVerticalScroll)
        self.h_scrollbar.valueChanged.connect(self.updateHorizontalScroll)
        
    def updateScrollbars(self):
        """
        Updates the visibility and range of the scrollbars based on content size.
        """
        content_height = self.widget.height()
        viewport_height = self.viewport.height()
        
        if content_height > viewport_height:
            self.v_scrollbar.setRange(0, content_height - viewport_height)
            self.v_scrollbar.page_step = viewport_height
            self.v_scrollbar.show()
        else:
            self.v_scrollbar.hide()
            
        content_width = self.widget.width()
        viewport_width = self.viewport.width()
        
        if content_width > viewport_width:
            self.h_scrollbar.setRange(0, content_width - viewport_width)
            self.h_scrollbar.page_step = viewport_width
            self.h_scrollbar.show()
        else:
            self.h_scrollbar.hide()
            
    def updateVerticalScroll(self, value):
        """
        Slot to move the viewport vertically when the vertical scrollbar's value changes.

        Args:
            value (float): The new vertical scroll value.
        """
        self.viewport.move(self.viewport.x(), -int(value))
        
    def updateHorizontalScroll(self, value):
        """
        Slot to move the viewport horizontally when the horizontal scrollbar's value changes.

        Args:
            value (float): The new horizontal scroll value.
        """
        self.viewport.move(-int(value), self.viewport.y())
        
    def resizeEvent(self, event):
        """
        Handles resize events to update the scrollbars.

        Args:
            event (QResizeEvent): The resize event.
        """
        super().resizeEvent(event)
        self.updateScrollbars()

class ScrollHandle(QGraphicsObject):
    """A QGraphicsObject representing the draggable handle of a custom scrollbar."""
    def __init__(self, parent=None):
        """
        Initializes the ScrollHandle.

        Args:
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.width = 6
        self.min_height = 20
        self.height = self.min_height
        self.hover = False
        self.dragging = False
        self.start_drag_pos = None
        self.start_drag_value = 0
        self.setAcceptHoverEvents(True)
        
    def boundingRect(self):
        """
        Returns the bounding rectangle of the handle.

        Returns:
            QRectF: The bounding rectangle.
        """
        return QRectF(0, 0, self.width, self.height)
        
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the scrollbar handle.

        Args:
            painter (QPainter): The painter to use.
            option (QStyleOptionGraphicsItem): Provides style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
        color = QColor("#6a6a6a") if self.hover else QColor("#555555")
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
    
        painter.drawRoundedRect(0, 0, int(self.width), int(self.height), 3.0, 3.0)
        
    def hoverEnterEvent(self, event):
        """Updates hover state when the mouse enters the handle."""
        self.hover = True
        self.update()
        super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        """Updates hover state when the mouse leaves the handle."""
        self.hover = False
        self.update()
        super().hoverLeaveEvent(event)

class ScrollBar(QGraphicsObject):
    """
    A QGraphicsObject implementing a custom scrollbar, designed for use within a QGraphicsScene.
    """
    valueChanged = Signal(float)

    def __init__(self, parent=None):
        """
        Initializes the ScrollBar.

        Args:
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.width = 8
        self.height = 0
        self.value = 0 # Value is a float between 0.0 and 1.0
        self.handle = ScrollHandle(self)
        self.update_handle_position()
        
    def boundingRect(self):
        """
        Returns the bounding rectangle of the scrollbar.

        Returns:
            QRectF: The bounding rectangle.
        """
        return QRectF(0, 0, self.width, self.height)
        
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the scrollbar track.

        Args:
            painter (QPainter): The painter to use.
            option (QStyleOptionGraphicsItem): Provides style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        track_color = QColor("#2A2A2A")
        track_color.setAlpha(100)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(1, 0, self.width - 2, self.height, 4, 4)
        
    def set_range(self, visible_ratio):
        """
        Sets the size of the handle based on the ratio of visible content.

        Args:
            visible_ratio (float): The ratio of the visible area to the total content area.
        """
        self.handle.height = max(self.handle.min_height, 
                               self.height * visible_ratio)
        self.update_handle_position()
        
    def set_value(self, value):
        """
        Sets the current scroll value (0.0 to 1.0).

        Args:
            value (float): The new scroll value.
        """
        new_value = max(0, min(1, value))
        if self.value != new_value:
            self.value = new_value
            self.valueChanged.emit(self.value)
            self.update_handle_position()
        
    def update_handle_position(self):
        """Updates the visual position of the handle based on the current value."""
        max_y = self.height - self.handle.height
        self.handle.setPos(1, self.value * max_y)
        
    def mousePressEvent(self, event):
        """
        Handles mouse press events on the scrollbar for dragging or page-stepping.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse event.
        """
        handle_pos = self.handle.pos().y()
        click_pos = event.pos().y()
        
        # If the click is on the handle, start dragging.
        if handle_pos <= click_pos <= handle_pos + self.handle.height:
            self.handle.dragging = True
            self.handle.start_drag_pos = click_pos
            self.handle.start_drag_value = self.value
        # If the click is on the track, jump to that position.
        else:
            click_ratio = click_pos / self.height
            self.set_value(click_ratio)
                
    def mouseMoveEvent(self, event):
        """
        Handles mouse move events when dragging the handle.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse event.
        """
        if self.handle.dragging:
            delta = event.pos().y() - self.handle.start_drag_pos
            available_space = self.height - self.handle.height
            if available_space > 0:
                delta_ratio = delta / available_space
                new_value = self.handle.start_drag_value + delta_ratio
                self.set_value(new_value)
                
    def mouseReleaseEvent(self, event):
        """
        Handles mouse release events to stop dragging.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse event.
        """
        self.handle.dragging = False
        self.handle.start_drag_pos = None

class SpellCheckLineEdit(QLineEdit):
    """
    A QLineEdit subclass that provides real-time spell checking with squiggly underlines
    and a context menu for suggestions.
    """
    def __init__(self, parent=None):
        """
        Initializes the SpellCheckLineEdit.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        if not SPELLCHECK_AVAILABLE:
            return

        self.spell = SpellChecker()
        self.misspelled_words = set()
        self.error_spans = []

        self.textChanged.connect(self._check_spelling)

    def _check_spelling(self, text):
        """
        Checks the spelling of the text and updates the list of misspelled words.

        Args:
            text (str): The current text of the line edit.
        """
        self.misspelled_words.clear()
        self.error_spans.clear()
        
        # Use regex to find all words in the text.
        words = re.finditer(r'\b\w+\b', text)
        for match in words:
            word = match.group(0)
            if self.spell.unknown([word]):
                self.misspelled_words.add(word)
                self.error_spans.append((match.start(), match.end()))
        
        self.update() # Trigger a repaint to draw squiggles.

    def paintEvent(self, event):
        """
        Overrides the paint event to draw wavy red lines under misspelled words.

        Args:
            event (QPaintEvent): The paint event.
        """
        super().paintEvent(event)
        if not self.error_spans:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        pen = QPen(Qt.red)
        pen.setCosmetic(True)
        painter.setPen(pen)

        fm = self.fontMetrics()
        text = self.text()
        
        # Calculate the precise rectangle where the text is drawn, considering style and margins.
        from PySide6.QtWidgets import QStyle, QStyleOptionFrame
        opt = QStyleOptionFrame()
        self.initStyleOption(opt)
        contents = self.style().subElementRect(QStyle.SubElement.SE_LineEditContents, opt)
        left_m, top_m, right_m, bottom_m = self.getTextMargins()
        text_rect = contents.adjusted(left_m, top_m, -right_m, -bottom_m)
        
        # Account for vertical centering and horizontal scroll offset.
        vpad = max(0, (text_rect.height() - fm.height()) // 2)
        cur_idx = self.cursorPosition()
        cur_left = self.cursorRect().left()
        x_offset = cur_left - fm.horizontalAdvance(text[:cur_idx])
        
        # Determine the Y position for the baseline of the squiggles.
        baseline_y = (
            text_rect.top()
            + vpad
            + fm.ascent()
            + max(2, int(fm.descent() * 0.95))
        )

        # Draw squiggly lines for each misspelled word.
        wave_len = 4
        wave_amp = 1.5
        clip_left, clip_right = text_rect.left(), text_rect.right()

        for start, end in self.error_spans:
            sx = text_rect.left() + fm.horizontalAdvance(text[:start]) + x_offset
            ex = text_rect.left() + fm.horizontalAdvance(text[:end]) + x_offset

            # Clip the drawing to the visible area of the line edit.
            if ex < clip_left or sx > clip_right:
                continue
            sx = max(sx, clip_left)
            ex = min(ex, clip_right)

            path = QPainterPath()
            x = sx
            path.moveTo(x, baseline_y)
            # Create the wavy path using quadratic curves.
            while x < ex:
                mid = x + wave_len / 2.0
                nx = min(x + wave_len, ex)
                path.quadTo(mid, baseline_y + wave_amp, nx, baseline_y)
                x = nx

            painter.strokePath(path, pen)

    def getStyleOption(self):
        """
        Helper method to get the style options for the line edit.

        Returns:
            QStyleOptionFrame: The style options.
        """
        from PySide6.QtWidgets import QStyleOptionFrame
        opt = QStyleOptionFrame()
        self.initStyleOption(opt)
        return opt

    def contextMenuEvent(self, event):
        """
        Overrides the context menu event to add spelling suggestions.

        Args:
            event (QContextMenuEvent): The context menu event.
        """
        if not SPELLCHECK_AVAILABLE:
            super().contextMenuEvent(event)
            return

        menu = self.createStandardContextMenu()
        
        char_index = self.cursorPositionAt(event.pos())
        
        # Find if the click was on a misspelled word.
        word_span = None
        clicked_word = ""
        for start, end in self.error_spans:
            if start <= char_index < end:
                word_span = (start, end)
                clicked_word = self.text()[start:end]
                break

        # If a misspelled word was clicked, add suggestions to the menu.
        if clicked_word:
            suggestions = self.spell.candidates(clicked_word)
            if suggestions:
                menu.addSeparator()
                for suggestion in sorted(list(suggestions))[:5]:
                    action = QAction(suggestion, self)
                    action.triggered.connect(lambda checked=False, s=suggestion, ws=word_span: self._replace_word(s, ws[0], ws[1]))
                    menu.addAction(action)

        menu.exec(event.globalPos())

    def _replace_word(self, suggestion, start, end):
        """
        Replaces a misspelled word with a selected suggestion.

        Args:
            suggestion (str): The suggested word.
            start (int): The starting index of the word to replace.
            end (int): The ending index of the word to replace.
        """
        current_text = self.text()
        new_text = current_text[:start] + suggestion + current_text[end:]
        self.setText(new_text)

class LoadingAnimation(QGraphicsObject):
    """A QGraphicsObject that displays a multi-arc spinning loading animation."""
    def __init__(self, parent=None):
        """
        Initializes the LoadingAnimation.

        Args:
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.setZValue(100) # Ensure it renders on top
        self._angle1 = 0.0
        self._angle2 = 0.0
        self._angle3 = 0.0

        # Animation for the first (outer) arc
        self.anim1 = QPropertyAnimation(self, b'angle1')
        self.anim1.setStartValue(0)
        self.anim1.setEndValue(360)
        self.anim1.setDuration(1200)
        self.anim1.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # Animation for the second (middle) arc
        self.anim2 = QPropertyAnimation(self, b'angle2')
        self.anim2.setStartValue(70)
        self.anim2.setEndValue(430)
        self.anim2.setDuration(1000)
        self.anim2.setEasingCurve(QEasingCurve.Type.InOutSine)

        # Animation for the third (inner) arc
        self.anim3 = QPropertyAnimation(self, b'angle3')
        self.anim3.setStartValue(140)
        self.anim3.setEndValue(500)
        self.anim3.setDuration(1500)
        self.anim3.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Group animations to run in parallel and loop indefinitely.
        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.anim1)
        self.anim_group.addAnimation(self.anim2)
        self.anim_group.addAnimation(self.anim3)
        self.anim_group.setLoopCount(-1)

    def boundingRect(self):
        """Returns the bounding rectangle of the animation."""
        return QRectF(-20, -20, 40, 40)

    def paint(self, painter, option, widget):
        """
        Paints the three rotating arcs.

        Args:
            painter (QPainter): The painter to use.
            option (QStyleOptionGraphicsItem): Provides style options.
            widget (QWidget): The widget being painted on.
        """
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen1 = QPen(palette.USER_NODE, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen1)
        painter.drawArc(self.boundingRect().toRect(), int(self._angle1 * 16), 120 * 16)
        
        pen2 = QPen(palette.AI_NODE, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawArc(self.boundingRect().adjusted(5, 5, -5, -5).toRect(), int(self._angle2 * 16), 120 * 16)

        pen3 = QPen(palette.NAV_HIGHLIGHT.darker(120), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen3)
        painter.drawArc(self.boundingRect().adjusted(10, 10, -10, -10).toRect(), int(self._angle3 * 16), 120 * 16)

    def start(self):
        """Starts the animation."""
        self.anim_group.start()

    def stop(self):
        """Stops the animation."""
        self.anim_group.stop()

    # Define properties for the animation angles to be animated by QPropertyAnimation.
    @Property(float)
    def angle1(self):
        return self._angle1

    @angle1.setter
    def angle1(self, value):
        self._angle1 = value
        self.update()

    @Property(float)
    def angle2(self):
        return self._angle2

    @angle2.setter
    def angle2(self, value):
        self._angle2 = value
        self.update()

    @Property(float)
    def angle3(self):
        return self._angle3

    @angle3.setter
    def angle3(self, value):
        self._angle3 = value
        self.update()

class SearchOverlay(QWidget):
    """
    An overlay widget for finding text within the application.
    It includes an input field, result count, and navigation buttons.
    """
    textChanged = Signal(str)
    findNext = Signal()
    findPrevious = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        """
        Initializes the SearchOverlay.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setFixedWidth(300)
        self.setObjectName("searchOverlay")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find...")
        self.search_input.textChanged.connect(self.textChanged.emit)
        self.search_input.returnPressed.connect(self.findNext.emit)
        layout.addWidget(self.search_input)

        self.results_label = QLabel("0 / 0")
        layout.addWidget(self.results_label)

        prev_btn = QPushButton(qta.icon('fa5s.chevron-up', color='white'), "")
        prev_btn.setFixedSize(24, 24)
        prev_btn.setToolTip("Previous match (Shift+Enter)")
        prev_btn.clicked.connect(self.findPrevious.emit)
        layout.addWidget(prev_btn)
        
        # Add keyboard shortcuts for navigation.
        QShortcut(QKeySequence("Shift+Return"), self.search_input, self.findPrevious.emit)
        QShortcut(QKeySequence("Shift+Enter"), self.search_input, self.findPrevious.emit)

        next_btn = QPushButton(qta.icon('fa5s.chevron-down', color='white'), "")
        next_btn.setFixedSize(24, 24)
        next_btn.setToolTip("Next match (Enter)")
        next_btn.clicked.connect(self.findNext.emit)
        layout.addWidget(next_btn)
        
        close_btn = QPushButton(qta.icon('fa5s.times', color='white'), "")
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.closed.emit)
        layout.addWidget(close_btn)
        
        QShortcut(QKeySequence("Esc"), self, self.closed.emit)

        self.setStyleSheet("""
            QWidget#searchOverlay {
                background-color: #2d2d2d;
                border: 1px solid #3f3f3f;
                border-radius: 5px;
            }
            QLabel { color: #ccc; background-color: transparent; }
            QLineEdit {
                border: 1px solid #555;
                background-color: #3f3f3f;
                border-radius: 3px;
                padding: 4px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)

    def update_results_label(self, current, total):
        """
        Updates the label showing the current match and total matches.

        Args:
            current (int): The index of the current match (1-based).
            total (int): The total number of matches found.
        """
        self.results_label.setText(f"{current} / {total}")
        # Change color based on whether matches are found.
        if total > 0 and current > 0:
            self.results_label.setStyleSheet("color: #fff;")
        elif total > 0 and current == 0:
             self.results_label.setStyleSheet("color: #ccc;")
        else:
            self.results_label.setStyleSheet("color: #e74c3c;")

    def focus_input(self):
        """Sets focus to the search input field and selects its text."""
        self.search_input.setFocus()
        self.search_input.selectAll()

class PinOverlay(QWidget):
    """
    An overlay widget that displays a list of navigation pins, allowing users
    to create new pins and navigate to existing ones.
    """
    closed = Signal()

    def __init__(self, parent=None):
        """
        Initializes the PinOverlay.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.window = parent
        self.setFixedWidth(250 + 30)
        self.setMinimumHeight(400)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(15, 15, 15, 15)
        
        self.container = QWidget()
        self.container.setObjectName("pinContainer")
        outer_layout.addWidget(self.container)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 2)
        self.container.setGraphicsEffect(shadow)
        
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.pins = []
        
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)
        
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.map-marked-alt', color='white').pixmap(QSize(16, 16)))
        header_layout.addWidget(icon_label)
        
        self.header_text = QLabel("Navigation Pins")
        self.header_text.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        header_layout.addWidget(self.header_text)
        header_layout.addStretch()

        close_btn = QPushButton(qta.icon('fa5s.times', color='white'), "")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("background-color: transparent; border: none;")
        close_btn.clicked.connect(self.closed.emit)
        header_layout.addWidget(close_btn)

        main_layout.addWidget(header_widget)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.pin_list = QWidget()
        self.pin_layout = QVBoxLayout(self.pin_list)
        self.pin_layout.setSpacing(5)
        self.pin_layout.setContentsMargins(5, 5, 5, 5)
        self.pin_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll.setWidget(self.pin_list)
        main_layout.addWidget(self.scroll)
        
        self.add_btn = QPushButton("Drop New Pin")
        self.add_btn.setIcon(qta.icon('fa5s.map-pin', color='white'))
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self.create_pin)
        main_layout.addWidget(self.add_btn)
        
        self.on_theme_changed()

    def on_theme_changed(self):
        """Updates the widget's stylesheet when the application theme changes."""
        palette = get_current_palette()
        bg_color = palette.SELECTION
        
        # Determine brightness to choose contrasting text color for buttons.
        brightness = (bg_color.red() * 299 + bg_color.green() * 587 + bg_color.blue() * 114) / 1000
        text_color = "black" if brightness > 128 else "white"

        self.add_btn.setIcon(qta.icon('fa5s.map-pin', color=text_color))

        self.setStyleSheet(f"""
            PinOverlay {{
                background-color: transparent;
            }}
            QWidget#pinContainer {{
                background-color: #252526;
                border-radius: 8px;
            }}
            QPushButton {{
                background-color: {bg_color.name()};
                border: none;
                border-radius: 5px;
                padding: 10px;
                color: {text_color};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {bg_color.lighter(110).name()};
            }}
            QPushButton:disabled {{
                background-color: #555555;
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: #2d2d2d; width: 8px; margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #3f3f3f; min-height: 20px; border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        # Refresh the pin list to update styles of existing pin buttons.
        self.refresh_pins()


    def refresh_pins(self):
        """
        Clears and rebuilds the list of pin buttons from the internal `self.pins` list.
        """
        # Filter out any pins that might have been deleted from the scene elsewhere.
        self.pins = [pin for pin in self.pins if pin.scene() is not None]

        # Clear existing widgets from the layout.
        while self.pin_layout.count():
            item = self.pin_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for pin in self.pins:
            if pin.scene():
                self._create_pin_button(pin)

        # Disable adding new pins if the limit is reached.
        self.add_btn.setEnabled(len(self.pins) < 10)

    def _create_pin_button(self, pin):
        """
        Creates a single widget for a navigation pin.

        Args:
            pin (NavigationPin): The pin object to create a button for.
        """
        palette = get_current_palette()
        pin_widget = QWidget()
        pin_widget.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                border-radius: 5px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 3px;
                padding: 8px;
                color: white;
                text-align: left;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)
        
        layout = QHBoxLayout(pin_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        btn = QPushButton(pin.title)
        btn.setIcon(qta.icon('fa5s.map-pin', color=palette.NAV_HIGHLIGHT.name()))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.navigate_to_pin(pin))
        layout.addWidget(btn, stretch=1)
        
        del_btn = QPushButton()
        del_btn.setIcon(qta.icon('fa5s.times', color='#666666'))
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.remove_pin(pin))
        layout.addWidget(del_btn)
        
        self.pin_layout.addWidget(pin_widget)

    def create_pin(self):
        """Creates a new navigation pin at the center of the current view."""
        if len(self.pins) >= 10:
            return
            
        scene = self.window.scene()
        view = self.window
        center = view.mapToScene(view.viewport().rect().center())
        
        pin = scene.add_navigation_pin(center)
        self.pins.append(pin)
        self.refresh_pins()

    def remove_pin(self, pin):
        """
        Removes a pin from both the overlay and the scene.

        Args:
            pin (NavigationPin): The pin object to remove.
        """
        if pin in self.pins:
            scene = self.window.scene()

            if pin in scene.pins:
                scene.pins.remove(pin)

            if pin.scene() == scene:
                scene.removeItem(pin)

            self.pins.remove(pin)
            self.refresh_pins()

    def navigate_to_pin(self, pin):
        """
        Centers the view on the specified pin.

        Args:
            pin (NavigationPin): The pin to navigate to.
        """
        if pin.scene():
            view = self.window
            view.centerOn(pin)
            pin.setSelected(True)

    def clear_pins(self):
        """Removes all pins from the overlay."""
        self.pins.clear()
        
        while self.pin_layout.count():
            item = self.pin_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self.add_btn.setEnabled(True)

    def update_pin(self, pin):
        """
        Refreshes the pin list if a specific pin has been updated.

        Args:
            pin (NavigationPin): The updated pin.
        """
        if pin in self.pins and pin.scene():
            self.refresh_pins()
            
    def add_pin_button(self, pin):
        """
        Adds a button for an existing pin (e.g., when loading from a file).

        Args:
            pin (NavigationPin): The pin to add a button for.
        """
        if len(self.pins) >= 10 or pin in self.pins:
            return

        if pin.scene():
            self.pins.append(pin)
            self.refresh_pins()

class PrecisionSlider(QSlider):
    """
    A custom slider that eliminates 'slop' by jumping exactly to the clicked position
    and tracking the mouse precisely (centered on handle) during drags.
    """
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        """Jump directly to the value under the mouse on click."""
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            val = self._pixel_to_value(event.pos())
            self.setValue(val)
            self.sliderPressed.emit()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Track mouse movement precisely."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            event.accept()
            val = self._pixel_to_value(event.pos())
            self.setValue(val)
            self.sliderMoved.emit(val)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle release."""
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.sliderReleased.emit()
        else:
            super().mouseReleaseEvent(event)

    def _pixel_to_value(self, pos):
        """Calculates the logical value from the physical pixel position, centering the handle."""
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        
        # Get geometry of the groove and handle
        groove_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
        )
        handle_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
        )

        if self.orientation() == Qt.Orientation.Horizontal:
            handle_length = handle_rect.width()
            slider_start = groove_rect.x()
            slider_end = groove_rect.right() - handle_length + 1
            
            # IMPORTANT: Offset the click by half the handle width to center it
            click_coord = pos.x() - (handle_length / 2)
        else:
            handle_length = handle_rect.height()
            slider_start = groove_rect.y()
            slider_end = groove_rect.bottom() - handle_length + 1
            
            # IMPORTANT: Offset the click by half the handle height to center it
            click_coord = pos.y() - (handle_length / 2)

        # The span available for the handle to move (track length - handle length)
        span = slider_end - slider_start

        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(),
            int(click_coord - slider_start), int(span),
            opt.upsideDown
        )

class PrecisionSlider(QSlider):
    """
    A custom slider that eliminates 'slop' by jumping exactly to the clicked position,
    tracking the mouse precisely (centered on handle), and ensuring proper visual states.
    """
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Enable mouse tracking to ensure hover effects update instantly
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        """Jump directly to the value under the mouse on click and set pressed state."""
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            # Crucial: Tell Qt the slider is being interacted with to trigger :pressed styles
            self.setSliderDown(True)
            val = self._pixel_to_value(event.pos())
            self.setValue(val)
            self.sliderPressed.emit()
            self.repaint() # Force immediate redraw
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Track mouse movement precisely."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            event.accept()
            val = self._pixel_to_value(event.pos())
            self.setValue(val)
            self.sliderMoved.emit(val)
            self.repaint()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle release and reset pressed state."""
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.setSliderDown(False) # Release the visual pressed state
            self.sliderReleased.emit()
            self.repaint()
        else:
            super().mouseReleaseEvent(event)

    def _pixel_to_value(self, pos):
        """Calculates the logical value from the physical pixel position, centering the handle."""
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        
        # Get geometry of the groove and handle
        groove_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
        )
        handle_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
        )

        if self.orientation() == Qt.Orientation.Horizontal:
            handle_length = handle_rect.width()
            slider_start = groove_rect.x()
            slider_end = groove_rect.right() - handle_length + 1
            
            # IMPORTANT: Offset the click by half the handle width to center it
            click_coord = pos.x() - (handle_length / 2)
        else:
            handle_length = handle_rect.height()
            slider_start = groove_rect.y()
            slider_end = groove_rect.bottom() - handle_length + 1
            
            # IMPORTANT: Offset the click by half the handle height to center it
            click_coord = pos.y() - (handle_length / 2)

        # The span available for the handle to move (track length - handle length)
        span = slider_end - slider_start

        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(),
            int(click_coord - slider_start), int(span),
            opt.upsideDown
        )

class ControlsPanel(QWidget):
    """
    A unified control panel for managing canvas navigation, grid settings, and typography.
    """
    # Signals for View Navigation
    dragSpeedChanged = Signal(float)
    
    # Signals for Grid Control
    gridOpacityChanged = Signal(float)
    gridSizeChanged = Signal(int)
    gridStyleChanged = Signal(str)
    gridColorChanged = Signal(QColor)
    snapToGridChanged = Signal(bool)
    orthogonalConnectionsChanged = Signal(bool)
    smartGuidesChanged = Signal(bool)
    
    # Signals for Typography
    fontFamilyChanged = Signal(str)
    fontSizeChanged = Signal(int)
    fontColorChanged = Signal(QColor)
    
    # Signal to close the panel
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Default State
        self.grid_size = 10
        self.grid_opacity = 0.3
        self.grid_style = "Dots"
        self.grid_color = QColor("#555555")
        self.drag_speed_percent = 100
        
        # Setup Main Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # Container for styling (dark background, shadow)
        self.container = QWidget()
        self.container.setObjectName("controlsContainer")
        main_layout.addWidget(self.container)
        
        # Apply Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)
        
        # Container Layout
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # --- Header ---
        header = QHBoxLayout()
        title = QLabel("Canvas Controls")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #e0e0e0; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.closed.emit)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #aaa; border: none; font-weight: bold; }
            QPushButton:hover { color: white; background-color: #c42b1c; border-radius: 4px; }
        """)
        header.addWidget(close_btn)
        layout.addLayout(header)
        
        # --- Separator ---
        self._add_separator(layout)
        
        # --- Section 1: View & Navigation ---
        self._create_nav_section(layout)
        
        self._add_separator(layout)
        
        # --- Section 2: Grid System ---
        self._create_grid_section(layout)
        
        self._add_separator(layout)
        
        # --- Section 3: Typography ---
        self._create_type_section(layout)
        
        # Stylesheet
        self.on_theme_changed()
        
        # Set fixed width for panel consistency
        self.setFixedWidth(280)

    def _add_separator(self, layout):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3f3f3f; border: none; min-height: 1px; max-height: 1px;")
        layout.addWidget(line)

    def _create_nav_section(self, layout):
        layout.addWidget(QLabel("View & Navigation", styleSheet="font-weight: bold; color: #ccc; font-size: 11px; background: transparent;"))
        
        # Drag Speed Slider (Using PrecisionSlider)
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Pan Speed:", styleSheet="background: transparent;"))
        self.drag_slider = PrecisionSlider(Qt.Orientation.Horizontal)
        self.drag_slider.setMinimum(10)
        self.drag_slider.setMaximum(100)
        self.drag_slider.setValue(100)
        self.drag_slider.valueChanged.connect(self._on_drag_changed)
        slider_layout.addWidget(self.drag_slider)
        layout.addLayout(slider_layout)
        
        # Drag Presets
        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(5)
        self.drag_group = QButtonGroup(self)
        for val in [25, 50, 75, 100]:
            btn = QPushButton(f"{val}%")
            btn.setCheckable(True)
            btn.setMinimumWidth(45)
            if val == 100: btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, v=val: self.drag_slider.setValue(v))
            self.drag_group.addButton(btn)
            presets_layout.addWidget(btn)
        layout.addLayout(presets_layout)

    def _create_grid_section(self, layout):
        layout.addWidget(QLabel("Grid System", styleSheet="font-weight: bold; color: #ccc; font-size: 11px; background: transparent;"))
        
        # Opacity Slider (Using PrecisionSlider)
        op_layout = QHBoxLayout()
        op_layout.addWidget(QLabel("Opacity:", styleSheet="background: transparent;"))
        self.grid_opacity_slider = PrecisionSlider(Qt.Orientation.Horizontal)
        self.grid_opacity_slider.setMinimum(0)
        self.grid_opacity_slider.setMaximum(100)
        self.grid_opacity_slider.setValue(int(self.grid_opacity * 100))
        self.grid_opacity_slider.valueChanged.connect(lambda v: self.gridOpacityChanged.emit(v / 100.0))
        op_layout.addWidget(self.grid_opacity_slider)
        layout.addLayout(op_layout)
        
        # Grid Size
        layout.addWidget(QLabel("Grid Size:", styleSheet="color: #aaa; font-size: 10px; background: transparent;"))
        size_layout = QHBoxLayout()
        size_layout.setSpacing(5)
        self.size_group = QButtonGroup(self)
        for size in [10, 20, 50, 100]:
            btn = QPushButton(f"{size}px")
            btn.setCheckable(True)
            btn.setMinimumWidth(45)
            if size == 10: btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, s=size: self._set_grid_size(s))
            self.size_group.addButton(btn)
            size_layout.addWidget(btn)
        layout.addLayout(size_layout)
        
        # Grid Style
        layout.addWidget(QLabel("Style:", styleSheet="color: #aaa; font-size: 10px; background: transparent;"))
        style_layout = QHBoxLayout()
        style_layout.setSpacing(5)
        self.style_group = QButtonGroup(self)
        styles = [("Dots", "fa5s.ellipsis-h"), ("Lines", "fa5s.grip-lines"), ("Cross", "fa5s.plus")]
        for style_name, icon in styles:
            btn = QPushButton()
            btn.setIcon(qta.icon(icon, color="#ccc"))
            btn.setToolTip(style_name)
            btn.setCheckable(True)
            if style_name == "Dots": btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, s=style_name: self._set_grid_style(s))
            self.style_group.addButton(btn)
            style_layout.addWidget(btn)
        layout.addLayout(style_layout)
        
        # Toggles
        toggles_layout = QVBoxLayout()
        toggles_layout.setSpacing(5)
        
        snap = QCheckBox("Snap to Grid")
        snap.toggled.connect(self.snapToGridChanged.emit)
        toggles_layout.addWidget(snap)
        
        ortho = QCheckBox("Orthogonal Connections")
        ortho.toggled.connect(self.orthogonalConnectionsChanged.emit)
        toggles_layout.addWidget(ortho)
        
        guides = QCheckBox("Smart Guides")
        guides.toggled.connect(self.smartGuidesChanged.emit)
        toggles_layout.addWidget(guides)
        
        layout.addLayout(toggles_layout)

    def _create_type_section(self, layout):
        layout.addWidget(QLabel("Typography", styleSheet="font-weight: bold; color: #ccc; font-size: 11px; background: transparent;"))
        
        # Font Family
        self.font_combo = QComboBox()
        self.font_combo.addItems([
            "Segoe UI", "Arial", "Verdana", "Tahoma", "Consolas",
            "Calibri", "Cambria", "Courier New", "Times New Roman", "Georgia"
        ])
        self.font_combo.currentTextChanged.connect(self.fontFamilyChanged.emit)
        layout.addWidget(self.font_combo)
        
        # Font Size (Using PrecisionSlider)
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size:", styleSheet="background: transparent;"))
        self.font_size_slider = PrecisionSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setMinimum(8)
        self.font_size_slider.setMaximum(24)
        self.font_size_slider.setValue(10)
        self.font_size_slider.valueChanged.connect(self.fontSizeChanged.emit)
        size_layout.addWidget(self.font_size_slider)
        layout.addLayout(size_layout)
        
        # Font Color Presets
        color_layout = QHBoxLayout()
        colors = ["#dddddd", "#999999", "#2ecc71", "#3498db"]
        for c in colors:
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setStyleSheet(f"background-color: {c}; border: 1px solid #555; border-radius: 10px;")
            btn.clicked.connect(lambda checked=False, col=c: self.fontColorChanged.emit(QColor(col)))
            color_layout.addWidget(btn)
        layout.addLayout(color_layout)

    def _on_drag_changed(self, value):
        self.dragSpeedChanged.emit(value / 100.0)
        
    def _set_grid_size(self, size):
        self.grid_size = size
        self.gridSizeChanged.emit(size)
        
    def _set_grid_style(self, style):
        self.grid_style = style
        self.gridStyleChanged.emit(style)

    def on_theme_changed(self):
        palette = get_current_palette()
        bg = "#252526" # Solid dark background
        input_bg = "#1e1e1e" # Darker input well for visual contrast
        accent = palette.SELECTION.name()
        
        self.container.setStyleSheet(f"""
            QWidget#controlsContainer {{
                background-color: {bg};
                border: 1px solid #3f3f3f;
                border-radius: 8px;
            }}
            QLabel {{ color: #e0e0e0; background: transparent; }}
            QPushButton {{
                background-color: {input_bg};
                border: 1px solid #3f3f3f;
                color: #e0e0e0;
                border-radius: 4px;
                padding: 6px;
                min-width: 30px;
            }}
            QPushButton:hover {{ background-color: #2d2d2d; }}
            QPushButton:checked {{
                background-color: {accent};
                border-color: {accent};
                color: white;
            }}
            QSlider::groove:horizontal {{
                background: {input_bg}; height: 4px; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: #888; width: 12px; margin: -4px 0; border-radius: 6px;
            }}
            /* Highlight on both hover and pressed (drag) */
            QSlider::handle:horizontal:hover {{ background: {accent}; }}
            QSlider::handle:horizontal:pressed {{ background: {accent}; }}
            
            QComboBox {{
                background-color: {input_bg}; border: 1px solid #3f3f3f;
                color: #e0e0e0; padding: 4px; border-radius: 4px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QCheckBox {{ color: #ccc; background: transparent; }}
            QCheckBox::indicator:checked {{
                background-color: {accent}; border: 1px solid {accent}; border-radius: 2px;
            }}
        """)

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        return super().eventFilter(watched, event)

class SplashAnimationWidget(QWidget):
    """A standalone animation widget used in the splash screen."""
    def __init__(self, parent=None):
        """
        Initializes the SplashAnimationWidget.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._angle1 = 0.0
        self._angle2 = 0.0
        self._angle3 = 0.0

        # Set up three parallel property animations for the rotating arcs.
        self.anim1 = QPropertyAnimation(self, b'angle1')
        self.anim1.setStartValue(0)
        self.anim1.setEndValue(360)
        self.anim1.setDuration(1200)
        self.anim1.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.anim2 = QPropertyAnimation(self, b'angle2')
        self.anim2.setStartValue(70)
        self.anim2.setEndValue(430)
        self.anim2.setDuration(1000)
        self.anim2.setEasingCurve(QEasingCurve.Type.InOutSine)

        self.anim3 = QPropertyAnimation(self, b'angle3')
        self.anim3.setStartValue(140)
        self.anim3.setEndValue(500)
        self.anim3.setDuration(1500)
        self.anim3.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_group = QParallelAnimationGroup()
        self.anim_group.addAnimation(self.anim1)
        self.anim_group.addAnimation(self.anim2)
        self.anim_group.addAnimation(self.anim3)
        self.anim_group.setLoopCount(-1)
        self.anim_group.start()

    def paintEvent(self, event):
        """
        Paints the three rotating arcs using the current animation angles.

        Args:
            event (QPaintEvent): The paint event.
        """
        palette = get_current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect().adjusted(5, 5, -5, -5)
        
        pen1 = QPen(palette.USER_NODE, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen1)
        painter.drawArc(rect, int(self._angle1 * 16), 120 * 16)
        
        pen2 = QPen(palette.AI_NODE, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawArc(rect.adjusted(10, 10, -10, -10), int(self._angle2 * 16), 120 * 16)

        pen3 = QPen(palette.NAV_HIGHLIGHT.darker(120), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen3)
        painter.drawArc(rect.adjusted(20, 20, -20, -20), int(self._angle3 * 16), 120 * 16)
    
    # Define properties for animation angles.
    @Property(float)
    def angle1(self): return self._angle1
    @angle1.setter
    def angle1(self, value):
        self._angle1 = value
        self.update()

    @Property(float)
    def angle2(self): return self._angle2
    @angle2.setter
    def angle2(self, value):
        self._angle2 = value
        self.update()

    @Property(float)
    def angle3(self): return self._angle3
    @angle3.setter
    def angle3(self, value):
        self._angle3 = value
        self.update()

class SplashScreen(QWidget):
    """
    The main splash screen widget shown on application startup.
    """
    def __init__(self, main_window, welcome_screen, show_welcome=True):
        """
        Initializes the SplashScreen.

        Args:
            main_window (QMainWindow): The main application window to show after the splash.
            welcome_screen (QMainWindow): The welcome screen to show (if enabled).
            show_welcome (bool): Flag indicating whether to show the welcome screen.
        """
        super().__init__()
        self.main_window = main_window
        self.welcome_screen = welcome_screen
        self.show_welcome = show_welcome
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(400, 300)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        self.container = QWidget(self)
        self.container.setObjectName("splashContainer")
        main_layout.addWidget(self.container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 2)
        self.container.setGraphicsEffect(shadow)
        
        content_layout = QVBoxLayout(self.container)
        content_layout.setSpacing(15)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # ASCII art for the title.
        ascii_art = """
░█▀▀░█▀▄░█▀█░█▀█░█░█░▀█▀░▀█▀░█▀▀░
░█░█░█▀▄░█▀█░█▀▀░█▀█░░█░░░█░░█▀▀░
░▀▀▀░▀░▀░▀░▀░▀░░░▀░▀░▀▀▀░░▀░░▀▀▀░                                                   
"""
        title_label = QLabel(ascii_art)
        font = QFont("Consolas", 7)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(title_label)
        
        self.animation_widget = SplashAnimationWidget()
        content_layout.addWidget(self.animation_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Version Beta-0.5.3 | © 2025 All Rights Reserved.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.status_label)

        self.setStyleSheet("""
            QWidget#splashContainer {
                background-color: #1e1e1e;
                border-radius: 8px;
            }
            QLabel {
                color: #717573;
            }
        """)
        
        # Center the splash screen on the primary monitor.
        screen = QGuiApplication.primaryScreen().geometry()
        self.move(int((screen.width() - self.width()) / 2), int((screen.height() - self.height()) / 2))
        
        # Set a timer to close the splash screen and show the main window.
        QTimer.singleShot(3500, self.close_splash)

    def close_splash(self):
        """Closes the splash screen and shows the main application window or welcome screen."""
        self.main_window.show()
        if self.show_welcome:
            self.welcome_screen.show()
        self.close()