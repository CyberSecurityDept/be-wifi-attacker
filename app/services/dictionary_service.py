# app/services/dictionary_service.py

import os
import shutil
from typing import List, Dict
from pathlib import Path

DICT_DIR = "dictionaries"


class DictionaryService:
    def __init__(self):
        os.makedirs(DICT_DIR, exist_ok=True)

    def list_dictionaries(self) -> List[Dict[str, str]]:
        """Get a list of available dictionaries."""
        dictionaries = []
        for file in os.listdir(DICT_DIR):
            if file.endswith(".txt"):
                path = os.path.join(DICT_DIR, file)
                word_count = 0
                with open(path, "r", errors="ignore") as f:
                    word_count = sum(1 for _ in f)
                dictionaries.append(
                    {"name": file, "path": path, "word_count": word_count}
                )
        return dictionaries

    def create_dictionary(self, name: str, content: str) -> Dict[str, str]:
        """Create a new dictionary file."""
        # Ensure filename ends with .txt
        if not name.endswith(".txt"):
            name = f"{name}.txt"

        file_path = os.path.join(DICT_DIR, name)
        with open(file_path, "w") as f:
            f.write(content)

        word_count = len(content.splitlines())
        return {"name": name, "path": file_path, "word_count": word_count}

    def delete_dictionary(self, name: str) -> bool:
        """Delete a dictionary file."""
        file_path = os.path.join(DICT_DIR, name)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
