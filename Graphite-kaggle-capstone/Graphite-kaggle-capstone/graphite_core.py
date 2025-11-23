import json
import sqlite3
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, QThread, Signal
from PySide6.QtGui import QTransform
import base64

# Import UI classes needed for serialization/deserialization
from graphite_canvas_items import Note, NavigationPin, Frame, Container
from graphite_chart_item import ChartItem
from graphite_connections import (
    ConnectionItem, ContentConnectionItem, SystemPromptConnectionItem,
    DocumentConnectionItem, ImageConnectionItem, PyCoderConnectionItem,
    ConversationConnectionItem, ReasoningConnectionItem, GroupSummaryConnectionItem,
    HtmlConnectionItem, ThinkingConnectionItem, OrchestratorConnectionItem, MemoryBankConnectionItem,
    SynthesisConnectionItem
)
from graphite_node import ChatNode, CodeNode, DocumentNode, ImageNode, ThinkingNode
from graphite_pycoder import PyCoderNode, PyCoderMode
from graphite_web import WebNode, WebConnectionItem
from graphite_conversation_node import ConversationNode
from graphite_reasoning import ReasoningNode
from graphite_html_view import HtmlViewNode
from graphite_orchestrator import OrchestratorNode, MemoryBankNode, SynthesisNode
import graphite_config as config
import api_provider

def _process_content_for_serialization(content):
    """
    Recursively finds and base64-encodes image bytes within a list of content parts.
    This prepares multi-modal content for JSON serialization.

    Args:
        content (list or any): The content to process. Expected to be a list for multi-modal messages.

    Returns:
        list or any: A new list with image data encoded, or the original content if not a list.
    """
    if isinstance(content, list):
        processed_parts = []
        for part in content:
            # Check for the specific image_bytes dictionary structure
            if isinstance(part, dict) and part.get('type') == 'image_bytes' and isinstance(part.get('data'), bytes):
                # Create a copy to avoid modifying the original in-memory object
                new_part = part.copy()
                # Encode the raw bytes into a base64 string
                new_part['data'] = base64.b64encode(part['data']).decode('utf-8')
                processed_parts.append(new_part)
            else:
                # Append non-image parts as-is
                processed_parts.append(part)
        return processed_parts
    return content

def _process_content_for_deserialization(content):
    """
    Recursively finds and base64-decodes image strings within a list of content parts.
    This reconstructs raw image bytes after loading from a JSON file.

    Args:
        content (list or any): The content to process.

    Returns:
        list or any: A new list with image data decoded back to bytes, or the original content.
    """
    if isinstance(content, list):
        processed_parts = []
        for part in content:
            # Look for the specific structure of an encoded image part
            if isinstance(part, dict) and part.get('type') == 'image_bytes' and isinstance(part.get('data'), str):
                new_part = part.copy()
                try:
                    # Decode the base64 string back into raw bytes
                    new_part['data'] = base64.b64decode(part['data'])
                    processed_parts.append(new_part)
                except (base64.binascii.Error, ValueError):
                    # Handle case where data is malformed or corrupted, skip this part
                    continue
            else:
                # Append non-image parts as-is
                processed_parts.append(part)
        return processed_parts
    return content

class TitleGenerator:
    """An agent responsible for generating concise titles for new chat sessions."""
    def __init__(self):
        """Initializes the TitleGenerator with a specific system prompt."""
        self.system_prompt = """You are a title generation assistant. Your only job is to create short, 
        2-3 word titles based on conversation content. Rules:
        - ONLY output the title, nothing else
        - Keep it between 2-3 words
        - Use title case
        - Make it descriptive but concise
        - NO punctuation
        - NO explanations
        - NO additional text"""
        
    def generate_title(self, message):
        """
        Generates a 2-3 word title based on the first user message of a chat.

        Args:
            message (str): The text content of the message to use for title generation.

        Returns:
            str: A formatted title string, or a default timestamped title on failure.
        """
        try:
            title = ""
            messages = [
                {'role': 'system', 'content': self.system_prompt},
                {'role': 'user', 'content': f"Create a 2-3 word title for this message: {message}"}
            ]
            response = api_provider.chat(task=config.TASK_TITLE, messages=messages)
            title = response['message']['content'].strip()

            # Clean up title to ensure it adheres to the length constraint
            title = ' '.join(title.split()[:3])
            return title
        except Exception as e:
            # Fallback to a timestamped title if the API call fails
            print(f"Title generation failed: {e}")
            return f"Chat {datetime.now().strftime('%Y%m%d_%H%M')}"

class ChatDatabase:
    """Manages the SQLite database for storing and retrieving all chat session data."""
    def __init__(self):
        """Initializes the database connection and ensures the schema is up to date."""
        self.db_path = Path.home() / '.graphite' / 'chats.db'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
        
    def init_database(self):
        """
        Creates all necessary tables if they don't exist and performs schema migrations
        by adding new columns to existing tables for backward compatibility.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Main table for storing chat sessions. 'data' column holds the JSON blob.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data TEXT NOT NULL
                )
            """)
            
            # Separate table for notes, linked by chat_id for efficient loading.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    position_x REAL NOT NULL,
                    position_y REAL NOT NULL,
                    width REAL NOT NULL,
                    height REAL NOT NULL,
                    color TEXT NOT NULL,
                    header_color TEXT,
                    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
                )
            """)
            
            # Separate table for navigation pins.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    note TEXT,
                    position_x REAL NOT NULL,
                    position_y REAL NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
                )
            """)

            # --- Schema Migration Logic ---
            # This section ensures that databases created with older versions of the application
            # are updated with new columns without losing data.
            cursor.execute("PRAGMA table_info(notes)")
            columns = [info[1] for info in cursor.fetchall()]
            
            # Add a boolean column to identify system prompt notes
            if 'is_system_prompt' not in columns:
                try:
                    cursor.execute("ALTER TABLE notes ADD COLUMN is_system_prompt INTEGER DEFAULT 0")
                    conn.commit()
                except sqlite3.OperationalError as e:
                    # This might happen in a race condition, but it's safe to ignore.
                    print(f"Could not add column, it might already exist: {e}")
            
            # Add a boolean column to identify group summary notes
            if 'is_summary_note' not in columns:
                try:
                    cursor.execute("ALTER TABLE notes ADD COLUMN is_summary_note INTEGER DEFAULT 0")
                    conn.commit()
                except sqlite3.OperationalError as e:
                    print(f"Could not add column, it might already exist: {e}")
            
    def save_pins(self, chat_id, pins_data):
        """
        Saves all navigation pins for a given chat session.

        Args:
            chat_id (int): The ID of the chat session.
            pins_data (list[dict]): A list of serialized pin dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            # First delete existing pins for this chat to prevent duplicates
            conn.execute("DELETE FROM pins WHERE chat_id = ?", (chat_id,))
            
            # Insert new pins
            for pin_data in pins_data:
                conn.execute("""
                    INSERT INTO pins (
                        chat_id, title, note, position_x, position_y
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    chat_id,
                    pin_data['title'],
                    pin_data['note'],
                    pin_data['position']['x'],
                    pin_data['position']['y']
                ))
                
    def load_pins(self, chat_id):
        """
        Loads all navigation pins for a chat session.

        Args:
            chat_id (int): The ID of the chat session.

        Returns:
            list[dict]: A list of deserialized pin dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT title, note, position_x, position_y
                FROM pins WHERE chat_id = ?
            """, (chat_id,))
            
            pins = []
            for row in cursor.fetchall():
                pins.append({
                    'title': row[0],
                    'note': row[1],
                    'position': {'x': row[2], 'y': row[3]}
                })
            return pins
            
    def save_notes(self, chat_id, notes_data):
        """
        Saves all notes for a given chat session.

        Args:
            chat_id (int): The ID of the chat session.
            notes_data (list[dict]): A list of serialized note dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            # First delete existing notes for this chat
            conn.execute("DELETE FROM notes WHERE chat_id = ?", (chat_id,))
            
            # Insert new notes
            for note_data in notes_data:
                conn.execute("""
                    INSERT INTO notes (
                        chat_id, content, position_x, position_y,
                        width, height, color, header_color, is_system_prompt, is_summary_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chat_id,
                    note_data['content'],
                    note_data['position']['x'],
                    note_data['position']['y'],
                    note_data['size']['width'],
                    note_data['size']['height'],
                    note_data['color'],
                    note_data.get('header_color'),
                    1 if note_data.get('is_system_prompt') else 0,
                    1 if note_data.get('is_summary_note') else 0
                ))
                
    def load_notes(self, chat_id):
        """
        Loads all notes for a chat session.

        Args:
            chat_id (int): The ID of the chat session.

        Returns:
            list[dict]: A list of deserialized note dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT content, position_x, position_y, width, height,
                       color, header_color, is_system_prompt, is_summary_note
                FROM notes WHERE chat_id = ?
            """, (chat_id,))
            
            notes = []
            for row in cursor.fetchall():
                notes.append({
                    'content': row[0],
                    'position': {'x': row[1], 'y': row[2]},
                    'size': {'width': row[3], 'height': row[4]},
                    'color': row[5],
                    'header_color': row[6],
                    'is_system_prompt': bool(row[7]),
                    'is_summary_note': bool(row[8])
                })
            return notes
            
    def save_chat(self, title, chat_data):
        """
        Saves a new chat session to the database.

        Args:
            title (str): The title of the chat.
            chat_data (dict): The serialized JSON data for the chat scene.

        Returns:
            int: The ID of the newly created chat record.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO chats (title, data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (title, json.dumps(chat_data)))
            return cursor.lastrowid
            
    def get_latest_chat_id(self):
        """
        Gets the ID of the most recently created chat.

        Returns:
            int or None: The ID of the latest chat, or None if no chats exist.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id FROM chats 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            result = cursor.fetchone()
            return result[0] if result else None
            
    def update_chat(self, chat_id, title, chat_data):
        """
        Updates an existing chat session in the database.

        Args:
            chat_id (int): The ID of the chat to update.
            title (str): The current title of the chat.
            chat_data (dict): The complete serialized JSON data for the chat scene.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE chats 
                SET title = ?, data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (title, json.dumps(chat_data), chat_id))
            
    def load_chat(self, chat_id):
        """
        Loads a specific chat session from the database.

        Args:
            chat_id (int): The ID of the chat to load.

        Returns:
            dict or None: A dictionary containing the chat 'title' and 'data', or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                SELECT title, data FROM chats WHERE id = ?
            """, (chat_id,)).fetchone()
            if result:
                return {
                    'title': result[0],
                    'data': json.loads(result[1])
                }
            return None
            
    def get_all_chats(self):
        """
        Retrieves a list of all saved chats, ordered by most recently updated.

        Returns:
            list[tuple]: A list of tuples, each containing (id, title, created_at, updated_at).
        """
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("""
                SELECT id, title, created_at, updated_at 
                FROM chats 
                ORDER BY updated_at DESC
            """).fetchall()
            
    def delete_chat(self, chat_id):
        """
        Deletes a chat session from the database. Cascade delete handles associated notes/pins.

        Args:
            chat_id (int): The ID of the chat to delete.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            
    def rename_chat(self, chat_id, new_title):
        """
        Renames a chat session.

        Args:
            chat_id (int): The ID of the chat to rename.
            new_title (str): The new title for the chat.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE chats 
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_title, chat_id))

class SaveWorkerThread(QThread):
    finished = Signal(int) # Emits new chat ID on success
    error = Signal(str)

    def __init__(self, db, title_generator, chat_data, current_chat_id, first_message):
        super().__init__()
        self.db = db
        self.title_generator = title_generator
        self.chat_data = chat_data
        self.current_chat_id = current_chat_id
        self.first_message = first_message

    def run(self):
        try:
            new_chat_id = self.current_chat_id
            if not self.current_chat_id:
                title = self.title_generator.generate_title(self.first_message)
                new_chat_id = self.db.save_chat(title, self.chat_data)
            else:
                chat = self.db.load_chat(self.current_chat_id)
                if chat:
                    title = chat['title']
                    self.db.update_chat(self.current_chat_id, title, self.chat_data)
                else:
                    title = self.title_generator.generate_title(self.first_message)
                    new_chat_id = self.db.save_chat(title, self.chat_data)
            
            if new_chat_id:
                self.db.save_notes(new_chat_id, self.chat_data.get('notes_data', []))
                self.db.save_pins(new_chat_id, self.chat_data.get('pins_data', []))
            
            self.finished.emit(new_chat_id)
        except Exception as e:
            self.error.emit(f"Background save failed: {str(e)}")


class ChatSessionManager:
    """
    Orchestrates the saving and loading of chat sessions. It acts as the bridge
    between the live QGraphicsScene (UI state) and the ChatDatabase (persistent storage),
    handling the complex logic of serialization and deserialization.
    """
    def __init__(self, window):
        """
        Initializes the ChatSessionManager.

        Args:
            window (QMainWindow): A reference to the main application window.
        """
        self.window = window
        self.db = ChatDatabase()
        self.title_generator = TitleGenerator()
        self.current_chat_id = None
        self.save_thread = None
        self._is_saving = False
        
    def serialize_pin(self, pin):
        """
        Converts a NavigationPin object into a serializable dictionary.

        Args:
            pin (NavigationPin): The pin object to serialize.

        Returns:
            dict: A dictionary representing the pin's data.
        """
        return {
            'title': pin.title,
            'note': pin.note,
            'position': {'x': pin.pos().x(), 'y': pin.pos().y()}
        }
        
    def serialize_pin_layout(self, pin):
        """
        Converts a connection's Pin object into a serializable dictionary for layout.

        Args:
            pin (Pin): The connection pin object to serialize.

        Returns:
            dict: A dictionary representing the pin's position.
        """
        return {
            'position': {'x': pin.pos().x(), 'y': pin.pos().y()}
        }
        
    def serialize_connection(self, connection, all_nodes_list):
        """
        Converts a ConnectionItem into a serializable dictionary using node indices.

        Args:
            connection (ConnectionItem): The connection object.
            all_nodes_list (list): A list of all node objects in the scene, used for indexing.

        Returns:
            dict: A dictionary representing the connection.
        """
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }
    
    def serialize_content_connection(self, connection, all_nodes_list):
        """Serializes a ContentConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_document_connection(self, connection, all_nodes_list):
        """Serializes a DocumentConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_image_connection(self, connection, all_nodes_list):
        """Serializes an ImageConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_thinking_connection(self, connection, all_nodes_list):
        """Serializes a ThinkingConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_system_prompt_connection(self, connection, notes_list, nodes_list):
        """Serializes a SystemPromptConnectionItem using note and node indices."""
        return {
            'start_note_index': notes_list.index(connection.start_node),
            'end_node_index': nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }
    
    def serialize_pycoder_connection(self, connection, all_nodes_list):
        """Serializes a PyCoderConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }
    
    def serialize_web_connection(self, connection, all_nodes_list):
        """Serializes a WebConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_conversation_connection(self, connection, all_nodes_list):
        """Serializes a ConversationConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }
        
    def serialize_reasoning_connection(self, connection, all_nodes_list):
        """Serializes a ReasoningConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_html_connection(self, connection, all_nodes_list):
        """Serializes an HtmlConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_group_summary_connection(self, connection, nodes_list, notes_list):
        """Serializes a GroupSummaryConnectionItem using node and note indices."""
        return {
            'start_node_index': nodes_list.index(connection.start_node),
            'end_note_index': notes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_orchestrator_connection(self, connection, all_nodes_list):
        """Serializes an OrchestratorConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_memory_bank_connection(self, connection, all_nodes_list):
        """Serializes a MemoryBankConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }

    def serialize_synthesis_connection(self, connection, all_nodes_list):
        """Serializes a SynthesisConnectionItem using node indices."""
        return {
            'start_node_index': all_nodes_list.index(connection.start_node),
            'end_node_index': all_nodes_list.index(connection.end_node),
            'pins': [self.serialize_pin_layout(pin) for pin in connection.pins]
        }
        
    def serialize_node(self, node):
        """
        Converts a generic node object (ChatNode, CodeNode, etc.) into a serializable dictionary.
        This method uses `isinstance` to determine the node type and serialize its specific properties.

        Args:
            node (QGraphicsItem): The node object to serialize.

        Returns:
            dict or None: A dictionary representing the node, or None if the type is unknown.
        """
        scene = self.window.chat_view.scene()
        # Create a combined list of all node types to establish a consistent index
        # REORDERED to ensure parents (like Orchestrator) appear before their children (like Tools)
        all_nodes_list = (
            scene.nodes + 
            scene.code_nodes + 
            scene.document_nodes +
            scene.image_nodes + 
            scene.thinking_nodes + 
            scene.orchestrator_nodes +  # Orchestrator before tools
            scene.pycoder_nodes + 
            scene.web_nodes +
            scene.memory_bank_nodes + 
            scene.synthesis_nodes +
            scene.conversation_nodes + 
            scene.reasoning_nodes + 
            scene.html_view_nodes # HTML after Code
        )

        if isinstance(node, ChatNode):
            # Process conversation history to encode any potential image data
            serializable_history = []
            for msg in node.conversation_history:
                new_msg = msg.copy()
                new_msg['content'] = _process_content_for_serialization(msg['content'])
                serializable_history.append(new_msg)
            return {
                'node_type': 'chat',
                'raw_content': _process_content_for_serialization(node.raw_content),
                'is_user': node.is_user,
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'conversation_history': serializable_history,
                'children_indices': [all_nodes_list.index(child) for child in node.children],
                'scroll_value': node.scroll_value,
                'is_collapsed': node.is_collapsed
            }
        elif isinstance(node, CodeNode):
            return {
                'node_type': 'code',
                'code': node.code,
                'language': node.language,
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'parent_content_node_index': all_nodes_list.index(node.parent_content_node)
            }
        elif isinstance(node, DocumentNode):
            return {
                'node_type': 'document',
                'title': node.title,
                'content': node.content,
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'parent_content_node_index': all_nodes_list.index(node.parent_content_node)
            }
        elif isinstance(node, ImageNode):
            return {
                'node_type': 'image',
                'image_bytes': base64.b64encode(node.image_bytes).decode('utf-8'),
                'prompt': node.prompt,
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'parent_content_node_index': all_nodes_list.index(node.parent_content_node)
            }
        elif isinstance(node, ThinkingNode):
            return {
                'node_type': 'thinking',
                'thinking_text': node.thinking_text,
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'parent_content_node_index': all_nodes_list.index(node.parent_content_node),
                'is_docked': node.is_docked
            }
        elif isinstance(node, PyCoderNode):
            return {
                'node_type': 'pycoder',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'mode': node.mode.name,
                'prompt': node.get_prompt(),
                'code': node.get_code(),
                'output': node.output_display.toPlainText(),
                'analysis': node.ai_analysis_display.toPlainText(),
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        elif isinstance(node, WebNode):
            return {
                'node_type': 'web',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'query': node.query,
                'status': node.status,
                'summary': node.summary,
                'sources': node.sources,
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        elif isinstance(node, ConversationNode):
            return {
                'node_type': 'conversation',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'conversation_history': node.conversation_history,
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        elif isinstance(node, ReasoningNode):
            return {
                'node_type': 'reasoning',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'prompt': node.prompt,
                'thinking_budget': node.thinking_budget,
                'thought_process': node.thought_process,
                'status': node.status,
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        elif isinstance(node, HtmlViewNode):
            return {
                'node_type': 'html',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'html_content': node.html_input.toHtml(),
                'splitter_state': node.get_splitter_state(),
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        elif isinstance(node, OrchestratorNode):
            return {
                'node_type': 'orchestrator',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'goal': node.goal,
                'plan': node.plan,
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        elif isinstance(node, MemoryBankNode):
            return {
                'node_type': 'memory_bank',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'memory': node._memory,
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        elif isinstance(node, SynthesisNode):
            return {
                'node_type': 'synthesis',
                'position': {'x': node.pos().x(), 'y': node.pos().y()},
                'instruction': node.instruction_input.toPlainText(),
                'output': node.output_display.toPlainText(),
                'parent_node_index': all_nodes_list.index(node.parent_node),
                'children_indices': [all_nodes_list.index(child) for child in node.children]
            }
        return None

    def serialize_frame(self, frame):
        """
        Converts a Frame object into a serializable dictionary.

        Args:
            frame (Frame): The frame object to serialize.

        Returns:
            dict: A dictionary representing the frame.
        """
        scene = self.window.chat_view.scene()
        # REORDERED to ensure consistent indexing with other serialization methods
        all_nodes_list = (
            scene.nodes + 
            scene.code_nodes + 
            scene.document_nodes +
            scene.image_nodes + 
            scene.thinking_nodes + 
            scene.orchestrator_nodes +  # Orchestrator before tools
            scene.pycoder_nodes + 
            scene.web_nodes +
            scene.memory_bank_nodes + 
            scene.synthesis_nodes +
            scene.conversation_nodes + 
            scene.reasoning_nodes + 
            scene.html_view_nodes # HTML after Code
        )
        return {
            'nodes': [all_nodes_list.index(node) for node in frame.nodes],
            'position': {'x': frame.pos().x(), 'y': frame.pos().y()},
            'note': frame.note,
            'size': {
                'width': frame.rect.width(),
                'height': frame.rect.height()
            },
            'color': frame.color,
            'header_color': frame.header_color
        }

    def serialize_container(self, container, all_items_map):
        """
        Converts a Container object into a serializable dictionary.

        Args:
            container (Container): The container to serialize.
            all_items_map (dict): A map from scene item objects to their indices.

        Returns:
            dict: A dictionary representing the container.
        """
        return {
            'items': [all_items_map[item] for item in container.contained_items],
            'position': {'x': container.pos().x(), 'y': container.pos().y()},
            'title': container.title,
            'is_collapsed': container.is_collapsed,
            'color': container.color,
            'header_color': container.header_color,
            'expanded_rect': {
                'x': container.expanded_rect.x(),
                'y': container.expanded_rect.y(),
                'width': container.expanded_rect.width(),
                'height': container.expanded_rect.height()
            }
        }
        
    def serialize_note(self, note):
        """
        Converts a Note object into a serializable dictionary.

        Args:
            note (Note): The note object to serialize.

        Returns:
            dict: A dictionary representing the note.
        """
        return {
            'content': note.content,
            'position': {'x': note.pos().x(), 'y': note.pos().y()},
            'size': {'width': note.width, 'height': note.height},
            'color': note.color,
            'header_color': note.header_color,
            'is_system_prompt': getattr(note, 'is_system_prompt', False),
            'is_summary_note': getattr(note, 'is_summary_note', False)
        }
        
    def serialize_chart(self, chart):
        """
        Converts a ChartItem into a serializable dictionary.

        Args:
            chart (ChartItem): The chart object to serialize.

        Returns:
            dict: A dictionary representing the chart.
        """
        return {
            'data': chart.data,
            'position': {'x': chart.pos().x(), 'y': chart.pos().y()},
            'size': {'width': chart.width, 'height': chart.height}
        }

    def _get_serialized_chat_data(self):
        scene = self.window.chat_view.scene()
    
        # Gather all item types that will be serialized.
        notes = [item for item in scene.items() if isinstance(item, Note)]
        pins = [item for item in scene.items() if isinstance(item, NavigationPin)]
        charts = [item for item in scene.items() if isinstance(item, ChartItem)]
    
        # Create a comprehensive list of all nodes for consistent indexing.
        # REORDERED to ensure parents (like Orchestrator) appear before their children (like Tools)
        all_nodes_list = (
            scene.nodes + 
            scene.code_nodes + 
            scene.document_nodes +
            scene.image_nodes + 
            scene.thinking_nodes + 
            scene.orchestrator_nodes +  # Orchestrator before tools
            scene.pycoder_nodes + 
            scene.web_nodes +
            scene.memory_bank_nodes + 
            scene.synthesis_nodes +
            scene.conversation_nodes + 
            scene.reasoning_nodes + 
            scene.html_view_nodes # HTML after Code
        )
        
        # Create a map from item object to its index, needed for container serialization.
        all_serializable_items = all_nodes_list + notes + charts + scene.frames + scene.containers
        all_items_map = {item: i for i, item in enumerate(all_serializable_items)}

        # Build the main data dictionary by serializing each category of item.
        chat_data = {
            'nodes': [self.serialize_node(node) for node in all_nodes_list],
            'connections': [self.serialize_connection(conn, all_nodes_list) for conn in scene.connections],
            'content_connections': [self.serialize_content_connection(conn, all_nodes_list) for conn in scene.content_connections],
            'document_connections': [self.serialize_document_connection(conn, all_nodes_list) for conn in scene.document_connections],
            'image_connections': [self.serialize_image_connection(conn, all_nodes_list) for conn in scene.image_connections],
            'thinking_connections': [self.serialize_thinking_connection(conn, all_nodes_list) for conn in scene.thinking_connections],
            'system_prompt_connections': [self.serialize_system_prompt_connection(conn, notes, scene.nodes) for conn in scene.system_prompt_connections],
            'pycoder_connections': [self.serialize_pycoder_connection(conn, all_nodes_list) for conn in scene.pycoder_connections],
            'web_connections': [self.serialize_web_connection(conn, all_nodes_list) for conn in scene.web_connections],
            'conversation_connections': [self.serialize_conversation_connection(conn, all_nodes_list) for conn in scene.conversation_connections],
            'reasoning_connections': [self.serialize_reasoning_connection(conn, all_nodes_list) for conn in scene.reasoning_connections],
            'group_summary_connections': [self.serialize_group_summary_connection(conn, scene.nodes, notes) for conn in scene.group_summary_connections],
            'html_connections': [self.serialize_html_connection(conn, all_nodes_list) for conn in scene.html_connections],
            'orchestrator_connections': [self.serialize_orchestrator_connection(conn, all_nodes_list) for conn in scene.orchestrator_connections],
            'memory_bank_connections': [self.serialize_memory_bank_connection(conn, all_nodes_list) for conn in scene.memory_bank_connections],
            'synthesis_connections': [self.serialize_synthesis_connection(conn, all_nodes_list) for conn in scene.synthesis_connections],
            'frames': [self.serialize_frame(frame) for frame in scene.frames],
            'containers': [self.serialize_container(c, all_items_map) for c in scene.containers],
            'charts': [self.serialize_chart(chart) for chart in charts],
            'view_state': {
                'zoom_factor': self.window.chat_view._zoom_factor,
                'scroll_position': {
                    'x': self.window.chat_view.horizontalScrollBar().value(),
                    'y': self.window.chat_view.verticalScrollBar().value()
                }
            },
            'notes_data': [self.serialize_note(note) for note in notes],
            'pins_data': [self.serialize_pin(pin) for pin in pins]
        }
        return chat_data

    def deserialize_chart(self, data, scene):
        """
        Recreates a ChartItem object from its serialized dictionary representation.

        Args:
            data (dict): The serialized chart data.
            scene (ChatScene): The scene to add the chart to.

        Returns:
            ChartItem: The newly created chart item.
        """
        chart = scene.add_chart(data['data'], QPointF(
            data['position']['x'],
            data['position']['y']
        ))
        
        if 'size' in data:
            chart.width = data['size']['width']
            chart.height = data['size']['height']
            chart.generate_chart()
            
        return chart
        
    def deserialize_pin(self, data, connection):
        """
        Recreates a connection Pin from its serialized data using direct restoration
        to preserve order and position.

        Args:
            data (dict): The serialized pin data.
            connection (ConnectionItem): The parent connection item.

        Returns:
            Pin: The newly created pin object.
        """
        # Use the direct restoration method to avoid smart insertion logic
        local_pos = QPointF(data['position']['x'], data['position']['y'])
        return connection.restore_pin(local_pos)
        
    def deserialize_connection(self, data, scene, all_nodes_map):
        """
        Recreates a ConnectionItem from its serialized dictionary.

        Args:
            data (dict): The serialized connection data.
            scene (ChatScene): The scene to add the connection to.
            all_nodes_map (dict): A map from node index to the live node object.

        Returns:
            ConnectionItem: The newly created connection.
        """
        start_node = all_nodes_map[data['start_node_index']]
        end_node = all_nodes_map[data['end_node_index']]
        
        connection = ConnectionItem(start_node, end_node)
        
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        
        scene.addItem(connection)
        scene.connections.append(connection)
        
        # Recreate any pins on the connection
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
            
        return connection
        
    def deserialize_content_connection(self, data, scene, all_nodes_map):
        """Deserializes a ContentConnectionItem."""
        start_node = all_nodes_map[data['start_node_index']]
        end_node = all_nodes_map[data['end_node_index']]
        connection = ContentConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.content_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_document_connection(self, data, scene, all_nodes_map):
        """Deserializes a DocumentConnectionItem."""
        start_node = all_nodes_map[data['start_node_index']]
        end_node = all_nodes_map[data['end_node_index']]
        connection = DocumentConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.document_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_image_connection(self, data, scene, all_nodes_map):
        """Deserializes an ImageConnectionItem."""
        start_node = all_nodes_map[data['start_node_index']]
        end_node = all_nodes_map[data['end_node_index']]
        connection = ImageConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.image_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_thinking_connection(self, data, scene, all_nodes_map):
        """Deserializes a ThinkingConnectionItem."""
        start_node = all_nodes_map[data['start_node_index']]
        end_node = all_nodes_map[data['end_node_index']]
        connection = ThinkingConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.thinking_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_system_prompt_connection(self, data, scene, notes_map, nodes_map):
        """Deserializes a SystemPromptConnectionItem."""
        start_note = notes_map.get(data['start_note_index'])
        end_node = nodes_map.get(data['end_node_index'])
        
        if not start_note or not end_node:
            print(f"Warning: Skipping orphaned system prompt connection during load.")
            return None

        connection = SystemPromptConnectionItem(start_note, end_node)
        scene.addItem(connection)
        scene.system_prompt_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_pycoder_connection(self, data, scene, all_nodes_map):
        """Deserializes a PyCoderConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = PyCoderConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.pycoder_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_web_connection(self, data, scene, all_nodes_map):
        """Deserializes a WebConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = WebConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.web_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_conversation_connection(self, data, scene, all_nodes_map):
        """Deserializes a ConversationConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = ConversationConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.conversation_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_reasoning_connection(self, data, scene, all_nodes_map):
        """Deserializes a ReasoningConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = ReasoningConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.reasoning_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_html_connection(self, data, scene, all_nodes_map):
        """Deserializes an HtmlConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = HtmlConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.html_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_group_summary_connection(self, data, scene, nodes_map, notes_map):
        """Deserializes a GroupSummaryConnectionItem."""
        start_node = nodes_map.get(data['start_node_index'])
        end_note = notes_map.get(data['end_note_index'])
        
        if not start_node or not end_note:
            print(f"Warning: Skipping orphaned group summary connection.")
            return None

        connection = GroupSummaryConnectionItem(start_node, end_note)
        scene.addItem(connection)
        scene.group_summary_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_orchestrator_connection(self, data, scene, all_nodes_map):
        """Deserializes an OrchestratorConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = OrchestratorConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.orchestrator_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_memory_bank_connection(self, data, scene, all_nodes_map):
        """Deserializes a MemoryBankConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = MemoryBankConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.memory_bank_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_synthesis_connection(self, data, scene, all_nodes_map):
        """Deserializes a SynthesisConnectionItem."""
        start_node = all_nodes_map.get(data['start_node_index'])
        end_node = all_nodes_map.get(data['end_node_index'])
        if not start_node or not end_node:
            return None
        connection = SynthesisConnectionItem(start_node, end_node)
        if hasattr(end_node, 'incoming_connection'):
            end_node.incoming_connection = connection
        scene.addItem(connection)
        scene.synthesis_connections.append(connection)
        for pin_data in data.get('pins', []):
            self.deserialize_pin(pin_data, connection)
        return connection

    def deserialize_node(self, index, data, all_nodes_map):
        """
        Deserializes a generic node from its dictionary representation based on its type.

        Args:
            index (int): The index of the node in the serialized list.
            data (dict): The serialized node data.
            all_nodes_map (dict): The map to populate with the created node object.

        Returns:
            QGraphicsItem or None: The created node object.
        """
        scene = self.window.chat_view.scene()
        node_type = data.get('node_type', 'chat') # Default to 'chat' for backward compatibility

        node = None
        if node_type == 'chat':
            # Decode any base64 image data in the content and history
            raw_content = _process_content_for_deserialization(data.get('raw_content', data.get('text')))
            deserialized_history = []
            for msg in data.get('conversation_history', []):
                new_msg = msg.copy()
                new_msg['content'] = _process_content_for_deserialization(msg['content'])
                deserialized_history.append(new_msg)

            node = scene.add_chat_node(
                raw_content,
                is_user=data.get('is_user', True),
                parent_node=None, # Parent is set in a second pass
                conversation_history=deserialized_history
            )
            node.setPos(data['position']['x'], data['position']['y'])
            # Restore scroll position and collapsed state
            node.scroll_value = data.get('scroll_value', 0)
            node.scrollbar.set_value(node.scroll_value)
            if data.get('is_collapsed', False):
                node.set_collapsed(True)

        elif node_type == 'code':
            parent_node = all_nodes_map.get(data['parent_content_node_index'])
            if parent_node:
                node = scene.add_code_node(
                    data['code'],
                    data['language'],
                    parent_node
                )
                node.setPos(data['position']['x'], data['position']['y'])
        
        elif node_type == 'document':
            parent_node = all_nodes_map.get(data['parent_content_node_index'])
            if parent_node:
                node = scene.add_document_node(
                    data['title'],
                    data['content'],
                    parent_node
                )
                node.setPos(data['position']['x'], data['position']['y'])

        elif node_type == 'image':
            parent_node = all_nodes_map.get(data['parent_content_node_index'])
            if parent_node:
                image_bytes = base64.b64decode(data['image_bytes'])
                node = scene.add_image_node(
                    image_bytes,
                    parent_node,
                    prompt=data.get('prompt', '')
                )
                node.setPos(data['position']['x'], data['position']['y'])
        
        elif node_type == 'thinking':
            parent_node = all_nodes_map.get(data['parent_content_node_index'])
            if parent_node:
                node = scene.add_thinking_node(
                    data['thinking_text'],
                    parent_node
                )
                node.setPos(data['position']['x'], data['position']['y'])
                if data.get('is_docked', False):
                    node.dock()
        
        elif node_type == 'pycoder':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                mode_name = data.get('mode', 'AI_DRIVEN')
                mode = PyCoderMode[mode_name]
                
                node = PyCoderNode(parent_node, mode=mode)
                node.setPos(data['position']['x'], data['position']['y'])
                
                # Restore the state of the PyCoder node's UI
                node.prompt_input.setText(data.get('prompt', ''))
                node.code_input.setText(data.get('code', ''))
                node.set_code(data.get('code', '')) # Syncs both code views
                node.set_output(data.get('output', ''))
                node.set_ai_analysis(data.get('analysis', ''))
                
                scene.addItem(node)
                scene.pycoder_nodes.append(node)
        
        elif node_type == 'web':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                node = WebNode(parent_node)
                node.setPos(data['position']['x'], data['position']['y'])
                
                node.query_input.setText(data.get('query', ''))
                node.set_status(data.get('status', 'Idle'))
                summary = data.get('summary', '')
                sources = data.get('sources', [])
                if summary:
                    node.set_result(summary, sources)
                
                node.run_button_clicked.connect(self.window.execute_web_node)
                
                scene.addItem(node)
                scene.web_nodes.append(node)
        
        elif node_type == 'conversation':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                node = ConversationNode(parent_node)
                node.setPos(data['position']['x'], data['position']['y'])
                node.set_history(data.get('conversation_history', []))
                
                node.ai_request_sent.connect(self.window.handle_conversation_node_request)
                
                scene.addItem(node)
                scene.conversation_nodes.append(node)
        
        elif node_type == 'reasoning':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                node = ReasoningNode(parent_node)
                node.setPos(data['position']['x'], data['position']['y'])
                
                node.prompt_input.setText(data.get('prompt', ''))
                node.budget_slider.setValue(data.get('thinking_budget', 3))
                node.thought_process_display.setMarkdown(data.get('thought_process', ''))
                node.set_status(data.get('status', 'Idle'))
                
                node.reasoning_requested.connect(self.window.execute_reasoning_node)
                
                scene.addItem(node)
                scene.reasoning_nodes.append(node)
        
        elif node_type == 'html':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                node = HtmlViewNode(parent_node)
                node.setPos(data['position']['x'], data['position']['y'])
                node.set_html_content(data.get('html_content', ''))
                node.set_splitter_state(data.get('splitter_state'))
                
                scene.addItem(node)
                scene.html_view_nodes.append(node)
        
        elif node_type == 'orchestrator':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                node = OrchestratorNode(parent_node)
                node.setPos(data['position']['x'], data['position']['y'])
                node.goal_input.setText(data.get('goal', ''))
                node.set_plan(data.get('plan', ''))
                node.orchestration_requested.connect(self.window.execute_orchestrator_node)
                scene.addItem(node)
                scene.orchestrator_nodes.append(node)

        elif node_type == 'memory_bank':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                node = MemoryBankNode(parent_node)
                node.setPos(data['position']['x'], data['position']['y'])
                node._memory = data.get('memory', {})
                node._update_display()
                scene.addItem(node)
                scene.memory_bank_nodes.append(node)

        elif node_type == 'synthesis':
            parent_node = all_nodes_map.get(data['parent_node_index'])
            if parent_node:
                node = SynthesisNode(parent_node)
                node.setPos(data['position']['x'], data['position']['y'])
                node.instruction_input.setText(data.get('instruction', ''))
                node.set_output(data.get('output', ''))
                scene.addItem(node)
                scene.synthesis_nodes.append(node)

        if node:
            all_nodes_map[index] = node
        return node
        
    def deserialize_frame(self, data, scene, all_nodes_map):
        """Recreates a Frame from its serialized data."""
        nodes_indices = [i for i in data['nodes'] if i in all_nodes_map]
        nodes = [all_nodes_map[i] for i in nodes_indices]
        
        frame = Frame(nodes)
        frame.setPos(data['position']['x'], data['position']['y'])
        frame.note = data['note']
        
        if 'color' in data:
            frame.color = data['color']
        if 'header_color' in data:
            frame.header_color = data['header_color']
            
        if 'size' in data:
            frame.rect.setWidth(data['size']['width'])
            frame.rect.setHeight(data['size']['height'])
            
        scene.addItem(frame)
        scene.frames.append(frame)
        frame.setZValue(-2) # Ensure frames are drawn behind nodes
        return frame

    def deserialize_container(self, data, scene, all_items_map):
        """Recreates a Container from its serialized data."""
        items_indices = [i for i in data['items'] if i in all_items_map]
        items = [all_items_map[i] for i in items_indices]
        container = Container(items)
        container.setPos(data['position']['x'], data['position']['y'])
        container.title = data.get('title', "Container")
        container.color = data.get('color', "#3a3a3a")
        container.header_color = data.get('header_color')
        
        rect_data = data.get('expanded_rect')
        if rect_data:
            container.expanded_rect = QRectF(rect_data['x'], rect_data['y'], rect_data['width'], rect_data['height'])

        if data.get('is_collapsed', False):
            container.toggle_collapse() # This will set it to collapsed and update geometry

        scene.addItem(container)
        scene.containers.append(container)
        container.setZValue(-3) # Ensure containers are behind frames
        return container

    def load_chat(self, chat_id):
        """
        Loads a complete chat session from the database and reconstructs the scene.
        This is the main entry point for loading a session.

        Args:
            chat_id (int): The ID of the chat to load.

        Returns:
            dict or None: The raw chat data dictionary, or None on failure.
        """
        chat = self.db.load_chat(chat_id)
        if not chat:
            return

        scene = self.window.chat_view.scene()
        scene.clear()
        self.window.current_node = None

        try:
            all_nodes_map = {}
            notes_map = {}
            
            # First pass: Create all node objects without setting relationships.
            # This ensures all potential parents/children/connection points exist before
            # we try to link them.
            for i, node_data in enumerate(chat['data']['nodes']):
                self.deserialize_node(i, node_data, all_nodes_map)

            # Second pass: Now that all nodes are created, establish parent-child relationships.
            for i, node_data in enumerate(chat['data']['nodes']):
                node = all_nodes_map.get(i)
                if not node: continue
                
                valid_node_types = (ChatNode, PyCoderNode, WebNode, ConversationNode, ReasoningNode, HtmlViewNode, OrchestratorNode, MemoryBankNode, SynthesisNode)
                if isinstance(node, valid_node_types) and 'children_indices' in node_data:
                    for child_index in node_data['children_indices']:
                        child_node = all_nodes_map.get(child_index)
                        if child_node:
                            node.children.append(child_node)
                            child_node.parent_node = node

            # Deserialize notes and charts, which are standalone or parents to connections.
            notes_data = self.db.load_notes(chat_id)
            for i, note_data in enumerate(notes_data):
                note = scene.add_note(QPointF(note_data['position']['x'], note_data['position']['y']))
                # Set properties that affect geometry calculation BEFORE setting content
                note.width = note_data['size']['width']
                note.color = note_data['color']
                note.header_color = note_data['header_color']
                note.is_system_prompt = note_data.get('is_system_prompt', False)
                note.is_summary_note = note_data.get('is_summary_note', False)
                # Set content last to trigger automatic height recalculation
                note.content = note_data['content']
                notes_map[i] = note

            charts_map = {}
            if 'charts' in chat['data']:
                for i, chart_data in enumerate(chat['data']['charts']):
                    charts_map[i] = self.deserialize_chart(chart_data, scene)

            # Create maps for all items for container and connection deserialization
            all_deserialized_nodes = list(all_nodes_map.values())
            all_deserialized_notes = list(notes_map.values())
            all_deserialized_charts = list(charts_map.values())

            # Deserialize frames and containers, which may contain other items.
            frames_map = {}
            if 'frames' in chat['data']:
                for i, frame_data in enumerate(chat['data']['frames']):
                    frames_map[i] = self.deserialize_frame(frame_data, scene, all_nodes_map)

            all_deserialized_frames = list(frames_map.values())
            
            # Create a comprehensive map of ALL items to their original indices for containers
            all_items_list = all_deserialized_nodes + all_deserialized_notes + all_deserialized_charts + all_deserialized_frames
            all_items_map = {i: item for i, item in enumerate(all_items_list)}

            if 'containers' in chat['data']:
                for container_data in chat['data']['containers']:
                    self.deserialize_container(container_data, scene, all_items_map)

            # Final pass: Recreate all connections now that all potential endpoints exist.
            chat_nodes_map = {i: node for i, node in enumerate(scene.nodes)}

            for conn_data in chat['data'].get('connections', []):
                self.deserialize_connection(conn_data, scene, all_nodes_map)
            
            for conn_data in chat['data'].get('content_connections', []):
                self.deserialize_content_connection(conn_data, scene, all_nodes_map)

            for conn_data in chat['data'].get('document_connections', []):
                self.deserialize_document_connection(conn_data, scene, all_nodes_map)

            for conn_data in chat['data'].get('image_connections', []):
                self.deserialize_image_connection(conn_data, scene, all_nodes_map)
            
            if 'thinking_connections' in chat['data']:
                for conn_data in chat['data']['thinking_connections']:
                    self.deserialize_thinking_connection(conn_data, scene, all_nodes_map)
            
            for conn_data in chat['data'].get('pycoder_connections', []):
                self.deserialize_pycoder_connection(conn_data, scene, all_nodes_map)
            
            if 'web_connections' in chat['data']:
                 for conn_data in chat['data']['web_connections']:
                    self.deserialize_web_connection(conn_data, scene, all_nodes_map)

            if 'conversation_connections' in chat['data']:
                for conn_data in chat['data']['conversation_connections']:
                    self.deserialize_conversation_connection(conn_data, scene, all_nodes_map)
            
            if 'reasoning_connections' in chat['data']:
                for conn_data in chat['data']['reasoning_connections']:
                    self.deserialize_reasoning_connection(conn_data, scene, all_nodes_map)
            
            if 'html_connections' in chat['data']:
                for conn_data in chat['data']['html_connections']:
                    self.deserialize_html_connection(conn_data, scene, all_nodes_map)
            
            if 'orchestrator_connections' in chat['data']:
                for conn_data in chat['data']['orchestrator_connections']:
                    self.deserialize_orchestrator_connection(conn_data, scene, all_nodes_map)

            if 'memory_bank_connections' in chat['data']:
                for conn_data in chat['data']['memory_bank_connections']:
                    self.deserialize_memory_bank_connection(conn_data, scene, all_nodes_map)

            if 'synthesis_connections' in chat['data']:
                for conn_data in chat['data']['synthesis_connections']:
                    self.deserialize_synthesis_connection(conn_data, scene, all_nodes_map)

            if 'system_prompt_connections' in chat['data']:
                for conn_data in chat['data']['system_prompt_connections']:
                    self.deserialize_system_prompt_connection(conn_data, scene, notes_map, chat_nodes_map)
            
            if 'group_summary_connections' in chat['data']:
                for conn_data in chat['data']['group_summary_connections']:
                    self.deserialize_group_summary_connection(conn_data, scene, chat_nodes_map, notes_map)

            # Restore navigation pins
            if self.window and hasattr(self.window, 'pin_overlay'):
                self.window.pin_overlay.clear_pins()
        
            pins_data = self.db.load_pins(chat_id)
            for pin_data in pins_data:
                pin = scene.add_navigation_pin(QPointF(pin_data['position']['x'], pin_data['position']['y']))
                pin.title, pin.note = pin_data['title'], pin_data.get('note', '')
                if self.window and hasattr(self.window, 'pin_overlay'):
                    self.window.pin_overlay.add_pin_button(pin)

            # Restore view state (zoom and scroll position)
            if 'view_state' in chat['data']:
                view_state = chat['data']['view_state']
                self.window.chat_view._zoom_factor = view_state['zoom_factor']
                self.window.chat_view.setTransform(QTransform().scale(view_state['zoom_factor'], view_state['zoom_factor']))
                self.window.chat_view.horizontalScrollBar().setValue(view_state['scroll_position']['x'])
                self.window.chat_view.verticalScrollBar().setValue(view_state['scroll_position']['y'])
    
            self.current_chat_id = chat_id
            scene.update_connections() # Final update to ensure all paths are correct           
            

        except Exception as e:
            # Handle errors during loading, which can happen with corrupted or old save files
            from PySide6.QtWidgets import QMessageBox
            print(f"Error loading chat: {str(e)}")
            QMessageBox.critical(self.window, "Load Error", f"Failed to load the chat session. The file may be from an incompatible version.\n\nError: {e}")
            self.window.new_chat() # Reset to a clean state
            
        return chat
        
    def save_current_chat(self):
        """
        Saves the current chat session. This is a high-level wrapper around the serialization process.
        """
        if self._is_saving:
            return

        scene = self.window.chat_view.scene()
        if not scene.nodes and not scene.conversation_nodes and not scene.reasoning_nodes and not scene.orchestrator_nodes:
            return

        self._is_saving = True
        chat_data = self._get_serialized_chat_data()
        
        first_message = ""
        if not self.current_chat_id:
            last_message_node = next((node for node in reversed(scene.nodes) if node.text), None)
            first_message = last_message_node.text if last_message_node else "New Chat"

        self.save_thread = SaveWorkerThread(self.db, self.title_generator, chat_data, self.current_chat_id, first_message)
        self.save_thread.finished.connect(self._on_save_finished)
        self.save_thread.error.connect(self._on_save_error)
        self.save_thread.start()

    def _on_save_finished(self, new_chat_id):
        self.current_chat_id = new_chat_id
        self._is_saving = False
        print(f"Background save completed for chat ID: {new_chat_id}")
        if hasattr(self.window, 'update_title_bar'):
            self.window.update_title_bar()

    def _on_save_error(self, error_message):
        self._is_saving = False
        print(f"Error during background save: {error_message}")
        if hasattr(self.window, 'notification_banner'):
            self.window.notification_banner.show_message(f"Error saving chat: {error_message}", 10000)