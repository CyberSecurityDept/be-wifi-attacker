import os
import re
import asyncio
from typing import Dict, AsyncGenerator
import subprocess


async def crack_with_wordlist(cap_file: str, bssid: str, wordlist_file: str) -> AsyncGenerator[Dict, None]:
    if not os.path.exists(cap_file):
        yield {"error": f"Capture file not found: {cap_file}"}
        return

    if not os.path.exists(wordlist_file):
        yield {"error": f"Wordlist file not found: {wordlist_file}"}
        return

    try:
        cap_file_path = os.path.abspath(cap_file)
        wordlist_path = os.path.abspath(wordlist_file)

        with open(wordlist_file, "r", errors="ignore") as f:
            total_passwords = sum(1 for line in f if line.strip())

        yield {
            "status": "start",
            "total": total_passwords,
            "message": f"Starting to crack {bssid} with {total_passwords} passwords",
        }

        print(f"Starting aircrack attempt on BSSID: {bssid}")
        print(f"Using cap file: {cap_file_path} and wordlist: {wordlist_path}")

        cmd = ["aircrack-ng", "-a2", "-w", wordlist_path, "-b", bssid, cap_file_path]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            shell=False,
        )

        pid = process.pid
        print(f"Aircrack-ng process started with PID: {pid}")

        try:
            subprocess.check_call(f"ps -p {pid} > /dev/null", shell=True)
            print(f"Verified process {pid} is running")
        except subprocess.CalledProcessError:
            print(f"Warning: Process {pid} not found in process list right after starting")

        current_password = 0
        password_found = None

        while process.poll() is None:
            line = process.stdout.readline()
            if not line:
                continue

            print(f"AIRCRACK> {line.strip()}")

            if "Tested" in line and "keys" in line:
                try:
                    match = re.search(r"Tested\s+(\d+)\/(\d+)\s+keys", line)
                    if match:
                        current_password = int(match.group(1))
                        total_in_output = int(match.group(2))
                        if total_in_output > total_passwords:
                            total_passwords = total_in_output

                        percent = min(99, int(current_password * 100 / max(1, total_passwords)))
                        print(f"Progress: {current_password}/{total_passwords} ({percent}%)")
                        yield {
                            "status": "progress",
                            "current": current_password,
                            "total": total_passwords,
                            "percent": percent,
                        }
                except Exception as e:
                    print(f"Error parsing progress: {str(e)}")

            if "KEY FOUND!" in line:
                print("Found KEY FOUND! in output, extracting password")
                password_match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", line)
                if password_match:
                    password_found = password_match.group(1)
                    print(f"PASSWORD FOUND: {password_found}")
                    break

            await asyncio.sleep(0.1)

        if password_found:
            print(f"SUCCESS: Password found: {password_found}")
            yield {
                "status": "success",
                "key": password_found,
                "current": current_password,
                "total": total_passwords,
                "percent": 100,
            }
        else:
            remaining_output, stderr = process.communicate()
            print(f"Process finished. Checking remaining output for password")  # noqa

            if stderr:
                print(f"STDERR output: {stderr}")

            if "KEY FOUND!" in remaining_output:
                password_match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", remaining_output)
                if password_match:
                    password_found = password_match.group(1)
                    print(f"SUCCESS: Password found in final output: {password_found}")
                    yield {
                        "status": "success",
                        "key": password_found,
                        "current": total_passwords,
                        "total": total_passwords,
                        "percent": 100,
                    }
                    return

            print(f"Process exited with code: {process.returncode}")

            print("FAILED: Password not found in wordlist")
            yield {
                "status": "failed",
                "message": "Password not found in wordlist",
                "percent": 100,
            }

    except Exception as e:
        print(f"ERROR in crack_with_wordlist: {str(e)}")
        import traceback

        traceback.print_exc()
        yield {"status": "error", "message": f"Error during cracking: {str(e)}"}
