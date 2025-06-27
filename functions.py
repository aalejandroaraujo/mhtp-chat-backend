import os
import logging
import json
import sqlite3
import time
from contextlib import contextmanager
from flask import Flask, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from functools import wraps


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Get configuration from environment variables
ASSISTANT_INTAKE_ID = os.getenv('ASSISTANT_INTAKE_ID')
ASSISTANT_ADVICE_ID = os.getenv('ASSISTANT_ADVICE_ID')
TYPEBOT_SECRET = os.getenv('TYPEBOT_SECRET')
REDIS_URL = os.getenv('REDIS_URL')

# Validate environment variables
if not all([os.getenv('OPENAI_API_KEY'), ASSISTANT_INTAKE_ID, ASSISTANT_ADVICE_ID, TYPEBOT_SECRET]):
    logger.error("Missing required environment variables")
    raise ValueError("Missing required environment variables: OPENAI_API_KEY, ASSISTANT_INTAKE_ID, ASSISTANT_ADVICE_ID, TYPEBOT_SECRET")

# Initialize persistence layer
redis_client = None
if REDIS_URL:
    try:
        import redis
        redis_client = redis.from_url(REDIS_URL)
        redis_client.ping()
        logger.info("Connected to Redis for thread persistence")
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}. Falling back to SQLite.")
        redis_client = None

# SQLite setup if Redis is not available
if not redis_client:
    DB_PATH = 'threads.db'
    
    def init_sqlite():
        """Initialize SQLite database for thread persistence"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS threads (
                    session_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
    
    init_sqlite()
    logger.info("Using SQLite for thread persistence")

class OpenAIError(Exception):
    """Custom exception for OpenAI API errors"""
    pass

def require_auth(f):
    """Decorator to require authentication header"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('X-TYPEBOT-KEY')
        if not auth_header or auth_header != TYPEBOT_SECRET:
            logger.warning(f"Unauthorized request from {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated_function

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    if redis_client:
        yield redis_client
    else:
        conn = sqlite3.connect(DB_PATH)
        try:
            yield conn
        finally:
            conn.close()

def get_thread_id(session_id):
    """Get thread_id for a session_id"""
    try:
        with get_db_connection() as db:
            if redis_client:
                thread_id = db.get(f"thread:{session_id}")
                return thread_id.decode('utf-8') if thread_id else None
            else:
                cursor = db.execute("SELECT thread_id FROM threads WHERE session_id = ?", (session_id,))
                result = cursor.fetchone()
                return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting thread_id for session {session_id}: {e}")
        return None

def save_thread_id(session_id, thread_id):
    """Save thread_id for a session_id"""
    try:
        with get_db_connection() as db:
            if redis_client:
                db.set(f"thread:{session_id}", thread_id, ex=86400)  # 24 hours expiry
            else:
                db.execute('''
                    INSERT OR REPLACE INTO threads (session_id, thread_id, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (session_id, thread_id))
                db.commit()
        logger.info(f"Saved thread_id {thread_id} for session {session_id}")
    except Exception as e:
        logger.error(f"Error saving thread_id for session {session_id}: {e}")

def trim_thread_history(thread_id):
    """Trim thread history to keep only the last 25 messages"""
    try:
        messages = client.beta.threads.messages.list(thread_id=thread_id, limit=100)
        
        if len(messages.data) > 25:
            # Sort messages by created_at (oldest first)
            sorted_messages = sorted(messages.data, key=lambda x: x.created_at)
            
            # Calculate how many to delete (keep pairs intact)
            to_delete = len(sorted_messages) - 25
            
            # Ensure we delete in pairs (user-assistant) to maintain conversation flow
            if to_delete % 2 != 0:
                to_delete += 1
            
            # Delete oldest messages
            for i in range(min(to_delete, len(sorted_messages))):
                try:
                    client.beta.threads.messages.delete(
                        thread_id=thread_id,
                        message_id=sorted_messages[i].id
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete message {sorted_messages[i].id}: {e}")
            
            logger.info(f"Trimmed {min(to_delete, len(sorted_messages))} messages from thread {thread_id}")
    
    except Exception as e:
        logger.error(f"Error trimming thread history for {thread_id}: {e}")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OpenAIError,)),
    reraise=True
)
def call_openai_assistant(assistant_id, message, session_id, temperature=0.2, max_tokens=200, function_name=None):
    """
    Call OpenAI assistant with retry logic and native conversation handling
    """
    try:
        # Get or create thread
        thread_id = get_thread_id(session_id)
        
        if not thread_id:
            # Create new thread
            thread = client.beta.threads.create()
            thread_id = thread.id
            save_thread_id(session_id, thread_id)
            logger.info(f"Created new thread {thread_id} for session {session_id}")
        else:
            logger.info(f"Using existing thread {thread_id} for session {session_id}")
        
        # Trim history if needed
        trim_thread_history(thread_id)
        
        # Add current user message
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )
        
        # Create run with specific parameters
        run_params = {
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "request_timeout": 25
        }
        
        if function_name:
            run_params["tools"] = [{"type": "function", "function": {"name": function_name}}]
        
        run = client.beta.threads.runs.create(**run_params)
        
        # Wait for completion
        while run.status in ['queued', 'in_progress', 'cancelling']:
            time.sleep(0.2)
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        
        if run.status == 'completed':
            # Get the latest assistant message
            messages = client.beta.threads.messages.list(thread_id=thread_id, limit=1)
            
            if messages.data and messages.data[0].role == 'assistant':
                assistant_message = messages.data[0]
                content = assistant_message.content[0].text.value
                
                # Process function calls if any
                function_result = None
                if hasattr(run, 'required_action') and run.required_action:
                    tool_calls = run.required_action.submit_tool_outputs.tool_calls
                    if tool_calls:
                        for tool_call in tool_calls:
                            if tool_call.function.name == function_name:
                                try:
                                    function_result = json.loads(tool_call.function.arguments)
                                except json.JSONDecodeError:
                                    logger.warning(f"Failed to parse function arguments: {tool_call.function.arguments}")
                
                return content, function_result
            
            raise OpenAIError("No assistant response found")
        
        elif run.status == 'failed':
            logger.error(f"Run failed: {run.last_error}")
            raise OpenAIError(f"Assistant run failed: {run.last_error}")
        
        elif run.status == 'requires_action':
            # Handle function calls
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            function_result = None
            
            for tool_call in tool_calls:
                if tool_call.function.name == function_name:
                    try:
                        function_result = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse function arguments: {tool_call.function.arguments}")
            
            # Submit empty tool outputs to complete the run
            client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=[{
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(function_result) if function_result else "{}"
                } for tool_call in tool_calls]
            )
            
            # Wait for completion after submitting tool outputs
            while run.status in ['queued', 'in_progress', 'cancelling']:
                time.sleep(0.2)
                run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            
            # Get the final response
            messages = client.beta.threads.messages.list(thread_id=thread_id, limit=1)
            if messages.data and messages.data[0].role == 'assistant':
                content = messages.data[0].content[0].text.value
                return content, function_result
            
            raise OpenAIError("No assistant response after function call")
        
        else:
            logger.error(f"Unexpected run status: {run.status}")
            raise OpenAIError(f"Unexpected run status: {run.status}")
            
    except Exception as e:
        if hasattr(e, 'status_code'):
            if e.status_code == 429:
                logger.warning(f"Rate limit exceeded for session {session_id}")
                raise OpenAIError("Rate limit exceeded")
            elif e.status_code >= 500:
                logger.error(f"Server error {e.status_code} for session {session_id}")
                raise OpenAIError(f"Server error: {e.status_code}")
        
        logger.error(f"OpenAI API error for session {session_id}: {str(e)}")
        raise OpenAIError(f"OpenAI API error: {str(e)}")

def validate_request_data(data):
    """
    Validate incoming request data
    """
    required_fields = ['message', 'history', 'session_id', 'metadata']
    
    if not data:
        return False, "No JSON data provided"
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    if not isinstance(data['message'], str):
        return False, "Message must be a string"
    
    if not isinstance(data['history'], list):
        return False, "History must be a list"
    
    if not isinstance(data['session_id'], str):
        return False, "Session ID must be a string"
    
    if not isinstance(data['metadata'], dict):
        return False, "Metadata must be a dictionary"
    
    return True, None

@app.route('/intake', methods=['POST'])
@require_auth
def intake():
    """
    Endpoint for intake assistant
    """
    try:
        data = request.get_json()
        
        # Validate request data
        is_valid, error_msg = validate_request_data(data)
        if not is_valid:
            logger.warning(f"Invalid request data: {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        message = data['message']
        session_id = data['session_id']
        
        logger.info(f"Processing intake request for session {session_id}")
        
        # Call OpenAI assistant with intake parameters
        response, _ = call_openai_assistant(
            assistant_id=ASSISTANT_INTAKE_ID,
            message=message,
            session_id=session_id,
            temperature=0.2,
            max_tokens=200
        )
        
        logger.info(f"Intake response generated for session {session_id}")
        
        return jsonify({
            "reply": response,
            "end_chat": False
        }), 200, {'Content-Type': 'application/json; charset=utf-8'}
        
    except OpenAIError as e:
        logger.error(f"OpenAI error in intake: {str(e)}")
        return jsonify({
            "reply": "Lo siento, hay un problema técnico. Por favor, inténtalo de nuevo.",
            "end_chat": False
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}
    
    except Exception as e:
        logger.error(f"Unexpected error in intake: {str(e)}")
        return jsonify({
            "reply": "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo.",
            "end_chat": False
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}

@app.route('/needs_more_data', methods=['POST'])
@require_auth
def needs_more_data():
    """
    Endpoint for intake assistant with needs_more_data function
    """
    try:
        data = request.get_json()
        
        # Validate request data
        is_valid, error_msg = validate_request_data(data)
        if not is_valid:
            logger.warning(f"Invalid request data: {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        message = data['message']
        session_id = data['session_id']
        
        logger.info(f"Processing needs_more_data request for session {session_id}")
        
        # Call OpenAI assistant with needs_more_data function
        response, function_result = call_openai_assistant(
            assistant_id=ASSISTANT_INTAKE_ID,
            message=message,
            session_id=session_id,
            temperature=0.2,
            max_tokens=200,
            function_name='needs_more_data'
        )
        
        logger.info(f"Needs more data response generated for session {session_id}")
        
        # Build response with function call result
        response_data = {
            "reply": response,
            "end_chat": False
        }
        
        # Add function call result if available
        if function_result:
            response_data.update(function_result)
            # Ensure 'need' field is present
            if 'need' not in response_data:
                response_data['need'] = 'no'
            # Add back_to_intake flag if need="yes"
            if response_data.get('need') == 'yes':
                response_data['back_to_intake'] = True
        else:
            response_data['need'] = 'no'
        
        return jsonify(response_data), 200, {'Content-Type': 'application/json; charset=utf-8'}
        
    except OpenAIError as e:
        logger.error(f"OpenAI error in needs_more_data: {str(e)}")
        return jsonify({
            "reply": "Lo siento, hay un problema técnico. Por favor, inténtalo de nuevo.",
            "need": "no",
            "end_chat": False
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}
    
    except Exception as e:
        logger.error(f"Unexpected error in needs_more_data: {str(e)}")
        return jsonify({
            "reply": "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo.",
            "need": "no",
            "end_chat": False
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}

@app.route('/give_advice', methods=['POST'])
@require_auth
def give_advice():
    """
    Endpoint for advice assistant
    """
    try:
        data = request.get_json()
        
        # Validate request data
        is_valid, error_msg = validate_request_data(data)
        if not is_valid:
            logger.warning(f"Invalid request data: {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        message = data['message']
        session_id = data['session_id']
        
        logger.info(f"Processing give_advice request for session {session_id}")
        
        # Call OpenAI assistant with advice parameters
        response, function_result = call_openai_assistant(
            assistant_id=ASSISTANT_ADVICE_ID,
            message=message,
            session_id=session_id,
            temperature=0.7,
            max_tokens=250
        )
        
        logger.info(f"Advice response generated for session {session_id}")
        
        # Build response
        response_data = {
            "reply": response,
            "end_chat": False
        }
        
        # Check if assistant indicates need to go back to intake
        if function_result and function_result.get('need_intake'):
            response_data['back_to_intake'] = True
        
        return jsonify(response_data), 200, {'Content-Type': 'application/json; charset=utf-8'}
        
    except OpenAIError as e:
        logger.error(f"OpenAI error in give_advice: {str(e)}")
        return jsonify({
            "reply": "Lo siento, hay un problema técnico. Por favor, inténtalo de nuevo.",
            "end_chat": False
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}
    
    except Exception as e:
        logger.error(f"Unexpected error in give_advice: {str(e)}")
        return jsonify({
            "reply": "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo.",
            "end_chat": False
        }), 500, {'Content-Type': 'application/json; charset=utf-8'}

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors"""
    return jsonify({"error": "Forbidden"}), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

