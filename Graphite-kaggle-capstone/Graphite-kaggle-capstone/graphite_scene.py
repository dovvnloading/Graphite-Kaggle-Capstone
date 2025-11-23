from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsScene, QMessageBox, QGraphicsLineItem
)
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QPen, QTransform

from graphite_node import ChatNode, CodeNode, DocumentNode, ImageNode, ThinkingNode
from graphite_connections import (
    ConnectionItem, ContentConnectionItem, SystemPromptConnectionItem,
    DocumentConnectionItem, ImageConnectionItem, PyCoderConnectionItem,
    ConversationConnectionItem, ReasoningConnectionItem, GroupSummaryConnectionItem,
    HtmlConnectionItem, ThinkingConnectionItem, OrchestratorConnectionItem, MemoryBankConnectionItem,
    SynthesisConnectionItem
)
from graphite_canvas_items import Frame, Note, NavigationPin, Container
from graphite_chart_item import ChartItem
from graphite_pycoder import PyCoderNode
from graphite_web import WebNode, WebConnectionItem
from graphite_conversation_node import ConversationNode
from graphite_reasoning import ReasoningNode
from graphite_html_view import HtmlViewNode
from graphite_orchestrator import (
    OrchestratorNode, MemoryBankNode, SynthesisNode
)


class ChatScene(QGraphicsScene):
    """
    The core data model and controller for the Graphite canvas.

    This class manages all graphical items, including nodes, connections, frames,
    and notes. It handles the logic for adding, removing, and arranging these items,
    as well as implementing features like snapping, smart guides, and organizing the
    layout. It acts as the central hub for all canvas-related operations.
    """
    scene_changed = Signal()

    def __init__(self, window):
        """
        Initializes the ChatScene.

        Args:
            window (QMainWindow): A reference to the main application window.
        """
        super().__init__()
        self.window = window
        # Lists to track all items of a specific type in the scene.
        self.nodes = []
        self.connections = []
        self.frames = []
        self.containers = []
        self.pins = []
        self.notes = []
        self.code_nodes = []
        self.document_nodes = []
        self.image_nodes = []
        self.thinking_nodes = []
        self.pycoder_nodes = []
        self.web_nodes = []
        self.conversation_nodes = []
        self.reasoning_nodes = []
        self.html_view_nodes = []
        self.content_connections = []
        self.document_connections = []
        self.image_connections = []
        self.thinking_connections = []
        self.system_prompt_connections = []
        self.pycoder_connections = []
        self.web_connections = []
        self.conversation_connections = []
        self.reasoning_connections = []
        self.group_summary_connections = []
        self.html_connections = []
        self.orchestrator_nodes = []
        self.memory_bank_nodes = []
        self.orchestrator_connections = []
        self.memory_bank_connections = []
        self.synthesis_nodes = []
        self.synthesis_connections = []

        self.setBackgroundBrush(QColor("#252526"))
        
        # Parameters for the auto-layout algorithm.
        self.horizontal_spacing = 150
        self.vertical_spacing = 60
        self.is_branch_hidden = False
        
        # Properties for alignment, snapping, and routing.
        self.snap_to_grid = False
        self.orthogonal_routing = False
        self.smart_guides = False
        self._is_dragging_item = False
        self._alignment_targets = [] # Cache for smart guide targets
        self.smart_guide_lines = []
        self.is_rubber_band_dragging = False

        # Optimzed lookup map for connections {node: set(connections)}
        self._node_connections_map = {}

        # Global font properties for nodes that support them.
        self.font_family = "Segoe UI"
        self.font_size = 10
        self.font_color = QColor("#dddddd")

    @property
    def is_dragging_item(self):
        return self._is_dragging_item

    @is_dragging_item.setter
    def is_dragging_item(self, value):
        if self._is_dragging_item != value:
            self._is_dragging_item = value
            if value:
                # When dragging starts, cache the static items for snapping to avoid O(N) scan on move
                valid_types = (
                    ChatNode, CodeNode, Note, Frame, ChartItem, DocumentNode, ImageNode, 
                    ThinkingNode, Container, PyCoderNode, WebNode, ConversationNode, 
                    ReasoningNode, HtmlViewNode, OrchestratorNode, MemoryBankNode, SynthesisNode
                )
                # We only snap to items that are NOT selected (i.e., not moving)
                self._alignment_targets = [
                    item for item in self.items() 
                    if isinstance(item, valid_types) and not item.isSelected()
                ]
            else:
                self._alignment_targets = []
                self._clear_smart_guides()

    def register_connection(self, connection):
        """Registers a connection in the lookup map for O(1) access during node movement."""
        for node in [connection.start_node, connection.end_node]:
            if node:
                if node not in self._node_connections_map:
                    self._node_connections_map[node] = set()
                self._node_connections_map[node].add(connection)

    def unregister_connection(self, connection):
        """Removes a connection from the lookup map."""
        for node in [connection.start_node, connection.end_node]:
            if node and node in self._node_connections_map:
                self._node_connections_map[node].discard(connection)
                # Clean up empty sets to keep map small
                if not self._node_connections_map[node]:
                    del self._node_connections_map[node]

    def add_connection_to_scene(self, connection, target_list=None):
        """Helper to add connection to scene, specific list, and lookup map."""
        self.addItem(connection)
        if target_list is not None:
            target_list.append(connection)
        self.register_connection(connection)

    def setFontFamily(self, family):
        """Sets the font family for all applicable nodes in the scene."""
        if self.font_family != family:
            self.font_family = family
            self._update_all_node_fonts()

    def setFontSize(self, size):
        """Sets the font size for all applicable nodes in the scene."""
        if self.font_size != size:
            self.font_size = size
            self._update_all_node_fonts()
    
    def setFontColor(self, color):
        """Sets the font color for all applicable nodes in the scene."""
        if self.font_color != color:
            self.font_color = color
            self._update_all_node_fonts()

    def _update_all_node_fonts(self):
        """Iterates through all nodes that support font changes and applies the current settings."""
        nodes_to_update = self.nodes + self.document_nodes
        for node in nodes_to_update:
            if hasattr(node, 'update_font_settings'):
                node.update_font_settings(self.font_family, self.font_size, self.font_color)

    def find_items(self, text):
        """Searches all nodes for a given text string."""
        if not text:
            return []

        text = text.lower()
        matches = []
        
        all_nodes = (self.nodes + self.code_nodes + self.document_nodes + self.image_nodes +
                     self.thinking_nodes + self.conversation_nodes + self.reasoning_nodes + 
                     self.orchestrator_nodes + self.memory_bank_nodes + self.synthesis_nodes)
        for node in all_nodes:
            content = ""
            if isinstance(node, ChatNode):
                content = node.text
            elif isinstance(node, CodeNode):
                content = node.code
            elif isinstance(node, DocumentNode):
                content = node.content
            elif isinstance(node, ImageNode):
                content = node.prompt
            elif isinstance(node, ThinkingNode):
                content = node.thinking_text
            elif isinstance(node, ConversationNode):
                content = "\n".join([msg.get('content', '') for msg in node.conversation_history])
            elif isinstance(node, ReasoningNode):
                content = node.prompt + "\n" + node.thought_process
            elif isinstance(node, OrchestratorNode):
                content = node.goal + "\n" + node.plan
            elif isinstance(node, SynthesisNode):
                content = node.instruction_input.toPlainText() + "\n" + node.output_display.toPlainText()
            
            if text in content.lower():
                matches.append(node)

        # Sort matches by their Y, then X position for consistent navigation.
        matches.sort(key=lambda n: (n.pos().y(), n.pos().x()))
        return matches

    def update_search_highlight(self, matched_nodes):
        """Updates the visual search highlight state for all nodes."""
        all_nodes = self.nodes + self.code_nodes
        for node in all_nodes:
            is_match = node in matched_nodes
            if node.is_search_match != is_match:
                node.is_search_match = is_match
                node.update()

    def add_chat_node(self, text, is_user=True, parent_node=None, conversation_history=None):
        """Creates and adds a new ChatNode to the scene."""
        try:
            if parent_node is not None:
                valid_parent_types = (
                    self.nodes + self.pycoder_nodes + self.web_nodes + self.conversation_nodes + 
                    self.reasoning_nodes + self.html_view_nodes + self.orchestrator_nodes + self.memory_bank_nodes +
                    self.synthesis_nodes
                )
                if parent_node not in valid_parent_types or not parent_node.scene():
                    print("Warning: Parent node is invalid or no longer in the scene.")
                    parent_node = None
            
            node = ChatNode(text, is_user)
            if conversation_history:
                node.conversation_history = conversation_history.copy()
            
            if parent_node:
                parent_pos = parent_node.pos()
                parent_node.children.append(node)
                node.parent_node = parent_node
                
                existing_children_count = len(parent_node.children) - 1
                vertical_offset = existing_children_count * (node.height + self.vertical_spacing)

                base_pos = QPointF(parent_pos.x() + self.horizontal_spacing, parent_pos.y() + vertical_offset)
                node.setPos(self.find_free_position(base_pos, node))
                
                connection = ConnectionItem(parent_node, node)
                node.incoming_connection = connection
                self.add_connection_to_scene(connection, self.connections)
            else:
                node.setPos(50, 150)
            
            self.addItem(node)
            self.nodes.append(node)
                
            self.scene_changed.emit()
            return node
            
        except Exception as e:
            print(f"Error adding chat node: {str(e)}")
            if 'node' in locals() and node.scene() == self:
                self.removeItem(node)
            return None

    def _get_next_content_node_y(self, parent_node):
        """Calculates the Y position for a new content node below its parent."""
        last_y = parent_node.pos().y() + parent_node.height
        
        all_content_nodes = self.code_nodes + self.document_nodes + self.image_nodes + self.thinking_nodes
        for node in all_content_nodes:
            if hasattr(node, 'parent_content_node') and node.parent_content_node == parent_node:
                last_y = max(last_y, node.pos().y() + node.height)
                
        return last_y + 50

    def add_code_node(self, code, language, parent_content_node):
        """Creates and adds a new CodeNode."""
        node = CodeNode(code, language, parent_content_node)
        y_pos = self._get_next_content_node_y(parent_content_node)
        node.setPos(QPointF(parent_content_node.pos().x(), y_pos))
        
        self.addItem(node)
        self.code_nodes.append(node)
        
        connection = ContentConnectionItem(parent_content_node, node)
        self.add_connection_to_scene(connection, self.content_connections)
        
        self.scene_changed.emit()
        return node

    def add_image_node(self, image_bytes, parent_chat_node, prompt=""):
        """Creates and adds a new ImageNode."""
        node = ImageNode(image_bytes, parent_chat_node, prompt)
        y_pos = self._get_next_content_node_y(parent_chat_node)
        node.setPos(QPointF(parent_chat_node.pos().x(), y_pos))
        
        self.addItem(node)
        self.image_nodes.append(node)
        
        connection = ImageConnectionItem(parent_chat_node, node)
        self.add_connection_to_scene(connection, self.image_connections)
        
        self.scene_changed.emit()
        return node

    def add_document_node(self, title, content, parent_user_node):
        """Creates and adds a new DocumentNode."""
        node = DocumentNode(title, content, parent_user_node)
        y_pos = self._get_next_content_node_y(parent_user_node)
        node.setPos(QPointF(parent_user_node.pos().x(), y_pos))
        
        self.addItem(node)
        self.document_nodes.append(node)
        
        connection = DocumentConnectionItem(parent_user_node, node)
        self.add_connection_to_scene(connection, self.document_connections)
        
        self.scene_changed.emit()
        return node

    def add_thinking_node(self, thinking_text, parent_chat_node):
        """Creates and adds a new ThinkingNode."""
        node = ThinkingNode(thinking_text, parent_chat_node)
        y_pos = self._get_next_content_node_y(parent_chat_node)
        node.setPos(QPointF(parent_chat_node.pos().x(), y_pos))
        
        self.addItem(node)
        self.thinking_nodes.append(node)
        
        connection = ThinkingConnectionItem(parent_chat_node, node)
        self.add_connection_to_scene(connection, self.thinking_connections)
        
        self.scene_changed.emit()
        return node

    def nodeMoved(self, node):
        """
        Callback triggered when a node is moved. Updates all attached connections.
        Optimized to use lookup map instead of iterating lists.
        """
        # Valid types check is still good to avoid processing unnecessary items
        valid_types = (
            self.nodes + self.code_nodes + self.document_nodes + self.image_nodes + self.thinking_nodes +
            self.pycoder_nodes + self.web_nodes + self.conversation_nodes + self.reasoning_nodes +
            self.html_view_nodes + self.orchestrator_nodes + self.memory_bank_nodes + self.synthesis_nodes
        )
        if not isinstance(node, (Note, Container)) and node not in valid_types or not node.scene():
            return
            
        # OPTIMIZED: Lookup connections for this node directly
        if node in self._node_connections_map:
            for conn in self._node_connections_map[node]:
                conn.update_path()
        
        self.scene_changed.emit()
                        
    def add_navigation_pin(self, pos):
        """Adds a new NavigationPin to the scene."""
        pin = NavigationPin()
        pin.setPos(pos)
        self.addItem(pin)
        self.pins.append(pin)
        return pin
    
    def add_chart(self, data, pos):
        """Adds a new ChartItem to the scene."""
        chart = ChartItem(data, pos)
        self.addItem(chart)
        self.scene_changed.emit()
        return chart

    def createFrame(self):
        """Creates a Frame around the currently selected nodes."""
        selected_nodes = [item for item in self.selectedItems() 
                         if isinstance(item, (ChatNode, CodeNode, DocumentNode, ImageNode, ThinkingNode, 
                                              PyCoderNode, WebNode, ConversationNode, ReasoningNode, HtmlViewNode,
                                              OrchestratorNode, MemoryBankNode, SynthesisNode))]
        
        if not selected_nodes:
            return
            
        # If a selected node is already in a frame, un-parent it first.
        for node in selected_nodes:
            if node.parentItem() and isinstance(node.parentItem(), Frame):
                old_frame = node.parentItem()
                scene_pos = node.scenePos()
                node.setParentItem(None)
                node.setPos(scene_pos)
                old_frame.nodes.remove(node)
                # If the old frame is now empty, remove it.
                if not old_frame.nodes:
                    self.removeItem(old_frame)
                    if old_frame in self.frames:
                        self.frames.remove(old_frame)
                else:
                    old_frame.updateGeometry()
        
        frame = Frame(selected_nodes)
        self.addItem(frame)
        self.frames.append(frame)
        frame.setZValue(-2) # Ensure frames are drawn behind nodes.
        
        # Trigger connection updates for all affected nodes.
        for node in selected_nodes:
            self.nodeMoved(node)
        
        self.scene_changed.emit()

    def createContainer(self):
        """Creates a Container around the currently selected items."""
        selected_items = [item for item in self.selectedItems() 
                         if isinstance(item, (ChatNode, CodeNode, DocumentNode, ImageNode, ThinkingNode, Note, ChartItem, 
                                              Frame, Container, PyCoderNode, WebNode, ConversationNode, ReasoningNode, HtmlViewNode,
                                              OrchestratorNode, MemoryBankNode, SynthesisNode))]
        
        if not selected_items:
            return

        # Un-parent selected items from any existing containers or frames.
        for item in selected_items:
            if item.parentItem() and isinstance(item.parentItem(), (Frame, Container)):
                old_parent = item.parentItem()
                scene_pos = item.scenePos()
                item.setParentItem(None)
                item.setPos(scene_pos)
                
                # Clean up the old parent if it becomes empty.
                if isinstance(old_parent, Frame):
                    old_parent.nodes.remove(item)
                    if not old_parent.nodes: self.deleteFrame(old_parent)
                elif isinstance(old_parent, Container):
                    old_parent.contained_items.remove(item)
                    if not old_parent.contained_items: self.deleteContainer(old_parent)
        
        container = Container(selected_items)
        self.addItem(container)
        self.containers.append(container)
        container.setZValue(-3) # Ensure containers are drawn behind frames and nodes.
        
        for item in selected_items:
            self.nodeMoved(item)
        
        self.scene_changed.emit()
            
    def add_note(self, pos):
        """Adds a new Note item to the scene."""
        note = Note(pos)
        self.addItem(note)
        self.notes.append(note)
        self.scene_changed.emit()
        return note
    
    def deleteSelectedNotes(self):
        """Deletes all currently selected Note items."""
        for item in list(self.selectedItems()):
            if isinstance(item, Note):
                self.removeItem(item)
    
    def deleteFrame(self, frame):
        """Deletes a Frame, releasing its contained nodes."""
        for node in frame.nodes:
            scene_pos = node.scenePos()
            node.setParentItem(None)
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            node.setPos(scene_pos)
            self.nodeMoved(node)
        
        self.removeItem(frame)
        if frame in self.frames:
            self.frames.remove(frame)
        self.scene_changed.emit()

    def deleteContainer(self, container):
        """Deletes a Container, releasing its contained items."""
        for item in container.contained_items:
            scene_pos = item.scenePos()
            item.setParentItem(None)
            item.setPos(scene_pos)
            item.setVisible(True)
            self.nodeMoved(item)
        
        self.removeItem(container)
        if container in self.containers:
            self.containers.remove(container)
        self.scene_changed.emit()

    def keyPressEvent(self, event):
        """Handles key press events for scene-wide shortcuts."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_A:
            self.selectAllNodes()
        elif event.key() == Qt.Key.Key_Delete:
            self.deleteSelectedItems()
        super().keyPressEvent(event)
        
    def selectAllNodes(self):
        """Selects all ChatNode items in the scene."""
        for node in self.nodes:
            node.setSelected(True)

    def calculate_node_rect(self, node, pos):
        """Calculates a padded bounding rectangle for collision detection."""
        PADDING = 50 
        width = 0
        height = 0
        
        if hasattr(node, 'width'): 
            width = node.width
        elif hasattr(node, 'rect'): 
            width = node.rect.width()
        else: 
            width = node.boundingRect().width()
            
        if hasattr(node, 'height'): 
            height = node.height
        elif hasattr(node, 'rect'): 
            height = node.rect.height()
        else: 
            height = node.boundingRect().height()
        
        return QRectF(pos.x() - PADDING, pos.y() - PADDING, width + (PADDING * 2), height + (PADDING * 2))

    def check_collision(self, test_rect, ignore_node=None):
        """Checks if a given rectangle intersects with any existing nodes or items."""
        all_items = (
            self.nodes + self.code_nodes + self.document_nodes + self.image_nodes +
            self.thinking_nodes + self.pycoder_nodes + self.web_nodes +
            self.conversation_nodes + self.reasoning_nodes + self.html_view_nodes +
            self.orchestrator_nodes + self.memory_bank_nodes + self.synthesis_nodes +
            self.frames + self.containers + self.notes
        )
        
        for item in all_items:
            if item == ignore_node: continue
            item_rect = self.calculate_node_rect(item, item.pos())
            if test_rect.intersects(item_rect):
                return True
        return False

    def find_free_position(self, base_pos, node, max_attempts=50):
        """Finds an unoccupied position for a new node."""
        def spiral_positions():
            x, y = base_pos.x(), base_pos.y()
            layer = 1
            spacing_x = self.horizontal_spacing + 50
            spacing_y = self.vertical_spacing + 50
            
            while True:
                for _ in range(layer): yield QPointF(x, y); x += spacing_x
                for _ in range(layer): yield QPointF(x, y); y += spacing_y
                layer += 1
                for _ in range(layer): yield QPointF(x, y); x -= spacing_x
                for _ in range(layer): yield QPointF(x, y); y -= spacing_y
                layer += 1

        for pos in spiral_positions():
            if max_attempts <= 0: break
            test_rect = self.calculate_node_rect(node, pos)
            if not self.check_collision(test_rect, node):
                return pos
            max_attempts -= 1

        return QPointF(base_pos.x(), base_pos.y() + len(self.nodes) * self.vertical_spacing)

    def mousePressEvent(self, event):
        """Handles mouse press events for adding/removing connection pins."""
        clicked_item = self.itemAt(event.scenePos(), QTransform())
        if not clicked_item:
            for item in self.items():
                if isinstance(item, ConnectionItem):
                    item.is_selected = False
                    item.stopArrowAnimation()
                    item.update()
                
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            if isinstance(item, ConnectionItem) and event.button() == Qt.MouseButton.LeftButton:
                item.add_pin(event.scenePos())
                event.accept()
                return
                
        super().mousePressEvent(event)
    
        if not event.modifiers and not self.itemAt(event.scenePos(), self.views()[0].transform()):
            self.clearSelection()
            
    def update_connections(self):
        """
        Updates the paths of all connections and removes any invalid connections.
        Also rebuilds the lookup map to ensure consistency (e.g. after file load).
        """
        # Rebuild map from scratch based on current lists
        self._node_connections_map.clear()

        all_nodes = (self.nodes + self.code_nodes + self.document_nodes + self.image_nodes + self.thinking_nodes + 
                     self.pycoder_nodes + self.web_nodes + 
                     self.conversation_nodes + self.reasoning_nodes + self.html_view_nodes + 
                     self.orchestrator_nodes + self.memory_bank_nodes + self.synthesis_nodes)
        
        # Validate and update primary connections.
        valid_connections = []
        for conn in self.connections[:]:
            try:
                start_node_valid = conn.start_node in all_nodes and conn.start_node.scene() == self
                end_node_valid = conn.end_node in all_nodes and conn.end_node.scene() == self

                if start_node_valid and end_node_valid and hasattr(conn.start_node, 'children') and conn.end_node in conn.start_node.children:
                    valid_connections.append(conn)
                    conn.setZValue(-1)
                    conn.update_path()
                    conn.show()
                    self.register_connection(conn) # Re-register
                else:
                    self.removeItem(conn)
            except RuntimeError:
                if conn.scene() == self: self.removeItem(conn)
        self.connections = valid_connections

        all_other_connections = [self.content_connections, self.document_connections, self.image_connections, self.thinking_connections,
                          self.system_prompt_connections, self.pycoder_connections, self.web_connections,
                          self.conversation_connections, self.reasoning_connections, self.group_summary_connections,
                          self.html_connections, self.orchestrator_connections, self.memory_bank_connections, self.synthesis_connections]

        for conn_list in all_other_connections:
            for conn in conn_list:
                conn.update_path()
                self.register_connection(conn) # Re-register

    def toggle_branch_visibility(self, originating_node):
        """
        Toggles the visibility of conversation branches.
        """
        if self.is_branch_hidden:
            for node in self.nodes:
                node.is_dimmed = False
                node.update()
            self.is_branch_hidden = False
            return

        active_branch = set()

        def get_ancestors(node):
            ancestors = set()
            current = node
            while current:
                ancestors.add(current)
                current = current.parent_node
            return ancestors

        def get_descendants(node):
            descendants = set()
            nodes_to_visit = [node]
            while nodes_to_visit:
                current = nodes_to_visit.pop(0)
                if current not in descendants:
                    descendants.add(current)
                    nodes_to_visit.extend(current.children)
            return descendants

        active_branch.update(get_ancestors(originating_node))
        active_branch.update(get_descendants(originating_node))

        for node in self.nodes:
            node.is_dimmed = node not in active_branch
            node.update()
        
        self.is_branch_hidden = True

    def _get_node_dimensions(self, node):
        """Helper to get a consistent width and height for any node type."""
        if hasattr(node, 'width') and hasattr(node, 'height'):
            return node.width, node.height
        bounds = node.boundingRect()
        return bounds.width(), bounds.height()

    def _position_subtree(self, node, x, y):
        """Recursively positions a node and its entire subtree in a horizontal layout."""
        is_fixed = node.parentItem() and isinstance(node.parentItem(), (Frame, Container))
        
        node_width, node_height = self._get_node_dimensions(node)

        if is_fixed:
            current_x = node.scenePos().x()
            current_y = node.scenePos().y()
        else:
            node.setPos(x, y)
            current_x = x
            current_y = y

        my_rect = QRectF(current_x, current_y, node_width, node_height)

        if not hasattr(node, 'children') or not node.children:
            return my_rect

        child_bounds = []
        child_x_start = current_x + node_width + self.horizontal_spacing
        current_child_y = current_y 
        
        for child in node.children:
            bounds = self._position_subtree(child, child_x_start, current_child_y)
            child_bounds.append(bounds)
            current_child_y = bounds.bottom() + self.vertical_spacing

        total_children_bounds = QRectF()
        if child_bounds:
            total_children_bounds = child_bounds[0]
            for bounds in child_bounds[1:]:
                total_children_bounds = total_children_bounds.united(bounds)

        if not is_fixed and child_bounds:
            parent_y = total_children_bounds.center().y() - node_height / 2
            node.setPos(x, parent_y)
            my_rect = QRectF(x, parent_y, node_width, node_height)

        return my_rect.united(total_children_bounds)

    def organize_nodes(self):
        """Automatically arranges all nodes into a non-overlapping, horizontal tree layout."""
        all_conversational_nodes = (
            self.nodes + self.pycoder_nodes + self.web_nodes +
            self.conversation_nodes + self.reasoning_nodes + self.html_view_nodes +
            self.orchestrator_nodes + self.memory_bank_nodes + self.synthesis_nodes
        )
        if not all_conversational_nodes:
            return

        root_nodes = [node for node in all_conversational_nodes if not (hasattr(node, 'parent_node') and node.parent_node)]
        root_nodes.sort(key=lambda n: n.pos().y())

        current_y_offset = 50.0
        for root in root_nodes:
            tree_bounds = self._position_subtree(root, 50.0, current_y_offset)
            current_y_offset = tree_bounds.bottom() + self.vertical_spacing * 2
        
        all_content_nodes = self.code_nodes + self.document_nodes + self.image_nodes + self.thinking_nodes
        for parent_node in all_conversational_nodes:
            associated_content = sorted(
                [cn for cn in all_content_nodes if hasattr(cn, 'parent_content_node') and cn.parent_content_node == parent_node],
                key=lambda n: n.pos().y()
            )
            
            if associated_content:
                parent_scene_x = parent_node.scenePos().x()
                parent_scene_y = parent_node.scenePos().y()

                parent_width, parent_height = self._get_node_dimensions(parent_node)
                current_content_y = parent_scene_y + parent_height + 50
                for content_node in associated_content:
                    if content_node.parentItem() and isinstance(content_node.parentItem(), (Frame, Container)):
                        continue

                    content_node_height = self._get_node_dimensions(content_node)[1]
                    content_node.setPos(QPointF(parent_scene_x, current_content_y))
                    current_content_y += content_node_height + 20

        self.update_connections()
        self.scene_changed.emit()

    def remove_associated_content_nodes(self, chat_node):
        """Finds and removes all Code, Document, and Image nodes linked to a given ChatNode."""
        nodes_to_remove = [cn for cn in self.code_nodes if cn.parent_content_node == chat_node]
        for node in nodes_to_remove:
            for conn in self.content_connections[:]:
                if conn.end_node == node:
                    self.removeItem(conn)
                    self.content_connections.remove(conn)
                    self.unregister_connection(conn)
            self.removeItem(node)
            if node in self.code_nodes: self.code_nodes.remove(node)

        docs_to_remove = [dn for dn in self.document_nodes if dn.parent_content_node == chat_node]
        for node in docs_to_remove:
            for conn in self.document_connections[:]:
                if conn.end_node == node:
                    self.removeItem(conn)
                    self.document_connections.remove(conn)
                    self.unregister_connection(conn)
            self.removeItem(node)
            if node in self.document_nodes: self.document_nodes.remove(node)
        
        images_to_remove = [im for im in self.image_nodes if im.parent_content_node == chat_node]
        for node in images_to_remove:
            for conn in self.image_connections[:]:
                if conn.end_node == node:
                    self.removeItem(conn)
                    self.image_connections.remove(conn)
                    self.unregister_connection(conn)
            self.removeItem(node)
            if node in self.image_nodes: self.image_nodes.remove(node)

        thinking_to_remove = [tn for tn in self.thinking_nodes if tn.parent_content_node == chat_node]
        for node in thinking_to_remove:
            for conn in self.thinking_connections[:]:
                if conn.end_node == node:
                    self.removeItem(conn)
                    self.thinking_connections.remove(conn)
                    self.unregister_connection(conn)
            self.removeItem(node)
            if node in self.thinking_nodes: self.thinking_nodes.remove(node)
        
        self.scene_changed.emit()

    def _recursively_delete_node(self, node_to_delete):
        """Recursively deletes a node and its entire subtree of children."""
        if not node_to_delete or not node_to_delete.scene():
            return

        if hasattr(node_to_delete, 'children'):
            for child in list(node_to_delete.children):
                self._recursively_delete_node(child)

        if hasattr(node_to_delete, 'parent_node') and node_to_delete.parent_node:
            if node_to_delete in node_to_delete.parent_node.children:
                node_to_delete.parent_node.children.remove(node_to_delete)

        all_conn_lists = [
            self.connections, self.content_connections, self.document_connections, self.image_connections,
            self.thinking_connections, self.system_prompt_connections, self.pycoder_connections, self.web_connections,
            self.conversation_connections, self.reasoning_connections, self.group_summary_connections,
            self.html_connections, self.orchestrator_connections, self.memory_bank_connections, self.synthesis_connections
        ]
        for conn_list in all_conn_lists:
            for conn in conn_list[:]:
                if node_to_delete in (conn.start_node, conn.end_node):
                    self.removeItem(conn)
                    if conn in conn_list:
                        conn_list.remove(conn)
                    self.unregister_connection(conn)
        
        if isinstance(node_to_delete, ChatNode):
            self.remove_associated_content_nodes(node_to_delete)

        node_lists = {
            ChatNode: self.nodes, CodeNode: self.code_nodes, DocumentNode: self.document_nodes,
            ImageNode: self.image_nodes, ThinkingNode: self.thinking_nodes, PyCoderNode: self.pycoder_nodes,
            WebNode: self.web_nodes, ConversationNode: self.conversation_nodes, ReasoningNode: self.reasoning_nodes,
            HtmlViewNode: self.html_view_nodes, OrchestratorNode: self.orchestrator_nodes, MemoryBankNode: self.memory_bank_nodes,
            SynthesisNode: self.synthesis_nodes
        }
        for node_type, node_list in node_lists.items():
            if isinstance(node_to_delete, node_type) and node_to_delete in node_list:
                node_list.remove(node_to_delete)
                break

        self.removeItem(node_to_delete)

        if self.window and self.window.current_node == node_to_delete:
            self.window.setCurrentNode(None)

    def deleteSelectedItems(self):
        """Deletes all currently selected items, with confirmation and recursive deletion for nodes."""
        items_to_delete = list(self.selectedItems())
        if not items_to_delete:
            return

        reply = QMessageBox.question(
            self.views()[0], 'Confirm Deletion',
            'Are you sure you want to delete the selected item(s)?\nThis will also delete all subsequent nodes in any selected branch and cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return

        node_types = (ChatNode, CodeNode, DocumentNode, ImageNode, ThinkingNode, 
                      PyCoderNode, WebNode, ConversationNode, ReasoningNode, HtmlViewNode,
                      OrchestratorNode, MemoryBankNode, SynthesisNode)
        nodes_to_delete = [item for item in items_to_delete if isinstance(item, node_types)]
        other_items_to_delete = [item for item in items_to_delete if not isinstance(item, node_types)]

        top_level_nodes = [node for node in nodes_to_delete if not (
            (hasattr(node, 'parent_node') and node.parent_node in nodes_to_delete) or
            (hasattr(node, 'parent_content_node') and node.parent_content_node in nodes_to_delete)
        )]

        for node in top_level_nodes:
            self._recursively_delete_node(node)

        for item in other_items_to_delete:
            if isinstance(item, Frame): self.deleteFrame(item)
            elif isinstance(item, Container): self.deleteContainer(item)
            elif isinstance(item, Note):
                for conn_list in [self.system_prompt_connections, self.group_summary_connections]:
                    for conn in conn_list[:]:
                        if item in (conn.start_node, conn.end_node): 
                            self.removeItem(conn)
                            conn_list.remove(conn)
                            self.unregister_connection(conn)
                self.removeItem(item)
                if item in self.notes: self.notes.remove(item)
            elif isinstance(item, ChartItem): self.removeItem(item)
            elif isinstance(item, NavigationPin):
                if hasattr(self.window, 'pin_overlay') and self.window.pin_overlay:
                     self.window.pin_overlay.remove_pin(item)
                
                if item in self.pins:
                     self.pins.remove(item)
                
                if item.scene() == self:
                    self.removeItem(item)
        
        if self.window.current_node and not self.window.current_node.scene():
            self.window.setCurrentNode(None)

        self.update_connections()
        self.scene_changed.emit()

    def _clear_smart_guides(self):
        """Removes all smart guide lines from the scene."""
        for line in self.smart_guide_lines:
            self.removeItem(line)
        self.smart_guide_lines.clear()

    def _calculate_smart_guide_snap(self, moving_item, new_pos):
        """
        Calculates a new position for a moving item by checking for alignment
        with other static items in the scene (smart guides).
        OPTIMIZED: Uses cached self._alignment_targets
        """
        ALIGNMENT_TOLERANCE = 5
        snapped_pos = QPointF(new_pos)
        snapped_x, snapped_y = False, False

        moving_rect = moving_item.sceneBoundingRect()
        offset = new_pos - moving_item.pos()
        moving_rect.translate(offset)
        
        moving_points = {
            'v_left': moving_rect.left(), 'v_center': moving_rect.center().x(), 'v_right': moving_rect.right(),
            'h_top': moving_rect.top(), 'h_middle': moving_rect.center().y(), 'h_bottom': moving_rect.bottom(),
        }

        # Iterate only over cached targets, ignoring self if present
        for static_item in self._alignment_targets:
            if static_item == moving_item: continue
            
            static_rect = static_item.sceneBoundingRect()
            static_points = {
                'v_left': static_rect.left(), 'v_center': static_rect.center().x(), 'v_right': static_rect.right(),
                'h_top': static_rect.top(), 'h_middle': static_rect.center().y(), 'h_bottom': static_rect.bottom(),
            }

            if not snapped_x:
                for m_key, m_val in moving_points.items():
                    if m_key.startswith('v_'):
                        for s_key, s_val in static_points.items():
                            if s_key == m_key and abs(m_val - s_val) < ALIGNMENT_TOLERANCE:
                                snapped_pos.setX(snapped_pos.x() + (s_val - m_val))
                                y1, y2 = min(moving_rect.top(), static_rect.top()), max(moving_rect.bottom(), static_rect.bottom())
                                line = QGraphicsLineItem(s_val, y1, s_val, y2)
                                line.setPen(QPen(QColor(255, 0, 100, 200), 1, Qt.PenStyle.DashLine))
                                self.addItem(line)
                                self.smart_guide_lines.append(line)
                                snapped_x = True
                                break
                    if snapped_x: break
            
            if not snapped_y:
                for m_key, m_val in moving_points.items():
                    if m_key.startswith('h_'):
                        for s_key, s_val in static_points.items():
                            if s_key == m_key and abs(m_val - s_val) < ALIGNMENT_TOLERANCE:
                                snapped_pos.setY(snapped_pos.y() + (s_val - m_val))
                                x1, x2 = min(moving_rect.left(), static_rect.left()), max(moving_rect.right(), static_rect.right())
                                line = QGraphicsLineItem(x1, s_val, x2, s_val)
                                line.setPen(QPen(QColor(255, 0, 100, 200), 1, Qt.PenStyle.DashLine))
                                self.addItem(line)
                                self.smart_guide_lines.append(line)
                                snapped_y = True
                                break
                    if snapped_y: break
            
            if snapped_x and snapped_y:
                return snapped_pos
        
        return snapped_pos

    def snap_position(self, item, new_pos):
        """Determines the final snapped position of an item."""
        self._clear_smart_guides()
        snapped_pos = QPointF(new_pos)
        
        x_was_snapped, y_was_snapped = False, False
        if self.smart_guides and self.is_dragging_item:
            guide_snapped_pos = self._calculate_smart_guide_snap(item, new_pos)
            x_was_snapped = abs(guide_snapped_pos.x() - new_pos.x()) > 0.1
            y_was_snapped = abs(guide_snapped_pos.y() - new_pos.y()) > 0.1
            snapped_pos = guide_snapped_pos

        if self.snap_to_grid:
            grid_size = self.views()[0].grid_control.grid_size
            if not x_was_snapped:
                snapped_pos.setX(round(new_pos.x() / grid_size) * grid_size)
            if not y_was_snapped:
                snapped_pos.setY(round(new_pos.y() / grid_size) * grid_size)
                
        return snapped_pos

    def create_web_node(self, parent_node):
        web_node = WebNode(parent_node=parent_node)
        parent_node.children.append(web_node)
        web_node.run_button_clicked.connect(self.window.execute_web_node)
        
        parent_pos = parent_node.pos()
        parent_width = parent_node.width if hasattr(parent_node, 'width') else parent_node.boundingRect().width()
        
        child_count = len(parent_node.children)
        y_offset = (child_count - 1) * (web_node.height + 50)
        
        base_pos = QPointF(parent_pos.x() + parent_width + 150, parent_pos.y() + y_offset)
        web_node_pos = self.find_free_position(base_pos, web_node)
        web_node.setPos(web_node_pos)

        self.addItem(web_node)
        self.web_nodes.append(web_node)

        connection = WebConnectionItem(parent_node, web_node)
        web_node.incoming_connection = connection
        self.add_connection_to_scene(connection, self.web_connections)
        self.scene_changed.emit()
        return web_node

    def create_pycoder_node(self, parent_node):
        pycoder_node = PyCoderNode(parent_node=parent_node)
        parent_node.children.append(pycoder_node)
        
        parent_pos = parent_node.pos()
        parent_width = parent_node.width if hasattr(parent_node, 'width') else parent_node.boundingRect().width()

        child_count = len(parent_node.children)
        y_offset = (child_count - 1) * (pycoder_node.height + 50)

        base_pos = QPointF(parent_pos.x() + parent_width + 150, parent_pos.y() + y_offset)
        pycoder_pos = self.find_free_position(base_pos, pycoder_node)
        pycoder_node.setPos(pycoder_pos)

        self.addItem(pycoder_node)
        self.pycoder_nodes.append(pycoder_node)

        connection = PyCoderConnectionItem(parent_node, pycoder_node)
        pycoder_node.incoming_connection = connection
        self.add_connection_to_scene(connection, self.pycoder_connections)
        self.scene_changed.emit()
        return pycoder_node

    def create_memory_bank_node(self, parent_node):
        memory_node = MemoryBankNode(parent_node=parent_node)
        parent_node.children.append(memory_node)
        
        parent_pos = parent_node.pos()
        parent_width = parent_node.width if hasattr(parent_node, 'width') else parent_node.boundingRect().width()
        
        child_count = len(parent_node.children)
        y_offset = (child_count - 1) * (memory_node.height + 50)
        
        base_pos = QPointF(parent_pos.x() + parent_width + 150, parent_pos.y() + y_offset)
        node_pos = self.find_free_position(base_pos, memory_node)
        memory_node.setPos(node_pos)

        self.addItem(memory_node)
        self.memory_bank_nodes.append(memory_node)

        connection = MemoryBankConnectionItem(parent_node, memory_node)
        memory_node.incoming_connection = connection
        self.add_connection_to_scene(connection, self.memory_bank_connections)
        self.scene_changed.emit()
        return memory_node

    def create_synthesis_node(self, parent_node):
        synthesis_node = SynthesisNode(parent_node=parent_node)
        parent_node.children.append(synthesis_node)

        parent_pos = parent_node.pos()
        parent_width = parent_node.width if hasattr(parent_node, 'width') else parent_node.boundingRect().width()
        
        child_count = len(parent_node.children)
        y_offset = (child_count - 1) * (synthesis_node.height + 50)
        
        base_pos = QPointF(parent_pos.x() + parent_width + 150, parent_pos.y() + y_offset)
        node_pos = self.find_free_position(base_pos, synthesis_node)
        synthesis_node.setPos(node_pos)

        self.addItem(synthesis_node)
        self.synthesis_nodes.append(synthesis_node)

        connection = SynthesisConnectionItem(parent_node, synthesis_node)
        synthesis_node.incoming_connection = connection
        self.add_connection_to_scene(connection, self.synthesis_connections)
        self.scene_changed.emit()
        return synthesis_node

    def clear(self):
        """
        Clears the entire scene, removing all items and resetting all tracking lists.
        """
        super().clear()
        self.nodes.clear()
        self.connections.clear()
        self.frames.clear()
        self.containers.clear()
        self.pins.clear()
        self.notes.clear()
        self.code_nodes.clear()
        self.document_nodes.clear()
        self.image_nodes.clear()
        self.thinking_nodes.clear()
        self.pycoder_nodes.clear()
        self.web_nodes.clear()
        self.conversation_nodes.clear()
        self.reasoning_nodes.clear()
        self.html_view_nodes.clear()
        self.content_connections.clear()
        self.document_connections.clear()
        self.image_connections.clear()
        self.thinking_connections.clear()
        self.system_prompt_connections.clear()
        self.pycoder_connections.clear()
        self.web_connections.clear()
        self.conversation_connections.clear()
        self.reasoning_connections.clear()
        self.group_summary_connections.clear()
        self.html_connections.clear()
        self.orchestrator_nodes.clear()
        self.memory_bank_nodes.clear()
        self.orchestrator_connections.clear()
        self.memory_bank_connections.clear()
        self.synthesis_nodes.clear()
        self.synthesis_connections.clear()
        self._node_connections_map.clear()
        self._alignment_targets = []
        if hasattr(self, 'window') and self.window:
            self.window.current_node = None
        self.scene_changed.emit()