import os
import subprocess
from typing import List, Dict
import re

DICT_DIR = "dictionaries"


class DictionaryService:
    def __init__(self):
        os.makedirs(DICT_DIR, exist_ok=True)

    def list_dictionaries(self) -> List[Dict[str, str]]:
        dictionaries = []
        for file in os.listdir(DICT_DIR):
            if file.endswith(".txt"):
                path = os.path.join(DICT_DIR, file)
                word_count = 0
                with open(path, "r", errors="ignore") as f:
                    word_count = sum(1 for _ in f)
                dictionaries.append({"name": file, "path": path, "word_count": word_count})
        return dictionaries

    def create_dictionary(self, name: str, content: str) -> Dict[str, str]:
        if not name.endswith(".txt"):
            name = f"{name}.txt"

        file_path = os.path.join(DICT_DIR, name)
        with open(file_path, "w") as f:
            f.write(content)

        word_count = len(content.splitlines())
        return {"name": name, "path": file_path, "word_count": word_count}

    def delete_dictionary(self, name: str) -> bool:
        file_path = os.path.join(DICT_DIR, name)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    def generate_custom_wordlist(self, params: dict) -> dict:
        output_name = params.get("output", "custom-wordlist.txt")
        if "." in output_name:
            base, ext = output_name.rsplit(".", 1)
            pattern = re.compile(rf"^{re.escape(base)}-(\d{{2}})\.{re.escape(ext)}$")
            existing = [f for f in os.listdir(DICT_DIR) if pattern.match(f)]
        else:
            base = output_name
            ext = ""
            pattern = re.compile(rf"^{re.escape(base)}-(\d{{2}})$")
            existing = [f for f in os.listdir(DICT_DIR) if pattern.match(f)]
        max_idx = 0
        for fname in existing:
            m = pattern.match(fname)
            if m:
                idx = int(m.group(1))
                if idx > max_idx:
                    max_idx = idx
        next_idx = max_idx + 1
        suffix = f"-{next_idx:02d}"
        if ext:
            output_name = f"{base}{suffix}.{ext}"
        else:
            output_name = f"{base}{suffix}"
        output_path = os.path.join(DICT_DIR, output_name)
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../helpers/wordlist_gen.py"))

        cmd = ["python3", script_path]

        names = params.get("names")
        if not names:
            raise ValueError("'names' parameter is required")
        cmd += ["--names"] + names
        # Optional params
        for key, value in params.items():
            if key == "names":
                continue
            if isinstance(value, list):
                cmd.append(f"--{key}")
                cmd += value
            else:
                cmd.append(f"--{key}")
                cmd.append(str(value))

        cmd += ["--output", output_path]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Wordlist generation failed: {proc.stderr}")

        word_count = 0
        if os.path.exists(output_path):
            with open(output_path, "r", errors="ignore") as f:
                word_count = sum(1 for _ in f)
        return {"name": output_name, "path": output_path, "word_count": word_count}
