"""
Configuration Management
Loads configurations uniformly from the project root's .env file.
"""

import os
from dotenv import load_dotenv

# Load the .env file from the project root
# Path: MiroFish/.env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in the root, try to load environment variables (for production)
    load_dotenv(override=True)


class Config:
    """Flask Configuration Class"""

    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    JSON_AS_ASCII = False

    # LLM configuration (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # FalkorDB configuration
    FALKORDB_HOST = os.environ.get('FALKORDB_HOST', 'localhost')
    FALKORDB_PORT = int(os.environ.get('FALKORDB_PORT', '6379'))
    FALKORDB_PASSWORD = os.environ.get('FALKORDB_PASSWORD', '')
    FALKORDB_DATABASE = os.environ.get('FALKORDB_DATABASE', 'mirofish')

    # Embedding configuration (for Graphiti semantic search)
    # Must point to an OpenAI-compatible /embeddings endpoint.
    # Defaults to OpenAI — change if your LLM provider supports embeddings.
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY') or os.environ.get('LLM_API_KEY')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'https://api.openai.com/v1')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')

    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing configuration
    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50

    # OASIS simulation configuration
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent configuration
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    @classmethod
    def validate(cls):
        """Validates necessary configurations"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is not configured")
        if not cls.EMBEDDING_API_KEY:
            errors.append("EMBEDDING_API_KEY is not configured (or set LLM_API_KEY)")
        return errors
