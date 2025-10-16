#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate MCQs from a PDF using OpenAI, with strict JSON output.
- Extracts text from a PDF
- Calls OpenAI with stricter "JSON-only" guidelines
- Logs every step
- Saves one combined JSON file
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, List, Literal

import pdfplumber
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from openai import OpenAI
from openai.types.responses import Response
from dotenv import load_dotenv, find_dotenv

# Language constants
LANG_EN = ("en", "english", "en-us", "en-gb")
LANG_HE = ("he", "hebrew", "iw", "he-il")

def normalize_language(raw: str | None) -> Literal["en", "he"]:
    """Normalize language input to standard values."""
    v = (raw or "").strip().lower()
    if v in LANG_HE:
        return "he"
    return "en"

def clamp_num_questions(raw, default=6, low=1, high=20):
    """Clamp number of questions to valid range."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(low, min(high, n))

def resolve_token_path():
    """Resolve token path for Cloud Run vs local dev."""
    from pathlib import Path
    cloud = Path("/secrets/token.pkl")
    return str(cloud) if cloud.exists() else "token.pkl"

def build_language_instructions(lang: Literal["en","he"]) -> str:
    """Build language-specific instructions for the AI prompt."""
    if lang == "he":
        return ("השאלות, אפשרויות הבחירה וההסברים חייבים להיות בעברית תקינה. "
                "שמור על RTL וסימני פיסוק.")
    return "All questions, choices, and explanations must be in clear English."

def call_openai_generate_diagnostic(client, model, messages):
    """Call OpenAI with comprehensive diagnostics and error handling."""
    print(json.dumps({
        "evt": "openai.call.start",
        "model": model,
        "key_present": bool(os.getenv("OPENAI_API_KEY")),
    }), flush=True)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            timeout=120,  # keep under Cloud Run timeout
        )
        print(json.dumps({"evt": "openai.call.ok"}), flush=True)
        return resp
    except Exception as e:
        print(json.dumps({
            "evt": "openai.call.error",
            "type": type(e).__name__,
            "msg": str(e),
        }), flush=True)
        traceback.print_exc()
        raise

def build_prompts_from_inputs(text_chunk: str, language: str, num_questions: int):
    """Build OpenAI messages with proper language handling."""
    lang = normalize_language(language)
    lang_instr = build_language_instructions(lang)
    # Ensure we never exceed requested count
    system_prompt = (
        f"You generate multiple-choice questions from provided text.\n"
        f"{lang_instr}\n"
        f"Return EXACTLY {num_questions} questions unless the content cannot support that many; never exceed {num_questions}."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text_chunk},
    ]
    return messages


def setup_logging(verbosity: int = 1):
    level = logging.INFO if verbosity == 1 else logging.DEBUG if verbosity == 2 else logging.ERROR
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def extract_text_from_pdf(pdf_path: str) -> str:
    logging.info(f"Opening PDF: {pdf_path}")
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages_text: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        logging.info(f"PDF has {len(pdf.pages)} pages. Extracting text...")
        for i, page in enumerate(pdf.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as e:
                logging.exception(f"Failed to extract text from page {i}: {e}")
                page_text = ""
            pages_text.append(f"\n\n===== PAGE {i} START =====\n{page_text}\n===== PAGE {i} END =====")

    full_text = "\n".join(pages_text).strip()
    logging.info(f"Extraction complete. Characters extracted: {len(full_text)}")
    return full_text




def build_user_prompt(pdf_text: str, num_questions: int, language: str = 'en') -> str:
    # Use the new language normalization
    lang = normalize_language(language)
    lang_instructions = build_language_instructions(lang)
    
    schema_instruction = f"""
You are generating professional monthly mission **medical multiple-choice questions (MCQs)** from input text.
Audience: trained medics. Content must be accurate, unambiguous, and operationally useful.
Try to refer any single key takeaway from the text.

{lang_instructions}

Return **ONLY** a single JSON object that **exactly** matches this schema (no markdown, no code fences, no extra keys):

{{
  "source_summary": "string, ≤ 400 chars concise summary of the key takeaways the questions are based on",
  "questions": [
    {{
      "id": "string, unique like Q1, Q2 ...",
      "topic": "string, short (e.g., 'Air Evacuation', 'Vascular Access', 'Heat Injury', 'Airway/Neck Trauma')",
      "difficulty": "string, one of ['basic','intermediate','advanced']",
      "stem": "string, the question stem in one paragraph, ≤ 320 chars, no line breaks",
      "options": [
        {{"label":"A","text":"string, plausible distractor or correct answer"}},
        {{"label":"B","text":"string"}},
        {{"label":"C","text":"string"}},
        {{"label":"D","text":"string"}}
      ],
      "answer": {{"label": "one of ['A','B','C','D']", "text": "string that exactly matches the chosen option text"}},
      "rationale": "string, ≤ 300 chars, why the correct answer is correct and why others are not appropriate in this context",
      "operational_note": "string, ≤ 200 chars, practical field note (if applicable), else empty string",
      "safety_flags": ["array of short strings for safety-critical cues present in the question, can be empty"]
    }}
  ]
}}

Hard constraints:
- Produce **exactly {num_questions}** questions in "questions".
- Use **clear, field-proven guidance** from the text; **do not invent** protocols.
- No references/citations or page numbers in the JSON.
- **Do not** include any text before or after the JSON.
- **Do not** include code fences, markdown, or comments.

Content guardrails:
- Prefer single-best-answer MCQs.
- Options must be mutually exclusive and collectively plausible.
- Avoid ambiguous wording, double negatives, or local jargon without context.
- Avoid exposing the answer in the question or the options.
- Do not include sensitive PII.

Here is the source text to base your questions on:
---
{pdf_text}
---
"""
    return schema_instruction


def init_openai_client() -> OpenAI:
    logging.info("Initializing OpenAI client...")
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY is not set.")
    try:
        client = OpenAI()
        logging.info("OpenAI client initialized.")
        return client
    except Exception as e:
        logging.exception("Failed to initialize OpenAI client.")
        raise e


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
)
def call_openai_generate(
    client: OpenAI,
    model: str,
    user_prompt: str,
) -> Dict[str, Any]:
    logging.info(f"Calling OpenAI model: {model}")
    text = None

    # 1) Try Responses API with JSON response_format (newer SDKs)
    try:
        resp: Response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
        )
        try:
            text = resp.output_text
        except Exception:
            # Fallback extraction if SDK shape differs
            text = resp.choices[0].message.content  # type: ignore[attr-defined]
        logging.debug("Received text via Responses API.")
    except TypeError as e:
        logging.warning(f"Responses API not available or incompatible: {e}")
    except Exception as e:
        logging.warning(f"Responses API call failed: {e}")

    # 2) If not available, try Chat Completions with response_format (mid SDKs)
    if text is None:
        try:
            resp_cc = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_prompt}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            text = resp_cc.choices[0].message.content
            logging.debug("Received text via Chat Completions (JSON response_format).")
        except TypeError as e:
            logging.warning(f"chat.completions response_format not supported: {e}")
        except Exception as e:
            logging.warning(f"chat.completions with response_format failed: {e}")

    # 3) Last resort: Chat Completions without response_format; rely on strict prompt
    if text is None:
        resp_cc2 = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0,
        )
        text = resp_cc2.choices[0].message.content
        logging.debug("Received text via Chat Completions (no response_format).")

    try:
        data = json.loads(text)
        logging.info("Parsed JSON from model successfully.")
    except json.JSONDecodeError as e:
        logging.error("Model did not return valid JSON. Saving raw text for inspection.")
        data = {"_raw_text": text, "_error": "json_decode_failed", "_exception": str(e)}

    return data

def generate_mcqs_to_file(pdf_path: str, output_dir: str, model: str, num_questions: int, language: str = 'en') -> str:
    """Generate MCQs from a PDF and write one combined JSON. Returns the JSON path."""
    # Normalize inputs
    lang = normalize_language(language)
    num_questions = clamp_num_questions(num_questions)
    
    logging.info(f"Generating MCQs (library mode)… Language: {lang}, Questions: {num_questions}")
    
    # Ensure output_dir is in /tmp for Cloud Run
    if not output_dir.startswith('/tmp'):
        output_dir = os.path.join('/tmp', os.path.basename(output_dir))
        os.makedirs(output_dir, exist_ok=True)
    
    text = extract_text_from_pdf(pdf_path)
    
    # Use the existing build_user_prompt function for now
    user_prompt = build_user_prompt(text, num_questions, lang)
    messages = [{"role": "user", "content": user_prompt}]
    
    # Check OpenAI key
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set at runtime.")
    
    client = init_openai_client()
    resp = call_openai_generate_diagnostic(client, model, messages)
    
    # Extract content from response
    if hasattr(resp, 'choices') and resp.choices:
        text_content = resp.choices[0].message.content
        logging.info(f"Raw OpenAI response length: {len(text_content)}")
        logging.info(f"Raw response preview: {text_content[:200]}...")
        
        try:
            payload = json.loads(text_content)
            logging.info(f"✅ Successfully parsed JSON with {len(payload.get('questions', []))} questions")
        except json.JSONDecodeError as e:
            logging.error(f"❌ JSON parsing failed: {e}")
            logging.error(f"📄 Raw OpenAI response (first 500 chars):")
            logging.error(f"{text_content[:500]}")
            logging.error(f"📄 Raw OpenAI response (last 500 chars):")
            logging.error(f"{text_content[-500:]}")
            
            # Try to extract JSON from the response if it's wrapped in markdown
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text_content, re.DOTALL)
            if json_match:
                logging.info(f"🔍 Found JSON in markdown, attempting extraction...")
                try:
                    payload = json.loads(json_match.group(1))
                    logging.info(f"✅ Successfully extracted JSON from markdown with {len(payload.get('questions', []))} questions")
                except json.JSONDecodeError as e2:
                    logging.error(f"❌ Failed to parse extracted JSON: {e2}")
                    logging.error(f"📄 Extracted JSON: {json_match.group(1)[:200]}...")
                    payload = {"_raw_text": text_content, "_error": "json_decode_failed", "_exception": str(e2)}
            else:
                logging.error(f"❌ No JSON found in markdown format")
                # Try to find the first { and last } to extract JSON
                first_brace = text_content.find('{')
                last_brace = text_content.rfind('}')
                if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                    potential_json = text_content[first_brace:last_brace+1]
                    logging.info(f"🔍 Attempting to extract JSON from position {first_brace} to {last_brace}")
                    try:
                        payload = json.loads(potential_json)
                        logging.info(f"✅ Successfully extracted JSON from position with {len(payload.get('questions', []))} questions")
                    except json.JSONDecodeError as e3:
                        logging.error(f"❌ Failed to parse position-extracted JSON: {e3}")
                        payload = {"_raw_text": text_content, "_error": "json_decode_failed", "_exception": str(e3)}
                else:
                    payload = {"_raw_text": text_content, "_error": "json_decode_failed", "_exception": str(e)}
    else:
        raise RuntimeError("No valid response from OpenAI")

    written_paths = save_outputs(payload, output_dir)
    combined_path = written_paths[0]
    logging.info(f"MCQs JSON written to: {combined_path}")
    return combined_path

def save_outputs(payload: Dict[str, Any], output_dir: str) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    
    # Use fixed filename "mcqs.json" instead of timestamped filename
    combined_path = os.path.join(output_dir, "mcqs.json")
    logging.info(f"Writing combined JSON: {combined_path}")
    
    # Remove existing file if it exists (override behavior)
    if os.path.exists(combined_path):
        logging.info(f"Overwriting existing file: {combined_path}")
        os.remove(combined_path)
    
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return [combined_path]


def main():
    load_dotenv('/secrets/.env')

    # Accept VERBOSITY as numeric or string (INFO/DEBUG/ERROR)
    v_raw = (os.getenv("VERBOSITY") or "1").strip().upper()
    verbosity = {"0": 0, "ERROR": 0, "1": 1, "INFO": 1, "2": 2, "DEBUG": 2}.get(v_raw, 1)

    # NUM_QUESTIONS as int
    try:
        num_questions = int((os.getenv("NUM_QUESTIONS") or "4").strip())
    except ValueError:
        num_questions = 4

    # Normalize PDF_PATH to avoid stray quotes/whitespace from .env
    pdf_path = (os.getenv("PDF_PATH") or "").strip().strip('"').strip("'")
    output_dir = (os.getenv("OUTPUT_DIR") or "").strip().strip('"').strip("'")
    model = (os.getenv("MODEL") or "gpt-4.1").strip()

    setup_logging(verbosity)
    logging.debug(f"PDF_PATH raw: {repr(os.getenv('PDF_PATH'))}")
    logging.debug(f"PDF_PATH normalized: {repr(pdf_path)}")

    if not pdf_path:
        logging.error("PDF_PATH environment variable is required.")
        sys.exit(1)
    if not output_dir:
        logging.error("OUTPUT_DIR environment variable is required.")
        sys.exit(1)

    logging.info("Starting MCQ generation pipeline...")
    logging.info(
        f"Env: pdf='{pdf_path}', output_dir='{output_dir}', model='{model}', "
        f"num_questions={num_questions}, verbosity={verbosity}"
    )

    try:
        combined_path = generate_mcqs_to_file(pdf_path, output_dir, model, num_questions)
        logging.info("All files written:")
        logging.info(f" - {combined_path}")

        logging.info("Done.")
    except Exception as e:
        logging.exception(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()