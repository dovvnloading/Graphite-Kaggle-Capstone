from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QVariantAnimation, QEasingCurve
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPainterPath,
    QLinearGradient, QPainterPathStroker
)

from graphite_canvas_items import Container, Note
from graphite_config import get_current_palette
from graphite_pycoder import PyCoderNode
from graphite_conversation_node import ConversationNode
from graphite_html_view import HtmlViewNode

class Pin(QGraphicsItem):
    """
    A draggable point on a ConnectionItem that allows the user to curve the path.
    Pins are children of a ConnectionItem.
    """
    def __init__(self, parent=None):
        """
        Initializes the Pin.

        Args:
            parent (QGraphicsItem, optional): The parent ConnectionItem. Defaults to None.
        """
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.hover = False
        self.radius = 5
        self._dragging = False
        
    def boundingRect(self):
        """
        Returns the bounding rectangle of the pin.

        Returns:
            QRectF: The bounding rectangle.
        """
        return QRectF(-self.radius, -self.radius, 
                     self.radius * 2, self.radius * 2)
        
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the pin.

        Args:
            painter (QPainter): The painter object.
            option (QStyleOptionGraphicsItem): Style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Change color based on selection or hover state.
        if self.isSelected():
            color = palette.SELECTION
        elif self.hover:
            color = palette.AI_NODE
        else:
            color = QColor("#ffffff")
            
        painter.setPen(QPen(color.darker(120), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(self.boundingRect())
        
    def hoverEnterEvent(self, event):
        """Updates hover state when the mouse enters the pin."""
        self.hover = True
        self.update()
        super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        """Updates hover state when the mouse leaves the pin."""
        self.hover = False
        self.update()
        super().hoverLeaveEvent(event)
        
    def mousePressEvent(self, event):
        """
        Handles mouse press events. A Ctrl+RightClick removes the pin.
        A regular left click initiates dragging.

        Args:
            event (QGraphicsSceneMouseEvent): The mouse press event.
        """
        if event.button() == Qt.MouseButton.RightButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            parent_connection = self.parentItem()
            if parent_connection and isinstance(parent_connection, ConnectionItem):
                parent_connection.remove_pin(self)
                if self.scene():
                    self.scene().removeItem(self)
                event.accept()
                return
        else:
            self._dragging = True
            super().mousePressEvent(event)
            
    def mouseReleaseEvent(self, event):
        """Handles mouse release to stop the dragging operation."""
        self._dragging = False
        super().mouseReleaseEvent(event)
            
    def itemChange(self, change, value):
        """
        Handles item changes, snapping the pin to a grid during movement and
        notifying the parent connection to update its path.

        Args:
            change (QGraphicsItem.GraphicsItemChange): The type of change.
            value: The new value of the changed attribute.

        Returns:
            The modified value or the result of the superclass implementation.
        """
        if change == QGraphicsItem.ItemPositionChange and self._dragging:
            grid_size = 5
            new_pos = QPointF(
                round(value.x() / grid_size) * grid_size,
                round(value.y() / grid_size) * grid_size
            )
            # Notify the parent connection to redraw its path
            if isinstance(self.parentItem(), ConnectionItem):
                self.parentItem().prepareGeometryChange()
                self.parentItem().update_path()
            return new_pos
        return super().itemChange(change, value)

class ConnectionItem(QGraphicsItem):
    """
    The base class for drawing a connection line between two nodes.
    It supports curved paths using draggable Pins and animated arrows to show data flow.
    """
    def __init__(self, start_node, end_node):
        """
        Initializes the ConnectionItem.

        Args:
            start_node (QGraphicsItem): The item where the connection starts.
            end_node (QGraphicsItem): The item where the connection ends.
        """
        super().__init__()
        self.start_node = start_node
        self.end_node = end_node
        self.setZValue(-1) # Draw behind nodes
        self.setAcceptHoverEvents(True)
        self.path = QPainterPath()
        self.pins = [] # List to hold Pin objects
        self.hover = False
        self.click_tolerance = 20.0 # Increased hitbox for easier clicking
        self.hover_path = None # Cached path for hover detection
        self.is_selected = False
        
        # Timer to delay the start of the arrow animation on long hover
        self.hover_start_timer = QTimer()
        self.hover_start_timer.setSingleShot(True)
        self.hover_start_timer.timeout.connect(self.startArrowAnimation)
        
        # Timer to drive the arrow animation frames
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.updateArrows)
        
        # Animation properties
        self.arrows = []
        self.arrow_spacing = 30
        self.arrow_size = 10
        self.animation_speed = 2
        self.is_animating = False
        
        self.setAcceptHoverEvents(True)
        
        self.update_path()
        
        # Removed DeviceCoordinateCache to prevent visual "slipping" during node movement.
        # This forces a redraw on every frame update, ensuring tight synchronization.
        # self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache) 

    def boundingRect(self):
        """
        Returns the bounding rectangle of the connection path, including a generous
        padding to ensure the entire line and its hover area are accounted for.

        Returns:
            QRectF: The bounding rectangle.
        """
        if not self.path:
            return QRectF()
            
        padding = self.click_tolerance * 2
        return self.path.boundingRect().adjusted(-padding, -padding,
                                               padding, padding)

    def create_hover_path(self):
        """
        Creates a wider, invisible path based on the visible path to serve as a
        larger hitbox for mouse interactions.

        Returns:
            QPainterPath or None: The stroked path for hover detection.
        """
        if not self.path:
            return None
            
        stroke = QPainterPathStroker()
        stroke.setWidth(self.click_tolerance * 2)
        stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroke.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroke.createStroke(self.path)

    def contains_point(self, point):
        """
        Custom containment check to see if a point is "on" the line, using the
        wider hover path for easier interaction.

        Args:
            point (QPointF): The point to check.

        Returns:
            bool: True if the point is on or near the line, False otherwise.
        """
        if not self.hover_path:
            self.hover_path = self.create_hover_path()
            
        if not self.hover_path:
            return False
            
        point_rect = QRectF(
            point.x() - self.click_tolerance/2,
            point.y() - self.click_tolerance/2,
            self.click_tolerance,
            self.click_tolerance
        )
        
        return self.hover_path.intersects(point_rect)

    def add_pin(self, scene_pos):
        """
        Adds a new draggable pin to the connection at a specific scene position.
        It intelligently inserts the pin into the correct order in the sequence
        based on the clicked location.

        Args:
            scene_pos (QPointF): The position in the scene to add the pin.

        Returns:
            Pin: The newly created pin object.
        """
        endpoints = self.get_endpoints()
        if not endpoints:
            # Fallback if endpoints can't be determined
            pin = Pin(self)
            local_pos = self.mapFromScene(scene_pos)
            pin.setPos(local_pos)
            self.pins.append(pin)
            self.update_path()
            return pin

        start_pos, end_pos = endpoints
        local_pos = self.mapFromScene(scene_pos)

        # Determine insertion index by finding the closest segment on the current path
        current_points = [start_pos] + [p.pos() for p in self.pins] + [end_pos]
        best_index = len(self.pins) # Default to appending
        min_dist = float('inf')

        # Iterate through segments to find where the click occurred
        for i in range(len(current_points) - 1):
            p1 = current_points[i]
            p2 = current_points[i+1]
            
            # Calculate distance from point to line segment p1-p2
            # Standard point-to-line-segment distance formula
            l2 = (p1.x() - p2.x())**2 + (p1.y() - p2.y())**2
            if l2 == 0:
                dist = (local_pos.x() - p1.x())**2 + (local_pos.y() - p1.y())**2
            else:
                t = ((local_pos.x() - p1.x()) * (p2.x() - p1.x()) + (local_pos.y() - p1.y()) * (p2.y() - p1.y())) / l2
                t = max(0, min(1, t))
                proj_x = p1.x() + t * (p2.x() - p1.x())
                proj_y = p1.y() + t * (p2.y() - p1.y())
                dist = (local_pos.x() - proj_x)**2 + (local_pos.y() - proj_y)**2
            
            if dist < min_dist:
                min_dist = dist
                best_index = i

        pin = Pin(self)
        pin.setPos(local_pos)
        self.pins.insert(best_index, pin)
        self.update_path()
        return pin

    def restore_pin(self, local_pos):
        """
        Restores a pin from saved data without recalculating insertion logic.
        This ensures pins are loaded in the exact order they were saved.

        Args:
            local_pos (QPointF): The local coordinate for the pin.

        Returns:
            Pin: The created pin.
        """
        pin = Pin(self)
        pin.setPos(local_pos)
        self.pins.append(pin)
        self.update_path()
        return pin
        
    def remove_pin(self, pin):
        """
        Removes a pin from the connection.

        Args:
            pin (Pin): The pin object to remove.
        """
        if pin in self.pins:
            self.pins.remove(pin)
            if pin.scene():
                pin.scene().removeItem(pin)
            self.update_path()
                
    def clear(self):
        """
        Clears all pins from the connection.
        """
        if hasattr(self, 'window') and hasattr(self.window, 'pin_overlay'):
            self.window.pin_overlay.clear_pins()
        
        self.pins.clear()

    def _get_visual_rect(self, item):
        """
        Helper to get the effective visual rectangle of an item, accounting for
        its collapsed state if applicable.

        Args:
            item (QGraphicsItem): The item to get the rectangle for.

        Returns:
            QRectF: The visual bounding rectangle of the item.
        """
        from graphite_node import ChatNode
        if hasattr(item, 'is_collapsed') and item.is_collapsed:
            if isinstance(item, Container):
                return QRectF(0, 0, item.COLLAPSED_WIDTH, item.COLLAPSED_HEIGHT)
            elif isinstance(item, ChatNode):
                return QRectF(0, 0, item.COLLAPSED_WIDTH, item.COLLAPSED_HEIGHT)
        if hasattr(item, 'rect'): # Frame, Container
            return item.rect
        elif hasattr(item, 'width') and hasattr(item, 'height'): # Nodes, Charts, Notes
            return QRectF(0, 0, item.width, item.height)
        return item.boundingRect()

    def _get_effective_endpoint(self, item):
        """
        Finds the "effective" endpoint for a connection. If an item is inside a
        collapsed container, the container itself becomes the endpoint for drawing.

        Args:
            item (QGraphicsItem): The original endpoint item.

        Returns:
            QGraphicsItem: The effective endpoint item (either the original or a parent container).
        """
        current = item
        while current:
            parent = current.parentItem()
            if isinstance(parent, Container) and parent.is_collapsed:
                return parent
            current = parent
        return item

    def get_endpoints(self):
        """
        Calculates the start and end points for the connection line in local coordinates.
        Handles default Horizontal logic (Right to Left connection). Subclasses can override
        this to provide different connection points (e.g., Top to Bottom).

        Returns:
            tuple: (start_pos, end_pos) as QPointF, or None if connection should be hidden.
        """
        if not (self.start_node and self.end_node):
            return None
            
        # CRITICAL FIX: Ensure both nodes are still part of the scene before calculating.
        # This prevents crashes during deletion/cleanup where a node is removed but the connection
        # still attempts to render or calculate geometry.
        if not (self.start_node.scene() and self.end_node.scene()):
            return None

        effective_start = self._get_effective_endpoint(self.start_node)
        effective_end = self._get_effective_endpoint(self.end_node)
        
        if effective_start == effective_end:
            self.setVisible(False)
            return None
        
        self.setVisible(True)
        
        start_rect = self._get_visual_rect(effective_start)
        end_rect = self._get_visual_rect(effective_end)

        start_offset = getattr(effective_start, 'CONNECTION_DOT_OFFSET', 0)
        end_offset = getattr(effective_end, 'CONNECTION_DOT_OFFSET', 0)

        # Default Horizontal Logic: Right side of start to Left side of end
        start_scene_pos = effective_start.mapToScene(QPointF(start_rect.width() + start_offset, start_rect.height() / 2))
        end_scene_pos = effective_end.mapToScene(QPointF(0 - end_offset, end_rect.height() / 2))
        
        start_pos = self.mapFromScene(start_scene_pos)
        end_pos = self.mapFromScene(end_scene_pos)

        return start_pos, end_pos

    def update_path(self):
        """
        Recalculates the QPainterPath of the connection based on the positions of the
        start and end nodes and any intermediate pins.
        """
        endpoints = self.get_endpoints()
        if not endpoints:
            return

        start_pos, end_pos = endpoints
        old_path = self.path
        
        new_path = QPainterPath()
        new_path.moveTo(start_pos)
        
        scene = self.scene()
        use_orthogonal = scene and scene.orthogonal_routing and not self.pins
        
        if use_orthogonal:
            # Draw a right-angled orthogonal path
            mid_x = start_pos.x() + (end_pos.x() - start_pos.x()) / 2
            new_path.lineTo(mid_x, start_pos.y())
            new_path.lineTo(mid_x, end_pos.y())
            new_path.lineTo(end_pos)
        elif self.pins:
            # Draw a path through the series of pins, respecting their explicit order.
            points = [start_pos]
            
            for pin in self.pins:
                points.append(pin.pos())
            points.append(end_pos)
            
            # Draw cubic Bezier curves between each point
            for i in range(len(points) - 1):
                current_point = points[i]
                next_point = points[i + 1]
                
                dx = next_point.x() - current_point.x()
                distance = min(abs(dx) / 2, 200)
                
                ctrl1_x = current_point.x() + distance
                ctrl1_y = current_point.y()
                ctrl2_x = next_point.x() - distance
                ctrl2_y = next_point.y()
                
                new_path.cubicTo(
                    ctrl1_x, ctrl1_y,
                    ctrl2_x, ctrl2_y,
                    next_point.x(), next_point.y()
                )
        else:
            # Draw a standard S-shaped cubic Bezier curve
            dx = end_pos.x() - start_pos.x()
            distance = min(abs(dx) / 2, 200)
            
            ctrl1_x = start_pos.x() + distance
            ctrl1_y = start_pos.y()
            ctrl2_x = end_pos.x() - distance
            ctrl2_y = end_pos.y()
            
            new_path.cubicTo(
                ctrl1_x, ctrl1_y,
                ctrl2_x, ctrl2_y,
                end_pos.x(), end_pos.y()
            )
        
        # If the path has changed, update geometry and cached hover path
        if new_path != old_path:
            self.path = new_path
            self.hover_path = None
            self.prepareGeometryChange()
            self.update()

    def startArrowAnimation(self):
        """Starts the animated arrow flow along the connection path."""
        if not self.is_animating:
            self.is_animating = True
            self.arrows = []
            path_length = self.path.length()
            
            # Pre-populate arrows along the path
            current_distance = 0
            while current_distance < path_length:
                self.arrows.append({
                    'pos': current_distance / path_length,
                    'opacity': 1.0,
                    'distance': current_distance
                })
                current_distance += self.arrow_spacing
            
            self.animation_timer.start(16) # ~60 FPS
            self.update()

    def stopArrowAnimation(self):
        """Stops the arrow animation and clears the arrows."""
        self.is_animating = False
        self.animation_timer.stop()
        self.arrows.clear()
        self.update()

    def updateArrows(self):
        """Updates the position of each arrow for the next animation frame."""
        if not self.is_animating:
            return
            
        path_length = self.path.length()
        arrows_to_remove = []
        
        for arrow in self.arrows:
            arrow['distance'] += self.animation_speed
            arrow['pos'] = arrow['distance'] / path_length
            
            # Mark arrows that have reached the end of the path for removal
            if arrow['pos'] >= 1:
                arrows_to_remove.append(arrow)
                
        for arrow in arrows_to_remove:
            self.arrows.remove(arrow)
            
        # Add a new arrow at the start if there's space
        if not self.arrows or self.arrows[0]['distance'] >= self.arrow_spacing:
            self.arrows.insert(0, {
                'pos': 0,
                'opacity': 1.0,
                'distance': 0
            })
        
        self.update()

    def drawArrow(self, painter, pos, opacity):
        """
        Draws a single arrow at a specific percentage along the path.

        Args:
            painter (QPainter): The painter object.
            pos (float): The position along the path (0.0 to 1.0).
            opacity (float): The opacity of the arrow.
        """
        if pos < 0 or pos > 1:
            return
        
        palette = get_current_palette()
        point = self.path.pointAtPercent(pos)
        angle = self.path.angleAtPercent(pos)
        
        # Define the arrow shape
        arrow = QPainterPath()
        arrow.moveTo(-self.arrow_size, -self.arrow_size/2)
        arrow.lineTo(0, 0)
        arrow.lineTo(-self.arrow_size, self.arrow_size/2)
        
        painter.save()
        
        # Translate and rotate the painter to draw the arrow correctly
        painter.translate(point)
        painter.rotate(-angle)
        
        # Interpolate the color based on the arrow's position along the gradient
        start_color = palette.USER_NODE if self.start_node.is_user else palette.AI_NODE
        end_color = palette.USER_NODE if self.end_node.is_user else palette.AI_NODE
        
        r = int(start_color.red() * (1 - pos) + end_color.red() * pos)
        g = int(start_color.green() * (1 - pos) + end_color.green() * pos)
        b = int(start_color.blue() * (1 - pos) + end_color.blue() * pos)
        
        color = QColor(r, g, b)
        color.setAlphaF(opacity)
        
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 1))
        
        painter.drawPath(arrow)
        painter.restore()

    def shape(self):
        """
        Returns the shape of the item used for collision detection and mouse events.
        We use the wider hover_path to make it easier to click.

        Returns:
            QPainterPath: The shape of the item.
        """
        if not self.hover_path:
            self.hover_path = self.create_hover_path()
        return self.hover_path if self.hover_path else self.path

    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the connection line and its animated arrows.

        Args:
            painter (QPainter): The painter object.
            option (QStyleOptionGraphicsItem): Style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        if not (self.start_node and self.end_node):
            return
            
        palette = get_current_palette()
        # Culling: Don't draw if the connection is off-screen
        view = self.scene().views()[0]
        view_rect = view.mapToScene(view.viewport().rect()).boundingRect()
        if not self.boundingRect().intersects(view_rect):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Create a gradient that follows the path
        gradient = QLinearGradient(
            self.path.pointAtPercent(0),
            self.path.pointAtPercent(1)
        )
        
        start_color = palette.USER_NODE if self.start_node.is_user else palette.AI_NODE
        end_color = palette.USER_NODE if self.end_node.is_user else palette.AI_NODE
        
        if self.hover or self.is_selected:
            start_color = start_color.lighter(120)
            end_color = end_color.lighter(120)
        
        gradient.setColorAt(0, start_color)
        gradient.setColorAt(1, end_color)
        
        width = 3 if (self.hover or self.is_selected) else 2
        pen = QPen(QBrush(gradient), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(self.path)
        
        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], arrow['opacity'])

    def hoverEnterEvent(self, event):
        """Handles mouse hover enter events."""
        point = event.pos()
        hover_rect = QRectF(
            point.x() - self.click_tolerance,
            point.y() - self.click_tolerance,
            self.click_tolerance * 2,
            self.click_tolerance * 2
        )
        
        if self.path.intersects(hover_rect) or self.contains_point(point):
            if not self.hover:
                self.hover = True
                self.hover_start_timer.start(1000) # Start timer for animation
                self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        """Handles mouse hover move events."""
        if self.contains_point(event.pos()):
            if not self.hover:
                self.hover = True
                self.hover_start_timer.start(1000)
                self.update()
        else:
            if self.hover:
                self.hover = False
                self.hover_start_timer.stop()
                self.stopArrowAnimation()
                self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles mouse hover leave events."""
        self.hover = False
        self.hover_start_timer.stop()
        if self.is_animating:
            self.stopArrowAnimation()
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        """Handles mouse press events, adding a pin on Ctrl+Click."""
        if self.contains_point(event.pos()):
            if event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                scene_pos = self.mapToScene(event.pos())
                self.add_pin(scene_pos)
                event.accept()
            else:
                event.ignore()
        else:
            event.ignore()

    def focusOutEvent(self, event):
        """Clears selection state when the item loses focus."""
        self.is_selected = False
        self.update()
        super().focusOutEvent(event)

class ContentConnectionItem(ConnectionItem):
    """
    A specialized connection item with a dashed line style, used to link a
    ChatNode to its associated content nodes (like CodeNode).
    Now supports Pins for curved routing.
    """
    def __init__(self, start_node, end_node):
        super().__init__(start_node, end_node)
        self.arrow_size = 8
        self.animation_speed = 1.5

    def get_endpoints(self):
        """Override for vertical connection logic (Bottom to Top)."""
        if not (self.start_node and self.end_node): return None
        
        # SAFETY CHECK
        if not (self.start_node.scene() and self.end_node.scene()): return None

        effective_start = self._get_effective_endpoint(self.start_node)
        effective_end = self._get_effective_endpoint(self.end_node)
        
        if effective_start == effective_end:
            self.setVisible(False); return None
        self.setVisible(True)
        
        start_rect = self._get_visual_rect(effective_start)
        end_rect = self._get_visual_rect(effective_end)
        
        start_scene = effective_start.mapToScene(QPointF(start_rect.width() / 2, start_rect.height()))
        end_scene = effective_end.mapToScene(QPointF(end_rect.width() / 2, 0))
        
        return self.mapFromScene(start_scene), self.mapFromScene(end_scene)

    def update_path(self):
        """Use base path logic if pins exist, else draw straight line."""
        if self.pins:
            super().update_path()
        else:
            endpoints = self.get_endpoints()
            if not endpoints: return
            
            start, end = endpoints
            self.path = QPainterPath()
            self.path.moveTo(start)
            self.path.lineTo(end)
            self.hover_path = None
            self.prepareGeometryChange()
            self.update()

    def drawArrow(self, painter, pos, color):
        """Draws arrow with specific color passed from paint()."""
        if pos < 0 or pos > 1: return
        point = self.path.pointAtPercent(pos)
        angle = self.path.angleAtPercent(pos)
        
        arrow = QPainterPath()
        arrow.moveTo(-self.arrow_size, -self.arrow_size/2)
        arrow.lineTo(0, 0)
        arrow.lineTo(-self.arrow_size, self.arrow_size/2)
        
        painter.save()
        painter.translate(point)
        painter.rotate(-angle)
        
        # Fixed gray color for content connections
        fixed_color = QColor("#888888")
        # If 'color' arg is float (opacity) from base class update loop
        opacity = color if isinstance(color, (int, float)) else 1.0
        fixed_color.setAlphaF(opacity)
        
        painter.setBrush(fixed_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(arrow)
        painter.restore()
        
    def paint(self, painter, option, widget=None):
        """Paints the dashed connection line."""
        # Important: Check if connection should be visible (handled in update_path/get_endpoints but safe to check)
        if self.path.isEmpty(): return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#888888"), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], arrow['opacity'])

class DocumentConnectionItem(ConnectionItem):
    """
    A specialized connection item with a dotted line style, used to link a
    ChatNode to its associated DocumentNode. Now supports Pins.
    """
    def __init__(self, start_node, end_node):
        super().__init__(start_node, end_node)
        self.arrow_size = 8
        self.animation_speed = 1.5

    def get_endpoints(self):
        """Override for vertical connection logic (Bottom to Top)."""
        if not (self.start_node and self.end_node): return None
        
        # SAFETY CHECK
        if not (self.start_node.scene() and self.end_node.scene()): return None

        effective_start = self._get_effective_endpoint(self.start_node)
        effective_end = self._get_effective_endpoint(self.end_node)
        
        if effective_start == effective_end:
            self.setVisible(False); return None
        self.setVisible(True)
        
        start_rect = self._get_visual_rect(effective_start)
        end_rect = self._get_visual_rect(effective_end)
        
        start_scene = effective_start.mapToScene(QPointF(start_rect.width() / 2, start_rect.height()))
        end_scene = effective_end.mapToScene(QPointF(end_rect.width() / 2, 0))
        
        return self.mapFromScene(start_scene), self.mapFromScene(end_scene)

    def update_path(self):
        if self.pins:
            super().update_path()
        else:
            endpoints = self.get_endpoints()
            if not endpoints: return
            start, end = endpoints
            self.path = QPainterPath()
            self.path.moveTo(start)
            self.path.lineTo(end)
            self.hover_path = None
            self.prepareGeometryChange()
            self.update()

    def drawArrow(self, painter, pos, opacity):
        if pos < 0 or pos > 1: return
        point = self.path.pointAtPercent(pos)
        angle = self.path.angleAtPercent(pos)
        arrow = QPainterPath()
        arrow.moveTo(-self.arrow_size, -self.arrow_size/2)
        arrow.lineTo(0, 0)
        arrow.lineTo(-self.arrow_size, self.arrow_size/2)
        painter.save()
        painter.translate(point)
        painter.rotate(-angle)
        
        palette = get_current_palette()
        color = palette.NAV_HIGHLIGHT
        # Opacity check
        alpha = opacity if isinstance(opacity, (int, float)) else 1.0
        color.setAlphaF(alpha)

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(arrow)
        painter.restore()
        
    def paint(self, painter, option, widget=None):
        if self.path.isEmpty(): return
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(palette.NAV_HIGHLIGHT, 1.5, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], arrow['opacity'])

class ImageConnectionItem(ConnectionItem):
    """
    A specialized connection item with a dash-dot line style, used to link a
    ChatNode to its associated ImageNode. Now supports Pins.
    """
    def __init__(self, start_node, end_node):
        super().__init__(start_node, end_node)
        self.arrow_size = 8
        self.animation_speed = 1.5

    def get_endpoints(self):
        """Override for vertical connection logic (Bottom to Top)."""
        if not (self.start_node and self.end_node): return None
        
        # SAFETY CHECK
        if not (self.start_node.scene() and self.end_node.scene()): return None

        effective_start = self._get_effective_endpoint(self.start_node)
        effective_end = self._get_effective_endpoint(self.end_node)
        
        if effective_start == effective_end:
            self.setVisible(False); return None
        self.setVisible(True)
        
        start_rect = self._get_visual_rect(effective_start)
        end_rect = self._get_visual_rect(effective_end)
        
        start_scene = effective_start.mapToScene(QPointF(start_rect.width() / 2, start_rect.height()))
        end_scene = effective_end.mapToScene(QPointF(end_rect.width() / 2, 0))
        
        return self.mapFromScene(start_scene), self.mapFromScene(end_scene)

    def update_path(self):
        if self.pins:
            super().update_path()
        else:
            endpoints = self.get_endpoints()
            if not endpoints: return
            start, end = endpoints
            self.path = QPainterPath()
            self.path.moveTo(start)
            self.path.lineTo(end)
            self.hover_path = None
            self.prepareGeometryChange()
            self.update()

    def drawArrow(self, painter, pos, opacity):
        if pos < 0 or pos > 1: return
        point = self.path.pointAtPercent(pos)
        angle = self.path.angleAtPercent(pos)
        arrow = QPainterPath()
        arrow.moveTo(-self.arrow_size, -self.arrow_size/2)
        arrow.lineTo(0, 0)
        arrow.lineTo(-self.arrow_size, self.arrow_size/2)
        painter.save()
        painter.translate(point)
        painter.rotate(-angle)
        
        palette = get_current_palette()
        color = palette.AI_NODE
        alpha = opacity if isinstance(opacity, (int, float)) else 1.0
        color.setAlphaF(alpha)
        
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(arrow)
        painter.restore()
        
    def paint(self, painter, option, widget=None):
        if self.path.isEmpty(): return
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(palette.AI_NODE, 1.5, Qt.PenStyle.DashDotLine)
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], arrow['opacity'])

class ThinkingConnectionItem(ContentConnectionItem):
    """
    A specialized connection item with a fine dotted line style, used to link a
    ChatNode to its associated ThinkingNode. Inherits pin support from ContentConnectionItem.
    """
    def paint(self, painter, option, widget=None):
        """Paints the dotted connection line."""
        if self.end_node and getattr(self.end_node, 'is_docked', False):
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen_color = QColor("#95a5a6") # A soft gray-blue
        if self.hover:
            pen_color = pen_color.lighter(130)

        pen = QPen(pen_color, 1.5, Qt.PenStyle.DotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], pen_color.alphaF())
    
    def drawArrow(self, painter, pos, opacity):
        """Override to use specific Thinking color."""
        if pos < 0 or pos > 1: return
        point = self.path.pointAtPercent(pos)
        angle = self.path.angleAtPercent(pos)
        
        arrow = QPainterPath()
        arrow.moveTo(-self.arrow_size, -self.arrow_size/2)
        arrow.lineTo(0, 0)
        arrow.lineTo(-self.arrow_size, self.arrow_size/2)
        
        painter.save()
        painter.translate(point)
        painter.rotate(-angle)
        
        color = QColor("#95a5a6")
        alpha = opacity if isinstance(opacity, (int, float)) else 1.0
        color.setAlphaF(alpha)
        
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(arrow)
        painter.restore()

class SystemPromptConnectionItem(ConnectionItem):
    """
    A visually distinct connection with a pulsing effect, used to link a
    System Prompt Note to the root of a conversation branch. Now supports Pins.
    """
    def __init__(self, start_node, end_node):
        super().__init__(start_node, end_node)
        self.hovered = False # Override generic hover logic if needed, but base is fine
        self._pulse_value = 0.0

        # Animation for the pulsing effect
        self.pulse_animation = QVariantAnimation()
        self.pulse_animation.setStartValue(2.0)
        self.pulse_animation.setEndValue(4.0)
        self.pulse_animation.setDuration(1500)
        self.pulse_animation.setLoopCount(-1)
        self.pulse_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.pulse_animation.valueChanged.connect(self._on_pulse_update)
        self.pulse_animation.start()

    def _on_pulse_update(self, value):
        """Slot to update the pulse value from the animation and trigger a repaint."""
        self._pulse_value = value
        self.update()

    def itemChange(self, change, value):
        """Stops the animation when the item is removed from the scene."""
        if change == QGraphicsItem.ItemSceneHasChanged:
            if self.pulse_animation:
                self.pulse_animation.stop()
        return super().itemChange(change, value)

    def get_endpoints(self):
        """Override for vertical connection logic (Note Bottom to Node Top)."""
        if not (self.start_node and self.end_node): return None
        
        # SAFETY CHECK
        if not (self.start_node.scene() and self.end_node.scene()): return None

        effective_start = self._get_effective_endpoint(self.start_node)
        effective_end = self._get_effective_endpoint(self.end_node)
        
        if effective_start == effective_end:
            self.setVisible(False); return None
        self.setVisible(True)
        
        start_rect = self._get_visual_rect(effective_start)
        end_rect = self._get_visual_rect(effective_end)
        
        start_scene = effective_start.mapToScene(QPointF(start_rect.width() / 2, start_rect.height()))
        end_scene = effective_end.mapToScene(QPointF(end_rect.width() / 2, 0))
        
        return self.mapFromScene(start_scene), self.mapFromScene(end_scene)

    def update_path(self):
        if self.pins:
            super().update_path()
        else:
            # Custom curved logic for default state
            endpoints = self.get_endpoints()
            if not endpoints: return
            start_pos, end_pos = endpoints
            
            self.path = QPainterPath()
            self.path.moveTo(start_pos)
            
            dy = end_pos.y() - start_pos.y()
            ctrl1 = QPointF(start_pos.x(), start_pos.y() + dy / 2)
            ctrl2 = QPointF(end_pos.x(), end_pos.y() - dy / 2)
            
            self.path.cubicTo(ctrl1, ctrl2, end_pos)
            self.hover_path = None
            self.prepareGeometryChange()
            self.update()
        
    def paint(self, painter, option, widget=None):
        """Paints the pulsing connection line."""
        if self.path.isEmpty(): return
        palette = get_current_palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        base_color = QColor(palette.FRAME_COLORS["Purple Header"]["color"])
        if self.hover: # Use base class hover state
            base_color = base_color.lighter(130)

        gradient = QLinearGradient(self.path.pointAtPercent(0), self.path.pointAtPercent(1))
        gradient.setColorAt(0, base_color.lighter(110))
        gradient.setColorAt(1, base_color)

        # The pen width is driven by the pulse animation value
        pen = QPen(QBrush(gradient), self._pulse_value, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self.path)

class PyCoderConnectionItem(ConnectionItem):
    """
    A specialized connection for PyCoder nodes, featuring a purple dashed line.
    Inherits from ConnectionItem to support Pins.
    """
    def __init__(self, start_node, end_node):
        super().__init__(start_node, end_node)
        self.arrow_size = 8
        self.animation_speed = 1.5

    # PyCoder uses default horizontal connection logic, so no get_endpoints override needed.

    def drawArrow(self, painter, pos, opacity):
        if pos < 0 or pos > 1: return
        point = self.path.pointAtPercent(pos)
        angle = self.path.angleAtPercent(pos)
        arrow = QPainterPath()
        arrow.moveTo(-self.arrow_size, -self.arrow_size/2)
        arrow.lineTo(0, 0)
        arrow.lineTo(-self.arrow_size, self.arrow_size/2)
        painter.save()
        painter.translate(point)
        painter.rotate(-angle)
        
        palette = get_current_palette()
        color = QColor(palette.FRAME_COLORS["Purple Header"]["color"])
        alpha = opacity if isinstance(opacity, (int, float)) else 1.0
        color.setAlphaF(alpha)
        
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(arrow)
        painter.restore()

    def paint(self, painter, option, widget=None):
        """Paints the purple dashed line."""
        if self.path.isEmpty(): return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        pycoder_color = QColor(palette.FRAME_COLORS["Purple Header"]["color"])
        pen = QPen(pycoder_color, 2, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], arrow['opacity'])

class ConversationConnectionItem(ConnectionItem):
    """
    A visually distinct connection for ConversationNodes, featuring a purple dashed line.
    This class inherits from ConnectionItem and overrides the paint method.
    """
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the connection line.

        Args:
            painter (QPainter): The painter object.
            option (QStyleOptionGraphicsItem): Style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        if not (self.start_node and self.end_node):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Purple"]["color"])

        pen = QPen(node_color, 2, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.hover:
            pen.setWidth(3)
        
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], node_color)

    def drawArrow(self, painter, pos, color):
        """Draws a single animated arrow on the path."""
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

class ReasoningConnectionItem(ConnectionItem):
    """
    A visually distinct connection for ReasoningNode, featuring a blue dash-dot-dot line.
    """
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the connection line.

        Args:
            painter (QPainter): The painter object.
            option (QStyleOptionGraphicsItem): Style options.
            widget (QWidget, optional): The widget being painted on. Defaults to None.
        """
        if not (self.start_node and self.end_node):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Blue"]["color"])

        pen = QPen(node_color, 2, Qt.PenStyle.DashDotDotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.hover:
            pen.setWidth(3)
        
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], node_color)

    def drawArrow(self, painter, pos, color):
        """Draws a single animated arrow on the path."""
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

class GroupSummaryConnectionItem(ConnectionItem):
    """
    A connection from a ChatNode (source) to a summary Note (destination).
    It is visually distinct and typically connects from the top of the ChatNode
    to the bottom of the Note.
    """
    def __init__(self, start_node, end_node):
        """
        Initializes the GroupSummaryConnectionItem.

        Args:
            start_node (ChatNode): The source node being summarized.
            end_node (Note): The destination note containing the summary.
        """
        super().__init__(start_node, end_node)
        self.setZValue(-2) # Draw behind regular connections
        self.animation_speed = 1.0 
        self.arrow_size = 8

    def get_endpoints(self):
        """Override for vertical connection logic (Top to Bottom)."""
        if not (self.start_node and self.end_node): return None
        
        # SAFETY CHECK
        if not (self.start_node.scene() and self.end_node.scene()): return None

        effective_start = self._get_effective_endpoint(self.start_node)
        effective_end = self._get_effective_endpoint(self.end_node)
        
        if effective_start == effective_end:
            self.setVisible(False); return None
        self.setVisible(True)
        
        start_rect = self._get_visual_rect(effective_start)
        end_rect = self._get_visual_rect(effective_end)
        
        # Connect from top-center of source to bottom-center of destination
        start_scene = effective_start.mapToScene(QPointF(start_rect.center().x(), 0))
        end_scene = effective_end.mapToScene(QPointF(end_rect.center().x(), end_rect.height()))
        
        return self.mapFromScene(start_scene), self.mapFromScene(end_scene)

    def update_path(self):
        """Recalculates the path for the summary connection."""
        if self.pins:
            super().update_path()
        else:
            # Logic if no pins (custom cubic curve)
            endpoints = self.get_endpoints()
            if not endpoints: return
            start_pos, end_pos = endpoints
            
            self.path = QPainterPath()
            self.path.moveTo(start_pos)
            
            scene = self.scene()
            if scene and scene.orthogonal_routing:
                mid_y = start_pos.y() + (end_pos.y() - start_pos.y()) / 2
                self.path.lineTo(start_pos.x(), mid_y)
                self.path.lineTo(end_pos.x(), mid_y)
                self.path.lineTo(end_pos)
            else:
                dy = end_pos.y() - start_pos.y()
                distance = min(abs(dy) / 2, 150)
                ctrl1 = QPointF(start_pos.x(), start_pos.y() - distance)
                ctrl2 = QPointF(end_pos.x(), end_pos.y() + distance)
                self.path.cubicTo(ctrl1, ctrl2, end_pos)
            
            self.hover_path = None
            self.prepareGeometryChange()
            self.update()

    def paint(self, painter, option, widget=None):
        """Paints the gray dashed line for the summary connection."""
        if self.path.isEmpty(): return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#888888"), 1.5, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], 1.0)

    def drawArrow(self, painter, pos, opacity):
        """Draws a single animated arrow for the summary connection."""
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
        
        color = QColor("#888888")
        if self.hover:
            color = QColor("#bbbbbb")
        color.setAlphaF(opacity)
        
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        painter.drawPath(arrow)
        painter.restore()

class HtmlConnectionItem(ConnectionItem):
    """
    A specialized connection for HtmlView nodes, featuring an orange dash-dot-dot line.
    """
    def paint(self, painter, option, widget=None):
        """
        Handles the custom painting of the connection line.
        """
        if not (self.start_node and self.end_node):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Orange"]["color"])

        pen = QPen(node_color, 2, Qt.PenStyle.DashDotDotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.hover:
            pen.setWidth(3)
        
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], node_color)

    def drawArrow(self, painter, pos, color):
        """Draws a single animated arrow on the path."""
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

class OrchestratorConnectionItem(ConnectionItem):
    """A visually distinct connection for OrchestratorNode."""
    def paint(self, painter, option, widget=None):
        if not (self.start_node and self.end_node):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Yellow"]["color"])

        pen = QPen(node_color, 2, Qt.PenStyle.DashDotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.hover:
            pen.setWidth(3)
        
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], node_color)

    def drawArrow(self, painter, pos, color):
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


class MemoryBankConnectionItem(ConnectionItem):
    """A visually distinct connection for MemoryBankNode."""
    def paint(self, painter, option, widget=None):
        if not (self.start_node and self.end_node):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Green"]["color"])

        pen = QPen(node_color, 2, Qt.PenStyle.DotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.hover:
            pen.setWidth(3)
        
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], node_color)

    def drawArrow(self, painter, pos, color):
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

class SynthesisConnectionItem(ConnectionItem):
    """A visually distinct connection for SynthesisNode."""
    def paint(self, painter, option, widget=None):
        if not (self.start_node and self.end_node):
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = get_current_palette()
        node_color = QColor(palette.FRAME_COLORS["Teal"]["color"])

        pen = QPen(node_color, 2, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.hover:
            pen.setWidth(3)
        
        painter.setPen(pen)
        painter.drawPath(self.path)

        if self.is_animating:
            for arrow in self.arrows:
                self.drawArrow(painter, arrow['pos'], node_color)

    def drawArrow(self, painter, pos, color):
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