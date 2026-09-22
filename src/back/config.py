from os import environ
from dotenv import load_dotenv

load_dotenv()
api_key = environ.get("MODEL_API_KEY")
model_name = environ.get("MODEL_NAME")
base_url = environ.get("MODEL_BASE_URL")
sqlite_path = environ.get("SQLITE_PATH")
sqlite_max_connections = int(environ.get("SQLITE_MAX_CONNECTIONS"))
history_max_length = int(environ.get("HISTORY_MAX_LENGTH"))
role_spliter = "\x1E"
lorebook_lifecycle = int(environ.get("LOREBOOK_LIFECYCLE", "3"))
context_window = int(environ.get("CONTEXT_WINDOW", "30"))
fold_segment = int(environ.get("FOLD_SEGMENT", "20"))
summary_temperature = float(environ.get("SUMMARY_TEMPERATURE", "0"))
summary_max_tokens = int(environ.get("SUMMARY_MAX_TOKENS", "1024"))
