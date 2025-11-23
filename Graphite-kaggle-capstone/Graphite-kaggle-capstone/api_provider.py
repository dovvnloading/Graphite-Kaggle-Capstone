"""
This module serves as the abstraction layer for interacting with the Google Gemini
Large Language Model (LLM). Its purpose is to offer a single, consistent interface
(`chat`, etc.) to the rest of the application.

This decouples the application's core logic from the specific implementation details
of the Gemini API.
"""

import os
import graphite_config as config
import io
import time

# --- Conditional Dependency Import ---
# Pillow is a soft dependency, only required at runtime for image support with Gemini.
# The application can run without it, but an error will be raised if a user tries
# to send an image without Pillow installed.
try:
    from PIL import Image
except ImportError:
    Image = None


try:
    from google.api_core import exceptions as google_exceptions
except ImportError:
    google_exceptions = None


# --- Global State Variables ---

# Stores the type of the currently configured API provider.
API_PROVIDER_TYPE = None
# Holds the initialized client object for the configured API provider.
API_CLIENT = None
# A dictionary mapping application-specific tasks (e.g., 'task_chat') to the specific model name
# to be used for that task when in API mode.
API_MODELS = {
    config.TASK_TITLE: None,
    config.TASK_CHAT: None,
    config.TASK_CHART: None,
    config.TASK_WEB_VALIDATE: None,
    config.TASK_WEB_SUMMARIZE: None
}

# A static, hard-coded list of reliable Gemini models. This is used to populate
# the settings UI.
GEMINI_MODELS_STATIC = sorted([
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "learnlm-2.0-flash-experimental",
    "gemini-2.5-flash-image",
])


def _convert_to_gemini_messages(messages: list) -> tuple:
    """
    Converts the application's standard message list format into the specific
    format required by the Google Gemini API. It also extracts the system prompt.

    The Gemini API has a different structure:
    - It uses 'user' and 'model' for roles instead of 'user' and 'assistant'.
    - The system prompt is a separate parameter, not part of the message list.
    - It requires strict alternation of 'user' and 'model' roles.
    - It accepts PIL.Image objects directly for multi-modal input.

    Args:
        messages (list): A list of message dictionaries in the standard format
                         ({'role': '...', 'content': '...'}).

    Returns:
        tuple: A tuple containing (system_prompt, gemini_history_list).
    """
    # Raise an error if Pillow is needed but not installed.
    if Image is None and any(isinstance(msg.get('content'), list) for msg in messages):
        raise ImportError("Pillow library is required for image support with Gemini. Please install it with: pip install Pillow")

    system_prompt = None
    gemini_history = []
    
    for msg in messages:
        # Extract the system prompt and skip adding it to the history.
        if msg['role'] == 'system':
            system_prompt = msg['content']
            continue
        
        # Map 'assistant' to 'model' for Gemini's API.
        role = 'model' if msg['role'] == 'assistant' else 'user'
        
        # Process the content, which could be a simple string or a list of parts for multi-modal messages.
        content = msg['content']
        parts = []
        if isinstance(content, list):
            # Handle multi-modal content (text and images).
            for part in content:
                if part.get('type') == 'text':
                    parts.append(part.get('text', ''))
                elif part.get('type') == 'image_bytes':
                    image_data = part.get('data')
                    if image_data:
                        try:
                            # Convert raw bytes into a PIL Image object, which Gemini's SDK accepts.
                            img = Image.open(io.BytesIO(image_data))
                            parts.append(img)
                        except Exception as e:
                            # Handle potential errors if the image data is corrupt.
                            print(f"Warning: Could not process image data. Error: {e}")
                            parts.append("[Image could not be processed]")
        else:
            # Handle simple text content.
            parts.append(str(content))

        # Ensure strict alternation of roles. Gemini's API will error if two 'user' or
        # two 'model' messages appear consecutively.
        if gemini_history and gemini_history[-1]['role'] == role:
            # If two user messages in a row, combine them into the previous message.
            if role == 'user':
                gemini_history[-1]['parts'].extend(parts)
                continue
            # If two model messages in a row (unusual), add a placeholder user message to maintain alternation.
            else:
                gemini_history.append({'role': 'user', 'parts': ["(Continuing...)"]})

        gemini_history.append({
            'role': role,
            'parts': parts
        })
        
    return system_prompt, gemini_history


def chat(task: str, messages: list, timeout: int = 120, **kwargs) -> dict:
    """
    The main entry point for all chat-based LLM interactions in the application.

    This function routes the request to the configured Google Gemini API,
    selecting the appropriate model for the given `task`.

    Args:
        task (str): An identifier for the type of task (e.g., 'task_chat', 'task_title'),
                    used to select the correct model from the configuration.
        messages (list): A list of message dictionaries representing the conversation.
        timeout (int, optional): The timeout in seconds for the API request. Defaults to 120.
        **kwargs: Additional keyword arguments to pass directly to the underlying
                  API call (e.g., temperature, max_tokens).

    Returns:
        dict: A dictionary in a standardized format: {'message': {'content': '...', 'role': 'assistant'}}

    Raises:
        RuntimeError: If the API client is not initialized or a model is not configured.
    """
    max_retries = 4
    base_delay = 2

    for attempt in range(max_retries):
        try:
            if not API_CLIENT:
                raise RuntimeError("API client not initialized. Configure API settings first.")

            api_model = None
            if task == config.TASK_WEB_VALIDATE:
                api_model = API_MODELS.get(task) or "gemini-1.5-flash-latest"
            else:
                 api_model = API_MODELS.get(task)

            if not api_model:
                raise RuntimeError(
                    f"No API model configured for task '{task}'.\n"
                    f"Please configure models in API Settings."
                )

            if API_PROVIDER_TYPE == config.API_PROVIDER_GEMINI:
                system_prompt, gemini_history = _convert_to_gemini_messages(messages)
                
                model_config = {}
                if system_prompt:
                    model_config['system_instruction'] = system_prompt

                gemini_model = API_CLIENT.GenerativeModel(api_model, **model_config)
                
                response = gemini_model.generate_content(
                    contents=gemini_history,
                    generation_config=kwargs,
                    request_options={'timeout': timeout}
                )
                
                return {
                    'message': {
                        'content': response.text,
                        'role': 'assistant'
                    }
                }
            else:
                raise RuntimeError(f"Unsupported API provider: {API_PROVIDER_TYPE}")
        
        except (google_exceptions.ResourceExhausted if google_exceptions else Exception) as e:
            if isinstance(e, google_exceptions.ResourceExhausted) or "429" in str(e):
                if attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)
                    print(f"Rate limit hit (429). Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError("API rate limit exceeded after multiple retries.") from e
            else:
                raise e
        except Exception as e:
            raise e


def initialize_api(provider: str, api_key: str, base_url: str = None):
    """
    Initializes and configures the global API client for the Gemini provider.

    Args:
        provider (str): The name of the provider (must be "Google Gemini").
        api_key (str): The API key for authentication.
        base_url (str, optional): This parameter is ignored for Gemini.

    Returns:
        The initialized API client object.

    Raises:
        RuntimeError: If the 'google-generativeai' library is not installed.
        ValueError: If a provider other than "Google Gemini" is given.
    """
    global API_PROVIDER_TYPE, API_CLIENT
    API_PROVIDER_TYPE = provider

    if provider == config.API_PROVIDER_GEMINI:
        try:
            import google.generativeai as genai
        except ImportError:
            raise RuntimeError("google-generativeai package required. Install with: pip install google-generativeai")
        
        genai.configure(api_key=api_key)
        API_CLIENT = genai
    else:
        raise ValueError(f"Unknown API provider: {provider}")

    return API_CLIENT


def get_available_models():
    """
    Returns the static list of available Gemini models.

    Returns:
        list: A sorted list of model names.

    Raises:
        RuntimeError: If the API client is not initialized.
    """
    if not API_CLIENT:
        raise RuntimeError("API client not initialized")

    try:
        if API_PROVIDER_TYPE == config.API_PROVIDER_GEMINI:
            return GEMINI_MODELS_STATIC
        else:
            return []
    except Exception as e:
        raise RuntimeError(f"Failed to fetch models: {str(e)}")


def set_task_model(task: str, api_model: str):
    """
    Maps a specific API model name to a task type.

    Args:
        task (str): The task identifier (e.g., 'task_chat').
        api_model (str): The name of the model to use for this task.
    """
    if task in API_MODELS:
        API_MODELS[task] = api_model

def get_task_models() -> dict:
    """Returns the current mapping of tasks to configured API models."""
    return API_MODELS.copy()

def is_configured() -> bool:
    """
    Checks if the API provider is fully initialized and models are configured.

    Returns:
        bool: True if the API client is set up and all models have a value, False otherwise.
    """
    return API_CLIENT is not None and all(API_MODELS.values())