import os
import re
import asyncio
from typing import Dict, AsyncGenerator
import subprocess


async def crack_with_wordlist(cap_file: str, bssid: str, wordlist_file: str) -> AsyncGenerator[Dict, None]:
    """Crack a captured handshake file using a wordlist file, yielding progress updates."""
    # Validate inputs
    if not os.path.exists(cap_file):
        yield {"error": f"Capture file not found: {cap_file}"}
        return

    if not os.path.exists(wordlist_file):
        yield {"error": f"Wordlist file not found: {wordlist_file}"}
        return

    try:
        # Use absolute paths to avoid issues
        cap_file_path = os.path.abspath(cap_file)
        wordlist_path = os.path.abspath(wordlist_file)

        # Count total passwords in wordlist for progress reporting
        with open(wordlist_file, "r", errors="ignore") as f:
            total_passwords = sum(1 for line in f if line.strip())

        # Initial progress update
        yield {
            "status": "start",
            "total": total_passwords,
            "message": f"Starting to crack {bssid} with {total_passwords} passwords",
        }

        # Log basic info about the cracking attempt
        print(f"Starting aircrack attempt on BSSID: {bssid}")
        print(f"Using cap file: {cap_file_path} and wordlist: {wordlist_path}")

        # Create the command exactly like in the diagnostic script
        # This has been verified to work correctly
        cmd = ["aircrack-ng", "-a2", "-w", wordlist_path, "-b", bssid, cap_file_path]

        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            shell=False,  # Must be False to see process in ps output
        )

        # Get the PID for logging
        pid = process.pid
        print(f"Aircrack-ng process started with PID: {pid}")

        # Verify the process exists in process list
        try:
            subprocess.check_call(f"ps -p {pid} > /dev/null", shell=True)
            print(f"Verified process {pid} is running")
        except subprocess.CalledProcessError:
            print(f"Warning: Process {pid} not found in process list right after starting")

        # Track progress
        current_password = 0
        password_found = None

        # Monitor output for progress and success
        while process.poll() is None:
            # Read a line from stdout
            line = process.stdout.readline()
            if not line:
                continue

            # Log the output line for debugging
            print(f"AIRCRACK> {line.strip()}")

            # Check for progress information
            if "Tested" in line and "keys" in line:
                try:
                    # Extract current key count from output
                    # Example: "Tested 52/1000 keys"
                    match = re.search(r"Tested\s+(\d+)\/(\d+)\s+keys", line)
                    if match:
                        current_password = int(match.group(1))
                        total_in_output = int(match.group(2))
                        # Use total from output if it's larger than what we calculated
                        if total_in_output > total_passwords:
                            total_passwords = total_in_output

                        # Report progress
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

            # Check for password found
            if "KEY FOUND!" in line:
                print("Found KEY FOUND! in output, extracting password")
                password_match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", line)
                if password_match:
                    password_found = password_match.group(1)
                    print(f"PASSWORD FOUND: {password_found}")
                    break

            # Brief pause to prevent high CPU usage from constant polling
            await asyncio.sleep(0.1)

        # Process has finished
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
            # Check final output for password in case we missed it
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

            # Check exit code
            print(f"Process exited with code: {process.returncode}")

            # No password found
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
