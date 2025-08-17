import google.generativeai as genai
import openai
import json
import os
import re

def get_ai_suggestions(provider: str, api_key: str, user_prompt: str, questionnaire_structure: list, chat_history: list, model_name: str = None, proxy: str = None, base_url: str = None) -> dict:
    """
    Connects to the specified AI service and gets suggestions for questionnaire configuration.

    Args:
        provider: The AI service provider ('Gemini' or 'OpenAI').
        api_key: The user's API key for the selected service.
        user_prompt: The user's natural language prompt.
        questionnaire_structure: A list of dictionaries representing the questionnaire structure.
        chat_history: A list of previous user/assistant messages.
        model_name: The specific model to use (e.g., 'gemini-1.5-pro-latest').
        proxy: The proxy server to use for the request (e.g., 'http://127.0.0.1:7890').
        base_url: The base URL for the API endpoint (for LM Studio).

    Returns:
        A dictionary with the AI's suggestions, or an error message.
    """
    if not api_key:
        return {"error": "API Key is not configured."}
    if not user_prompt or not user_prompt.strip():
        return {"error": "User prompt is empty. Please enter a message."}

    # Construct a common prompt structure for the AI
    initial_system_prompt = f"""
    You are an intelligent assistant for a questionnaire filling application. Your goal is to help the user configure a questionnaire through interactive conversation.

    **Your Task Modes:**

    You have two response modes:
    1.  **Configuration Mode**: When you have enough information from the user's request and the conversation history to generate a complete and logical configuration for the questionnaire.
    2.  **Question Mode**: When the user's request is ambiguous, incomplete, or requires more details to proceed. In this mode, you MUST ask a clarifying question.

    **Response Format Rules (VERY IMPORTANT):**

    *   If you are in **Configuration Mode**, you MUST respond with ONLY a valid JSON array of configuration objects.
        Example: `[ {{"id": "q1", "topic_num": 1, "raw_weight_input": "1, 5, 1"}}, {{"id": "q2", "topic_num": 2, "raw_text_input": "John Doe||Jane Smith"}} ]`
        - Configuration fields: 'raw_weight_input' (for single choice), 'raw_prob_input' (for multiple choice), 'raw_text_input' (for text fields).

    *   If you are in **Question Mode**, you MUST respond with ONLY a valid JSON object containing a single key "question".
        Example: `{{"question": "How many names should I generate for the text fields?"}}`

    **Interaction Logic:**

    *   Analyze the user's latest request in the context of the entire `chat_history`.
    *   Examine the `questionnaire_structure` to understand what needs to be configured.
    *   **Default to asking questions.** Only provide a full configuration when you are confident you understand all requirements.
    *   If the user says "fill in the names", you should ask "how many names?" or "any specific type of names?".
    *   If the user provides a vague instruction like "make it reasonable", you should ask for clarification on what "reasonable" means for a specific question.

   **Global Configuration Rules:**

   *   **Use Integers for Probabilities**: For multiple-choice questions (`raw_prob_input`), you MUST use whole numbers (integers) between 0 and 100 for probabilities. Do NOT use decimals.
   *   **Zero Weight for "Other" Options**: If a question has an option that is "Other" and requires custom text input (identified by `is_other_specify: true` in the questionnaire structure), you MUST set the weight for that specific option to 0 in the `raw_weight_input`.

    **Provided Information:**

    1.  **Questionnaire Structure:**
        ```json
        {json.dumps(questionnaire_structure, indent=2, ensure_ascii=False)}
        ```
    """

    if provider.lower() == 'gemini':
        original_proxy = None # Initialize outside the try block
        try:
            # Configure the proxy by setting the environment variable
            original_proxy = os.environ.get('https_proxy')
            if proxy:
                os.environ['https_proxy'] = proxy
            
            genai.configure(api_key=api_key)

            # Use the provided model_name, or default to 'gemini-pro'
            model_to_use = model_name if model_name else 'gemini-pro'
            model = genai.GenerativeModel(model_to_use, system_instruction=initial_system_prompt)

            # Build and convert conversation history for Gemini
            gemini_history = []
            for message in chat_history:
                # Gemini uses 'model' for the assistant's role
                role = 'model' if message['role'] == 'assistant' else 'user'
                gemini_history.append({'role': role, 'parts': [message['content']]})

            # Add the latest user prompt to the history
            messages = gemini_history + [{'role': 'user', 'parts': [user_prompt]}]

            response = model.generate_content(messages, request_options={'timeout': 60}) # Add a 60-second timeout
            
            # Robust JSON extraction to find either a JSON object {} or array []
            cleaned_response = response.text.strip()
            # This regex looks for a string that starts with { or [ and ends with } or ]
            json_match = re.search(r'(\{.*\}|\[.*\])', cleaned_response, re.DOTALL)
            if not json_match:
                 # Fallback for markdown code blocks
                json_match = re.search(r'```json\s*(\{.*\}|\[.*\])\s*```', cleaned_response, re.DOTALL)
                if not json_match:
                    raise json.JSONDecodeError("No valid JSON object or array found in the AI response.", cleaned_response, 0)
                json_str = json_match.group(1)
            else:
                json_str = json_match.group(0)

            ai_output = json.loads(json_str)
            
            # Check if it's a question or a configuration
            if isinstance(ai_output, dict) and 'question' in ai_output:
                return {"success": True, "question": ai_output['question']}
            elif isinstance(ai_output, list):
                return {"success": True, "config": ai_output}
            else:
                raise json.JSONDecodeError("JSON is not in the expected format (question object or config array).", json_str, 0)
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse AI response as JSON. Raw response: {e.doc}"}
        except Exception as e:
            return {"error": f"An error occurred while communicating with the Gemini service: {e}"}
        finally:
            # Restore original proxy settings
            if original_proxy:
                os.environ['https_proxy'] = original_proxy
            elif 'https_proxy' in os.environ:
                del os.environ['https_proxy']

    elif provider.lower() == 'openai':
        try:
            # Configure the proxy if provided
            import httpx
            proxies = {"http://": proxy, "https://": proxy} if proxy else None
            
            client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url if base_url else None,
                http_client=httpx.Client(proxies=proxies),
                timeout=60
            )

            # Use the provided model_name, or default to 'gpt-3.5-turbo'
            model_to_use = model_name if model_name else 'gpt-3.5-turbo'

            # Build conversation history
            messages=[
                {"role": "system", "content": initial_system_prompt + "\n" + "You are a helpful assistant that provides JSON configurations."},
            ] + chat_history + [
                {"role": "user", "content": user_prompt}
            ]

            response = client.chat.completions.create(
                model=model_to_use,
                messages=messages,
            )
            response_content = response.choices[0].message.content
            
            # Robust JSON extraction for OpenAI as well
            # This regex looks for a string that starts with { or [ and ends with } or ]
            json_match = re.search(r'(\{.*\}|\[.*\])', response_content, re.DOTALL)
            if not json_match:
                raise json.JSONDecodeError("No valid JSON object or array found in the AI response.", response_content, 0)
            
            ai_output = json.loads(json_match.group(0))

            # Check if it's a question or a configuration
            if isinstance(ai_output, dict) and 'question' in ai_output:
                return {"success": True, "question": ai_output['question']}
            elif isinstance(ai_output, list):
                return {"success": True, "config": ai_output}
            else:
                raise json.JSONDecodeError("JSON is not in the expected format (question object or config array).", response_content, 0)
        except json.JSONDecodeError as e:
            return {"error": f"Failed to parse AI response as JSON. Raw response: {e.doc}"}
        except openai.APITimeoutError:
            return {"error": "网络请求超时。请检查您的AI代理设置或网络连接。"}
        except Exception as e:
            return {"error": f"An error occurred while communicating with the OpenAI service: {e}"}
    else:
        return {"error": f"Unsupported AI provider: {provider}"}
