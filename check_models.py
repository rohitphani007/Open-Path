"""Run this once to see which Gemma models your API key can access."""
import os
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("Available Gemma models:\n")
for m in genai.list_models():
    if "gemma" in m.name.lower():
        print(f"  {m.name}")
        print(f"    Supports generateContent: {'generateContent' in m.supported_generation_methods}")
        print()
