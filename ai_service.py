import google.generativeai as genai
import openai
import json
import os
import re
import requests

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
    if not api_key and not (provider.lower() == 'openai' and base_url):
        return {"error": "API Key is not configured."}
    if not user_prompt or not user_prompt.strip():
        return {"error": "User prompt is empty. Please enter a message."}

    # Construct a common prompt structure for the AI
    initial_system_prompt = f"""
    You are a sophisticated AI assistant for a questionnaire filling application, specializing in simulating large-scale survey data. Your primary goal is to generate configurations that reflect the responses of a large, diverse population (e.g., thousands of participants), not just a single individual.

    **Core Persona: The Data Simulator**

    Instead of acting as a single respondent, you must adopt the persona of a data simulator. This means your configurations for weights, probabilities, and text answers should represent a statistical distribution that would be expected from a large user base.

    **Your Task Modes:**

    You have two response modes:
    1.  **Configuration Mode**: When you have enough information to generate a statistically representative configuration for the entire questionnaire.
    2.  **Question Mode**: When the user's request is ambiguous or lacks the necessary detail to create a meaningful population-level simulation. In this mode, you MUST ask a clarifying question.

    **Response Format Rules (VERY IMPORTANT):**

    *   If you are in **Configuration Mode**, you MUST respond with ONLY a valid JSON array of configuration objects. Your response MUST NOT include any explanatory text, greetings, or any characters outside of the JSON structure itself.
        Example: `[ {{"id": "q1", "topic_num": 1, "raw_weight_input": "1, 5, 1"}}, {{"id": "q2", "topic_num": 2, "raw_text_input": "John Doe||Jane Smith"}} ]`
        - Configuration fields: 'raw_weight_input' (for single choice), 'raw_prob_input' (for multiple choice), 'raw_text_input' (for text fields).

    *   If you are in **Question Mode**, you MUST respond with ONLY a valid JSON object containing a single key "question". Your response MUST NOT include any explanatory text, greetings, or any characters outside of the JSON structure itself.
        Example: `{{"question": "How many names should I generate for the text fields?"}}`

    **Interaction Logic & Data Simulation Principles:**

    *   **Analyze the user's request, `chat_history`, and `questionnaire_structure` to understand the survey's context and target audience.**
    *   **Think like a sociologist or market researcher.** Before generating a configuration, establish a plausible "group persona" or demographic model. For example, if the survey is about university life, the persona would be "thousands of university students with diverse backgrounds and opinions."
    *   **Handle Large Quantities:** If the user requests a large number of responses (e.g., "1000份"), this is your cue to generate highly diverse and statistically distributed answers. For text questions, this means providing a wide variety of distinct answers (e.g., 20+ different text snippets separated by '||'). For choice questions, the weights should reflect a realistic population distribution.
    *   **Default to asking questions.** If the user's request is vague (e.g., "make it reasonable"), you must ask for clarification in the context of a large-scale simulation. For example: "To make the results for 1000 participants reasonable, what kind of demographic distribution should I assume? For instance, what's the approximate ratio of male to female respondents?"
    *   **Text Answer Diversity is Key:** For any text input field, you are required to generate a rich set of varied answers. Do not provide just one or a few. The goal is to simulate the creativity and diversity of a large crowd.

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

            generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
            response = model.generate_content(messages, generation_config=generation_config, request_options={'timeout': 60}) # Add a 60-second timeout
            
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
            
            final_base_url = base_url
            if base_url and "localhost" in base_url and not base_url.endswith("/v1"):
                final_base_url = f"{base_url.rstrip('/')}/v1"

            client = openai.OpenAI(
                api_key=api_key,
                base_url=final_base_url if final_base_url else None,
                http_client=httpx.Client(proxies=proxies),
                timeout=120
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
                response_format={"type": "json_object"},
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
    elif provider.lower() == 'openrouter':
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": model_name if model_name else "anthropic/claude-3-sonnet",
                "messages": chat_history + [{"role": "user", "content": user_prompt}]
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data,
                proxies={"http": proxy, "https": proxy} if proxy else None,
                timeout=60
            )
            response.raise_for_status()
            
            ai_output = response.json()
            response_content = ai_output.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Robust JSON extraction
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
        except requests.exceptions.Timeout:
            return {"error": "网络请求超时。请检查您的AI代理设置或网络连接。"}
        except Exception as e:
            return {"error": f"An error occurred while communicating with the OpenRouter service: {e}"}
    else:
        return {"error": f"Unsupported AI provider: {provider}"}
