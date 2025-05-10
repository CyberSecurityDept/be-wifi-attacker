import os
import subprocess
import asyncio
import time
import re
from datetime import datetime
from typing import Dict, Optional, AsyncGenerator

# from app.helpers.network import enable_monitor, disable_monitor
from app.repositories.wifi_network_repository import WifiNetworkRepository

# from app.services.crack_password import crack_with_wordlist


# Global state to track running cracks across all service instances
_GLOBAL_RUNNING_CRACKS = {}


class WifiCrackService:
    def __init__(self, db):
        self.repo = WifiNetworkRepository(db)
        # Use the global dictionary to track cracks - this will be shared across all instances
        self._running_cracks = _GLOBAL_RUNNING_CRACKS
        print(
            f"WifiCrackService initialized with {len(self._running_cracks)} existing cracks"
        )
        if self._running_cracks:
            print(f"Active BSSIDs: {list(self._running_cracks.keys())}")

    @classmethod
    def get_active_cracks(cls):
        """Get a list of all active cracking jobs"""
        return list(_GLOBAL_RUNNING_CRACKS.keys())

    async def start_crack(
        self, bssid: str, handshake_file: str, dictionary_path: str
    ) -> str:
        """Start a password cracking attempt on a captured handshake file."""
        # Validate inputs
        if not os.path.exists(handshake_file):
            raise FileNotFoundError(f"Handshake file not found: {handshake_file}")

        if not os.path.exists(dictionary_path):
            raise FileNotFoundError(f"Dictionary file not found: {dictionary_path}")

        if bssid in self._running_cracks and not self._running_cracks[bssid].get(
            "completed", False
        ):
            raise ValueError(f"Cracking already in progress for {bssid}")

        # Use absolute paths to ensure files are found
        handshake_file_path = os.path.abspath(handshake_file)
        dictionary_path_absolute = os.path.abspath(dictionary_path)

        # Count words for progress tracking
        total_keys = self._count_words_in_dict(dictionary_path_absolute)
        print(f"Starting crack for BSSID {bssid} with {total_keys} passwords")

        # Create the aircrack-ng command - exactly as in our diagnostic script
        cmd = [
            "aircrack-ng",
            "-a2",
            "-w",
            dictionary_path_absolute,
            "-b",
            bssid,
            handshake_file_path,
        ]

        # Log the exact command we're running
        cmd_str = " ".join(cmd)
        print(f"Running command: {cmd_str}")

        # Start the process directly
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            shell=False,  # Must use shell=False to see in ps output
        )

        # Verify process is running and get its PID
        pid = process.pid
        print(f"Started aircrack-ng with PID {pid}")

        # Generate a unique ID for this cracking attempt
        job_id = f"{bssid}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Store information about the cracking job
        self._running_cracks[bssid] = {
            "job_id": job_id,
            "handshake_file": handshake_file_path,
            "dictionary_path": dictionary_path_absolute,
            "start_time": datetime.utcnow(),
            "password": None,
            "completed": False,
            "current_key": 0,
            "total_keys": total_keys,
            "process": process,  # Store the actual process
            "pid": pid,  # Store the PID for easier tracking
        }

        await self.repo.update_status(bssid, "Cracking")

        return job_id

    async def check_crack_status(self, bssid: str) -> Dict:
        """Check the status of a cracking attempt."""
        if bssid not in self._running_cracks:
            return {
                "status": "not_found",
                "message": f"No cracking job found for {bssid}",
            }

        job = self._running_cracks[bssid]

        # Check if the process has completed
        if job["completed"]:
            return {
                "status": "completed",
                "password": job["password"],
                "total_keys": job["total_keys"],
                "current_key": job["current_key"],
                "success": job["password"] is not None,
            }

        # If using the custom cracking approach
        if job.get("custom_process", False):
            return {
                "status": "running",
                "total_keys": job["total_keys"],
                "current_key": job["current_key"],
                "percent": min(
                    99, int(job["current_key"] * 100 / max(1, job["total_keys"]))
                ),
            }

        # Legacy process handling for backwards compatibility
        if "process" in job:
            process = job["process"]
            # Check if process is still running
            if process.poll() is None:
                return {
                    "status": "running",
                    "total_keys": job["total_keys"],
                    "current_key": job["current_key"],
                }

            # Process has completed, update status
            stdout, stderr = process.communicate()
            password = self._extract_password_from_output(stdout)

            if password:
                await self.repo.update_status(bssid, "Cracked")
                job["password"] = password
            else:
                await self.repo.update_status(bssid, "Failed")

            job["completed"] = True
            job["current_key"] = job["total_keys"]  # Set to total since finished

        return {
            "status": "completed",
            "password": job.get("password"),
            "total_keys": job["total_keys"],
            "current_key": job["current_key"],
            "success": job.get("password") is not None,
        }

    async def stop_crack(self, bssid: str) -> Dict:
        """Stop a running crack attempt."""
        if bssid not in self._running_cracks:
            return {
                "status": "not_found",
                "message": f"No cracking job found for {bssid}",
            }

        job = self._running_cracks[bssid]

        # Determine if we need to kill any running aircrack-ng processes
        try:
            # Try to find and kill any aircrack-ng processes for this BSSID
            kill_cmd = f"pkill -f 'aircrack-ng.*-b[[:space:]]+{bssid}'"
            subprocess.run(kill_cmd, shell=True, stderr=subprocess.PIPE)

            # For legacy processes (with the old approach)
            if "process" in job and job["process"].poll() is None:
                try:
                    job["process"].terminate()
                    job["process"].wait(timeout=2)
                except:
                    # If termination fails, force kill
                    job["process"].kill()
        except Exception as e:
            print(f"Error stopping crack process: {e}")

        # Mark as completed so the async generator will end
        await self.repo.update_status(bssid, "Stopped")
        job["completed"] = True

        return {
            "status": "stopped",
            "message": f"Cracking job for {bssid} stopped",
            "current_key": job.get("current_key", 0),
            "total_keys": job.get("total_keys", 0),
        }

    async def events(self, bssid: str) -> AsyncGenerator[str, None]:
        """Generate SSE events for cracking progress by reading directly from the aircrack-ng process."""
        if bssid not in self._running_cracks:
            yield 'event: error\ndata: {"message":"No cracking job found"}\n\n'
            return

        job = self._running_cracks[bssid]
        process = job.get("process")

        # Verify we have a process to monitor
        if not process or process.poll() is not None:
            error_msg = "Aircrack-ng process not running"
            print(f"Error: {error_msg}")
            yield f'event: error\ndata: {{"message":"{error_msg}"}}\n\n'
            return

        # Send initial start event
        total_keys = job["total_keys"]
        pid = job.get("pid", process.pid)
        start_msg = (
            f"Starting to crack {bssid} with {total_keys} passwords (PID: {pid})"
        )
        print(start_msg)
        yield f'event: start\ndata: {{"total_keys":{total_keys},"message":"{start_msg}"}}\n\n'

        # Check if the process is visible in system
        try:
            # Use ps command to verify the process is running
            ps_cmd = f"ps -p {pid} -o comm="
            result = subprocess.run(ps_cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(
                    f"Confirmed aircrack-ng process is running with PID {pid}: {result.stdout.strip()}"
                )
            else:
                print(f"Warning: Process with PID {pid} not found in process list")
        except Exception as e:
            print(f"Error checking process: {e}")

        # Initialize tracking variables
        current_password = 0
        password_found = None
        last_update_time = time.time()
        progress_counter = 0

        try:
            # Monitor the output of the aircrack-ng process for progress updates and results
            while process.poll() is None and not job.get("completed", False):
                # Read a line from stdout (non-blocking)
                line = process.stdout.readline()
                if not line:
                    # If no new output, periodically send a progress update anyway
                    if time.time() - last_update_time > 2 and current_password > 0:
                        progress_counter += 1
                        # Every 2 seconds, send current progress if we have data
                        progress_message = f"{current_password}/{total_keys}"
                        percent = min(
                            99, int(current_password * 100 / max(1, total_keys))
                        )
                        yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","counter":{progress_counter}}}\n\n'
                        last_update_time = time.time()

                    await asyncio.sleep(0.1)  # Brief pause if no output
                    continue

                # Log the line for debugging
                line = line.strip()
                if line:
                    print(f"AIRCRACK> {line}")

                # Extract progress information from format like '[00:00:25] 1018450/4646372 keys tested (39399.12 k/s)'
                if "keys tested" in line:
                    # Parse exact output format from aircrack-ng
                    match = re.search(
                        r"\[(\d+:\d+:\d+)\]\s+(\d+)\/(\d+)\s+keys\s+tested\s+\((.*?)\)",
                        line,
                    )
                    if match:
                        elapsed_time = match.group(1)
                        current_password = int(match.group(2))
                        total_in_output = int(match.group(3))
                        speed = match.group(4)

                        # Update total if aircrack reports a more accurate number
                        if total_in_output > total_keys:
                            total_keys = total_in_output
                            job["total_keys"] = total_keys

                        # Calculate and report progress
                        job["current_key"] = current_password

                        # Send progress event with the full formatted information
                        progress_message = (
                            f"{current_password}/{total_keys} keys tested ({speed})"
                        )
                        print(f"Progress: {progress_message}")

                        # Send progress event with all the details
                        yield f'event: progress\ndata: {{"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","speed":"{speed}","elapsed":"{elapsed_time}"}}\n\n'
                        last_update_time = time.time()

                # Extract percentage information from format like 'Time left: 1 minute, 32 seconds                           21.92%'
                elif "Time left" in line and "%" in line:
                    # Parse percentage at end of line
                    percent_match = re.search(r"(\d+\.\d+)%", line)
                    time_left_match = re.search(r"Time left:\s+(.+?)\s+\d", line)

                    if percent_match:
                        percent = float(percent_match.group(1))
                        time_left = (
                            time_left_match.group(1).strip()
                            if time_left_match
                            else "unknown"
                        )

                        # If we have current key info, update with percentage
                        if job.get("current_key", 0) > 0:
                            current_password = job["current_key"]
                            progress_message = f"{current_password}/{total_keys} ({percent}%) - Time left: {time_left}"
                            print(
                                f"Progress percentage: {percent}% - Time left: {time_left}"
                            )

                            # Send progress event with percentage
                            yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","time_left":"{time_left}"}}\n\n'
                            last_update_time = time.time()

                # Try to extract current passphrase being tested
                elif "Current passphrase:" in line:
                    passphrase_match = re.search(r"Current passphrase:\s+(\S+)", line)
                    if passphrase_match and current_password > 0:
                        current_passphrase = passphrase_match.group(1).strip()
                        print(f"Current passphrase: {current_passphrase}")

                        # Send an update with the current passphrase being tested
                        progress_message = f"{current_password}/{total_keys} - Testing: {current_passphrase}"
                        percent = job.get(
                            "percent",
                            min(99, int(current_password * 100 / max(1, total_keys))),
                        )

                        yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","current_passphrase":"{current_passphrase}"}}\n\n'
                        last_update_time = time.time()

                # Also watch for speed info
                elif "/s" in line and ("k/s" in line or "M/s" in line):
                    # Try to extract speed information from lines like: "Speed: 1234.5 k/s"
                    try:
                        speed_match = re.search(r"Speed:\s*([\d\.]+)\s*([kM]?/s)", line)
                        if speed_match and current_password > 0:
                            speed = speed_match.group(1)
                            unit = speed_match.group(2)

                            # Send an additional progress update with speed info
                            progress_message = (
                                f"{current_password}/{total_keys} at {speed} {unit}"
                            )
                            percent = min(
                                99, int(current_password * 100 / max(1, total_keys))
                            )
                            print(f"Speed update: {progress_message}")

                            yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}"}}\n\n'
                            last_update_time = time.time()
                    except Exception as e:
                        print(f"Error parsing speed info: {e}")

                # Check for password found
                if "KEY FOUND!" in line:
                    match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", line)
                    if match:
                        password_found = match.group(1)
                        print(f"PASSWORD FOUND: {password_found}")
                        break

                # Add a brief delay to avoid consuming too much CPU
                await asyncio.sleep(0.1)

            # Check final output if password wasn't found in the streaming output
            if process.poll() is not None and not password_found:
                # Get any remaining output
                remaining_output, stderr = process.communicate()
                if remaining_output and "KEY FOUND!" in remaining_output:
                    match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", remaining_output)
                    if match:
                        password_found = match.group(1)
                        print(f"PASSWORD FOUND in final output: {password_found}")

            # Report success or failure
            if password_found:
                job["password"] = password_found
                job["completed"] = True
                await self.repo.update_status(bssid, "Cracked")
                yield f'event: success\ndata: {{"password":"{password_found}","keys_tried":{current_password}}}\n\n'
            elif job.get("completed", False):
                # Job was marked as completed (possibly stopped manually)
                yield f'event: error\ndata: {{"message":"Cracking stopped manually"}}\n\n'
            else:
                # No password found, mark as failed
                job["completed"] = True
                await self.repo.update_status(bssid, "Failed")
                yield f'event: error\ndata: {{"message":"Password not found in wordlist"}}\n\n'

        except Exception as e:
            # Handle any exceptions during the monitoring process
            print(f"Error monitoring aircrack-ng process: {str(e)}")
            import traceback

            traceback.print_exc()
            job["completed"] = True
            await self.repo.update_status(bssid, "Failed")
            yield f'event: error\ndata: {{"message":"Error during cracking: {str(e)}"}}\n\n'

        except Exception as e:
            # Handle any exceptions during the cracking process
            job["completed"] = True
            await self.repo.update_status(bssid, "Failed")
            yield f'event: error\ndata: {{"message":"Error during cracking: {str(e)}"}}\n\n'

    def _count_words_in_dict(self, dict_path: str) -> int:
        """Count the number of words in a dictionary file."""
        try:
            with open(dict_path, "r", errors="ignore") as file:
                return sum(1 for _ in file)
        except Exception:
            return 0

    def _extract_current_key(self, line: str) -> Optional[int]:
        """Extract current key count from aircrack-ng output line."""
        line = (
            line.decode("utf-8", errors="ignore") if isinstance(line, bytes) else line
        )
        try:
            if "keys tested" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "keys" and i > 0:
                        return int(parts[i - 1].replace(",", ""))
        except:
            pass
        return None

    def _extract_password_from_output(self, output: str) -> Optional[str]:
        """Extract password from aircrack-ng output if found."""
        output = (
            output.decode("utf-8", errors="ignore")
            if isinstance(output, bytes)
            else output
        )
        try:
            if "KEY FOUND!" in output:
                lines = output.split("\n")
                for line in lines:
                    if "KEY FOUND!" in line:
                        # Format is typically: KEY FOUND! [ password ]
                        start = line.find("[")
                        end = line.find("]")
                        if start > 0 and end > start:
                            return line[start + 1 : end].strip()
        except:
            pass
        return None
