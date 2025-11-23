from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QPointF

from graphite_connections import (
    SystemPromptConnectionItem, PyCoderConnectionItem, ConversationConnectionItem,
    ReasoningConnectionItem, HtmlConnectionItem, OrchestratorConnectionItem,
    MemoryBankConnectionItem, SynthesisConnectionItem
)
from graphite_config import get_current_palette
from graphite_pycoder import PyCoderNode
from graphite_node import ChatNode, CodeNode
from graphite_web import WebNode, WebConnectionItem
from graphite_conversation_node import ConversationNode
from graphite_reasoning import ReasoningNode
from graphite_html_view import HtmlViewNode
from graphite_orchestrator import (
    OrchestratorNode, MemoryBankNode, SynthesisNode
)


class PluginPortal:
    """
    The PluginPortal acts as a centralized manager for discovering,
    listing, and executing available plugins. It provides a stable interface
    for the main application to interact with, decoupling the core logic
 from the plugins themselves. Each plugin is responsible for creating
    and configuring a specific type of specialized node on the canvas.
    """
    def __init__(self, main_window):
        """
        Initializes the PluginPortal.

        Args:
            main_window (QMainWindow): A reference to the main application window.
        """
        self.main_window = main_window
        self.plugins = []
        self._discover_plugins()

    def _discover_plugins(self):
        """
        Finds and registers available plugins. In a real-world scenario, this
        might scan a directory for plugin files. For now, plugins are manually
        defined here. Each plugin is a dictionary containing its name, a user-facing
        description, and the callback function to execute it.
        """
        self.plugins.append({
            'name': 'Agent Orchestrator',
            'description': 'Adds a conductor node to manage multi-agent workflows.',
            'callback': self._create_orchestrator_node
        })

        self.plugins.append({
            'name': 'Memory Bank',
            'description': 'Adds a key-value store for agents to share memory.',
            'callback': self._create_memory_bank_node
        })

        self.plugins.append({
            'name': 'Text Synthesizer',
            'description': 'Adds a node to summarize, combine, or reformat text.',
            'callback': self._create_synthesis_node
        })

        self.plugins.append({
            'name': 'System Prompt',
            'description': 'Adds a special node to override the default system prompt for a conversation branch.',
            'callback': self._create_system_prompt_node
        })
        
        self.plugins.append({
            'name': 'Py-Coder',
            'description': 'Opens a Python execution environment to run code and get AI analysis.',
            'callback': self._create_pycoder_node
        })

        self.plugins.append({
            'name': 'Graphite-Web',
            'description': 'Adds a node with web access for real-time information retrieval.',
            'callback': self._create_web_node
        })

        self.plugins.append({
            'name': 'Conversation Node',
            'description': 'Adds a node for a self-contained, linear chat conversation.',
            'callback': self._create_conversation_node
        })

        self.plugins.append({
            'name': 'Graphite-Reasoning',
            'description': 'A multi-step reasoning agent for solving complex problems.',
            'callback': self._create_reasoning_node
        })

        self.plugins.append({
            'name': 'HTML Renderer',
            'description': 'Adds a node to render HTML code from a parent node.',
            'callback': self._create_html_view_node
        })

    def get_plugins(self):
        """
        Returns a list of all discovered and available plugins.

        Returns:
            list[dict]: A list of plugin dictionaries, each with 'name', 'description', and 'callback'.
        """
        return self.plugins

    def execute_plugin(self, plugin_name):
        """
        Finds a plugin by its name and executes its associated callback function.

        Args:
            plugin_name (str): The name of the plugin to execute.
        """
        for plugin in self.plugins:
            if plugin['name'] == plugin_name:
                plugin['callback']()
                return
        print(f"Warning: Plugin '{plugin_name}' not found.")

    def _get_root_node(self):
        """
        Finds the root node of the currently selected branch. If no node is selected,
        it finds the first root-level node in the scene. This is used to anchor
        branch-wide plugins like the System Prompt.

        Returns:
            ChatNode or None: The root node of the current branch, or None if no suitable node is found.
        """
        scene = self.main_window.chat_view.scene()
        current_node = self.main_window.current_node

        if current_node:
            # Traverse up the parent chain to find the root.
            root_node = current_node
            while root_node.parent_node:
                root_node = root_node.parent_node
            return root_node
        
        # If no node is selected, find the first root node in the entire scene.
        for node in scene.nodes:
            if not node.parent_node:
                return node
        
        return None

    def _create_orchestrator_node(self):
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        valid_parents = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, MemoryBankNode, SynthesisNode)
        if not selected_node or not isinstance(selected_node, valid_parents):
            QMessageBox.warning(self.main_window, "Invalid Parent Node", "Please select a valid conversational or tool node to branch from. Orchestrators cannot be chained.")
            return

        # Create the OrchestratorNode and connect its execution signal.
        orchestrator_node = OrchestratorNode(parent_node=selected_node)
        selected_node.children.append(orchestrator_node)
        
        orchestrator_node.orchestration_requested.connect(self.main_window.execute_orchestrator_node)
        
        # Position it relative to the parent.
        parent_pos = selected_node.pos()
        parent_width = selected_node.width if hasattr(selected_node, 'width') else selected_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        node_pos = scene.find_free_position(base_pos, orchestrator_node)
        orchestrator_node.setPos(node_pos)

        scene.addItem(orchestrator_node)
        scene.orchestrator_nodes.append(orchestrator_node)

        # Create the specialized connection.
        connection = OrchestratorConnectionItem(selected_node, orchestrator_node)
        orchestrator_node.incoming_connection = connection
        scene.addItem(connection)
        scene.orchestrator_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_memory_bank_node(self):
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        valid_parents = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
        if not selected_node or not isinstance(selected_node, valid_parents):
            QMessageBox.warning(self.main_window, "Action Required", "Please select a valid node to branch from before adding a Memory Bank.")
            return

        # Create the MemoryBankNode.
        memory_node = MemoryBankNode(parent_node=selected_node)
        selected_node.children.append(memory_node)
        
        # Position it relative to the parent.
        parent_pos = selected_node.pos()
        parent_width = selected_node.width if hasattr(selected_node, 'width') else selected_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        node_pos = scene.find_free_position(base_pos, memory_node)
        memory_node.setPos(node_pos)

        scene.addItem(memory_node)
        scene.memory_bank_nodes.append(memory_node)

        # Create the specialized connection.
        connection = MemoryBankConnectionItem(selected_node, memory_node)
        memory_node.incoming_connection = connection
        scene.addItem(connection)
        scene.memory_bank_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_synthesis_node(self):
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        valid_parents = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
        if not selected_node or not isinstance(selected_node, valid_parents):
            QMessageBox.warning(self.main_window, "Action Required", "Please select a valid node to branch from before adding a Synthesizer.")
            return

        synthesis_node = SynthesisNode(parent_node=selected_node)
        selected_node.children.append(synthesis_node)

        parent_pos = selected_node.pos()
        parent_width = selected_node.width if hasattr(selected_node, 'width') else selected_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        node_pos = scene.find_free_position(base_pos, synthesis_node)
        synthesis_node.setPos(node_pos)

        scene.addItem(synthesis_node)
        scene.synthesis_nodes.append(synthesis_node)

        connection = SynthesisConnectionItem(selected_node, synthesis_node)
        synthesis_node.incoming_connection = connection
        scene.addItem(connection)
        scene.synthesis_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_system_prompt_node(self):
        """
        Callback to create a System Prompt node. This creates a specialized Note
        and connects it to the root of the current conversation branch.
        """
        scene = self.main_window.chat_view.scene()
        root_node = self._get_root_node()

        if not root_node:
            QMessageBox.warning(self.main_window, "Action Required", "Please start a conversation before adding a System Prompt.")
            return

        # Check if this root node already has a system prompt to avoid duplicates.
        for conn in scene.system_prompt_connections:
            if conn.end_node == root_node:
                QMessageBox.information(self.main_window, "Info", "A System Prompt node already exists for this conversation branch.")
                return

        palette = get_current_palette()

        # Create and configure the note to act as the system prompt editor.
        # For notes, we usually don't use collision detection as strictly since they float, 
        # but we can check if the space directly above is free.
        note_pos = QPointF(root_node.pos().x(), root_node.pos().y() - 200)
        prompt_note = scene.add_note(note_pos)
        
        # If default pos collides, try to find free space above
        rect = scene.calculate_node_rect(prompt_note, note_pos)
        if scene.check_collision(rect, prompt_note):
             note_pos = scene.find_free_position(note_pos, prompt_note)
             prompt_note.setPos(note_pos)

        prompt_note.is_system_prompt = True
        prompt_note.content = "Enter custom system prompt here..."
        prompt_note.header_color = palette.FRAME_COLORS["Purple Header"]["color"]
        prompt_note.color = "#252526"
        prompt_note.width = 300
        prompt_note.height = 150

        # Create the special connection to link the prompt to the conversation branch.
        connection = SystemPromptConnectionItem(prompt_note, root_node)
        scene.addItem(connection)
        scene.system_prompt_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_pycoder_node(self):
        """
        Callback to create a PyCoder node. It branches off the currently selected node,
        creating the node and its specialized connection.
        """
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        if not selected_node:
            QMessageBox.warning(self.main_window, "Action Required", "Please select a node to branch from before adding Py-Coder.")
            return

        # Determine the correct parent for conversational context. If a CodeNode is selected,
        # use its parent ChatNode as the context.
        parent_node = selected_node
        if isinstance(selected_node, CodeNode):
            parent_node = selected_node.parent_content_node
        
        valid_parents = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
        if not isinstance(parent_node, valid_parents):
             QMessageBox.warning(self.main_window, "Invalid Parent", "Py-Coder can only branch from a valid conversational or tool node.")
             return

        # Create the PyCoderNode instance.
        pycoder_node = PyCoderNode(parent_node=parent_node)
        parent_node.children.append(pycoder_node)
        
        # Position it to the right of the parent node.
        parent_pos = parent_node.pos()
        parent_width = parent_node.width if hasattr(parent_node, 'width') else parent_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        pycoder_pos = scene.find_free_position(base_pos, pycoder_node)
        pycoder_node.setPos(pycoder_pos)

        scene.addItem(pycoder_node)
        scene.pycoder_nodes.append(pycoder_node)

        # Create the specialized connection.
        connection = PyCoderConnectionItem(parent_node, pycoder_node)
        pycoder_node.incoming_connection = connection
        scene.addItem(connection)
        scene.pycoder_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_web_node(self):
        """
        Callback to create a WebNode for internet searches. It branches off the
        currently selected node.
        """
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        valid_parents = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
        if not selected_node or not isinstance(selected_node, valid_parents):
            QMessageBox.warning(self.main_window, "Action Required", "Please select a valid node to branch from before adding a Web Node.")
            return

        # Create the WebNode and connect its execution signal.
        web_node = WebNode(parent_node=selected_node)
        selected_node.children.append(web_node)
        web_node.run_button_clicked.connect(self.main_window.execute_web_node)
        
        # Position it relative to the parent.
        parent_pos = selected_node.pos()
        parent_width = selected_node.width if hasattr(selected_node, 'width') else selected_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        web_node_pos = scene.find_free_position(base_pos, web_node)
        web_node.setPos(web_node_pos)

        scene.addItem(web_node)
        scene.web_nodes.append(web_node)

        # Create the specialized connection.
        connection = WebConnectionItem(selected_node, web_node)
        web_node.incoming_connection = connection
        scene.addItem(connection)
        scene.web_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_conversation_node(self):
        """
        Callback to create a ConversationNode for self-contained chats. It inherits
        the conversation history from its parent.
        """
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        valid_parents = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
        if not selected_node or not isinstance(selected_node, valid_parents):
            QMessageBox.warning(self.main_window, "Action Required", "Please select a valid node to branch from before adding a Conversation Node.")
            return

        # Create the ConversationNode and connect its request signal.
        convo_node = ConversationNode(parent_node=selected_node)
        selected_node.children.append(convo_node)
        convo_node.ai_request_sent.connect(self.main_window.handle_conversation_node_request)
        
        # Inherit the conversation history from its parent to provide context.
        if hasattr(selected_node, 'conversation_history') and selected_node.conversation_history:
            history_copy = selected_node.conversation_history[:]
            convo_node.set_history(history_copy)

        # Position it relative to the parent.
        parent_pos = selected_node.pos()
        parent_width = selected_node.width if hasattr(selected_node, 'width') else selected_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        convo_node_pos = scene.find_free_position(base_pos, convo_node)
        convo_node.setPos(convo_node_pos)

        scene.addItem(convo_node)
        scene.conversation_nodes.append(convo_node)

        # Create the specialized connection.
        connection = ConversationConnectionItem(selected_node, convo_node)
        convo_node.incoming_connection = connection
        scene.addItem(connection)
        scene.conversation_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_reasoning_node(self):
        """
        Callback to create a ReasoningNode for multi-step problem-solving.
        """
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        valid_parents = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
        if not selected_node or not isinstance(selected_node, valid_parents):
            QMessageBox.warning(self.main_window, "Action Required", "Please select a valid node to branch from before adding a Reasoning Node.")
            return

        # Create the ReasoningNode and connect its request signal.
        reasoning_node = ReasoningNode(parent_node=selected_node)
        selected_node.children.append(reasoning_node)
        reasoning_node.reasoning_requested.connect(self.main_window.execute_reasoning_node)
        
        # Position it relative to the parent.
        parent_pos = selected_node.pos()
        parent_width = reasoning_node.width if hasattr(reasoning_node, 'width') else reasoning_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        reasoning_node_pos = scene.find_free_position(base_pos, reasoning_node)
        reasoning_node.setPos(reasoning_node_pos)

        scene.addItem(reasoning_node)
        scene.reasoning_nodes.append(reasoning_node)

        # Create the specialized connection.
        connection = ReasoningConnectionItem(selected_node, reasoning_node)
        reasoning_node.incoming_connection = connection
        scene.addItem(connection)
        scene.reasoning_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)

    def _create_html_view_node(self):
        """
        Callback to create an HtmlViewNode. It branches off the currently selected node,
        ideally a CodeNode containing HTML.
        """
        scene = self.main_window.chat_view.scene()
        selected_node = self.main_window.current_node

        valid_parents = (ChatNode, CodeNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
        if not selected_node or not isinstance(selected_node, valid_parents):
            QMessageBox.warning(self.main_window, "Action Required", "Please select a valid node (e.g., a Code Node) to branch from before adding an HTML Renderer.")
            return

        # Create the HtmlViewNode
        html_view_node = HtmlViewNode(parent_node=selected_node)
        selected_node.children.append(html_view_node)
        
        # Position it relative to the parent
        parent_pos = selected_node.pos()
        parent_width = selected_node.width if hasattr(selected_node, 'width') else selected_node.boundingRect().width()
        base_pos = QPointF(parent_pos.x() + parent_width + 100, parent_pos.y())
        html_node_pos = scene.find_free_position(base_pos, html_view_node)
        html_view_node.setPos(html_node_pos)

        scene.addItem(html_view_node)
        scene.html_view_nodes.append(html_view_node)
        
        # If the parent is a CodeNode, pre-fill the HTML content
        if isinstance(selected_node, CodeNode):
            html_view_node.set_html_content(selected_node.code)

        # Create the specialized connection
        connection = HtmlConnectionItem(selected_node, html_view_node)
        html_view_node.incoming_connection = connection
        scene.addItem(connection)
        scene.html_connections.append(connection)
        
        # Register connection for updates
        scene.register_connection(connection)