from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple
import base64
import mimetypes
import os
import time
import requests
from http import HTTPStatus
import dashscope
from dashscope import ImageSynthesis
from ..utils import get_logger
from ..utils.endpoints import get_provider_base_url
from ..utils.media_refs import MEDIA_REF_UNKNOWN, classify_media_ref
from ..utils.oss_utils import OSSImageUploader
from ..utils.provider_media import resolve_media_input
from ..utils.provider_registry import resolve_provider_backend

logger = get_logger(__name__)


# Provider error codes that need an actionable explanation rather than the raw
# English message — these are account-side problems the user must fix in a
# console, and retrying will never help.
_ACTIONABLE_PROVIDER_ERRORS = (
    (
        "AllocationQuota.FreeTierOnly",
        "阿里云百炼免费额度已用完，且账号开启了「仅使用免费额度」模式。"
        "请前往百炼控制台 https://bailian.console.aliyun.com/ 充值，"
        "或关闭「仅使用免费额度」开关以转为按量付费。",
    ),
    (
        "AllocationQuota",
        "阿里云百炼额度不足。请前往百炼控制台 https://bailian.console.aliyun.com/ 充值后重试。",
    ),
    (
        "InvalidApiKey",
        "DASHSCOPE_API_KEY 无效或已失效。请在设置页重新填写。",
    ),
    (
        "Arrearage",
        "阿里云账号已欠费，模型调用被拒绝。请前往阿里云控制台结清欠款。",
    ),
    (
        "Throttling",
        "阿里云百炼调用频率超限，请稍后重试或降低并发。",
    ),
)


def explain_provider_error(status_code: int, body_text: str) -> str:
    """Turn a provider error body into an actionable, user-facing message.

    Falls back to the provider's own message when we have no specific advice,
    so nothing is ever swallowed.
    """
    code = ""
    message = ""
    try:
        import json as _json
        data = _json.loads(body_text) if body_text else {}
        if isinstance(data, dict):
            code = str(data.get("code") or "")
            message = str(data.get("message") or "")
    except (ValueError, TypeError):
        pass

    for prefix, hint in _ACTIONABLE_PROVIDER_ERRORS:
        if code.startswith(prefix):
            return f"{hint}（HTTP {status_code} {code}）"

    detail = message or (body_text or "")[:300]
    return f"HTTP {status_code}: {detail}" if detail else f"HTTP {status_code}"


def _post_with_connection_retry(url: str, *, max_retries: int = 4, **kwargs) -> requests.Response:
    """POST with exponential backoff on transient connection failures.

    The link to DashScope can be reset mid-TLS-handshake (WinError 10054); a
    single blip used to fail an entire character generation. Only
    ConnectionError is retried — not ReadTimeout, since a timeout may mean the
    request did reach the server and retrying would create a duplicate task.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            return requests.post(url, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                break
            wait = min(2 ** attempt * 2, 20)
            logger.warning(
                f"Connection error posting to {url} ({exc}); "
                f"retrying in {wait}s (attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(wait)
    raise last_exc


class ImageGenModel(ABC):
    """Abstract base class for image generation models."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def generate(self, prompt: str, output_path: str, **kwargs) -> Tuple[str, float]:
        """
        Generates an image from a prompt.
        
        Args:
            prompt: The input text prompt.
            output_path: The path to save the generated image.
            **kwargs: Additional arguments.
            
        Returns:
            A tuple containing:
            - The path to the generated image file.
            - The duration of the API generation process in seconds.
        """
        pass

class WanxImageModel(ImageGenModel):
    def __init__(self, config):
        super().__init__(config)
        self.params = config.get('params', {})

    @property
    def api_key(self):
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            logger.warning("Dashscope API Key not found in config or environment variables.")
        return api_key

    def generate(self, prompt: str, output_path: str, ref_image_path: str = None, ref_image_paths: list = None, model_name: str = None, **kwargs) -> Tuple[str, float]:
        # Determine model based on whether reference image is provided
        # Support both single path (legacy) and list of paths
        dashscope.api_key = self.api_key

        all_ref_paths = []
        if ref_image_path:
            all_ref_paths.append(ref_image_path)
        if ref_image_paths:
            all_ref_paths.extend(ref_image_paths)
            
        # Remove duplicates
        all_ref_paths = list(set(all_ref_paths))
        # Model selection priority: explicit model_name > config params > defaults
        if model_name:
            final_model_name = model_name
        elif all_ref_paths:
            # For I2I, use i2i_model_name if configured, otherwise default to wan2.7-image
            final_model_name = self.params.get('i2i_model_name', 'wan2.7-image')
        else:
            # For T2I, use model_name if configured, otherwise default to wan2.7-image-pro
            final_model_name = self.params.get('model_name', 'wan2.7-image-pro')

        if all_ref_paths:
            logger.info(f"Using I2I model: {final_model_name} with {len(all_ref_paths)} reference images")
        else:
            logger.info(f"Using T2I model: {final_model_name}")

        size = kwargs.pop('size', self.params.get('size', '1280*1280'))
        n = kwargs.pop('n', self.params.get('n', 1))
        negative_prompt = kwargs.pop('negative_prompt', None)
        # model_name is already handled above, remove from kwargs if present
        kwargs.pop('model_name', None)
        
        # Determine reference image limit based on model
        if final_model_name.startswith('wan2.7-image') or final_model_name.startswith('qwen-image'):
            ref_limit = 9
        elif final_model_name == 'wan2.6-image':
            ref_limit = 4
        else:
            ref_limit = 3
        if len(all_ref_paths) > ref_limit:
            logger.warning(f"Limiting reference images from {len(all_ref_paths)} to {ref_limit} for model {final_model_name}")
            all_ref_paths = all_ref_paths[:ref_limit]
        
        logger.info(f"Starting image generation...")
        logger.info(f"Prompt: {prompt}")
        logger.info(f"Model: {final_model_name}, Size: {size}, N: {n}")

        try:
            api_start_time = time.time()
            # Use HTTP API for wan2.6+ models and qwen-image models
            if final_model_name == 'wan2.6-t2i':
                image_url = self._generate_wan26_http(prompt, size, n, negative_prompt)
            elif final_model_name == 'wan2.6-image':
                # wan2.6-image for I2I (requires reference images)
                image_url = self._generate_wan26_image_http(prompt, size, n, negative_prompt, all_ref_paths)
            elif final_model_name.startswith('qwen-image'):
                # qwen-image is served synchronously from a different endpoint
                # than wan2.7-image — see _generate_qwen_image_sync.
                image_url = self._generate_qwen_image_sync(
                    prompt=prompt,
                    model_name=final_model_name,
                    size=size,
                    n=n,
                    negative_prompt=negative_prompt,
                    ref_image_paths=all_ref_paths,
                    seed=kwargs.pop('seed', None),
                    prompt_extend=kwargs.pop('prompt_extend', True),
                    watermark=kwargs.pop('watermark', False),
                )
            elif final_model_name.startswith('wan2.7-image'):
                # Wan2.7-image via DashScope async HTTP API
                image_url = self._generate_dashscope_image_http(
                    prompt=prompt,
                    model_name=final_model_name,
                    size=size,
                    n=n,
                    negative_prompt=negative_prompt,
                    ref_image_paths=all_ref_paths,
                    seed=kwargs.pop('seed', None),
                    prompt_extend=kwargs.pop('prompt_extend', True),
                    watermark=kwargs.pop('watermark', False),
                )
            else:
                # Use SDK for other models
                image_url = self._generate_sdk(prompt, final_model_name, size, n, negative_prompt, all_ref_paths,
                                               kwargs)

            api_end_time = time.time()
            api_duration = api_end_time - api_start_time

            logger.info(f"Generation success. Image URL: {image_url}")
            logger.info(f"API duration: {api_duration:.2f}s")
            
            # Download image
            self._download_image(image_url, output_path)
            return output_path, api_duration

        except Exception as e:
            import traceback
            logger.error(f"Error during generation: {e}")
            logger.error(traceback.format_exc())
            raise

    def _build_image_payload(
        self,
        *,
        prompt: str,
        model_name: str,
        size: str,
        n: int,
        negative_prompt: str = None,
        ref_image_paths: list = None,
        seed: int = None,
        prompt_extend: bool = True,
        watermark: bool = False,
    ) -> Dict[str, Any]:
        """Build the shared multimodal request body.

        wan2.7-image and qwen-image take an identical payload; only the endpoint
        and the sync/async transport differ between them.
        """
        content = []
        if ref_image_paths:
            for path in ref_image_paths[:9]:
                image_input = self._resolve_wan26_reference_image(path, model_name=model_name)
                if image_input:
                    content.append({"image": image_input})
        content.append({"text": prompt})

        payload = {
            "model": model_name,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            },
            "parameters": {
                "prompt_extend": prompt_extend,
                "watermark": watermark,
                "n": n,
                "size": size,
            },
        }

        if negative_prompt:
            payload["parameters"]["negative_prompt"] = negative_prompt
        if seed:
            payload["parameters"]["seed"] = seed

        return payload

    def _generate_qwen_image_sync(
        self,
        prompt: str,
        model_name: str,
        size: str = "1280*1280",
        n: int = 1,
        negative_prompt: str = None,
        ref_image_paths: list = None,
        seed: int = None,
        prompt_extend: bool = True,
        watermark: bool = False,
    ) -> str:
        """Generate an image with the qwen-image family.

        Unlike wan2.7-image, qwen-image is served from multimodal-generation and
        rejects the async header ("current user api does not support asynchronous
        calls"); calling it on the async image-generation endpoint fails with
        "url error". It answers synchronously with the image URL, so there is no
        task to poll. Verified against the live API on 2026-08-01.
        """
        base = get_provider_base_url("DASHSCOPE")
        create_url = f"{base}/api/v1/services/aigc/multimodal-generation/generation"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = self._build_image_payload(
            prompt=prompt,
            model_name=model_name,
            size=size,
            n=n,
            negative_prompt=negative_prompt,
            ref_image_paths=ref_image_paths,
            seed=seed,
            prompt_extend=prompt_extend,
            watermark=watermark,
        )

        logger.info(f"Calling {model_name} HTTP API (sync)...")
        # Image synthesis takes tens of seconds and returns in one shot, so the
        # read timeout has to cover the whole generation, not just a handshake.
        response = _post_with_connection_retry(
            create_url, headers=headers, json=payload, timeout=300
        )

        logger.info(f"Sync generation response status: {response.status_code}")
        if response.status_code != 200:
            raise RuntimeError(
                f"{model_name} 调用失败 — {explain_provider_error(response.status_code, response.text)}"
            )

        result = response.json()
        choices = result.get("output", {}).get("choices", [])
        if not choices:
            raise RuntimeError(f"No choices in {model_name} response: {result}")

        for item in choices[0].get("message", {}).get("content", []):
            if isinstance(item, dict) and item.get("image"):
                return item["image"]

        raise RuntimeError(f"No image in {model_name} response: {result}")

    def _generate_dashscope_image_http(
        self,
        prompt: str,
        model_name: str,
        size: str = "1280*1280",
        n: int = 1,
        negative_prompt: str = None,
        ref_image_paths: list = None,
        seed: int = None,
        prompt_extend: bool = True,
        watermark: bool = False,
    ) -> str:
        """Generate image using Wan2.7-image / Qwen-image via DashScope async HTTP API."""
        base = get_provider_base_url("DASHSCOPE")
        create_url = f"{base}/api/v1/services/aigc/image-generation/generation"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-DashScope-Async": "enable",
        }

        payload = self._build_image_payload(
            prompt=prompt,
            model_name=model_name,
            size=size,
            n=n,
            negative_prompt=negative_prompt,
            ref_image_paths=ref_image_paths,
            seed=seed,
            prompt_extend=prompt_extend,
            watermark=watermark,
        )

        logger.info(f"Calling {model_name} HTTP API (async)...")
        logger.info(f"Payload: {payload}")

        # Step 1: Create task
        response = _post_with_connection_retry(create_url, headers=headers, json=payload, timeout=120)

        logger.info(f"Create task response status: {response.status_code}")
        logger.info(f"Create task response body: {response.text[:500]}")

        if response.status_code != 200:
            raise RuntimeError(
                f"{model_name} 调用失败 — {explain_provider_error(response.status_code, response.text)}"
            )

        result = response.json()
        task_id = result.get('output', {}).get('task_id')
        if not task_id:
            raise RuntimeError(f"No task_id in response: {result}")

        logger.info(f"Task created: {task_id}")

        # Step 2: Poll for task completion
        poll_url = f"{base}/api/v1/tasks/{task_id}"
        poll_headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        max_wait_time = 600
        poll_interval = 10
        elapsed = 0

        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval

            # The task is already created and billed, so a dropped connection
            # must not discard it — keep polling until max_wait_time.
            try:
                poll_response = requests.get(poll_url, headers=poll_headers, timeout=30)
            except requests.RequestException as exc:
                logger.warning(f"Poll request failed ({exc}); retrying (task {task_id})")
                continue

            if poll_response.status_code != 200:
                logger.warning(f"Poll request failed: {poll_response.status_code}")
                continue

            poll_result = poll_response.json()
            task_status = poll_result.get('output', {}).get('task_status')

            logger.info(f"Task {task_id} status: {task_status} (elapsed: {elapsed}s)")

            if task_status == 'SUCCEEDED':
                choices = poll_result.get('output', {}).get('choices', [])
                if not choices:
                    raise RuntimeError(f"No choices in completed task: {poll_result}")

                first_choice = choices[0]
                content = first_choice.get('message', {}).get('content', [])
                if not content:
                    raise RuntimeError(f"No content in choice: {first_choice}")

                image_url = content[0].get('image')
                if not image_url:
                    raise RuntimeError(f"No image URL in content: {content}")

                logger.info(f"Task completed. Image URL: {image_url}")
                return image_url

            elif task_status == 'FAILED':
                error_msg = (
                    poll_result.get('output', {}).get('message', '') or
                    poll_result.get('output', {}).get('code', '') or
                    poll_result.get('message', '') or
                    poll_result.get('code', '') or
                    'Unknown error'
                )
                raise RuntimeError(f"{model_name} task failed: {error_msg}")

            elif task_status in ['CANCELED', 'UNKNOWN']:
                raise RuntimeError(f"{model_name} task {task_status}: {poll_result}")

        raise RuntimeError(f"{model_name} task timed out after {max_wait_time}s")

    def _generate_wan26_http(self, prompt: str, size: str, n: int, negative_prompt: str = None) -> str:
        """Generate image using Wan 2.6 T2I via HTTP API (synchronous)."""
        base = get_provider_base_url("DASHSCOPE")
        url = f"{base}/api/v1/services/aigc/multimodal-generation/generation"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": "wan2.6-t2i",
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            },
            "parameters": {
                "prompt_extend": False,  # Disable auto prompt rewriting for consistency
                "watermark": False,
                "n": n,
                "size": size
            }
        }
        
        # Add negative_prompt if provided
        if negative_prompt:
            payload["parameters"]["negative_prompt"] = negative_prompt
        
        logger.info(f"Calling Wan 2.6 T2I HTTP API...")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=300)  # 5 minutes for slow API responses
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text[:500]}...")
        
        if response.status_code != 200:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get('message', response.text)
            raise RuntimeError(f"Wan 2.6 API failed: {error_msg}")
        
        result = response.json()
        
        # Extract image URL from response
        # Response format: output.choices[].message.content[].image
        choices = result.get('output', {}).get('choices', [])
        if not choices:
            raise RuntimeError(f"No choices in response: {result}")
        
        # Get first image from first choice
        first_choice = choices[0]
        content = first_choice.get('message', {}).get('content', [])
        if not content:
            raise RuntimeError(f"No content in choice: {first_choice}")
        
        image_url = content[0].get('image')
        if not image_url:
            raise RuntimeError(f"No image URL in content: {content}")
        
        return image_url

    def _generate_wan26_image_http(self, prompt: str, size: str, n: int, negative_prompt: str = None, ref_image_paths: list = None) -> str:
        """Generate image using Wan 2.6 Image via HTTP API (asynchronous with polling)."""
        base = get_provider_base_url("DASHSCOPE")
        create_url = f"{base}/api/v1/services/aigc/image-generation/generation"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-DashScope-Async": "enable"  # Required for async mode
        }
        
        # Build content array with reference images and prompt text
        content = []
        
        # Add reference images (upload to OSS first if local paths)
        if ref_image_paths:
            # Limit is already handled in generate(), but we keep a safety slice here
            # This method is specifically for wan2.6-image which supports 4 images
            ref_limit = 4
            for path in ref_image_paths[:ref_limit]:
                image_input = self._resolve_wan26_reference_image(path)
                if image_input:
                    content.append({"image": image_input})

        if ref_image_paths and not content:
            raise RuntimeError(
                "Wan 2.6 Image requires at least one usable reference image. "
                "Please provide a valid local image, public URL, or configure OSS."
            )

        content.append({"text": prompt})
        
        payload = {
            "model": "wan2.6-image",
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ]
            },
            "parameters": {
                "prompt_extend": False,  # Disable auto prompt rewriting for consistency
                "watermark": False,
                "n": n,
                "size": size,
                "enable_interleave": False  # Image editing mode (I2I)
            }
        }
        
        # Add negative_prompt if provided
        if negative_prompt:
            payload["parameters"]["negative_prompt"] = negative_prompt
        
        logger.info(f"Calling Wan 2.6 Image HTTP API (async)...")
        logger.info(f"Payload: {payload}")
        
        # Step 1: Create task
        response = _post_with_connection_retry(create_url, headers=headers, json=payload, timeout=120)  # 2 minutes for task creation
        
        logger.info(f"Create task response status: {response.status_code}")
        logger.info(f"Create task response body: {response.text[:500]}")
        
        if response.status_code != 200:
            raise RuntimeError(
                f"Wan 2.6 Image 调用失败 — {explain_provider_error(response.status_code, response.text)}"
            )
        
        result = response.json()
        task_id = result.get('output', {}).get('task_id')
        if not task_id:
            raise RuntimeError(f"No task_id in response: {result}")
        
        logger.info(f"Task created: {task_id}")
        
        # Step 2: Poll for task completion
        poll_url = f"{base}/api/v1/tasks/{task_id}"
        poll_headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        max_wait_time = 600  # 10 minutes max wait (I2I can take longer)
        poll_interval = 10   # Poll every 10 seconds
        elapsed = 0
        
        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval
            
            poll_response = requests.get(poll_url, headers=poll_headers, timeout=30)
            
            if poll_response.status_code != 200:
                logger.warning(f"Poll request failed: {poll_response.status_code}")
                continue
            
            poll_result = poll_response.json()
            task_status = poll_result.get('output', {}).get('task_status')
            
            logger.info(f"Task {task_id} status: {task_status} (elapsed: {elapsed}s)")
            
            if task_status == 'SUCCEEDED':
                # Extract image URL from choices
                choices = poll_result.get('output', {}).get('choices', [])
                if not choices:
                    raise RuntimeError(f"No choices in completed task: {poll_result}")
                
                first_choice = choices[0]
                content = first_choice.get('message', {}).get('content', [])
                if not content:
                    raise RuntimeError(f"No content in choice: {first_choice}")
                
                image_url = content[0].get('image')
                if not image_url:
                    raise RuntimeError(f"No image URL in content: {content}")
                
                logger.info(f"Task completed. Image URL: {image_url}")
                return image_url
            
            elif task_status == 'FAILED':
                # Log full response for debugging
                logger.error(f"Task {task_id} failed. Full response: {poll_result}")
                
                # Try to extract error message from various possible fields
                error_msg = (
                    poll_result.get('output', {}).get('message', '') or
                    poll_result.get('output', {}).get('code', '') or
                    poll_result.get('message', '') or
                    poll_result.get('code', '') or
                    'Unknown error - check logs for full response'
                )
                
                raise RuntimeError(f"Wan 2.6 Image task failed: {error_msg}")

            
            elif task_status in ['CANCELED', 'UNKNOWN']:
                raise RuntimeError(f"Wan 2.6 Image task {task_status}: {poll_result}")
            
            # PENDING or RUNNING - continue polling
        
        raise RuntimeError(f"Wan 2.6 Image task timed out after {max_wait_time}s")

    def _resolve_wan26_reference_image(self, path: str, model_name: str = "wan2.6-image") -> str:
        uploader = OSSImageUploader()
        backend = self._resolve_provider_backend_for_model(model_name)

        try:
            resolved = resolve_media_input(
                path,
                model_name=model_name,
                modality="image",
                backend=backend,
                uploader=uploader,
            )
            return resolved.value
        except ValueError as e:
            ref_type = classify_media_ref(path)
            if ref_type == MEDIA_REF_UNKNOWN and os.path.isabs(path) and os.path.exists(path):
                # Compatibility fallback: only for legacy absolute local paths
                # outside managed `output/` media refs.
                if uploader.is_configured:
                    object_key = uploader.upload_file(path, sub_path="temp/ref_images")
                    if object_key:
                        signed_url = uploader.sign_url_for_api(object_key)
                        if signed_url:
                            return signed_url

                return self._encode_local_image_as_data_uri(path)

            logger.warning(f"Reference image could not be resolved: {path}, reason: {e}")
            return None

    def _resolve_provider_backend_for_model(self, model_name: str) -> str:
        try:
            return resolve_provider_backend(model_name)
        except (KeyError, ValueError):
            # Keep image flows resilient for models not yet registered.
            return "dashscope"
        except Exception as e:
            logger.warning(
                f"Unexpected error resolving provider backend for model {model_name}: {e}. "
                "Falling back to dashscope."
            )
            return "dashscope"

    def _encode_local_image_as_data_uri(self, path: str) -> str:
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = "image/png"

        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")

        return f"data:{mime_type};base64,{encoded}"

    def _generate_sdk(self, prompt: str, model_name: str, size: str, n: int, negative_prompt: str, all_ref_paths: list, kwargs: dict) -> str:
        """Generate image using Dashscope SDK (for older models)."""
        call_args = {
            "model": model_name,
            "prompt": prompt,
            "n": n,
            "size": size,
        }
        
        # Add negative_prompt if provided
        if negative_prompt:
            call_args["negative_prompt"] = negative_prompt
        
        # Add remaining kwargs
        call_args.update(kwargs)
        
        logger.info(f"SDK call_args: {dict((k, v) for k, v in call_args.items() if k != 'images')}")
        # Model selection priority: explicit model_name > config params > defaults

        # Handle Reference Images for I2I
        if all_ref_paths:
            ref_image_urls = []
            uploader = OSSImageUploader()
            for path in all_ref_paths:
                if os.path.exists(path):
                    # Upload to OSS and get signed URL
                    if uploader.is_configured:
                        object_key = uploader.upload_file(path, sub_path="temp/ref_images")
                        if object_key:
                            signed_url = uploader.sign_url_for_api(object_key)
                            ref_image_urls.append(signed_url)
                            logger.info(f"Reference image uploaded, signed URL: {signed_url[:80]}...")
                        else:
                            raise RuntimeError(f"Failed to upload reference image to OSS: {path}")
                    else:
                        logger.warning(f"OSS not configured, cannot upload reference image: {path}")
                elif path.startswith("http"):
                    # Already a URL
                    ref_image_urls.append(path)
                else:
                    # Check if it's an OSS Object Key using the utility function
                    from ..utils.oss_utils import is_object_key
                    if is_object_key(path):
                        if uploader.is_configured:
                            signed_url = uploader.sign_url_for_api(path)
                            ref_image_urls.append(signed_url)
                            logger.info(f"Reference image (Object Key), signed URL: {signed_url[:80]}...")
                        else:
                            raise ValueError(f"OSS not configured but Object Key provided: {path}")
                    else:
                        raise ValueError(f"Reference image not found: {path}")
            
            logger.info(f"DEBUG: ref_image_urls count: {len(ref_image_urls)}")
            
            # Limit is already handled in generate(), but we keep a safety slice here
            ref_limit = 4 if model_name == 'wan2.6-image' else 3
            if len(ref_image_urls) > ref_limit:
                logger.warning(f"Limiting reference images from {len(ref_image_urls)} to {ref_limit}")
                ref_image_urls = ref_image_urls[:ref_limit]
            
            call_args['images'] = ref_image_urls

        # Call Dashscope SDK
        rsp = ImageSynthesis.call(**call_args)
        
        logger.info(f"SDK response: {rsp}")

        if rsp.status_code != HTTPStatus.OK:
            logger.error(f"Task failed with status code: {rsp.status_code}, code: {rsp.code}, message: {rsp.message}")
            raise RuntimeError(f"Task failed: {rsp.message}")

        # Extract Image URL
        if hasattr(rsp, 'output'):
            logger.info(f"Response Output: {rsp.output}")
            results = rsp.output.get('results')
            url = rsp.output.get('url')
            
            if results and len(results) > 0:
                 first_result = results[0]
                 if isinstance(first_result, dict):
                     image_url = first_result.get('url')
                 else:
                     image_url = getattr(first_result, 'url', None)
            elif url:
                 image_url = url
            else:
                 logger.error(f"Unexpected response structure. Output: {rsp.output}")
                 raise RuntimeError("Could not find image URL in response.")
        else:
             logger.error(f"Response has no output. Response: {rsp}")
             raise RuntimeError("Response has no output.")
        
        return image_url

    def _download_image(self, url: str, output_path: str):
        logger.info(f"Downloading image to {output_path}...")
        
        # Setup retry strategy
        from requests.adapters import HTTPAdapter
        from requests.packages.urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        http = requests.Session()
        http.mount("https://", adapter)
        http.mount("http://", adapter)

        temp_path = output_path + ".tmp"
        try:
            response = http.get(url, stream=True, timeout=60, verify=False) # verify=False to avoid some SSL issues
            response.raise_for_status()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Atomic replace. os.rename raises FileExistsError on Windows when the
            # target exists, which breaks any regeneration into a path already on disk.
            os.replace(temp_path, output_path)
            logger.info("Download complete.")
            
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise


# ---------------------------------------------------------------------------
# Provider routing for image generation
# ---------------------------------------------------------------------------

# Adapters are stateless and cheap to keep around, so one instance per provider
# is shared across the asset / storyboard / playground call sites.
_IMAGE_ADAPTER_CACHE: Dict[str, ImageGenModel] = {}


def _image_provider_for(model_name: str) -> str:
    """Which provider serves this image model id, or '' for the default one."""
    name = (model_name or "").strip().lower()
    if not name:
        return ""
    if name.startswith("gemini-"):
        return "gemini"
    # Imported lazily: src.models.vidu imports ImageGenModel from this module.
    from .vidu import is_vidu_image_model
    if is_vidu_image_model(name):
        return "vidu"
    return ""


def resolve_image_adapter(model_name: str, default_adapter: ImageGenModel = None) -> ImageGenModel:
    """Route a catalog image model id to the adapter that can actually run it.

    Every image entry point (assets, storyboard, playground) shares this so a
    new image provider is one branch here instead of one branch per call site.
    Anything unrecognized falls through to ``default_adapter`` (DashScope/Wanx),
    preserving the previous behavior for wan / qwen-image ids.

    Gemini is routed by prefix rather than made the default: wan / qwen-image
    have not migrated yet and existing projects still reference them, so
    swapping the default would send those requests to the wrong provider.
    That swap belongs to the step that deletes the wan family.
    """
    provider = _image_provider_for(model_name)
    if not provider:
        return default_adapter

    cached = _IMAGE_ADAPTER_CACHE.get(provider)
    if cached is not None:
        return cached

    if provider == "gemini":
        from .gemini_image import GeminiImageModel
        cached = GeminiImageModel({})
    elif provider == "vidu":
        from .vidu import ViduImageModel
        cached = ViduImageModel({})
    else:  # pragma: no cover - _image_provider_for returns "", "gemini" or "vidu"
        return default_adapter

    _IMAGE_ADAPTER_CACHE[provider] = cached
    return cached
