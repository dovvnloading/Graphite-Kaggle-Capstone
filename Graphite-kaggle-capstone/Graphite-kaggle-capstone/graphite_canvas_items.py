"""
This module defines various QGraphicsItem subclasses that serve as interactive
UI elements on the main canvas. These items are not part of the core conversation
flow (like ChatNode) but provide organizational and annotative functionalities.

This includes:
- Frame, Container: For visually grouping other items.
- Note: A "sticky note" for adding annotations or special prompts.
- NavigationPin: A bookmark for quick canvas navigation.
- Mixins: Reusable classes like HoverAnimationMixin to provide shared functionality.
"""

import qtawesome as qta
import markdown

from PySide6.QtWidgets import (
    QDialog, QGraphicsItem, QApplication, QMessageBox
)
from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QVariantAnimation,
    QSizeF, QEasingCurve
)
from PySide6.QtGui import (
    QFontMetrics, QPainter, QColor, QBrush, QPen, QFont, QPainterPath, QImage, QTextLayout, QTextOption,
    QLinearGradient, QConicalGradient, QCursor, QTextDocument
)

from graphite_dialogs import ColorPickerDialog, PinEditDialog
from graphite_config import get_current_palette
from graphite_widgets import ScrollBar


class GhostFrame(QGraphicsItem):
    """
    A temporary, semi-transparent QGraphicsItem that appears when hovering over a
    collapsed Container. It provides a visual preview of the container's size and
    position if it were to be expanded, helping the user understand the layout.
    """
    def __init__(self, rect, parent=None):
        """
        Initializes the GhostFrame.

        Args:
            rect (QRectF): The rectangle defining the size and shape of the ghost frame.
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.rect = rect
        self.setZValue(-5)  # Ensure it's drawn in the background.

    def boundingRect(self):
        """Returns the bounding rectangle of the item."""
        return self.rect

    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the ghost frame.

        Args:
            painter (QPainter): The painter object.
            option (QStyleOptionGraphicsItem): Provides style information.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Define a semi-transparent, dashed pen for the outline.
        pen_color = palette.SELECTION.lighter(120)
        pen_color.setAlpha(200)
        pen = QPen(pen_color, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        
        # Define a very transparent brush for the fill.
        brush_color = palette.SELECTION
        brush_color.setAlpha(50)
        painter.setBrush(brush_color)
        
        painter.drawRoundedRect(self.rect, 10, 10)


class Container(QGraphicsItem):
    """
    An advanced grouping item that acts as a parent to other QGraphicsItems.

    Unlike a Frame, a Container "owns" its children. When the container is moved,
    all contained items move with it. It supports a collapsed state to hide its
    contents and save screen space, and features in-place title editing.
    """
    PADDING = 30
    HEADER_HEIGHT = 40
    COLLAPSED_HEIGHT = 50
    COLLAPSED_WIDTH = 250
    
    def __init__(self, items, parent=None):
        """
        Initializes the Container.

        Args:
            items (list[QGraphicsItem]): The list of items to be contained.
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.contained_items = items
        self.title = "New Container"
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        
        # State attributes
        self.is_collapsed = False
        self.expanded_rect = QRectF() # Caches the size before collapsing.
        
        self.rect = QRectF()
        self.color = "#3a3a3a"
        self.header_color = None 
        
        # Rects for hover detection of UI buttons in the header.
        self.color_button_rect = QRectF()
        self.collapse_button_rect = QRectF()
        self.color_button_hovered = False
        self.collapse_button_hovered = False
        
        self.hovered = False
        self.editing = False # True when the title is being edited.
        self.edit_text = ""
        self.cursor_pos = 0
        self.cursor_visible = True
        
        # Animation for the pulsing glow effect in collapsed mode.
        self.pulse_animation = QVariantAnimation()
        self.pulse_animation.setDuration(1500)
        self.pulse_animation.setStartValue(2.0)
        self.pulse_animation.setEndValue(4.0)
        self.pulse_animation.setLoopCount(-1)
        self.pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.pulse_animation.valueChanged.connect(lambda: self.update())
        
        # Timer for the blinking cursor during title editing.
        self.cursor_timer = QTimer()
        self.cursor_timer.timeout.connect(self.toggle_cursor)
        self.cursor_timer.setInterval(500)
        
        # Timer to show a preview "ghost frame" on long hover when collapsed.
        self.ghost_frame_timer = QTimer()
        self.ghost_frame_timer.setSingleShot(True)
        self.ghost_frame_timer.setInterval(2000)
        self.ghost_frame_timer.timeout.connect(self._show_ghost_frame)
        self.ghost_frame = None

        # Re-parent all contained items to this container.
        for item in self.contained_items:
            item.setParentItem(self)

        self.updateGeometry()

    def _show_ghost_frame(self):
        """
        Creates and displays the GhostFrame preview when the container is collapsed
        and hovered over for a set duration.
        """
        if self.scene() and self.is_collapsed:
            # Determine the rectangle to show. Use the cached expanded_rect if valid.
            rect_to_show = self.expanded_rect
            if not rect_to_show.isValid():
                # If no cached rect, calculate it from the hidden children.
                bounding_rect = QRectF()
                for item in self.contained_items:
                    item_rect = item.mapToParent(item.boundingRect()).boundingRect()
                    bounding_rect = bounding_rect.united(item_rect)
                rect_to_show = bounding_rect.adjusted(-self.PADDING, -self.PADDING - self.HEADER_HEIGHT, self.PADDING, self.PADDING)

            if not rect_to_show.isValid():
                return

            # Position the ghost frame centered on the current cursor position.
            view = self.scene().views()[0]
            cursor_pos_global = QCursor.pos()
            cursor_pos_view = view.mapFromGlobal(cursor_pos_global)
            cursor_pos_scene = view.mapToScene(cursor_pos_view)

            ghost_width = rect_to_show.width()
            ghost_height = rect_to_show.height()

            top_left_pos = QPointF(
                cursor_pos_scene.x() - ghost_width / 2,
                cursor_pos_scene.y() - ghost_height / 2
            )

            self.ghost_frame = GhostFrame(QRectF(0, 0, ghost_width, ghost_height))
            self.ghost_frame.setPos(top_left_pos)
            self.scene().addItem(self.ghost_frame)
            
            # Set a timer to automatically hide the ghost frame.
            QTimer.singleShot(3000, self._hide_ghost_frame)

    def _hide_ghost_frame(self):
        """Removes the GhostFrame from the scene if it exists."""
        if self.ghost_frame and self.ghost_frame.scene():
            self.ghost_frame.scene().removeItem(self.ghost_frame)
        self.ghost_frame = None

    def boundingRect(self):
        """Returns the bounding rectangle of the item, with a small margin."""
        return self.rect.adjusted(-5, -5, 5, 5)

    def updateGeometry(self):
        """
        Recalculates the container's bounding rectangle based on its state
        (collapsed or expanded) and the geometry of its contained items.
        """
        self.prepareGeometryChange()
        if self.is_collapsed:
            # Use fixed dimensions when collapsed.
            self.rect = QRectF(0, 0, self.COLLAPSED_WIDTH, self.COLLAPSED_HEIGHT)
        else:
            if not self.contained_items:
                # If empty, use default dimensions.
                self.rect = QRectF(0, 0, 300, 150)
                self.expanded_rect = self.rect
                return

            # Calculate the union of all contained items' bounding rects.
            bounding_rect = QRectF()
            for item in self.contained_items:
                item_rect = item.mapToParent(item.boundingRect()).boundingRect()
                bounding_rect = bounding_rect.united(item_rect)
            
            # Adjust the final rect to include padding and header height.
            self.rect = bounding_rect.adjusted(-self.PADDING, -self.PADDING - self.HEADER_HEIGHT, self.PADDING, self.PADDING)
            self.expanded_rect = self.rect # Cache this size for when we collapse.
        
        # Notify the scene that this item and its children have effectively moved.
        if self.scene():
            for item in self.contained_items:
                self.scene().nodeMoved(item)
            self.scene().nodeMoved(self)

    def _get_all_descendant_nodes(self):
        """
        Recursively finds all node-like items contained within this container,
        including those inside nested Frames or Containers.
        """
        from graphite_node import ChatNode, CodeNode, DocumentNode, ImageNode
        nodes = []
        for item in self.contained_items:
            if isinstance(item, (ChatNode, CodeNode, DocumentNode, ImageNode, Note)):
                nodes.append(item)
            elif isinstance(item, Frame):
                nodes.extend(item.nodes)
            elif isinstance(item, Container):
                nodes.extend(item._get_all_descendant_nodes())
        return nodes

    def _update_child_connections(self):
        """
        Forces an update of all connections attached to any item inside this container.
        This is necessary after the container moves or resizes.
        """
        if not self.scene():
            return
            
        # Get all connection types from the scene.
        all_connection_lists = [
            self.scene().connections,
            self.scene().content_connections,
            self.scene().document_connections,
            self.scene().image_connections,
            self.scene().system_prompt_connections
        ]

        # Get all descendant nodes and check if they are endpoints for any connection.
        descendant_nodes = self._get_all_descendant_nodes()
        for item in descendant_nodes:
            for conn_list in all_connection_lists:
                for conn in conn_list:
                    if hasattr(conn, 'start_node') and hasattr(conn, 'end_node'):
                        if conn.start_node == item or conn.end_node == item:
                            conn.update_path()

    def toggle_collapse(self):
        """Toggles the container between its collapsed and expanded states."""
        # Store the center point to re-center the container after resizing.
        scene_center = self.mapToScene(self.rect.center())
        
        # Cache the expanded rect just before collapsing.
        if not self.is_collapsed:
            self.expanded_rect = self.rect
        
        self.is_collapsed = not self.is_collapsed
        
        # Show/hide contained items and start/stop pulsing animation.
        if self.is_collapsed:
            for item in self.contained_items:
                item.setVisible(False)
            self.pulse_animation.start()
        else:
            for item in self.contained_items:
                item.setVisible(True)
            self.pulse_animation.stop()

        # Recalculate geometry and reposition to maintain the center point.
        self.updateGeometry()
        new_pos = scene_center - self.rect.center()
        self.setPos(new_pos)

        # Update connections.
        self._update_child_connections()
        if self.scene():
            self.scene().update_connections()

    def toggle_cursor(self):
        """Toggles the visibility of the text editing cursor."""
        self.cursor_visible = not self.cursor_visible
        self.update()

    def paint(self, painter, option, widget=None):
        """Handles the custom painting of the container."""
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- Collapsed State Painting ---
        if self.is_collapsed:
            # Draw the pulsing glow effect.
            pulse_value = self.pulse_animation.currentValue() or 0.0
            glow_color = palette.AI_NODE
            glow_color.setAlpha(100)
            painter.setPen(QPen(glow_color, pulse_value))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect, 10, 10)

            # Draw the main collapsed body.
            path = QPainterPath()
            path.addRoundedRect(self.rect, 10, 10)
            base_color = QColor(self.color)
            painter.setPen(QPen(palette.AI_NODE, 2))
            painter.setBrush(base_color)
            painter.drawPath(path)

            # Draw the title text.
            painter.setPen(QColor("#ffffff"))
            font = QFont("Segoe UI", 12, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(self.rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignCenter, self.title)
            return

        # --- Expanded State Painting ---
        # Draw the main body with a gradient.
        gradient = QLinearGradient(self.rect.topLeft(), self.rect.bottomLeft())
        base_color = QColor(self.color)
        gradient.setColorAt(0, base_color)
        gradient.setColorAt(1, base_color.darker(120))
    
        outline_color = palette.AI_NODE if self.isSelected() or self.hovered else QColor("#555555")
        
        path = QPainterPath()
        path.addRoundedRect(self.rect, 10, 10)
    
        painter.setPen(QPen(outline_color, 2))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)
    
        # Draw the header area with its own gradient.
        header_rect = QRectF(self.rect.left(), self.rect.top(), self.rect.width(), self.HEADER_HEIGHT)
        header_path = QPainterPath()
        header_path.addRoundedRect(header_rect, 10, 10)
        
        header_gradient = QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
        header_base_color = QColor(self.header_color) if self.header_color else QColor(self.color).lighter(120)
        header_gradient.setColorAt(0, header_base_color)
        header_gradient.setColorAt(1, header_base_color.darker(110))

        painter.setBrush(QBrush(header_gradient))
        painter.drawPath(header_path)
    
        # Define and draw the collapse and color buttons in the header.
        self.collapse_button_rect = QRectF(self.rect.right() - 68, self.rect.top() + 8, 24, 24)
        self.color_button_rect = QRectF(self.rect.right() - 34, self.rect.top() + 8, 24, 24)
        
        # Draw Collapse Button
        painter.setBrush(QBrush(QColor("#3f3f3f")))
        pen_color = palette.USER_NODE if self.collapse_button_hovered else QColor("#555555")
        painter.setPen(QPen(pen_color))
        painter.drawEllipse(self.collapse_button_rect)
        icon = qta.icon('fa5s.compress-arrows-alt', color='white')
        icon.paint(painter, self.collapse_button_rect.adjusted(4, 4, -4, -4).toRect())

        # Draw Color Button
        painter.setPen(QPen(QColor("#ffffff") if self.color_button_hovered else QColor("#555555")))
        painter.setBrush(QBrush(header_base_color))
        painter.drawEllipse(self.color_button_rect)

        # Draw the three dots icon on the color button.
        painter.setPen(QPen(QColor(255, 255, 255, 180)))
        center = self.color_button_rect.center()
        painter.drawEllipse(center + QPointF(-6, 0), 2, 2)
        painter.drawEllipse(center, 2, 2)
        painter.drawEllipse(center + QPointF(6, 0), 2, 2)

        # Draw the title, either in display or editing mode.
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = header_rect.adjusted(10, 0, -78, 0)
    
        if self.editing:
            # In editing mode, draw the text and a blinking cursor.
            text = self.edit_text
            cursor_x = painter.fontMetrics().horizontalAdvance(text[:self.cursor_pos])
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
        
            if self.cursor_visible:
                cursor_height = painter.fontMetrics().height()
                cursor_y = text_rect.center().y() - cursor_height/2
                painter.drawLine(int(text_rect.left() + cursor_x), int(cursor_y), int(text_rect.left() + cursor_x), int(cursor_y + cursor_height))
        else:
            # In display mode, just draw the title.
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self.title)

    def finishEditing(self):
        """Finalizes the title editing process."""
        if self.editing:
            self.title = self.edit_text
            self.editing = False
            self.cursor_timer.stop()
            self.clearFocus()
            self.update()

    def mouseDoubleClickEvent(self, event):
        """Handles double-clicks to start title editing or expand if collapsed."""
        if self.is_collapsed:
            self.toggle_collapse()
            event.accept()
            return

        # Start editing if the double-click is in the header area.
        if self.rect.top() <= event.pos().y() <= self.rect.top() + self.HEADER_HEIGHT:
            self.editing = True
            self.edit_text = self.title
            self.cursor_pos = len(self.edit_text)
            self.cursor_timer.start()
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
            self.setFocus()
            self.update()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        """Handles clicks on the header buttons."""
        if not self.is_collapsed and self.collapse_button_rect.contains(event.pos()):
            self.toggle_collapse()
            event.accept()
        elif not self.is_collapsed and self.color_button_rect.contains(event.pos()):
            self.show_color_picker()
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def hoverMoveEvent(self, event):
        """Updates the hover state of the header buttons."""
        if not self.is_collapsed:
            self.collapse_button_hovered = self.collapse_button_rect.contains(event.pos())
            self.color_button_hovered = self.color_button_rect.contains(event.pos())
            self.update()
        super().hoverMoveEvent(event)

    def hoverEnterEvent(self, event):
        """Handles hover enter events."""
        self.hovered = True
        if self.is_collapsed:
            self.ghost_frame_timer.start() # Start timer for ghost preview.
        self.update()
        super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        """Handles hover leave events."""
        self.hovered = False
        self.collapse_button_hovered = False
        self.color_button_hovered = False
        self.ghost_frame_timer.stop() # Cancel ghost preview.
        self._hide_ghost_frame()
        self.update()
        super().hoverLeaveEvent(event)
    
    def show_color_picker(self):
        """Opens the color picker dialog to change the container's color."""
        dialog = ColorPickerDialog(self.scene().views()[0])
        # Position the dialog near the color button.
        frame_pos = self.mapToScene(self.color_button_rect.topRight())
        view_pos = self.scene().views()[0].mapFromScene(frame_pos)
        global_pos = self.scene().views()[0].mapToGlobal(view_pos)
        dialog.move(global_pos.x() + 10, global_pos.y())
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            color, color_type = dialog.get_selected_color()
            if color_type == "default":
                self.color = "#3a3a3a"
                self.header_color = None
            elif color_type == "full":
                self.color = color
                self.header_color = None
            else: # header
                self.header_color = color
            self.update()

    def finishEditing(self):
        """Finalizes title editing."""
        if self.editing:
            self.title = self.edit_text
            self.editing = False
            self.cursor_timer.stop()
            self.clearFocus()
            self.update()
            
    def focusOutEvent(self, event):
        """Ends editing when the item loses focus."""
        super().focusOutEvent(event)
        self.finishEditing()
        
    def itemChange(self, change, value):
        """Handles item changes, such as movement or scene removal."""
        # Clean up timers when the item is removed from the scene.
        if change == QGraphicsItem.ItemSceneHasChanged and value is None:
            self.pulse_animation.stop()
            self.ghost_frame_timer.stop()
            self.cursor_timer.stop()

        # Apply snapping when being moved.
        if change == QGraphicsItem.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            parent = self.parentItem()
            if parent and isinstance(parent, Container):
                parent.updateGeometry()
            return self.scene().snap_position(self, value)

        # Update child connections after the move is complete.
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            QTimer.singleShot(0, self._update_child_connections)
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def keyPressEvent(self, event):
        """Handles key presses during title editing."""
        if not self.editing:
            super().keyPressEvent(event)
            return
            
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finishEditing()
        elif event.key() == Qt.Key.Key_Escape:
            self.editing = False
            self.cursor_timer.stop()
            self.update()
        elif event.key() == Qt.Key.Key_Backspace and self.cursor_pos > 0:
            self.edit_text = self.edit_text[:self.cursor_pos-1] + self.edit_text[self.cursor_pos:]
            self.cursor_pos -= 1
            self.update()
        elif event.text():
            self.edit_text = self.edit_text[:self.cursor_pos] + event.text() + self.edit_text[self.cursor_pos:]
            self.cursor_pos += len(event.text())
            self.update()


class Frame(QGraphicsItem):
    """
    A simpler grouping item that acts as a background for other QGraphicsItems.

    Unlike a Container, a Frame does not own its children. It simply draws a
    background behind a group of nodes. Nodes can be moved freely in and out of it.
    It supports resizing via handles and can be "locked" to move its nodes with it.
    """
    PADDING = 30
    HEADER_HEIGHT = 40
    HANDLE_SIZE = 8
    
    def __init__(self, nodes, parent=None):
        """
        Initializes the Frame.

        Args:
            nodes (list[QGraphicsItem]): The list of items to be framed.
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.nodes = nodes
        self.note = "Add note..."
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        
        # Load icons for the lock/unlock button.
        self.lock_icon = qta.icon('fa.lock', color='#ffffff')
        self.unlock_icon = qta.icon('fa.unlock-alt', color='#ffffff')
        self.lock_icon_hover = qta.icon('fa.lock', color='#3498db')
        self.unlock_icon_hover = qta.icon('fa.unlock-alt', color='#2DBB6A')
        
        # State attributes
        self.is_locked = True
        self.rect = QRectF()
        self.color = "#2d2d2d"
        self.header_color = None 
        
        self.lock_button_rect = QRectF(0, 0, 24, 24)
        self.lock_button_hovered = False
        self.color_button_rect = QRectF(0, 0, 24, 24)
        self.color_button_hovered = False
        
        self.hovered = False
        self.editing = False
        self.edit_text = ""
        self.cursor_pos = 0
        self.cursor_visible = True
        
        # Resizing handle attributes
        self.handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
        self.handle_cursors = {
            'nw': Qt.CursorShape.SizeFDiagCursor, 'se': Qt.CursorShape.SizeFDiagCursor,
            'ne': Qt.CursorShape.SizeBDiagCursor, 'sw': Qt.CursorShape.SizeBDiagCursor,
            'n': Qt.CursorShape.SizeVerCursor, 's': Qt.CursorShape.SizeVerCursor,
            'e': Qt.CursorShape.SizeHorCursor, 'w': Qt.CursorShape.SizeHorCursor
        }
        self.handle_rects = {}
        self.resize_handle = None
        self.resizing = False
        self.resize_start_rect = None
        self.resize_start_pos = None
        
        self.original_positions = {node: node.scenePos() for node in nodes}
        
        # Animation for the "unlocked" state outline.
        self.outline_animation = QVariantAnimation()
        self.outline_animation.setDuration(2000)
        self.outline_animation.setStartValue(0.0)
        self.outline_animation.setEndValue(1.0)
        self.outline_animation.setLoopCount(-1)
        self.outline_animation.valueChanged.connect(lambda: self.update())
        
        self.updateGeometry()
        
        self.cursor_timer = QTimer()
        self.cursor_timer.timeout.connect(self.toggle_cursor)
        self.cursor_timer.setInterval(500)
        
        self._update_nodes_movable()
        
    def _update_child_connections(self):
        """Forces an update of connections attached to nodes within the frame."""
        if not self.scene():
            return
            
        all_connections = (
            self.scene().connections +
            self.scene().content_connections +
            self.scene().document_connections +
            self.scene().image_connections
        )

        for item in self.nodes:
            for conn in all_connections:
                if hasattr(conn, 'start_node') and hasattr(conn, 'end_node'):
                    if conn.start_node == item or conn.end_node == item:
                        conn.update_path()

    def calculate_minimum_size(self):
        """
        Calculates the smallest possible rectangle that can contain all nodes
        in the frame, including padding. This is used to constrain resizing.
        """
        if not self.nodes:
            return QRectF()
            
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        
        for node in self.nodes:
            node_rect = node.boundingRect()
            node_pos = node.pos()
            scene_pos = node.scenePos() if not node.parentItem() else self.mapToScene(node_pos)
            
            min_x = min(min_x, scene_pos.x())
            min_y = min(min_y, scene_pos.y())
            max_x = max(max_x, scene_pos.x() + node_rect.width())
            max_y = max(max_y, scene_pos.y() + node_rect.height())
        
        return QRectF(
            min_x - self.PADDING,
            min_y - self.PADDING - self.HEADER_HEIGHT,
            (max_x - min_x) + (self.PADDING * 2),
            (max_y - min_y) + (self.PADDING * 2) + self.HEADER_HEIGHT
        )

    def get_handle_rects(self):
        """
        Calculates the screen rectangles for all eight resize handles.
        It defines a larger "hit" rectangle for easier mouse interaction.
        """
        rects = {}
        rect = self.rect
    
        visual_handle_size = self.HANDLE_SIZE
        hit_handle_size = 16
    
        half_visual = visual_handle_size / 2
        half_hit = hit_handle_size / 2
    
        # Define visual and hit rects for each handle position (nw, ne, se, sw, n, s, e, w).
        rects['nw'] = {
            'visual': QRectF(rect.left() - half_visual, rect.top() - half_visual, visual_handle_size, visual_handle_size),
            'hit': QRectF(rect.left() - half_hit, rect.top() - half_hit, hit_handle_size, hit_handle_size)
        }
        # ... (definitions for other handles) ...
        rects['ne'] = {'visual': QRectF(rect.right() - half_visual, rect.top() - half_visual, visual_handle_size, visual_handle_size), 'hit': QRectF(rect.right() - half_hit, rect.top() - half_hit, hit_handle_size, hit_handle_size)}
        rects['se'] = {'visual': QRectF(rect.right() - half_visual, rect.bottom() - half_visual, visual_handle_size, visual_handle_size), 'hit': QRectF(rect.right() - half_hit, rect.bottom() - half_hit, hit_handle_size, hit_handle_size)}
        rects['sw'] = {'visual': QRectF(rect.left() - half_visual, rect.bottom() - half_visual, visual_handle_size, visual_handle_size), 'hit': QRectF(rect.left() - half_hit, rect.bottom() - half_hit, hit_handle_size, hit_handle_size)}
        rects['n'] = {'visual': QRectF(rect.center().x() - half_visual, rect.top() - half_visual, visual_handle_size, visual_handle_size), 'hit': QRectF(rect.center().x() - half_hit, rect.top() - half_hit, hit_handle_size, hit_handle_size)}
        rects['s'] = {'visual': QRectF(rect.center().x() - half_visual, rect.bottom() - half_visual, visual_handle_size, visual_handle_size), 'hit': QRectF(rect.center().x() - half_hit, rect.bottom() - half_hit, hit_handle_size, hit_handle_size)}
        rects['e'] = {'visual': QRectF(rect.right() - half_visual, rect.center().y() - half_visual, visual_handle_size, visual_handle_size), 'hit': QRectF(rect.right() - half_hit, rect.center().y() - half_hit, hit_handle_size, hit_handle_size)}
        rects['w'] = {'visual': QRectF(rect.left() - half_visual, rect.center().y() - half_visual, visual_handle_size, visual_handle_size), 'hit': QRectF(rect.left() - half_hit, rect.center().y() - half_hit, hit_handle_size, hit_handle_size)}
    
        return rects

    def handle_at(self, pos):
        """
        Determines which resize handle, if any, is at a given position.

        Args:
            pos (QPointF): The position to check, in the frame's local coordinates.

        Returns:
            str or None: The identifier of the handle (e.g., 'nw', 'e'), or None.
        """
        for handle, rects in self.get_handle_rects().items():
            if rects['hit'].contains(pos):
                return handle
        return None

    def updateGeometry(self):
        """
        Recalculates the frame's bounding rectangle to encompass all its nodes.
        This is called when nodes are added, moved, or the frame is unlocked.
        """
        if not self.nodes:
            return
            
        old_rect = self.rect
        
        # Find the bounding box of all nodes within the frame.
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        
        for node in self.nodes:
            node_rect = node.boundingRect()
            node_pos = node.pos()
            
            min_x = min(min_x, node_pos.x())
            min_y = min(min_y, node_pos.y())
            max_x = max(max_x, node_pos.x() + node_rect.width())
            max_y = max(max_y, node_pos.y() + node_rect.height())
        
        # Create a new rect based on the node bounds, plus padding and header.
        new_rect = QRectF(
            min_x - self.PADDING,
            min_y - self.PADDING - self.HEADER_HEIGHT,
            (max_x - min_x) + (self.PADDING * 2),
            (max_y - min_y) + (self.PADDING * 2) + self.HEADER_HEIGHT
        )
        
        # If an old rect exists (i.e., we are resizing), ensure the new rect is
        # at least as large as the old one to prevent snapping inward.
        if old_rect.isValid():
            self.rect = QRectF(
                min(old_rect.left(), new_rect.left()),
                min(old_rect.top(), new_rect.top()),
                max(old_rect.width(), new_rect.width()),
                max(old_rect.height(), new_rect.height())
            )
        else:
            self.rect = new_rect
            
        self.prepareGeometryChange()

    def _update_nodes_movable(self):
        """
        Updates the movable and selectable flags of all contained nodes based on
        the frame's locked state.
        """
        for node in self.nodes:
            scene_pos = node.scenePos()
            node.setParentItem(self)
            
            # When locked, nodes are re-parented but keep their visual scene position.
            if not self.is_locked:
                node.setPos(self.mapFromScene(scene_pos))
            
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self.is_locked)
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not self.is_locked)

    def boundingRect(self):
        """Returns the bounding rectangle of the item."""
        return self.rect

    def toggle_lock(self):
        """Toggles the locked state of the frame."""
        self.is_locked = not self.is_locked
    
        # Start/stop the "unlocked" animation.
        if not self.is_locked:
            self.outline_animation.start()
        else:
            self.outline_animation.stop()
    
        # Update the flags on all contained nodes.
        for node in self.nodes:
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self.is_locked)
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not self.is_locked)

    def toggle_cursor(self):
        """Toggles the visibility of the text editing cursor."""
        self.cursor_visible = not self.cursor_visible
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Starts title editing on a double-click in the header."""
        if self.rect.top() <= event.pos().y() <= self.rect.top() + self.HEADER_HEIGHT:
            self.editing = True
            self.edit_text = self.note
            self.cursor_pos = len(self.edit_text)
            self.cursor_timer.start()
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
            self.setFocus()
            self.update()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        """Handles mouse presses for resizing and button clicks."""
        if self.isSelected():
            handle = self.handle_at(event.pos())
            if handle:
                # Start resizing if a handle is clicked.
                self.resizing = True
                self.resize_handle = handle
                self.resize_start_rect = self.rect
                self.resize_start_pos = event.pos()
                event.accept()
                return
                
        if self.color_button_rect.contains(event.pos()):
            self.show_color_picker()
            event.accept()
        elif self.lock_button_rect.contains(event.pos()):
            self.toggle_lock()
            event.accept()
        
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop resizing or dragging."""
        if self.resizing:
            self.resizing = False
            self.resize_handle = None
            self.resize_start_rect = None
            self.resize_start_pos = None
            event.accept()
        
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
            
        super().mouseReleaseEvent(event)
        if self.is_locked:
            self.updateGeometry()

    def mouseMoveEvent(self, event):
        """Handles mouse movement for resizing the frame."""
        if self.resizing and self.resize_handle:
            delta = event.pos() - self.resize_start_pos
            new_rect = QRectF(self.resize_start_rect)
        
            # Calculate the minimum possible size to avoid crushing nodes.
            min_x, max_x = float('inf'), float('-inf')
            min_y, max_y = float('inf'), float('-inf')
        
            for node in self.nodes:
                node_rect = node.boundingRect()
                node_pos = node.pos()
                min_x = min(min_x, node_pos.x())
                max_x = max(max_x, node_pos.x() + node_rect.width())
                min_y = min(min_y, node_pos.y())
                max_y = max(max_y, node_pos.y() + node_rect.height())
    
            min_width = (max_x - min_x) + (self.PADDING * 2)
            min_height = (max_y - min_y) + (self.PADDING * 2) + self.HEADER_HEIGHT
    
            # Snap resize delta to a grid for cleaner resizing.
            grid_size = 10
            delta.setX(round(delta.x() / grid_size) * grid_size)
            delta.setY(round(delta.y() / grid_size) * grid_size)
    
            # Apply delta to the appropriate edges of the rect based on the handle being dragged.
            if 'n' in self.resize_handle:
                max_top = self.resize_start_rect.bottom() - min_height
                new_top = min(self.resize_start_rect.top() + delta.y(), max_top)
                new_rect.setTop(max(new_top, min_y - self.PADDING - self.HEADER_HEIGHT))
            # ... (logic for other handles) ...
            if 's' in self.resize_handle:
                min_bottom = self.resize_start_rect.top() + min_height
                new_bottom = max(self.resize_start_rect.bottom() + delta.y(), min_bottom)
                new_rect.setBottom(max(new_bottom, max_y + self.PADDING))
            if 'w' in self.resize_handle:
                max_left = self.resize_start_rect.right() - min_width
                new_left = min(self.resize_start_rect.left() + delta.x(), max_left)
                new_rect.setLeft(max(new_left, min_x - self.PADDING))
            if 'e' in self.resize_handle:
                min_right = self.resize_start_rect.left() + min_width
                new_right = max(self.resize_start_rect.right() + delta.x(), min_right)
                new_rect.setRight(max(new_right, max_x + self.PADDING))
    
            if new_rect != self.rect:
                self.prepareGeometryChange()
                self.rect = new_rect
                # Update connections of contained nodes after resizing.
                if self.scene():
                    for node in self.nodes:
                        for conn in self.scene().connections:
                            if conn.start_node == node or conn.end_node == node:
                                conn.update_path()
                        for conn in self.scene().content_connections:
                            if conn.start_node == node or conn.end_node == node:
                                conn.update_path()
    
            event.accept()
    
        elif self.is_locked:
            # If locked, move all child nodes along with the frame.
            old_positions = {node: node.scenePos() for node in self.nodes}
            pin_positions = {}
            for node in self.nodes:
                for conn in self.scene().connections:
                    if conn.start_node == node or conn.end_node == node:
                        for pin in conn.pins:
                            pin_positions[pin] = pin.mapToScene(QPointF(0, 0))
    
            super().mouseMoveEvent(event)
        
            delta = event.pos() - self.resize_start_pos if self.resize_start_pos else QPointF(0, 0)
        
            if self.scene():
                for node in self.nodes:
                    new_scene_pos = node.mapToScene(QPointF(0, 0))
                    if new_scene_pos != old_positions[node]:
                        self.scene().nodeMoved(node) # Notify scene of movement.

        else:
            # If unlocked, only the frame moves.
            super().mouseMoveEvent(event)
            if self.scene():
                moving_node = next((node for node in self.nodes if node.isUnderMouse()), None)
                if moving_node:
                    self.scene().nodeMoved(moving_node)
            
    def update_all_connections(self):
        """A utility to force-update all connections related to this frame's nodes."""
        if not self.scene(): return
        for node in self.nodes:
            self.scene().nodeMoved(node)

    def hoverMoveEvent(self, event):
        """Updates UI based on hover position (resize handles, buttons)."""
        if self.isSelected():
            handle = self.handle_at(event.pos())
            if handle:
                self.setCursor(self.handle_cursors[handle])
                return
                
        old_lock_hover = self.lock_button_hovered
        old_color_hover = self.color_button_hovered
        
        self.lock_button_hovered = self.lock_button_rect.contains(event.pos())
        self.color_button_hovered = self.color_button_rect.contains(event.pos())
        
        if (old_lock_hover != self.lock_button_hovered or old_color_hover != self.color_button_hovered):
            self.update()
            
        self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverEnterEvent(self, event):
        self.hovered = True; self.update(); super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        self.hovered = False; self.lock_button_hovered = False; self.color_button_hovered = False
        self.unsetCursor(); self.update(); super().hoverLeaveEvent(event)
        
    def show_color_picker(self):
        """Opens the color picker dialog."""
        dialog = ColorPickerDialog(self.scene().views()[0])
        frame_pos = self.mapToScene(self.color_button_rect.topRight())
        view_pos = self.scene().views()[0].mapFromScene(frame_pos)
        global_pos = self.scene().views()[0].mapToGlobal(view_pos)
        dialog.move(global_pos.x() + 10, global_pos.y())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            color, color_type = dialog.get_selected_color()
            if color_type == "default":
                self.color = "#2d2d2d"
                self.header_color = None
            elif color_type == "full":
                self.color = color
                self.header_color = None
            else: # header
                self.header_color = color
            self.update()

    def finishEditing(self):
        """Finalizes title editing."""
        if self.editing:
            self.note = self.edit_text
            self.editing = False
            self.cursor_timer.stop()
            self.clearFocus()
            self.update()
            
    def focusOutEvent(self, event):
        """Ends editing when focus is lost."""
        super().focusOutEvent(event)
        self.finishEditing()
        
    def itemChange(self, change, value):
        """Handles item changes."""
        # Clean up animation when removed from scene.
        if change == QGraphicsItem.ItemSceneHasChanged and value is None:
            self.outline_animation.stop()

        # Apply snapping when moved.
        if change == QGraphicsItem.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            parent = self.parentItem()
            if parent and isinstance(parent, Container):
                parent.updateGeometry()
            return self.scene().snap_position(self, value)

        # Update child connections after move is complete.
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            QTimer.singleShot(0, self._update_child_connections)
            self.scene().nodeMoved(self)

        return super().itemChange(change, value)

    def keyPressEvent(self, event):
        """Handles key presses during title editing."""
        if not self.editing:
            return super().keyPressEvent(event)
            
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.finishEditing()
        elif event.key() == Qt.Key.Key_Escape:
            self.editing = False
            self.cursor_timer.stop()
            self.update()
        elif event.key() == Qt.Key.Key_Backspace:
            if self.cursor_pos > 0:
                self.edit_text = self.edit_text[:self.cursor_pos-1] + self.edit_text[self.cursor_pos:]
                self.cursor_pos -= 1
                self.update()
        elif event.key() == Qt.Key.Key_Delete:
            if self.cursor_pos < len(self.edit_text):
                self.edit_text = self.edit_text[:self.cursor_pos] + self.edit_text[self.cursor_pos+1:]
                self.update()
        elif event.key() == Qt.Key.Key_Left:
            self.cursor_pos = max(0, self.cursor_pos - 1)
            self.update()
        elif event.key() == Qt.Key.Key_Right:
            self.cursor_pos = min(len(self.edit_text), self.cursor_pos + 1)
            self.update()
        elif event.key() == Qt.Key.Key_Home:
            self.cursor_pos = 0
            self.update()
        elif event.key() == Qt.Key.Key_End:
            self.cursor_pos = len(self.edit_text)
            self.update()
        elif len(event.text()) and event.text().isprintable():
            self.edit_text = (
                self.edit_text[:self.cursor_pos] + event.text() + self.edit_text[self.cursor_pos:]
            )
            self.cursor_pos += 1
            self.update()

    def paint(self, painter, option, widget=None):
        """Handles the custom painting of the frame."""
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
        # Draw main body with gradient.
        gradient = QLinearGradient(self.rect.topLeft(), self.rect.bottomLeft())
        base_color = QColor(self.color)
        gradient.setColorAt(0, base_color)
        gradient.setColorAt(1, base_color.darker(120))
    
        # Determine outline color based on state.
        if self.isSelected():
            outline_color = palette.SELECTION
        elif self.hovered:
            outline_color = palette.AI_NODE
        else:
            outline_color = QColor("#555555")
        
        path = QPainterPath()
        path.addRoundedRect(self.rect, 10, 10)
    
        painter.setPen(QPen(outline_color, 2))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)
    
        # Draw animated outline if unlocked.
        if not self.is_locked:
            outline_path = QPainterPath()
            outline_path.addRoundedRect(self.rect.adjusted(-2, -2, 2, 2), 10, 10)
            gradient = QConicalGradient(self.rect.center(), 360 * self.outline_animation.currentValue())
            blue, green = palette.AI_NODE, palette.USER_NODE
            gradient.setColorAt(0.0, blue)
            gradient.setColorAt(0.5, green)
            gradient.setColorAt(1.0, blue)
            painter.setPen(QPen(QBrush(gradient), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(outline_path)
    
        # Draw header.
        header_rect = QRectF(self.rect.left(), self.rect.top(), self.rect.width(), self.HEADER_HEIGHT)
        header_gradient = QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
        header_base_color = QColor(self.header_color) if self.header_color else QColor(self.color).lighter(120)
        header_gradient.setColorAt(0, header_base_color)
        header_gradient.setColorAt(1, header_base_color.darker(110))
        header_path = QPainterPath()
        header_path.addRoundedRect(header_rect, 10, 10)
        painter.setBrush(QBrush(header_gradient))
        painter.drawPath(header_path)
    
        # Draw lock button.
        self.lock_button_rect = QRectF(self.rect.right() - 68, self.rect.top() + 8, 24, 24)
        painter.setPen(QPen(palette.USER_NODE if self.lock_button_hovered else QColor("#555555")))
        painter.setBrush(QBrush(QColor("#3f3f3f")))
        painter.drawEllipse(self.lock_button_rect)
        icon = self.lock_icon_hover if self.is_locked and self.lock_button_hovered else self.lock_icon if self.is_locked else self.unlock_icon_hover if self.lock_button_hovered else self.unlock_icon
        icon_size = 18
        icon_pixmap = icon.pixmap(icon_size, icon_size)
        icon_x = self.lock_button_rect.center().x() - icon_size / 2
        icon_y = self.lock_button_rect.center().y() - icon_size / 2
        painter.drawPixmap(int(icon_x), int(icon_y), icon_pixmap)
    
        # Draw color button.
        self.color_button_rect = QRectF(self.rect.right() - 34, self.rect.top() + 8, 24, 24)
        painter.setPen(QPen(QColor("#ffffff") if self.color_button_hovered else QColor("#555555")))
        painter.setBrush(QBrush(QColor(self.header_color if self.header_color else self.color)))
        painter.drawEllipse(self.color_button_rect)
        icon_color = QColor("#ffffff"); icon_color.setAlpha(180)
        painter.setPen(QPen(icon_color))
        circle_size, spacing = 4, 3
        total_width = (circle_size * 3) + (spacing * 2)
        x_start = self.color_button_rect.center().x() - (total_width / 2)
        y_pos = self.color_button_rect.center().y() - (circle_size / 2)
        for i in range(3):
            x_pos = x_start + (i * (circle_size + spacing))
            painter.drawEllipse(QRectF(x_pos, y_pos, circle_size, circle_size))
    
        # Draw title (note).
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        text_rect = header_rect.adjusted(10, 0, -78, 0)
        if self.editing:
            text = self.edit_text
            cursor_x = painter.fontMetrics().horizontalAdvance(text[:self.cursor_pos])
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
            if self.cursor_visible:
                cursor_height = painter.fontMetrics().height()
                cursor_y = text_rect.center().y() - cursor_height/2
                painter.drawLine(int(text_rect.left() + cursor_x), int(cursor_y), int(text_rect.left() + cursor_x), int(cursor_y + cursor_height))
        else:
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self.note)
            
        # Draw resize handles if selected.
        if self.isSelected():
            painter.setPen(QPen(palette.SELECTION, 1))
            painter.setBrush(QBrush(palette.SELECTION))
            for handle_rects in self.get_handle_rects().values():
                painter.drawRect(handle_rects['visual'])
                            
class Note(QGraphicsItem):
    """
    A "sticky note" item for adding annotations to the canvas. It supports
    rich text (Markdown), scrolling, and in-place text editing. It can also
    serve special roles like being a System Prompt or a Group Summary.
    """
    PADDING = 20
    HEADER_HEIGHT = 40
    DEFAULT_WIDTH = 200
    DEFAULT_HEIGHT = 150
    MAX_HEIGHT = 500
    CONTROL_GUTTER = 25
    SCROLLBAR_PADDING = 5
    
    def __init__(self, pos, parent=None):
        """
        Initializes the Note.

        Args:
            pos (QPointF): The initial position of the note on the scene.
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.setPos(pos)
        self._content = ""
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.is_system_prompt = False
        self.is_summary_note = False
        
        # Geometry and appearance
        self.width = self.DEFAULT_WIDTH
        self.height = self.DEFAULT_HEIGHT
        self.color = "#2d2d2d"
        self.header_color = None
        
        # State for in-place text editing
        self.editing = False
        self.edit_text = ""
        self.cursor_pos = 0
        self.cursor_visible = True
        
        # State for text selection
        self.selection_start = 0
        self.selection_end = 0
        self.selecting = False
        self.mouse_drag_start_pos = None
        
        self.hovered = False
        self.color_button_hovered = False
        
        self.cursor_timer = QTimer()
        self.cursor_timer.timeout.connect(self.toggle_cursor)
        self.cursor_timer.setInterval(500)
        
        self.color_button_rect = QRectF(0, 0, 24, 24)

        # QTextDocument for rich text rendering
        self.document = QTextDocument()
        self.content_height = 0
        self.scroll_value = 0
        self.scrollbar = ScrollBar(self)
        self.scrollbar.width = 8
        self.scrollbar.valueChanged.connect(self.update_scroll_position)
        self.content = "Add note..." # This triggers the setter

    @property
    def content(self):
        """Gets the note's content."""
        return self._content

    @content.setter
    def content(self, new_content):
        """
        Sets the note's content. If not in editing mode, it immediately updates
        the QTextDocument for rendering.
        """
        if self._content != new_content:
            self._content = new_content
            if not self.editing:
                self._setup_document()
            self.update()

    def _setup_document(self):
        """
        Configures the QTextDocument for rendering, applying styles from the
        scene and converting the Markdown content to HTML.
        """
        font_family, font_size, color = "Segoe UI", 10, "#dddddd"
        
        if self.scene():
            font_family = self.scene().font_family
            font_size = self.scene().font_size
            color = self.scene().font_color.name()

        stylesheet = f"""
            p, ul, ol, li, blockquote {{ color: {color}; font-family: '{font_family}'; font-size: {font_size}pt; }}
            pre {{ background-color: #1e1e1e; padding: 8px; border-radius: 4px; white-space: pre-wrap; font-family: Consolas, monospace; }}
        """
        self.document.setDefaultStyleSheet(stylesheet)
        
        html = markdown.markdown(self._content, extensions=['fenced_code', 'tables'])
        self.document.setHtml(html)
        
        self._recalculate_geometry()

    def _recalculate_geometry(self):
        """
        Calculates the note's height based on its content, adding a scrollbar
        if the content exceeds the maximum height.
        """
        self.prepareGeometryChange()

        # Pass 1: Calculate ideal size assuming no scrollbar.
        available_width = self.width - (self.PADDING * 2)
        self.document.setTextWidth(available_width)
        self.content_height = self.document.size().height()
        total_required_height = self.content_height + self.HEADER_HEIGHT + 20

        # Pass 2: Decide if a scrollbar is needed and adjust dimensions.
        is_scrollable = total_required_height > self.MAX_HEIGHT
        self.scrollbar.setVisible(is_scrollable)

        if is_scrollable:
            self.height = self.MAX_HEIGHT
            # Recalculate text width to make space for the scrollbar.
            available_width -= (self.scrollbar.width + self.SCROLLBAR_PADDING)
            self.document.setTextWidth(available_width)
            self.content_height = self.document.size().height()

            # Configure scrollbar geometry and range.
            self.scrollbar.height = self.height - self.HEADER_HEIGHT - (self.SCROLLBAR_PADDING * 2)
            self.scrollbar.setPos(self.width - self.scrollbar.width - self.SCROLLBAR_PADDING, self.HEADER_HEIGHT + self.SCROLLBAR_PADDING)
            visible_content_height = self.height - self.HEADER_HEIGHT - 20
            visible_ratio = visible_content_height / self.content_height if self.content_height > 0 else 1
            self.scrollbar.set_range(visible_ratio)
        else:
            self.height = total_required_height
        
        self.update()

    def boundingRect(self):
        """Returns the bounding rectangle of the item."""
        return QRectF(0, 0, self.width, self.height)
        
    def toggle_cursor(self):
        """Toggles the visibility of the text editing cursor."""
        self.cursor_visible = not self.cursor_visible
        self.update()

    def paint(self, painter, option, widget=None):
        """Handles the custom painting of the note."""
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw a subtle drop shadow.
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(3, 3, self.width, self.height, 10, 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 30))
        painter.drawPath(shadow_path)
        
        # Draw the main body.
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)
        
        pen = QPen(QColor("#555555"))
        if self.isSelected(): pen = QPen(palette.SELECTION, 2)
        elif self.hovered: pen = QPen(QColor("#ffffff"), 2)

        # Special outline for system prompt notes.
        if self.is_system_prompt:
            pen = QPen(QColor(palette.FRAME_COLORS["Purple Header"]["color"]), 1.5, Qt.PenStyle.DashLine)
            if self.isSelected() or self.hovered: pen.setWidth(2.5)

        painter.setPen(pen)
            
        gradient = QLinearGradient(QPointF(0, 0), QPointF(0, self.height))
        gradient.setColorAt(0, QColor("#4a4a4a"))
        gradient.setColorAt(1, QColor("#2d2d2d"))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)
        
        # Draw the header.
        header_rect = QRectF(0, 0, self.width, self.HEADER_HEIGHT)
        header_path = QPainterPath()
        header_path.addRoundedRect(header_rect, 10, 10)
        header_gradient = QLinearGradient(header_rect.topLeft(), header_rect.bottomLeft())
        
        header_base_color = None
        if self.is_system_prompt: header_base_color = QColor(palette.FRAME_COLORS["Purple Header"]["color"])
        elif self.header_color: header_base_color = QColor(self.header_color)
        else: header_base_color = QColor(self.color).lighter(120)

        header_gradient.setColorAt(0, header_base_color)
        header_gradient.setColorAt(1, header_base_color.darker(110))
            
        painter.setBrush(QBrush(header_gradient))
        painter.drawPath(header_path)

        # Draw header icons for special note types.
        icon_rect = QRectF(10, (self.HEADER_HEIGHT - 16) / 2, 16, 16)
        if self.is_system_prompt:
            qta.icon('fa5s.cog', color='#ffffff').paint(painter, icon_rect.toRect())
        elif self.is_summary_note:
            qta.icon('fa5s.object-group', color='#ffffff').paint(painter, icon_rect.toRect())
        
        # Draw the color picker button.
        self.color_button_rect = QRectF(self.width - 34, 8, 24, 24)
        painter.setPen(QPen(QColor("#ffffff") if self.color_button_hovered else QColor("#555555")))
        painter.setBrush(QBrush(header_base_color))
        painter.drawEllipse(self.color_button_rect)
        icon_color = QColor("#ffffff"); icon_color.setAlpha(180)
        painter.setPen(QPen(icon_color))
        circle_size, spacing = 4, 3
        total_width = (circle_size * 3) + (spacing * 2)
        x_start = self.color_button_rect.center().x() - (total_width / 2)
        y_pos = self.color_button_rect.center().y() - (circle_size / 2)
        for i in range(3):
            x_pos = x_start + (i * (circle_size + spacing))
            painter.drawEllipse(QRectF(x_pos, y_pos, circle_size, circle_size))
            
        # --- Content Rendering ---
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        
        content_rect = QRectF(self.PADDING, self.HEADER_HEIGHT + 10, self.width - (self.PADDING * 2), self.height - self.HEADER_HEIGHT - 20)
        
        if self.editing:
            # --- In-place Text Editing Rendering ---
            # This is a manual implementation of a text editor's features, including
            # word wrap, cursor drawing, and selection highlighting.
            text = self.edit_text
            metrics = painter.fontMetrics()
            
            # Use QTextLayout to determine line breaks and character positions.
            layout = QTextLayout(text, font)
            text_option = QTextOption(); text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            layout.setTextOption(text_option)
            
            layout.beginLayout()
            height = 0; cursor_x = 0; cursor_y = 0; cursor_found = False
            text_lines = []
            
            # Break the text into lines based on the available width.
            while True:
                line = layout.createLine()
                if not line.isValid(): break
                line.setLineWidth(content_rect.width())
                line_height = metrics.height()
                text_lines.append({'line': line, 'y': height, 'text': text[line.textStart():line.textStart() + line.textLength()]})
                
                # Find the line containing the cursor to calculate its position.
                if not cursor_found and line.textStart() <= self.cursor_pos <= (line.textStart() + line.textLength()):
                    cursor_text = text[line.textStart():self.cursor_pos]
                    cursor_x = metrics.horizontalAdvance(cursor_text)
                    cursor_y = height
                    cursor_found = True
                height += line_height
            layout.endLayout()
            
            # Draw selection highlighting.
            if self.selection_start != self.selection_end:
                sel_start, sel_end = min(self.selection_start, self.selection_end), max(self.selection_start, self.selection_end)
                for line_info in text_lines:
                    line = line_info['line']
                    line_start, line_end = line.textStart(), line.textStart() + line.textLength()
                    if sel_start < line_end and sel_end > line_start:
                        start_x, width = 0, 0
                        if sel_start > line_start:
                            start_x = metrics.horizontalAdvance(text[line_start:sel_start])
                        sel_text = text[max(line_start, sel_start):min(line_end, sel_end)]
                        width = metrics.horizontalAdvance(sel_text)
                        sel_rect = QRectF(content_rect.left() + start_x, content_rect.top() + line_info['y'], width, metrics.height())
                        painter.fillRect(sel_rect, palette.SELECTION)
            
            # Draw the text lines.
            for line_info in text_lines:
                painter.drawText(QPointF(content_rect.left(), content_rect.top() + line_info['y'] + metrics.ascent()), line_info['text'])
            
            # Draw the cursor if visible and no text is selected.
            if self.cursor_visible and (not self.selecting or self.selection_start == self.selection_end):
                if cursor_found:
                    cursor_height = metrics.height()
                    painter.drawLine(int(content_rect.left() + cursor_x), int(content_rect.top() + cursor_y), int(content_rect.left() + cursor_x), int(content_rect.top() + cursor_y + cursor_height))
        else:
            # --- Display Mode Rendering ---
            # Render the pre-formatted QTextDocument.
            painter.save()
            painter.setClipRect(content_rect)
            
            # Apply scroll offset.
            visible_height = self.height - self.HEADER_HEIGHT - 20
            scrollable_distance = self.content_height - visible_height
            scroll_offset = scrollable_distance * self.scroll_value if scrollable_distance > 0 else 0
            painter.translate(self.PADDING, self.HEADER_HEIGHT + 10 - scroll_offset)

            # Draw a subtle background for the content area.
            container_path = QPainterPath()
            container_width, container_height = self.document.textWidth(), self.content_height
            container_path.addRoundedRect(0, 0, container_width, container_height, 5, 5)
            painter.setBrush(QColor(0, 0, 0, 25))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(container_path)

            self.document.drawContents(painter)
            painter.restore()

    def get_char_pos_at_x(self, x, y):
        """
        Calculates the character index in the raw text string corresponding to
        a given x, y coordinate within the note's content area. This is crucial
        for placing the cursor correctly when the user clicks.
        """
        metrics = QFontMetrics(QFont("Segoe UI", 10))
        content_rect = QRectF(self.PADDING, self.HEADER_HEIGHT + 10, self.width - (self.PADDING * 2), self.height - self.HEADER_HEIGHT - (self.PADDING * 2))
    
        # Use QTextLayout to determine line breaks and character positions.
        layout = QTextLayout(self.edit_text, QFont("Segoe UI", 10))
        layout.setTextOption(QTextOption(alignment=Qt.AlignmentFlag.AlignLeft, wrapMode=QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere))
    
        layout.beginLayout()
        height = 0
        clicked_line = None
        relative_x, relative_y = x - self.PADDING, y - (self.HEADER_HEIGHT + 10)
    
        # Find which line was clicked.
        while True:
            line = layout.createLine()
            if not line.isValid(): break
            line.setLineWidth(content_rect.width())
            line_height = metrics.height()
            if height <= relative_y < (height + line_height):
                clicked_line = line
                break
            height += line_height
        layout.endLayout()
    
        # Find the character index within the clicked line.
        if clicked_line:
            line_text = self.edit_text[clicked_line.textStart():clicked_line.textStart() + clicked_line.textLength()]
            text_width = 0
            for i, char in enumerate(line_text):
                char_width = metrics.horizontalAdvance(char)
                if text_width + (char_width / 2) > relative_x:
                    return clicked_line.textStart() + i
                text_width += char_width
            return clicked_line.textStart() + len(line_text)
    
        return len(self.edit_text)

    # --- Mouse and Key Event Handlers for Text Editing ---
    def mousePressEvent(self, event):
        """Handles mouse press for editing, selection, and button clicks."""
        if self.editing and event.pos().y() > self.HEADER_HEIGHT:
            self.selecting = True
            self.mouse_drag_start_pos = event.pos()
            char_pos = self.get_char_pos_at_x(event.pos().x(), event.pos().y())
            self.cursor_pos = self.selection_start = self.selection_end = char_pos
            self.update()
            event.accept()
        elif self.color_button_rect.contains(event.pos()):
            self.show_color_picker()
            event.accept()
        
        if event.button() == Qt.MouseButton.LeftButton and self.scene():
            self.scene().is_dragging_item = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handles mouse release to end selection."""
        if self.selecting:
            self.selecting = False
            self.mouse_drag_start_pos = None
            event.accept()
        
        if self.scene():
            self.scene().is_dragging_item = False
            self.scene()._clear_smart_guides()
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        """Handles mouse drag to update text selection."""
        if self.selecting and self.editing:
            char_pos = self.get_char_pos_at_x(event.pos().x(), event.pos().y())
            self.selection_end = self.cursor_pos = char_pos
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handles double-click to start editing or select a word."""
        if event.pos().y() > self.HEADER_HEIGHT:
            if not self.editing:
                self.editing = True
                self.edit_text = self.content
            
            char_pos = self.get_char_pos_at_x(event.pos().x(), event.pos().y())
            text = self.edit_text
            start = end = char_pos
            
            # Expand selection to the boundaries of the double-clicked word.
            while start > 0 and text[start-1].isalnum(): start -= 1
            while end < len(text) and text[end].isalnum(): end += 1
            
            self.selection_start, self.selection_end, self.cursor_pos = start, end, end
                
            self.cursor_timer.start()
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
            self.setFocus()
            self.update()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """Handles all keyboard input during text editing."""
        if not self.editing: return super().keyPressEvent(event)
            
        # Standard text editing shortcuts (copy, paste, cut, select all).
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C: self.copy_selection(); return
            elif event.key() == Qt.Key.Key_V: self.paste_text(); return
            elif event.key() == Qt.Key.Key_X: self.cut_selection(); return
            elif event.key() == Qt.Key.Key_A: self.select_all(); return
        
        if event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.finishEditing()
        elif event.key() == Qt.Key.Key_Escape:
            self.editing = False; self.cursor_timer.stop(); self.update()
        elif event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self.selection_start != self.selection_end: self.delete_selection()
            elif event.key() == Qt.Key.Key_Backspace and self.cursor_pos > 0:
                self.edit_text = self.edit_text[:self.cursor_pos-1] + self.edit_text[self.cursor_pos:]
                self.cursor_pos -= 1
            elif event.key() == Qt.Key.Key_Delete and self.cursor_pos < len(self.edit_text):
                self.edit_text = self.edit_text[:self.cursor_pos] + self.edit_text[self.cursor_pos+1:]
            self.selection_start = self.selection_end = self.cursor_pos
            self.update()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            # Handle cursor movement with and without Shift for selection.
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self.selection_start == self.selection_end: self.selection_start = self.cursor_pos
                self.cursor_pos = max(0, self.cursor_pos - 1) if event.key() == Qt.Key.Key_Left else min(len(self.edit_text), self.cursor_pos + 1)
                self.selection_end = self.cursor_pos
            else:
                if self.selection_start != self.selection_end:
                    self.cursor_pos = min(self.selection_start, self.selection_end) if event.key() == Qt.Key.Key_Left else max(self.selection_start, self.selection_end)
                else:
                    self.cursor_pos = max(0, self.cursor_pos - 1) if event.key() == Qt.Key.Key_Left else min(len(self.edit_text), self.cursor_pos + 1)
                self.selection_start = self.selection_end = self.cursor_pos
            self.update()
        elif event.key() == Qt.Key.Key_Home:
            # ... (Home/End key logic) ...
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self.selection_start == self.selection_end: self.selection_start = self.cursor_pos
                self.cursor_pos = self.selection_end = 0
            else:
                self.cursor_pos = self.selection_start = self.selection_end = 0
            self.update()
        elif event.key() == Qt.Key.Key_End:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self.selection_start == self.selection_end: self.selection_start = self.cursor_pos
                self.cursor_pos = self.selection_end = len(self.edit_text)
            else:
                self.cursor_pos = self.selection_start = self.selection_end = len(self.edit_text)
            self.update()
        elif event.key() == Qt.Key.Key_Return:
            # Insert newline.
            if self.selection_start != self.selection_end: self.delete_selection()
            self.edit_text = self.edit_text[:self.cursor_pos] + '\n' + self.edit_text[self.cursor_pos:]
            self.cursor_pos += 1; self.selection_start = self.selection_end = self.cursor_pos; self.update()
        elif len(event.text()) and event.text().isprintable():
            # Insert typed character.
            if self.selection_start != self.selection_end: self.delete_selection()
            self.edit_text = self.edit_text[:self.cursor_pos] + event.text() + self.edit_text[self.cursor_pos:]
            self.cursor_pos += 1; self.selection_start = self.selection_end = self.cursor_pos; self.update()

    def wheelEvent(self, event):
        """Handles mouse wheel scrolling for the note's content."""
        if self.editing or not self.scrollbar.isVisible():
            event.ignore(); return
            
        delta = event.angleDelta().y() / 120
        visible_height = self.height - self.HEADER_HEIGHT - 20
        scroll_range = self.content_height - visible_height
        
        if scroll_range <= 0: return

        scroll_delta = -(delta * 50) / scroll_range # 50 pixels per wheel tick
        
        new_value = max(0, min(1, self.scroll_value + scroll_delta))
        if new_value != self.scroll_value:
            self.scroll_value = new_value; self.scrollbar.set_value(new_value); self.update()
        event.accept()

    def update_scroll_position(self, value):
        """Slot connected to the scrollbar's valueChanged signal."""
        if self.scroll_value != value:
            self.scroll_value = value; self.update()

    # --- Text manipulation methods ---
    def copy_selection(self):
        if self.selection_start != self.selection_end:
            start, end = min(self.selection_start, self.selection_end), max(self.selection_start, self.selection_end)
            QApplication.clipboard().setText(self.edit_text[start:end])

    def cut_selection(self):
        if self.selection_start != self.selection_end:
            self.copy_selection(); self.delete_selection()

    def paste_text(self):
        text = QApplication.clipboard().text()
        if text:
            if self.selection_start != self.selection_end: self.delete_selection()
            self.edit_text = self.edit_text[:self.cursor_pos] + text + self.edit_text[self.cursor_pos:]
            self.cursor_pos += len(text); self.selection_start = self.selection_end = self.cursor_pos; self.update()

    def delete_selection(self):
        if self.selection_start != self.selection_end:
            start, end = min(self.selection_start, self.selection_end), max(self.selection_start, self.selection_end)
            self.edit_text = self.edit_text[:start] + self.edit_text[end:]
            self.cursor_pos = self.selection_start = self.selection_end = start
            self.update()

    def select_all(self):
        self.selection_start, self.selection_end = 0, len(self.edit_text)
        self.cursor_pos = self.selection_end; self.update()
        
    def hoverMoveEvent(self, event):
        """Updates hover state of the color button."""
        old_color_hover = self.color_button_hovered
        self.color_button_hovered = self.color_button_rect.contains(event.pos())
        if old_color_hover != self.color_button_hovered: self.update()
        self.setCursor(Qt.CursorShape.ArrowCursor)
            
    def hoverEnterEvent(self, event):
        self.hovered = True; self.update(); super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        self.hovered = False; self.color_button_hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor); self.update(); super().hoverLeaveEvent(event)
        
    def show_color_picker(self):
        """Opens the color picker dialog."""
        dialog = ColorPickerDialog(self.scene().views()[0])
        note_pos = self.mapToScene(self.color_button_rect.topRight())
        view_pos = self.scene().views()[0].mapFromScene(note_pos)
        global_pos = self.scene().views()[0].mapToGlobal(view_pos)
        dialog.move(global_pos.x() + 10, global_pos.y())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            color, color_type = dialog.get_selected_color()
            if color_type == "full": self.color, self.header_color = color, None
            else: self.header_color = color
            self.update()
            
    def finishEditing(self):
        """Finalizes text editing, saving the content."""
        if self.editing:
            self.editing = False; self.content = self.edit_text
            self.cursor_timer.stop(); self.clearFocus()
            
    def focusOutEvent(self, event):
        """Ends editing when the note loses focus."""
        super().focusOutEvent(event); self.finishEditing()
        
    def itemChange(self, change, value):
        """Handles item changes."""
        if change == QGraphicsItem.ItemPositionChange and self.scene() and self.scene().is_dragging_item:
            parent = self.parentItem()
            if parent and isinstance(parent, Container): parent.updateGeometry()
            return self.scene().snap_position(self, value)

        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.scene().nodeMoved(self)
        
        return super().itemChange(change, value)
    
class NavigationPin(QGraphicsItem):
    """
    A "bookmark" item that can be placed anywhere on the canvas. These pins
    are listed in an overlay, allowing users to quickly jump to different
    locations in a large graph.
    """
    def __init__(self, title="New Pin", note="", parent=None):
        """
        Initializes the NavigationPin.

        Args:
            title (str, optional): The display title of the pin.
            note (str, optional): An optional descriptive note for the pin.
            parent (QGraphicsItem, optional): The parent item. Defaults to None.
        """
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        
        self.title = title
        self.note = note
        self.hovered = False
        self.size = 32
        
    def boundingRect(self):
        """Returns the bounding rectangle of the pin's visual representation."""
        return QRectF(-self.size/2, -self.size/2, self.size, self.size)
        
    def paint(self, painter, option, widget=None):
        """Handles the custom painting of the pin icon."""
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Change color based on selection or hover state.
        if self.isSelected(): pin_color = palette.SELECTION
        elif self.hovered: pin_color = palette.AI_NODE
        else: pin_color = palette.NAV_HIGHLIGHT
            
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pin_color)
        
        # Draw the pin shape (a circle on top of a triangle).
        head_rect = QRectF(-10, -10, 20, 20)
        painter.drawEllipse(head_rect)
        
        path = QPainterPath()
        path.moveTo(0, 10); path.lineTo(-8, 25); path.lineTo(8, 25); path.closeSubpath()
        painter.setBrush(pin_color)
        painter.drawPath(path)
        
        # Show the title on hover or selection.
        if self.hovered or self.isSelected():
            painter.setPen(QPen(QColor("#ffffff")))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            text_rect = QRectF(-50, -35, 100, 20)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.title)
            
    def hoverEnterEvent(self, event):
        self.hovered = True; self.update(); super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        self.hovered = False; self.update(); super().hoverLeaveEvent(event)
        
    def mouseDoubleClickEvent(self, event):
        """Opens an editing dialog on double-click."""
        dialog = PinEditDialog(self.title, self.note, self.scene().views()[0])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.title = dialog.title_input.text()
            self.note = dialog.note_input.toPlainText()
            # Notify the pin overlay to update its list.
            if self.scene() and hasattr(self.scene().window, 'pin_overlay'):
                self.scene().window.pin_overlay.update_pin(self)
        super().mouseDoubleClickEvent(event)