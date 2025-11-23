"""
This module contains the core "business logic" for the AI agents and the background
worker threads that execute them. Each agent encapsulates a specific skill or task,
often defined by a detailed system prompt. The QThread workers are essential for
running these potentially long-running AI tasks (like API calls or code execution)
without freezing the main application's user interface.
"""

import json
from PySide6.QtCore import QThread, Signal, QPointF, QEventLoop
from PySide6.QtWidgets import QGraphicsObject
import graphite_config as config
import api_provider
import subprocess
import sys  # Added for sys.executable
import io
import contextlib
import re
from enum import Enum
import os
import time
from graphite_pycoder import PyCoderMode, PyCoderStage, PyCoderStatus

try:
    from ddgs import DDGS
    DUCKDUCKGO_SEARCH_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_SEARCH_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False


class ChatWorkerThread(QThread):
    """
    A QThread worker for handling standard chat conversations in the background.

    This thread takes a ChatAgent and the current conversation context, runs the
    agent to get a response, and emits a 'finished' signal with the new message
    or an 'error' signal if something goes wrong.
    """
    finished = Signal(dict) # Emits the new message dictionary on success.
    error = Signal(str)     # Emits an error message string on failure.
    
    def __init__(self, agent, conversation_history, current_node):
        """
        Initializes the ChatWorkerThread.

        Args:
            agent (ChatAgent): The AI agent instance to use for generating the response.
            conversation_history (list): A list of message dictionaries representing the
                                         conversation up to this point.
            current_node (QGraphicsItem): The node from which the new message is branching,
                                          used to determine context like system prompts.
        """
        super().__init__()
        self.agent = agent
        self.conversation_history = conversation_history
        self.current_node = current_node
        
    def run(self):
        """
        The main execution method for the thread. This is called when the thread starts.
        It runs the agent and emits the result.
        """
        try:
            # Call the agent to get the AI's response text.
            response_text = self.agent.get_response(self.conversation_history, self.current_node)
            # Format the response into the standard message dictionary structure.
            new_message = {'role': 'assistant', 'content': response_text}
            self.finished.emit(new_message)
        except Exception as e:
            # If any exception occurs during the agent's execution, emit an error signal.
            self.error.emit(str(e))

class ChatWorker:
    """
    A stateless worker class that encapsulates the logic for a single chat API call.
    It determines the correct system prompt to use based on the conversation context.
    """
    def __init__(self, system_prompt):
        """
        Initializes the ChatWorker.

        Args:
            system_prompt (str): The default system prompt to use if no custom one is found.
        """
        self.system_prompt = system_prompt
        
    def run(self, conversation_history, current_node):
        """
        Executes the chat logic for a single turn.

        Args:
            conversation_history (list): The list of messages in the conversation.
            current_node (QGraphicsItem): The current node context to check for custom prompts.

        Returns:
            str: The AI-generated response text.

        Raises:
            Exception: Propagates exceptions from the API provider.
        """
        final_system_prompt = self.system_prompt

        if current_node:
            # Traverse up the node hierarchy to find the root of the current branch.
            root_node = current_node
            while hasattr(root_node, 'parent_node') and root_node.parent_node:
                root_node = root_node.parent_node
            
            # Check if the root node has a custom system prompt note attached.
            if root_node.scene():
                for conn in root_node.scene().system_prompt_connections:
                    if conn.end_node == root_node:
                        prompt_note = conn.start_node
                        if prompt_note.content:
                            final_system_prompt = prompt_note.content
                        break

        try:
            # Construct the final list of messages to send to the API.
            # The history already includes the latest user message.
            messages = [
                {'role': 'system', 'content': final_system_prompt},
                *conversation_history
            ]
            response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
            ai_message = response['message']['content']
            return ai_message
        except Exception as e:
            print(f"  [LOG-CHATWORKER] API call failed: {e}")
            raise e

class ChatAgent:
    """
    The primary agent for handling general-purpose chat conversations.
    This agent is stateless; it relies on the conversation history passed to it for context.
    """
    def __init__(self, name, persona):
        """
        Initializes the ChatAgent.

        Args:
            name (str): The name of the AI assistant.
            persona (str): The detailed system prompt defining the AI's behavior and knowledge.
        """
        self.name = name or "AI Assistant"
        self.persona = persona or "(default persona)"
        self.system_prompt = f"You are {self.name}. {self.persona}"
        
    def get_response(self, conversation_history, current_node):
        """
        Gets an AI response for a given conversation history.

        Args:
            conversation_history (list): The list of messages in the conversation.
            current_node (QGraphicsItem): The current node context.

        Returns:
            str: The AI-generated response text.
        """
        # This agent is stateless. It does not store conversation_history.
        # It creates a temporary ChatWorker to handle the API call.
        chat_worker = ChatWorker(self.system_prompt)
        ai_response = chat_worker.run(conversation_history, current_node)
        return ai_response

class ExplainerAgent:
    """An agent specialized in simplifying complex topics."""
    def __init__(self):
        """Initializes the ExplainerAgent with a highly structured system prompt."""
        self.system_prompt = """You are an expert at explaining complex topics in simple terms. Follow these principles in order:

1. Simplification: Break down complex ideas into their most basic form
2. Clarification: Remove any technical jargon or complex terminology
3. Distillation: Extract only the most important concepts
4. Breakdown: Present information in small, digestible chunks
5. Simple Language: Use everyday words and short sentences

Always use:
- Analogies: Connect ideas to everyday experiences
- Metaphors: Compare complex concepts to simple, familiar things

Format your response exactly like this:

Simple Explanation
[2-3 sentence overview using everyday language]

Think of it Like This:
[Add one clear analogy or metaphor that a child would understand]

Key Parts:
• [First simple point]
• [Second simple point]
• [Third point if needed]

Remember: Write as if explaining to a curious 5-year-old. No technical terms, no complex words."""
        
    def clean_text(self, text):
        """
        Cleans and formats the raw AI response to ensure it adheres to the
        expected structure for display in a Note item.

        Args:
            text (str): The raw text from the AI model.

        Returns:
            str: The cleaned and formatted text.
        """
        # Remove markdown and special characters that might interfere with display.
        replacements = [
            ('```', ''),
            ('`', ''),
            ('**', ''),
            ('__', ''),
            ('*', ''),
            ('_', ''),
            ('•', '•'),
            ('→', '->'),
            ('\n\n\n', '\n\n'),
        ]
        
        cleaned = text
        for old, new in replacements:
            cleaned = cleaned.replace(old, new)
            
        # Split into lines and clean each line individually.
        lines = cleaned.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                # Standardize bullet points.
                if line.lstrip().startswith('-'):
                    line = '• ' + line.lstrip('- ')
                cleaned_lines.append(line)
        
        # Rebuild the text with consistent spacing and headers.
        formatted = ''
        in_bullet_list = False
        
        for i, line in enumerate(cleaned_lines):
            # Ensure the "Simple Explanation" title is present.
            if i == 0 and "Simple Explanation" not in line:
                formatted += "Simple Explanation\n"
                
            # Add line with proper spacing based on its content type.
            if line.startswith('•'):
                if not in_bullet_list:
                    formatted += '\n' if formatted else ''
                in_bullet_list = True
                formatted += line + '\n'
            elif any(section in line for section in ['Think of it Like This:', 'Key Parts:']):
                formatted += '\n' + line + '\n'
            else:
                in_bullet_list = False
                formatted += line + '\n'
        
        return formatted.strip()

    def get_response(self, text):
        """
        Generates a simplified explanation for the given text.

        Args:
            text (str): The text to explain.

        Returns:
            str: The simplified explanation.
        """
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': f"Explain this in simple terms: {text}"}
        ]
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        raw_response = response['message']['content']
        
        # Clean and format the final response.
        formatted_response = self.clean_text(raw_response)
        return formatted_response
        
class KeyTakeawayAgent:
    """An agent specialized in extracting key takeaways from a block of text."""
    def __init__(self):
        """Initializes the KeyTakeawayAgent with its structured system prompt."""
        self.system_prompt = """You are a key takeaway generator. Format your response exactly like this:

Key Takeaway
[1-2 sentence overview]

Main Points:
• [First key point]
• [Second key point]
• [Third key point if needed]

Keep total output under 150 words. Be direct and focused on practical value.
No markdown formatting, no special characters."""
        
    def clean_text(self, text):
        """
        Cleans and formats the raw AI response to fit the expected structure.

        Args:
            text (str): The raw text from the AI model.

        Returns:
            str: The cleaned and formatted text.
        """
        # A series of replacements to strip unwanted formatting.
        replacements = [
            ('```', ''),  # code blocks
            ('`', ''),    # inline code
            ('**', ''),   # bold
            ('__', ''),   # alternate bold
            ('*', ''),    # italic/bullet
            ('_', ''),    # alternate italic
            ('•', '•'),   # standardize bullets
            ('→', '->'),  # standardize arrows
            ('\n\n\n', '\n\n'),  # remove extra newlines
        ]
        
        cleaned = text
        for old, new in replacements:
            cleaned = cleaned.replace(old, new)
            
        # Process line by line for finer control.
        lines = cleaned.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                # Ensure bullet points are properly formatted.
                if line.lstrip().startswith('-'):
                    line = '• ' + line.lstrip('- ')
                cleaned_lines.append(line)
        
        # Rebuild the text with consistent spacing and headers.
        formatted = ''
        in_bullet_list = False
        
        for i, line in enumerate(cleaned_lines):
            # Ensure the main title is present.
            if i == 0 and "Key Takeaway" not in line:
                formatted += "Key Takeaway\n"
                
            # Add line with proper spacing.
            if line.startswith('•'):
                if not in_bullet_list:
                    formatted += '\n' if formatted else ''
                in_bullet_list = True
                formatted += line + '\n'
            elif 'Main Points:' in line:
                formatted += '\n' + line + '\n'
            else:
                in_bullet_list = False
                formatted += line + '\n'
        
        return formatted.strip()

    def get_response(self, text):
        """
        Generates key takeaways for the given text.

        Args:
            text (str): The text to summarize.

        Returns:
            str: The formatted key takeaways.
        """
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': f"Generate key takeaways from this text: {text}"}
        ]
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        raw_response = response['message']['content']
        
        # Clean and format the final response.
        formatted_response = self.clean_text(raw_response)
        return formatted_response

class GroupSummaryAgent:
    """An agent that synthesizes multiple text snippets into a single cohesive summary."""
    def __init__(self):
        """Initializes the GroupSummaryAgent with its synthesis-focused system prompt."""
        self.system_prompt = """You are a synthesis expert. Your task is to analyze a collection of separate text snippets and generate a single, cohesive summary.

RULES:
1.  **Do Not Summarize Individually:** Your goal is NOT to create a list of summaries for each snippet.
2.  **Find the Connection:** Read all snippets to understand the underlying theme, argument, or narrative that connects them.
3.  **Synthesize:** Weave the key information from all snippets into a single, flowing summary.
4.  **Be Cohesive:** The final output should read like a standalone piece of text that makes sense without seeing the original snippets.
5.  **Format your response exactly like this:**

Synthesized Summary
[A concise paragraph that combines the core ideas from all provided texts.]

Key Connected Points:
• [First synthesized point]
• [Second synthesized point]
• [Third synthesized point if needed]
"""

    def clean_text(self, text):
        """
        Cleans and formats the raw AI response to fit the expected structure.

        Args:
            text (str): The raw text from the AI model.

        Returns:
            str: The cleaned and formatted text.
        """
        replacements = [
            ('```', ''), ('`', ''), ('**', ''), ('__', ''), ('*', ''), ('_', ''),
            ('•', '•'), ('→', '->'), ('\n\n\n', '\n\n'),
        ]
        cleaned = text
        for old, new in replacements:
            cleaned = cleaned.replace(old, new)
        
        lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
        cleaned_lines = []
        for line in lines:
            if line.lstrip().startswith('-'):
                cleaned_lines.append('• ' + line.lstrip('- '))
            else:
                cleaned_lines.append(line)

        formatted = ''
        in_bullet_list = False
        for i, line in enumerate(cleaned_lines):
            if i == 0 and "Synthesized Summary" not in line:
                formatted += "Synthesized Summary\n"
            
            if line.startswith('•'):
                if not in_bullet_list:
                    formatted += '\n'
                in_bullet_list = True
                formatted += line + '\n'
            elif "Key Connected Points:" in line:
                formatted += '\n' + line + '\n'
                in_bullet_list = False
            else:
                in_bullet_list = False
                formatted += line + '\n'
        
        return formatted.strip()

    def get_response(self, texts: list):
        """
        Generates a synthesized summary from a list of text snippets.

        Args:
            texts (list[str]): A list of strings to synthesize.

        Returns:
            str: The synthesized summary.
        """
        # Combine the list of texts into a single string for the prompt,
        # clearly delineating each snippet.
        combined_text = ""
        for i, text in enumerate(texts):
            combined_text += f"--- Snippet {i+1} ---\n{text}\n\n"

        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': f"Synthesize the following text snippets into a single summary:\n\n{combined_text}"}
        ]
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        raw_response = response['message']['content']
        return self.clean_text(raw_response)

class GroupSummaryWorkerThread(QThread):
    """QThread worker for the GroupSummaryAgent."""
    finished = Signal(str, QPointF, list)
    error = Signal(str)

    def __init__(self, agent, texts, node_pos, source_nodes):
        """
        Initializes the worker.

        Args:
            agent (GroupSummaryAgent): The agent instance.
            texts (list[str]): The texts to summarize.
            node_pos (QPointF): The desired position for the resulting summary note.
            source_nodes (list): The original nodes being summarized, to create connections.
        """
        super().__init__()
        self.agent = agent
        self.texts = texts
        self.node_pos = node_pos
        self.source_nodes = source_nodes
        self._is_running = True

    def run(self):
        """Executes the agent's logic and emits the result."""
        try:
            if not self._is_running: return
            response = self.agent.get_response(self.texts)
            if self._is_running:
                self.finished.emit(response, self.node_pos, self.source_nodes)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))
        finally:
            self._is_running = False

    def stop(self):
        """Stops the thread safely."""
        self._is_running = False

class KeyTakeawayWorkerThread(QThread):
    """QThread worker for the KeyTakeawayAgent."""
    finished = Signal(str, QPointF)  # Signal includes response and node position
    error = Signal(str)
    
    def __init__(self, agent, text, node_pos):
        """
        Initializes the worker.

        Args:
            agent (KeyTakeawayAgent): The agent instance.
            text (str): The text to process.
            node_pos (QPointF): The position of the source node.
        """
        super().__init__()
        self.agent = agent
        self.text = text
        self.node_pos = node_pos
        self._is_running = True
        
    def run(self):
        """Executes the agent's logic and emits the result."""
        try:
            if not self._is_running: return
            response = self.agent.get_response(self.text)
            if self._is_running:
                self.finished.emit(response, self.node_pos)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))
        finally:
            self._is_running = False
            
    def stop(self):
        """Stops the thread safely."""
        self._is_running = False
        
class ChartDataAgent:
    """
    An agent that extracts structured data from natural language text to generate JSON
    payloads suitable for creating various types of charts.
    """
    # A dictionary of system prompts, one for each supported chart type.
    # Each prompt strictly defines the required JSON output format.
    CHART_PROMPTS = {
        'bar': """You are a data extraction agent specializing in creating JSON for BAR charts.
Your task is to analyze the user's text and extract data to fit the following JSON structure precisely.

STRUCTURE:
{
    "type": "bar",
    "title": "<A concise title for the chart>",
    "labels": ["<label_for_value_1>", "<label_for_value_2>", ...],
    "values": [<numeric_value_1>, <numeric_value_2>, ...],
    "xAxis": "<Label for the X-axis>",
    "yAxis": "<Label for the Y-axis>"
}

EXAMPLE:
User Text: "The report shows our Q3 sales figures. We sold 150 units of Product A, 220 of Product B, and 95 of Product C. This is an overview of sales per product."
Your Output:
{
    "type": "bar",
    "title": "Q3 Sales Figures",
    "labels": ["Product A", "Product B", "Product C"],
    "values": [150, 220, 95],
    "xAxis": "Product",
    "yAxis": "Units Sold"
}

RULES:
1. ONLY output the raw JSON object. Do not include `json`, markdown backticks, or any explanatory text.
2. The `labels` and `values` arrays must have the same number of elements.
3. If you cannot find appropriate data in the text, return this exact error object: {"error": "Could not find sufficient data to generate a bar chart."}""",

        'line': """You are a data extraction agent specializing in creating JSON for LINE charts.
Your task is to analyze the user's text and extract data to fit the following JSON structure precisely.

STRUCTURE:
{
    "type": "line",
    "title": "<A concise title for the chart>",
    "labels": ["<point_1_label>", "<point_2_label>", ...],
    "values": [<numeric_value_1>, <numeric_value_2>, ...],
    "xAxis": "<Label for the X-axis, often time or sequence>",
    "yAxis": "<Label for the Y-axis>"
}

EXAMPLE:
User Text: "Our website traffic over the last week was: Monday 1200 visitors, Tuesday 1350, Wednesday 1600, Thursday 1550, and Friday 1800. Let's visualize weekly visitor trends."
Your Output:
{
    "type": "line",
    "title": "Weekly Visitor Trends",
    "labels": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "values": [1200, 1350, 1600, 1550, 1800],
    "xAxis": "Day of the Week",
    "yAxis": "Number of Visitors"
}

RULES:
1. ONLY output the raw JSON object. Do not include `json`, markdown backticks, or any explanatory text.
2. The `labels` and `values` arrays must have the same number of elements.
3. If you cannot find appropriate data in the text, return this exact error object: {"error": "Could not find sufficient data to generate a line chart."}""",

        'pie': """You are a data extraction agent specializing in creating JSON for PIE charts.
Your task is to analyze the user's text and extract data representing parts of a whole to fit the following JSON structure precisely.

STRUCTURE:
{
    "type": "pie",
    "title": "<A concise title for the chart>",
    "labels": ["<category_1>", "<category_2>", ...],
    "values": [<numeric_value_1>, <numeric_value_2>, ...]
}

EXAMPLE:
User Text: "Our team's budget allocation is as follows: 50% for salaries, 30% for marketing, 15% for software, and 5% for miscellaneous expenses."
Your Output:
{
    "type": "pie",
    "title": "Team Budget Allocation",
    "labels": ["Salaries", "Marketing", "Software", "Miscellaneous"],
    "values": [50, 30, 15, 5]
}

RULES:
1. ONLY output the raw JSON object. Do not include `json`, markdown backticks, or any explanatory text.
2. The `labels` and `values` arrays must have the same number of elements.
3. If you cannot find appropriate data in the text, return this exact error object: {"error": "Could not find sufficient data for a pie chart."}""",

        'histogram': """You are a data extraction agent specializing in creating JSON for HISTOGRAMS.
Your task is to analyze the user's text and extract a dataset of raw numerical values to fit the following JSON structure precisely.

STRUCTURE:
{
    "type": "histogram",
    "title": "<A concise title for the chart>",
    "values": [<raw_numeric_value_1>, <raw_numeric_value_2>, ...],
    "bins": 10,
    "xAxis": "<Label for the values being measured>",
    "yAxis": "Frequency"
}

EXAMPLE:
User Text: "Here are the scores from the recent exam: 88, 92, 75, 81, 95, 88, 79, 83, 85, 91, 77, 89, 88. Let's see the score distribution."
Your Output:
{
    "type": "histogram",
    "title": "Exam Score Distribution",
    "values": [88, 92, 75, 81, 95, 88, 79, 83, 85, 91, 77, 89, 88],
    "bins": 10,
    "xAxis": "Exam Scores",
    "yAxis": "Frequency"
}

RULES:
1. ONLY output the raw JSON object. Do not include `json`, markdown backticks, or any explanatory text.
2. The `values` key must contain an array of raw numbers, not aggregated data.
3. If you cannot find a dataset of raw numbers, return this exact error object: {"error": "Could not find a valid dataset to generate a histogram."}""",

        'sankey': """You are a data extraction agent specializing in creating JSON for SANKEY diagrams.
Your task is to analyze text describing a flow or distribution between different stages or categories and extract this data to fit the following JSON structure precisely.

STRUCTURE:
{
    "type": "sankey",
    "title": "<A concise title for the flow diagram>",
    "flows": [
        {"source": "<source_category>", "target": "<target_category>", "value": <numeric_value>},
        ...
    ]
}

EXAMPLE:
User Text: "In our energy plant, we start with 1000 units of raw coal. 200 units are lost during transport. Of the remaining 800, 500 units are converted to electricity and 300 are lost as heat. The 500 electricity units are then sent to the grid."
Your Output:
{
    "type": "sankey",
    "title": "Energy Plant Flow",
    "flows": [
        {"source": "Raw Coal", "target": "Transport Loss", "value": 200},
        {"source": "Raw Coal", "target": "Processing", "value": 800},
        {"source": "Processing", "target": "Electricity", "value": 500},
        {"source": "Processing", "target": "Heat Loss", "value": 300},
        {"source": "Electricity", "target": "Grid", "value": 500}
    ]
}

RULES:
1. ONLY output the raw JSON object. Do not include `json`, markdown backticks, or any explanatory text.
2. Each item in the `flows` array must have a `source`, `target`, and `value`.
3. The value field MUST be a number. If the text contains ranges, use an average.
4. **Do NOT return an error.** If you cannot find explicit flows, try to infer them or provide a reasonable estimate based on the context. Create a valid JSON even if data is imperfect."""
    }

    def clean_response(self, text):
        """
        Cleans the raw string response from the LLM to isolate the JSON object.
        Models often wrap JSON in markdown backticks or add explanatory text.

        Args:
            text (str): The raw response string.

        Returns:
            str: The cleaned string, hopefully containing only a valid JSON object.
        """
        # Remove markdown code block fences.
        text = text.replace("```json", "").replace("```", "").strip()
        
        # Find the first opening brace and the last closing brace to extract the JSON.
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                text = text[start:end]
        except:
            pass
            
        return text

    def validate_chart_data(self, data, chart_type):
        """
        Validates the structure and data types of the parsed JSON object.

        Args:
            data (dict): The parsed JSON data from the LLM.
            chart_type (str): The expected type of chart.

        Returns:
            tuple[bool, str or None]: A tuple containing a boolean success flag
                                      and an error message if validation fails.
        """
        try:
            if chart_type == 'sankey':
                if not all(key in data for key in ['type', 'title', 'flows']):
                    return False, f"Missing required fields (type, title, or flows). Found: {list(data.keys())}"
                if not isinstance(data.get('flows'), list):
                    return False, "'flows' must be a list of objects"
                for i, flow in enumerate(data['flows']):
                    if not all(k in flow for k in ['source', 'target', 'value']):
                        return False, f"Flow item at index {i} is missing a source, target, or value."
                    
                    # Improved robustness: try to convert string numbers to float
                    val = flow['value']
                    if isinstance(val, str):
                        try:
                            flow['value'] = float(val)
                        except ValueError:
                             return False, f"Flow value at index {i} must be a number, got '{val}'"
                    elif not isinstance(val, (int, float)):
                        return False, f"Flow value at index {i} must be a number."
                
            elif chart_type == 'histogram':
                required = ['type', 'title', 'values', 'bins', 'xAxis', 'yAxis']
                if not all(key in data for key in required):
                    return False, f"Missing required fields for histogram: {[key for key in required if key not in data]}"
                if not isinstance(data['bins'], (int, float)):
                    return False, "Bins must be a number"
                    
            elif chart_type in ['bar', 'line']:
                required = ['type', 'title', 'labels', 'values', 'xAxis', 'yAxis']
                if not all(key in data for key in required):
                    return False, f"Missing required fields for {chart_type} chart: {[key for key in required if key not in data]}"
                if not isinstance(data.get('labels', []), list):
                    return False, "Labels must be a list"
                if len(data['labels']) != len(data['values']):
                    return False, "Labels and values must have the same length"
                    
            elif chart_type == 'pie':
                required = ['type', 'title', 'labels', 'values']
                if not all(key in data for key in required):
                    return False, f"Missing required fields for pie chart: {[key for key in required if key not in data]}"
                if not isinstance(data.get('labels', []), list):
                    return False, "Labels must be a list"
                if len(data['labels']) != len(data['values']):
                    return False, "Labels and values must have the same length"
            
            # Ensure all 'values' are numeric for non-Sankey charts.
            if chart_type != 'sankey':
                try:
                    if isinstance(data['values'], list):
                        # Robust conversion
                        new_values = []
                        for v in data['values']:
                            if isinstance(v, str):
                                new_values.append(float(v.replace(',', ''))) # Handle commas in strings
                            else:
                                new_values.append(float(v))
                        data['values'] = new_values
                except (ValueError, TypeError):
                    return False, "All values must be numeric"
                    
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def get_response(self, text, chart_type):
        """
        Extracts chart data from a given text for a specific chart type.

        Args:
            text (str): The natural language text containing data.
            chart_type (str): The type of chart to generate (e.g., 'bar', 'line').

        Returns:
            str: A JSON string of the chart data, or a JSON string with an error message.
        """
        if chart_type not in self.CHART_PROMPTS:
            return json.dumps({"error": f"Invalid chart type specified: {chart_type}"})

        system_prompt = self.CHART_PROMPTS[chart_type]

        try:
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Based on my system instructions, analyze the following text and generate the required JSON object for a {chart_type} chart:\n\n--- TEXT TO ANALYZE ---\n{text}"}
            ]
            
            response = api_provider.chat(task=config.TASK_CHART, messages=messages)
            cleaned_response = self.clean_response(response['message']['content'])
            
            try:
                data = json.loads(cleaned_response)
            except json.JSONDecodeError:
                return json.dumps({"error": "Invalid JSON response from model"})
            
            # Check for explicit error object returned by the model
            if 'error' in data:
                return json.dumps(data)

            is_valid, error_message = self.validate_chart_data(data, chart_type)
            if not is_valid:
                return json.dumps({"error": error_message})
            
            return json.dumps(data)
            
        except Exception as e:
            return json.dumps({"error": f"Data extraction failed: {str(e)}"})

class ChartWorkerThread(QThread):
    """QThread worker for the ChartDataAgent."""
    finished = Signal(str, str)
    error = Signal(str)
    
    def __init__(self, text, chart_type):
        super().__init__()
        self.agent = ChartDataAgent()
        self.text = text
        self.chart_type = chart_type
        
    def run(self):
        """Executes the agent and validates the response before emitting."""
        try:
            data = self.agent.get_response(self.text, self.chart_type)
            # Validate that the response is valid JSON and does not contain an error key.
            parsed = json.loads(data)
            if 'error' in parsed:
                raise ValueError(parsed['error'])
            self.finished.emit(data, self.chart_type)
        except Exception as e:
            self.error.emit(str(e))

class ExplainerWorkerThread(QThread):
    """QThread worker for the ExplainerAgent."""
    finished = Signal(str, QPointF)
    error = Signal(str)
    
    def __init__(self, agent, text, node_pos):
        super().__init__()
        self.agent = agent
        self.text = text
        self.node_pos = node_pos
        self._is_running = True
        
    def run(self):
        """Executes the agent's logic and emits the result."""
        try:
            if not self._is_running: return
            response = self.agent.get_response(self.text)
            if self._is_running:
                self.finished.emit(response, self.node_pos)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))
        finally:
            self._is_running = False
            
    def stop(self):
        """Stops the thread safely."""
        self._is_running = False

class ImageGenerationAgent:
    """An agent that generates an image from a text prompt."""
    def __init__(self):
        pass

    def get_response(self, prompt: str):
        """
        Calls the api_provider to generate an image.

        Args:
            prompt (str): The text prompt for the image generation.

        Returns:
            bytes: The raw byte data of the generated image.
        
        Raises:
            Exception: Propagates exceptions from the API provider.
        """
        try:
            image_bytes = api_provider.generate_image(prompt)
            return image_bytes
        except Exception as e:
            # Propagate the exception to be handled by the worker thread
            raise e

class ImageGenerationWorkerThread(QThread):
    """QThread worker for the ImageGenerationAgent."""
    finished = Signal(bytes, str)  # image_bytes, original_prompt
    error = Signal(str)

    def __init__(self, agent, prompt):
        super().__init__()
        self.agent = agent
        self.prompt = prompt
        self._is_running = True

    def run(self):
        """Executes the agent and emits the resulting image bytes."""
        try:
            if not self._is_running:
                return
            image_bytes = self.agent.get_response(self.prompt)
            if self._is_running:
                self.finished.emit(image_bytes, self.prompt)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))
        finally:
            self._is_running = False

    def stop(self):
        """Stops the thread safely."""
        self._is_running = False


class CodeExecutionWorker(QThread):
    """
    A QThread worker that safely executes a block of Python code and captures its output.
    """
    finished = Signal(str, object)
    error = Signal(str, object)

    def __init__(self, code, node):
        super().__init__()
        self.code = code
        self.node = node

    def run(self):
        """
        Executes the provided code using `exec()` and redirects stdout/stderr
        to capture any output or errors.
        """
        output_buffer = io.StringIO()
        try:
            # Redirect stdout and stderr to our in-memory buffer.
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                # Execute the code in a restricted global scope.
                exec(self.code, {})
            
            output = output_buffer.getvalue()
            # If there's no output, provide a placeholder message.
            self.finished.emit(output if output else "[No output produced]", self.node)
        except Exception as e:
            # Also capture exceptions that occur during the `exec` call itself.
            output_buffer.write(f"\n--- EXECUTION FAILED ---\n{type(e).__name__}: {e}")
            self.finished.emit(output_buffer.getvalue(), self.node)
        finally:
            output_buffer.close()


class PyCoderExecutionAgent:
    """
    The initial agent in the AI-driven PyCoder workflow. It decides whether to
    answer a prompt directly or to generate Python code to solve it.
    """
    def __init__(self):
        """Initializes the agent with its system prompt."""
        self.system_prompt = """
You are an expert programmer and a helpful assistant. Your goal is to answer user prompts, using a Python code tool when necessary.
You will be given the previous conversation history for context, followed by the user's final prompt.

1.  First, analyze the user's final prompt in the context of the conversation history.
2.  If the prompt can be answered without computation, provide a direct, helpful answer.
3.  If the prompt requires computation or information from the history, you MUST generate Python code to solve it.
4.  When you generate code, you MUST wrap it in [TOOL:PYTHON] and [/TOOL] tags.
5.  The code should be self-contained and print its result. Do not assume any external libraries unless they are standard.
6.  Do not include any other text or explanation outside the tool tags if you decide to use the tool.

Example (with context):
Conversation History:
[
  {"role": "user", "content": "I have a list of numbers: 15, 8, 22, 5, 19."},
  {"role": "assistant", "content": "Okay, I see that list of numbers."}
]
Final User Prompt: "Please sort them in descending order."
Your response:
[TOOL:PYTHON]
numbers = [15, 8, 22, 5, 19]
numbers.sort(reverse=True)
print(numbers)
[/TOOL]
"""
    def get_response(self, conversation_history, user_prompt):
        """
        Generates the initial response (either direct text or code).

        Args:
            conversation_history (list): The preceding conversation.
            user_prompt (str): The user's final request.

        Returns:
            str: The AI's response, which may contain code wrapped in tool tags.
        """
        history_str = json.dumps(conversation_history, indent=2)
        
        full_prompt = f"""
Conversation History:
{history_str}

Final User Prompt: "{user_prompt}"
"""
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': full_prompt}
        ]
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        return response['message']['content']


class PyCoderRepairAgent:
    """
    An agent that attempts to fix buggy Python code based on an error message.
    """
    def __init__(self):
        """Initializes the agent with its debugging-focused system prompts."""
        self.system_prompt = """You are an expert Python code debugging assistant. You will be given a block of Python code and the error that occurred when it was executed.
Your task is to analyze the error and fix the code.
You MUST return ONLY the complete, corrected, and runnable Python code block.
Do not add explanations, apologies, or any text outside the code.
"""
        # A different prompt for the final retry attempt, encouraging a new approach.
        self.retry_prompt = """The previous attempts to fix the code have failed. The fundamental approach might be wrong.
Re-evaluate the original problem and the previous error. Provide a new, different block of Python code to solve it.
Return ONLY the complete, runnable Python code. Do not include any other text.
"""
    
    def get_response(self, code, error, is_final_attempt=False):
        """
        Generates a corrected version of the provided code.

        Args:
            code (str): The buggy Python code.
            error (str): The error message from the execution of the code.
            is_final_attempt (bool, optional): If True, uses a more aggressive
                                               retry prompt. Defaults to False.

        Returns:
            str: The corrected Python code.
        """
        if is_final_attempt:
            user_message = f"""
Original Problem: Find a new way to solve the task that previously resulted in an error.
Previous Code:
```python
{code}
```
Resulting Error:
```
{error}
```
{self.retry_prompt}
"""
        else:
            user_message = f"""
The following Python code produced an error. Please fix it.

--- Code with Bug ---
```python
{code}
```

--- Error Message ---
```
{error}
```

Return only the corrected code.
"""
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': user_message}
        ]
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        # Clean the response to ensure only the code is returned, stripping markdown fences.
        cleaned_response = response['message']['content']
        code_match = re.search(r'```python\n(.*?)\n```', cleaned_response, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        # Fallback for models that might not use markdown fences correctly.
        return cleaned_response.strip()


class PyCoderAnalysisAgent:
    """
    The final agent in the PyCoder workflow. It analyzes the final code and its
    output to provide a comprehensive, user-friendly explanation.
    """
    def __init__(self):
        """Initializes the agent with its analysis-focused system prompt."""
        self.system_prompt = """
You are a code analysis AI. Your task is to provide a final, user-facing answer based on the available information.

- If an "Original Prompt" is provided, synthesize all information to answer it directly.
- If no "Original Prompt" is provided, simply analyze the given code and its output.
- Explain what the code does and how the output relates to it.
- If the output contains an error, explain the error and suggest a fix.
- Format your response clearly using markdown.
"""

    def get_response(self, original_prompt, code, code_output):
        """
        Generates the final analysis.

        Args:
            original_prompt (str or None): The user's initial prompt to the PyCoder node.
            code (str): The final (successfully executed or last failed) code.
            code_output (str): The output from the code execution.

        Returns:
            str: The formatted analysis text.
        """
        if original_prompt:
            user_message = f"""
Original Prompt: "{original_prompt}"

--- Generated Python Code ---
{code}

--- Code Execution Output ---
{code_output}

Based on all the above, please provide a comprehensive and helpful final answer to my original prompt.
"""
        else: # Case for manual mode where there's no initial prompt.
            user_message = f"""
Please analyze the following Python code and its execution output.

--- Python Code ---
{code}

--- Execution Output ---
{code_output}
"""
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': user_message}
        ]
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        return response['message']['content']


class PyCoderExecutionWorker(QThread):
    """
    Orchestrates the entire AI-driven PyCoder workflow, including code generation,
    execution, and self-repair loops.
    """
    log_update = Signal(object, object) # Stage, Status
    finished = Signal(dict, object)
    error = Signal(str, object)
    retry_feedback = Signal(str) # Signal for user feedback during retries

    def __init__(self, user_prompt, conversation_history, node):
        super().__init__()
        self.user_prompt = user_prompt
        self.conversation_history = conversation_history
        self.node = node
        self.execution_agent = PyCoderExecutionAgent()
        self.repair_agent = PyCoderRepairAgent()
        self.analysis_agent = PyCoderAnalysisAgent()

    def _is_error(self, output):
        """
        A simple heuristic to check if the captured output string contains an error.

        Args:
            output (str): The combined stdout/stderr from code execution.

        Returns:
            bool: True if an error keyword is found, False otherwise.
        """
        error_keywords = ["traceback (most recent call last)", "error:", "exception:", "failed"]
        return any(keyword in output.lower() for keyword in error_keywords)

    def run(self):
        """
        Executes the full PyCoder workflow.
        """
        try:
            retry_count = 0
            max_retries = 4
            current_code = None
            last_error = None

            # 1. Analyze the prompt and decide whether to generate code.
            self.log_update.emit(PyCoderStage.ANALYZE, PyCoderStatus.RUNNING)
            initial_response = self.execution_agent.get_response(self.conversation_history, self.user_prompt)
            self.log_update.emit(PyCoderStage.ANALYZE, PyCoderStatus.SUCCESS)

            # Check if the agent decided to generate code.
            code_match = re.search(r'\[TOOL:PYTHON\](.*?)\[/TOOL\]', initial_response, re.DOTALL)
            if not code_match:
                # No code was generated; the initial response is the final answer.
                self.log_update.emit(PyCoderStage.GENERATE, PyCoderStatus.SUCCESS)
                self.log_update.emit(PyCoderStage.EXECUTE, PyCoderStatus.SUCCESS)
                self.log_update.emit(PyCoderStage.ANALYZE_RESULT, PyCoderStatus.RUNNING)
                result = {
                    "code": "# No code was generated for this prompt.",
                    "output": "[Not applicable]",
                    "analysis": initial_response
                }
                self.finished.emit(result, self.node)
                self.log_update.emit(PyCoderStage.ANALYZE_RESULT, PyCoderStatus.SUCCESS)
                return
            
            current_code = code_match.group(1).strip()
            self.log_update.emit(PyCoderStage.GENERATE, PyCoderStatus.SUCCESS)

            # 2. Execute the code, with a retry loop for repairs.
            while retry_count < max_retries:
                self.log_update.emit(PyCoderStage.EXECUTE, PyCoderStatus.RUNNING)
                
                execution_output = ""
                is_success = False
                
                try:
                    # Execute the code in a separate process with a timeout
                    process = subprocess.run(
                        [sys.executable, "-c", current_code],
                        capture_output=True,
                        text=True,
                        timeout=20  # 20 second timeout to prevent infinite loops
                    )
                    execution_output = process.stdout + process.stderr
                    
                    # Consider non-zero exit codes as errors
                    if process.returncode != 0:
                         if not execution_output:
                             execution_output = f"Process exited with code {process.returncode}"
                         is_success = False
                    else:
                         # Even if return code is 0, check for error keywords in output (e.g. if caught but printed)
                         is_success = not self._is_error(execution_output)
                         
                except subprocess.TimeoutExpired:
                    execution_output = "TimeoutError: Code execution timed out after 20 seconds."
                    is_success = False
                except Exception as e:
                    execution_output = f"Execution Error: {str(e)}"
                    is_success = False

                if is_success:
                    # Success: break the loop and proceed to final analysis.
                    self.log_update.emit(PyCoderStage.EXECUTE, PyCoderStatus.SUCCESS)
                    self.log_update.emit(PyCoderStage.ANALYZE_RESULT, PyCoderStatus.RUNNING)
                    final_analysis = self.analysis_agent.get_response(
                        self.user_prompt, current_code, execution_output
                    )
                    result = {
                        "code": current_code,
                        "output": execution_output if execution_output else "[No output produced]",
                        "analysis": final_analysis
                    }
                    self.finished.emit(result, self.node)
                    self.log_update.emit(PyCoderStage.ANALYZE_RESULT, PyCoderStatus.SUCCESS)
                    return

                # Failure: log the error and attempt to repair the code.
                last_error = execution_output
                self.log_update.emit(PyCoderStage.EXECUTE, PyCoderStatus.FAILURE)
                
                # Emit feedback signal
                feedback_msg = f"\n--- Attempt {retry_count + 1} Failed ---\nError: {last_error[:200]}...\nRetrying with self-repair...\n"
                self.retry_feedback.emit(feedback_msg)
                
                retry_count += 1
                
                if retry_count < max_retries:
                    time.sleep(2)
                    self.log_update.emit(PyCoderStage.EXECUTE, PyCoderStatus.RUNNING)
                    is_final = (retry_count == max_retries - 1)
                    current_code = self.repair_agent.get_response(current_code, last_error, is_final)
            
            # If the loop finishes without success, the process has failed.
            self.log_update.emit(PyCoderStage.ANALYZE_RESULT, PyCoderStatus.RUNNING)
            final_failure_analysis = self.analysis_agent.get_response(
                self.user_prompt,
                current_code,
                f"The code failed to execute after {max_retries} attempts. The final error was:\n{last_error}"
            )
            result = {
                "code": current_code,
                "output": last_error,
                "analysis": f"**PROCESS FAILED**\n\nAfter {max_retries} attempts, the code could not be successfully executed.\n\n{final_failure_analysis}"
            }
            self.finished.emit(result, self.node)
            self.log_update.emit(PyCoderStage.ANALYZE_RESULT, PyCoderStatus.FAILURE)

        except Exception as e:
            self.error.emit(f"An unexpected error occurred in the PyCoder workflow: {str(e)}", self.node)


class PyCoderAgentWorker(QThread):
    """
    A simpler worker for the Manual Mode of the PyCoder node. It only runs the
    analysis step after the user-provided code has been executed.
    """
    finished = Signal(str, object)
    error = Signal(str, object)

    def __init__(self, code, code_output, node):
        super().__init__()
        self.code = code
        self.code_output = code_output
        self.node = node
        self.analysis_agent = PyCoderAnalysisAgent()

    def run(self):
        """Executes the analysis agent and emits the result."""
        try:
            # In manual mode, there is no "original prompt", so we pass None.
            ai_analysis = self.analysis_agent.get_response(
                original_prompt=None,
                code=self.code,
                code_output=self.code_output
            )
            self.finished.emit(ai_analysis, self.node)
        except Exception as e:
            self.error.emit(f"Failed to get AI analysis: {str(e)}", self.node)

# --- New Web Agent and Worker ---

class WebSearchAgent:
    """
    An agent that performs a multi-step web search workflow: refine query, search,
    fetch content, validate content, and summarize.
    """
    def __init__(self):
        """Initializes the agent and checks for required dependencies."""
        self._check_dependencies()
        self.generate_query_prompt = """
You are a search query refinement assistant. Your task is to analyze a conversation history and a final user query to generate a self-contained, effective search engine query.

RULES:
1.  Read the conversation history to understand the context.
2.  Analyze the final user query.
3.  If the query is already self-contained and clear (e.g., "what is the capital of France"), return it exactly as is.
4.  If the query is contextual (e.g., "what about its population?"), use the history to create a specific, self-contained query (e.g., "population of France").
5.  Your output MUST be ONLY the refined search query string. Do not add any explanation, preamble, or quotation marks.
"""
        self.validation_prompt = """
You are a content validation bot. Your only purpose is to determine if a piece of retrieved web content is safe and relevant to a user's original query.

RULES:
1. First, check for safety. The content is UNSAFE if it contains any of the following:
    - Explicit adult content (pornography, graphic violence)
    - Hate speech, harassment, or discriminatory language
    - Dangerous or illegal instructions (e.g., self-harm, building weapons)
    - Deceptive content (scams, phishing, malware links)

2. Second, check for relevance. The content is IRRELEVANT if it does NOT directly help answer the user's query. It is also irrelevant if it is:
    - A login page, error page, or navigation menu with no useful content.
    - A product page with only specifications and no descriptive text.
    - A forum index page without actual discussion content.
    - Gibberish or non-prose text.

3. Your response MUST be a single word: `SAFE` or `UNSAFE`.
    - If the content is safe AND relevant, output `SAFE`.
    - If the content is unsafe OR irrelevant, output `UNSAFE`.
    - Do NOT provide any explanation or other text.
"""
        self.summarization_prompt = """
You are a web-grounded summarization assistant. You will be given a user's original query, the conversation history for context, and a block of text retrieved from one or more web pages. Your task is to synthesize this information into a single, comprehensive, and well-written answer to the user's query.

RULES:
1.  **Use the Conversation History:** The history provides crucial context. Your answer must be relevant to the ongoing conversation.
2.  **Directly Answer the Query:** Your primary goal is to answer the user's original question using the provided web content.
3.  **Synthesize, Don't List:** Combine information from different parts of the text to form a coherent response. Do not treat the text as separate sources to be summarized individually.
4.  **Be Concise:** Extract the most important information and present it clearly. Avoid unnecessary details or filler text.
5.  **Use Markdown:** Format your response for readability using headings, bullet points, and bold text where appropriate.
"""

    def _check_dependencies(self):
        """
        Raises an ImportError if any of the required web-related libraries are missing.
        """
        if not DUCKDUCKGO_SEARCH_AVAILABLE:
            raise ImportError("Web search requires `ddgs`. Please install it: pip install ddgs")
        if not REQUESTS_AVAILABLE:
            raise ImportError("Web fetching requires `requests`. Please install it: pip install requests")
        if not BEAUTIFULSOUP_AVAILABLE:
            raise ImportError("Web parsing requires `beautifulsoup4`. Please install it: pip install beautifulsoup4")

    def generate_search_query(self, query: str, history: list) -> str:
        """
        Refines a user's query based on conversation history to make it self-contained.

        Args:
            query (str): The user's latest query.
            history (list): The preceding conversation history.

        Returns:
            str: A refined, standalone search query.
        """
        if not history:
            return query  # No context, query is as good as it gets.

        history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        user_prompt = f"""
--- Conversation History ---
{history_str}

--- Final User Query ---
{query}
"""
        try:
            # Use a fast model for this simple refinement task.
            response = api_provider.chat(
                task=config.TASK_TITLE,  # Re-using the title task model as it's meant to be fast
                messages=[
                    {'role': 'system', 'content': self.generate_query_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
            )
            return response['message']['content'].strip()
        except Exception as e:
            print(f"Failed to generate search query, falling back to original. Error: {e}")
            return query  # Fallback to original query on error

    def search(self, query: str) -> list:
        """
        Performs a web search using DuckDuckGo Search.

        Args:
            query (str): The search query.

        Returns:
            list: A list of search result dictionaries.
        """
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return results

    def fetch_content(self, url: str) -> (str | None, str | None):
        """
        Fetches and cleans the text content from a given URL.

        Args:
            url (str): The URL to fetch.

        Returns:
            tuple[str or None, str or None]: A tuple containing the cleaned text content
                                             and an error message if an error occurred.
        """
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            # Remove script, style, and common boilerplate elements.
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.extract()
            
            # Extract and clean up the text.
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return text, None
        except requests.RequestException as e:
            return None, f"Failed to fetch URL {url}: {e}"
        except Exception as e:
            return None, f"Failed to parse content from {url}: {e}"

    def validate_content(self, query: str, content: str) -> bool:
        """
        Uses an LLM to validate if fetched content is safe and relevant to the original query.

        Args:
            query (str): The original search query.
            content (str): The fetched web page content.

        Returns:
            bool: True if the content is deemed 'SAFE', False otherwise.
        """
        # Truncate content to avoid excessive token usage for a simple validation step.
        truncated_content = content[:4000]
        
        user_prompt = f"""
Original User Query: "{query}"

--- Retrieved Web Content ---
{truncated_content}
--- End of Content ---

Based on the rules, is this content safe and relevant? Respond with only `SAFE` or `UNSAFE`.
"""
        try:
            # This validation step now uses the api_provider to be mode-agnostic.
            messages = [
                {'role': 'system', 'content': self.validation_prompt},
                {'role': 'user', 'content': user_prompt}
            ]
            
            # Explicitly using TASK_WEB_VALIDATE to route to a faster, cheaper model
            response = api_provider.chat(task=config.TASK_WEB_VALIDATE, messages=messages)
            decision = response['message']['content'].strip().upper()
            
            return "SAFE" in decision
        except Exception as e:
            print(f"Content validation failed: {e}")
            # Re-raise with a more user-friendly message for the UI.
            raise RuntimeError(f"Content validation step failed: {e}")

    def summarize_content(self, query: str, validated_content: str, history: list) -> str:
        """
        Synthesizes the validated web content into a final answer for the user.

        Args:
            query (str): The user's original query.
            validated_content (str): The combined text from all validated sources.
            history (list): The preceding conversation history for context.

        Returns:
            str: A formatted summary answering the user's query.
        """
        history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        user_prompt = f"""
--- Conversation History ---
{history_str}

--- Original User Query for this step ---
"{query}"

--- Validated Web Content ---
{validated_content}
--- End of Content ---

Please provide a comprehensive answer to the original query based on the content provided and the conversation history for context.
"""
        try:
            # Explicitly using TASK_WEB_SUMMARIZE to route to a smarter, more capable model
            response = api_provider.chat(
                task=config.TASK_WEB_SUMMARIZE,
                messages=[
                    {'role': 'system', 'content': self.summarization_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
            )
            return response['message']['content']
        except Exception as e:
            raise RuntimeError(f"Failed to summarize web content: {e}")


class WebWorkerThread(QThread):
    """Orchestrates the WebSearchAgent's workflow in a background thread."""
    update_status = Signal(str) # Emits status updates for the UI.
    finished = Signal(dict, object)
    error = Signal(str, object)

    def __init__(self, query: str, history: list, node):
        super().__init__()
        self.query = query
        self.history = history
        self.node = node
        self.agent = WebSearchAgent()
        self._is_running = True

    def run(self):
        """Executes the full web search workflow step-by-step."""
        try:
            if not self._is_running: return

            # 1. Generate a context-aware search query.
            self.update_status.emit("Refining search query...")
            effective_query = self.agent.generate_search_query(self.query, self.history)

            # 2. Perform the web search.
            if not self._is_running: return
            self.update_status.emit(f"Searching for: \"{effective_query}\"...")
            results = self.agent.search(effective_query)
            if not results:
                raise ValueError("No search results found for your query.")

            # 3. Fetch, clean, and validate content from the top search results.
            if not self._is_running: return
            validated_texts = []
            source_urls = []
            for i, result in enumerate(results[:3]): # Process top 3 results
                if not self._is_running: return
                
                # Minimal polite delay to avoid hitting rate limits too aggressively
                self.update_status.emit(f"Fetching content from result {i+1}...")
                time.sleep(1)
                
                url = result.get('href')
                if not url: continue
                
                content, error = self.agent.fetch_content(url)
                if error or not content:
                    print(f"Skipping {url}: {error}")
                    continue

                if not self._is_running: return
                self.update_status.emit(f"Validating result {i+1}...")
                # Use the refined `effective_query` for more accurate validation.
                if self.agent.validate_content(effective_query, content):
                    validated_texts.append(content)
                    source_urls.append(url)
            
            if not self._is_running: return
            if not validated_texts:
                raise ValueError("No relevant and safe content could be retrieved from the web.")

            # 4. Synthesize the validated content into a final summary.
            self.update_status.emit("Synthesizing information...")
            combined_content = "\n\n---\n\n".join(validated_texts)
            # Pass the original query and history to the summarizer for full context.
            summary = self.agent.summarize_content(self.query, combined_content, self.history)

            if self._is_running:
                self.finished.emit({
                    "summary": summary,
                    "sources": source_urls,
                    "query": self.query # Keep original query for the node's display
                }, self.node)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e), self.node)
        finally:
            self._is_running = False
            
    def stop(self):
        """Stops the thread safely."""
        self._is_running = False

class ReasoningAgent:
    """
    An agent that uses a multi-step "plan, reason, critique" process to solve
    complex problems that a single LLM call might fail on.
    """
    PLAN_PROMPT = """
You are a methodical planner. Your task is to break down a complex user query into a series of simple, actionable steps. Each step should represent a single thought process or question that builds towards the final answer.

RULES:
- Output this plan as a numbered list (e.g., "1. First step...").
- Do NOT attempt to answer the query yet.
- Each step should be a clear, self-contained instruction or question.
- The plan should logically flow from one step to the next.
- The final step should always be to synthesize the previous steps into a final answer.
"""

    REASON_PROMPT = """
You are a reasoning engine executing one step of a larger plan.
You will be given the original query, the full plan, the history of previous thoughts, and the current step to execute.

RULES:
- Your task is to focus EXCLUSIVELY on the CURRENT step.
- Use the 'Original Query' and 'Thought History' for context.
- Provide a detailed, self-contained answer for the current step.
- Do NOT solve the entire problem. Only address the single step you are given.
- Think through your response clearly and logically.
"""

    CRITIQUE_PROMPT = """
You are a critical analyst. Your task is to review a 'thought' generated by another AI to find flaws.

RULES:
1.  **Review the Thought:** Read the thought in the context of the original query.
2.  **Identify Weaknesses:** Check for logical fallacies, missing information, incorrect assumptions, or alternative perspectives. Ask critical questions like:
    - Is this assumption valid?
    - What is the counter-argument?
    - Is there a simpler explanation?
    - What evidence is missing?
3.  **Provide a Refined Thought:** Based on your critique, provide a new, improved version of the thought. It should be more robust, logical, and complete.
4.  **Format:** Your output MUST be in this format:
    **Critique:** [Your brief, bulleted critique of the original thought.]
    **Refined Thought:** [Your new, improved version of the thought.]
"""

    SYNTHESIZE_PROMPT = """
You are a synthesis expert. You have been provided with a user's original query and a series of vetted, refined 'thoughts' that break down the problem.

RULES:
- Your task is to weave these thoughts together into a single, comprehensive, and well-structured final answer.
- Do not just list the thoughts; synthesize them into a coherent narrative that directly addresses the user's original query.
- Use clear markdown formatting (headings, lists, bold text) for readability.
- The final answer should be self-contained and understandable without needing to read the intermediate thoughts.
"""

    def run_step(self, system_prompt: str, user_prompt: str) -> str:
        """
        Executes a single LLM call for one step of the reasoning process.

        Args:
            system_prompt (str): The system prompt defining the agent's role for this step.
            user_prompt (str): The user prompt containing the context and current task.

        Returns:
            str: The AI's response for this step.
        """
        try:
            response = api_provider.chat(
                task=config.TASK_CHAT,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ]
            )
            return response['message']['content']
        except Exception as e:
            raise RuntimeError(f"API call failed during reasoning step: {e}")

class ReasoningWorkerThread(QThread):
    """Orchestrates the ReasoningAgent's workflow in a background thread."""
    step_finished = Signal(str, str) # title, text
    finished = Signal(str) # final_answer
    error = Signal(str)

    def __init__(self, agent: ReasoningAgent, original_prompt: str, budget: int):
        super().__init__()
        self.agent = agent
        self.original_prompt = original_prompt
        self.budget = budget # The number of "reason -> critique" cycles.
        self._is_running = True

    def run(self):
        """Executes the full multi-step reasoning workflow."""
        try:
            if not self._is_running: return

            # 1. Create a plan based on the original prompt.
            plan_user_prompt = f"Original Query: \"{self.original_prompt}\"\n\nCreate a step-by-step plan to answer this query."
            plan_str = self.agent.run_step(self.agent.PLAN_PROMPT, plan_user_prompt)
            # Parse the numbered list from the plan string.
            plan_steps = [f"{i}. {step.strip()}" for i, step in enumerate(re.split(r'\d+\.\s*', plan_str)) if step.strip()]
            self.step_finished.emit("Step 1: The Plan", "\n".join(plan_steps))
            
            thought_history = []
            
            # 2. Iterate through the plan for the number of steps defined by the "thinking budget".
            for i in range(self.budget):
                if not self._is_running: return
                time.sleep(3)
                # Use modulo to loop through plan steps if the budget is larger than the plan.
                step_index = i % len(plan_steps)
                current_step = plan_steps[step_index]

                # 2a. Execute the "Reason" step.
                reason_user_prompt = (
                    f"Original Query: \"{self.original_prompt}\"\n\n"
                    f"Full Plan:\n{plan_str}\n\n"
                    f"Thought History:\n{''.join(thought_history) or 'No thoughts yet.'}\n\n"
                    f"CURRENT STEP TO EXECUTE: {current_step}"
                )
                initial_thought = self.agent.run_step(self.agent.REASON_PROMPT, reason_user_prompt)

                if not self._is_running: return

                # 2b. Execute the "Critique" step on the previous thought.
                critique_user_prompt = (
                    f"Original Query: \"{self.original_prompt}\"\n\n"
                    f"Thought to Critique:\n{initial_thought}"
                )
                critique_response = self.agent.run_step(self.agent.CRITIQUE_PROMPT, critique_user_prompt)
                
                # Parse the refined thought from the critique response.
                refined_thought = critique_response
                if "Refined Thought:" in critique_response:
                    parts = critique_response.split("Refined Thought:", 1)
                    if len(parts) > 1:
                        refined_thought = parts[1].strip()

                # Add the refined thought to the history for the next step.
                thought_history.append(f"Thought on '{current_step}':\n{refined_thought}\n\n")
                self.step_finished.emit(f"Step {i+2}: {current_step}", critique_response)

            if not self._is_running: return

            # 3. Synthesize the final answer from the history of refined thoughts.
            synthesis_user_prompt = (
                f"Original Query: \"{self.original_prompt}\"\n\n"
                f"Full History of Refined Thoughts:\n{''.join(thought_history)}"
            )
            final_answer = self.agent.run_step(self.agent.SYNTHESIZE_PROMPT, synthesis_user_prompt)
            
            if self._is_running:
                self.finished.emit(final_answer)

        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))
        finally:
            self._is_running = False

    def stop(self):
        """Stops the thread safely."""
        self._is_running = False

class OrchestratorAgent:
    """
    An agent that takes a high-level goal and generates a structured,
    executable JSON plan for a multi-agent workflow.
    """
    def __init__(self):
        """Initializes the agent with its plan-generation system prompt."""
        self.system_prompt = """
You are an expert planner for an agentic workflow system. Your task is to take a user's high-level goal and create the most efficient, high-level plan possible in a JSON format.

**CRITICAL RULES:**
1.  **MAXIMUM 7 STEPS:** The entire plan MUST NOT exceed 7 steps under any circumstances. This is a hard limit.
2.  **THINK HIGH-LEVEL:** Your goal is efficiency. Combine multiple small actions into a single logical step. Do not create granular, single-action steps. For example, instead of one step to "Search for X" and another to "Save result to memory", create a single step: "Research Topic X and save the findings to memory key 'topic_x_data'".
3.  **BE EFFICIENT:** Create the shortest, most logical plan to achieve the goal with the fewest steps.

You have access to the following tools:
1.  `Web Researcher`: Use this to search the internet for NEW information.
2.  `Py-Coder`: Use this for any task that requires calculation, data processing, or code execution.
3.  `Memory Bank`: Use this to save ("input" with "output_key") or retrieve ("input" with key name) information between steps.
4.  `Synthesizer`: Use this to combine, summarize, analyze, or reformat text from previous steps. The input must be a clear instruction and the source text (usually from memory using `{{step_N.output}}`).
5. NEVER offload more than (one) a single search query to the web agent, that is NOT how that tool is meant to be used! It is for SINGLE calls! NOT multiple in a single search query, BREAK the search topics and web related tool-calls into multiple steps. NEVER a single step! 

EXAMPLE of an EFFICIENT plan:
User Goal: "Research the main competitors of OpenAI, find their flagship products, and write a summary comparing them."

[
  {
    "step": 1,
    "task": "Research OpenAI's main competitors and their flagship products.",
    "tool": "Web Researcher",
    "input": "main competitors of OpenAI and their flagship products"
  },
  {
    "step": 2,
    "task": "Save the research findings to the memory bank for later use.",
    "tool": "Memory Bank",
    "input": "{{step_1.output}}",
    "output_key": "competitor_research"
  },
  {
    "step": 3,
    "task": "Synthesize the research into a comparative summary.",
    "tool": "Synthesizer",
    "input": "Using the provided text, write a report comparing OpenAI's competitors and their flagship products. Text: {{step_2.output}}"
  }
]

Now, analyze the user's goal and generate the JSON plan. Your output MUST be ONLY the raw JSON array.
"""

    def _clean_response(self, text: str) -> str:
        """
        Cleans the raw string response from the LLM to isolate the JSON object.
        Models often wrap JSON in markdown backticks or add explanatory text.
        """
        # Remove markdown code block fences.
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # Find the first opening bracket and the last closing bracket to extract the JSON array.
        try:
            start = text.find('[')
            end = text.rfind(']') + 1
            if start >= 0 and end > start:
                text = text[start:end]
        except:
            pass
            
        return text

    def generate_plan(self, goal: str, history: list) -> str:
        """
        Generates the JSON plan for a given goal and conversation history.

        Args:
            goal (str): The user's high-level goal.
            history (list): The preceding conversation history for context.

        Returns:
            str: A JSON string representing the plan.
        """
        # Clean history to ensure only text is included, preventing image bytes from being passed to the planner
        clean_history = []
        for msg in history:
            role = msg['role']
            content = msg['content']
            
            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                # Extract only text parts from multi-modal content
                text_parts = [part.get('text', '') for part in content if part.get('type') == 'text']
                text_content = "\n".join(text_parts)
            
            if text_content:
                 clean_history.append(f"{role}: {text_content}")

        history_str = "\n".join(clean_history)

        user_prompt = f"""
--- Conversation History (for context) ---
{history_str}

--- User's High-Level Goal ---
{goal}
"""
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]
        
        # Use a "smart" model for this complex planning task
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        raw_response = response['message']['content']
        
        return self._clean_response(raw_response)

class OrchestratorWorkerThread(QThread):
    """
    QThread worker for the OrchestratorAgent. This thread's responsibility is
    to generate the initial plan. The execution of the plan will be handled
    by a different, more complex worker later.
    """
    plan_generated = Signal(str, object)
    error = Signal(str, object)

    def __init__(self, agent: OrchestratorAgent, goal: str, history: list, node):
        super().__init__()
        self.agent = agent
        self.goal = goal
        self.history = history
        self.node = node
        self._is_running = True

    def run(self):
        """Executes the plan generation and emits the result."""
        try:
            if not self._is_running: return
            plan_json_str = self.agent.generate_plan(self.goal, self.history)
            
            # Basic validation to ensure the response is valid JSON
            try:
                json.loads(plan_json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"Model returned invalid JSON. Error: {e}\n\nResponse:\n{plan_json_str}")

            if self._is_running:
                self.plan_generated.emit(plan_json_str, self.node)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e), self.node)
        finally:
            self._is_running = False

    def stop(self):
        """Stops the thread safely."""
        self._is_running = False

class OrchestratorExecutionWorker(QThread):
    """
    Executes a pre-defined JSON plan by interacting with tool nodes on the canvas.
    This is the "Executor" part of the Orchestrator.
    """
    step_started = Signal(int)
    log_message = Signal(str)
    execution_finished = Signal(str)
    step_finished = Signal(int, str) # New signal for granular UI updates: (step_num, output)
    error = Signal(str)
    request_tool_node = Signal(str, QGraphicsObject)
    tool_node_created = Signal(QGraphicsObject)
    execute_tool = Signal(object, str, dict)
    tool_execution_finished = Signal(str)

    def __init__(self, scene, plan: list, orchestrator_node):
        super().__init__()
        self.scene = scene
        self.plan = plan
        self.orchestrator_node = orchestrator_node
        self.step_outputs = {}
        self._is_running = True
        self.created_node = None
        self._current_tool_result = ""

    def _get_or_create_tool_node(self, tool_name: str):
        from graphite_web import WebNode
        from graphite_pycoder import PyCoderNode
        from graphite_orchestrator import MemoryBankNode, SynthesisNode

        if tool_name == "Web Researcher":
            nodes = self.scene.web_nodes
            node_class = WebNode
        elif tool_name == "Py-Coder":
            nodes = self.scene.pycoder_nodes
            node_class = PyCoderNode
        elif tool_name == "Memory Bank":
            nodes = self.scene.memory_bank_nodes
            node_class = MemoryBankNode
        elif tool_name == "Synthesizer":
            nodes = self.scene.synthesis_nodes
            node_class = SynthesisNode
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

        for node in nodes:
            if isinstance(node, node_class):
                return node

        self.log_message.emit(f"> Tool node '{tool_name}' not found. Creating a new one...")
        
        loop = QEventLoop()
        self.created_node = None

        def on_node_created(node):
            self.created_node = node
            loop.quit()

        self.tool_node_created.connect(on_node_created)
        self.request_tool_node.emit(tool_name, self.orchestrator_node)
        loop.exec()
        self.tool_node_created.disconnect(on_node_created)

        if not self.created_node:
             raise RuntimeError(f"Failed to create the required tool node: {tool_name}")

        return self.created_node

    def run(self):
        try:
            for step in self.plan:
                if not self._is_running: return
                time.sleep(2) # Short delay for visual pacing
                step_num = step['step']
                task = step['task']
                tool = step['tool']
                raw_input = step['input']

                self.step_started.emit(step_num)
                self.log_message.emit(f"**Step {step_num}:** {task}")
                
                tool_node = self._get_or_create_tool_node(tool)

                def substitute_input(match):
                    prev_step_num_str = match.group(1)
                    if prev_step_num_str.isdigit():
                        prev_step_num = int(prev_step_num_str)
                        return str(self.step_outputs.get(prev_step_num, ""))
                    return ""
                
                final_input = re.sub(r'\{\{step_(\d+)\.output\}\}', substitute_input, str(raw_input))
                self.log_message.emit(f"> Using tool `{tool}` with input: *\"{final_input[:100]}...\"*")
                
                loop = QEventLoop()
                
                def on_tool_finished(result):
                    self._current_tool_result = result
                    loop.quit()
                
                self.tool_execution_finished.connect(on_tool_finished)
                self.execute_tool.emit(tool_node, final_input, step)
                loop.exec()
                self.tool_execution_finished.disconnect(on_tool_finished)
                
                self.step_outputs[step_num] = self._current_tool_result
                
                # New: Emit signal for granular UI update
                self.step_finished.emit(step_num, self._current_tool_result)
                
                self.log_message.emit(f"**Result:** {str(self.step_outputs.get(step_num, ''))[:200]}...")

            final_result = self.step_outputs.get(len(self.plan), "Workflow completed.")
            self.execution_finished.emit(final_result)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            self._is_running = False

    def stop(self):
        self._is_running = False

class SynthesisAgent:
    """An agent for summarizing, combining, or re-writing text based on instructions."""
    def __init__(self):
        self.system_prompt = """You are an expert writing and synthesis assistant.
Your task is to take a set of instructions and a body of text and generate a new text that fulfills the user's request.
- Analyze the instructions carefully.
- Use the provided text as your source of information.
- Format your response clearly and concisely.
- Your output should be only the final, synthesized text.
"""

    def get_response(self, instruction_and_text: str) -> str:
        """
        Generates a synthesized response.

        Args:
            instruction_and_text (str): A single string containing both the user's
                                        instructions and the source text.

        Returns:
            str: The synthesized text.
        """
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': instruction_and_text}
        ]
        response = api_provider.chat(task=config.TASK_CHAT, messages=messages)
        return response['message']['content']

class SynthesisWorkerThread(QThread):
    """QThread worker for the SynthesisAgent."""
    finished = Signal(str, object)
    error = Signal(str, object)

    def __init__(self, agent: SynthesisAgent, instruction: str, node):
        super().__init__()
        self.agent = agent
        self.instruction = instruction
        self.node = node
        self._is_running = True

    def run(self):
        """Executes the agent and emits the result."""
        try:
            if not self._is_running: return
            response = self.agent.get_response(self.instruction)
            if self._is_running:
                self.finished.emit(response, self.node)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))
        finally:
            self._is_running = False

    def stop(self):
        """Stops the thread safely."""
        self._is_running = False