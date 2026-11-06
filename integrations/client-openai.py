"""Exemple client OpenAI (Python). pip install openai ; variable LITELLM_MASTER_KEY definie."""
import os
from openai import OpenAI

client = OpenAI(base_url="http://localhost:4000/v1", api_key=os.environ["LITELLM_MASTER_KEY"])
r = client.chat.completions.create(model="free-fast", messages=[{"role": "user", "content": "Reponds OK."}], max_tokens=50)
print(r.choices[0].message.content)
