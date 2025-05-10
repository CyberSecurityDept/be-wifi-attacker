import os
import subprocess
import asyncio
import time
import re
from datetime import datetime
from typing import Dict, Optional, AsyncGenerator

from app.repositories.wifi_network_repository import WifiNetworkRepository

_GLOBAL_RUNNING_CRACKS = {}


class WifiCrackService:
    def __init__(self, db):
        self.repo = WifiNetworkRepository(db)
        self._running_cracks = _GLOBAL_RUNNING_CRACKS
        print(f"WifiCrackService initialized with {len(self._running_cracks)} existing cracks")
        if self._running_cracks:
            print(f"Active BSSIDs: {list(self._running_cracks.keys())}")

    @classmethod
    def get_active_cracks(cls):
        return list(_GLOBAL_RUNNING_CRACKS.keys())

    async def start_crack(self, bssid: str, handshake_file: str, dictionary_path: str) -> str:
        if not os.path.exists(handshake_file):
            raise FileNotFoundError(f"Handshake file not found: {handshake_file}")

        if not os.path.exists(dictionary_path):
            raise FileNotFoundError(f"Dictionary file not found: {dictionary_path}")

        if bssid in self._running_cracks and not self._running_cracks[bssid].get("completed", False):
            raise ValueError(f"Cracking already in progress for {bssid}")

        handshake_file_path = os.path.abspath(handshake_file)
        dictionary_path_absolute = os.path.abspath(dictionary_path)

        total_keys = self._count_words_in_dict(dictionary_path_absolute)
        print(f"Starting crack for BSSID {bssid} with {total_keys} passwords")

        cmd = [
            "aircrack-ng",
            "-a2",
            "-w",
            dictionary_path_absolute,
            "-b",
            bssid,
            handshake_file_path,
        ]

        cmd_str = " ".join(cmd)
        print(f"Running command: {cmd_str}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            shell=False,
        )

        pid = process.pid
        print(f"Started aircrack-ng with PID {pid}")

        job_id = f"{bssid}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        self._running_cracks[bssid] = {
            "job_id": job_id,
            "handshake_file": handshake_file_path,
            "dictionary_path": dictionary_path_absolute,
            "start_time": datetime.utcnow(),
            "password": None,
            "completed": False,
            "current_key": 0,
            "total_keys": total_keys,
            "process": process,
            "pid": pid,
        }

        await self.repo.update_status(bssid, "Cracking")

        return job_id

    async def check_crack_status(self, bssid: str) -> Dict:
        if bssid not in self._running_cracks:
            return {
                "status": "not_found",
                "message": f"No cracking job found for {bssid}",
            }

        job = self._running_cracks[bssid]

        if job["completed"]:
            return {
                "status": "completed",
                "password": job["password"],
                "total_keys": job["total_keys"],
                "current_key": job["current_key"],
                "success": job["password"] is not None,
            }

        if job.get("custom_process", False):
            return {
                "status": "running",
                "total_keys": job["total_keys"],
                "current_key": job["current_key"],
                "percent": min(99, int(job["current_key"] * 100 / max(1, job["total_keys"]))),
            }

        if "process" in job:
            process = job["process"]
            if process.poll() is None:
                return {
                    "status": "running",
                    "total_keys": job["total_keys"],
                    "current_key": job["current_key"],
                }

            stdout, stderr = process.communicate()
            password = self._extract_password_from_output(stdout)

            if password:
                await self.repo.update_status(bssid, "Cracked")
                job["password"] = password
            else:
                await self.repo.update_status(bssid, "Failed")

            job["completed"] = True
            job["current_key"] = job["total_keys"]

        return {
            "status": "completed",
            "password": job.get("password"),
            "total_keys": job["total_keys"],
            "current_key": job["current_key"],
            "success": job.get("password") is not None,
        }

    async def stop_crack(self, bssid: str) -> Dict:
        if bssid not in self._running_cracks:
            return {
                "status": "not_found",
                "message": f"No cracking job found for {bssid}",
            }

        job = self._running_cracks[bssid]

        try:
            kill_cmd = f"pkill -f 'aircrack-ng.*-b[[:space:]]+{bssid}'"
            subprocess.run(kill_cmd, shell=True, stderr=subprocess.PIPE)

            if "process" in job and job["process"].poll() is None:
                try:
                    job["process"].terminate()
                    job["process"].wait(timeout=2)
                except Exception as e:
                    print(e)
                    job["process"].kill()
        except Exception as e:
            print(f"Error stopping crack process: {e}")

        await self.repo.update_status(bssid, "Stopped")
        job["completed"] = True

        return {
            "status": "stopped",
            "message": f"Cracking job for {bssid} stopped",
            "current_key": job.get("current_key", 0),
            "total_keys": job.get("total_keys", 0),
        }

    async def events(self, bssid: str) -> AsyncGenerator[str, None]:
        if bssid not in self._running_cracks:
            yield 'event: error\ndata: {"message":"No cracking job found"}\n\n'
            return

        job = self._running_cracks[bssid]
        process = job.get("process")

        if not process or process.poll() is not None:
            error_msg = "Aircrack-ng process not running"
            print(f"Error: {error_msg}")
            yield f'event: error\ndata: {{"message":"{error_msg}"}}\n\n'
            return

        total_keys = job["total_keys"]
        pid = job.get("pid", process.pid)
        start_msg = f"Starting to crack {bssid} with {total_keys} passwords (PID: {pid})"
        print(start_msg)
        yield f'event: start\ndata: {{"total_keys":{total_keys},"message":"{start_msg}"}}\n\n'

        try:
            ps_cmd = f"ps -p {pid} -o comm="
            result = subprocess.run(ps_cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Confirmed aircrack-ng process is running with PID {pid}: {result.stdout.strip()}")
            else:
                print(f"Warning: Process with PID {pid} not found in process list")
        except Exception as e:
            print(f"Error checking process: {e}")

        current_password = 0
        password_found = None
        last_update_time = time.time()
        progress_counter = 0

        try:
            while process.poll() is None and not job.get("completed", False):
                line = process.stdout.readline()
                if not line:
                    if time.time() - last_update_time > 2 and current_password > 0:
                        progress_counter += 1
                        progress_message = f"{current_password}/{total_keys}"
                        percent = min(99, int(current_password * 100 / max(1, total_keys)))
                        yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","counter":{progress_counter}}}\n\n'  # noqa
                        last_update_time = time.time()

                    await asyncio.sleep(0.1)
                    continue

                line = line.strip()
                if line:
                    print(f"AIRCRACK> {line}")

                if "keys tested" in line:
                    match = re.search(
                        r"\[(\d+:\d+:\d+)\]\s+(\d+)\/(\d+)\s+keys\s+tested\s+\((.*?)\)",
                        line,
                    )
                    if match:
                        elapsed_time = match.group(1)
                        current_password = int(match.group(2))
                        total_in_output = int(match.group(3))
                        speed = match.group(4)

                        if total_in_output > total_keys:
                            total_keys = total_in_output
                            job["total_keys"] = total_keys

                        job["current_key"] = current_password

                        progress_message = f"{current_password}/{total_keys} keys tested ({speed})"
                        print(f"Progress: {progress_message}")

                        yield f'event: progress\ndata: {{"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","speed":"{speed}","elapsed":"{elapsed_time}"}}\n\n'  # noqa
                        last_update_time = time.time()

                elif "Time left" in line and "%" in line:
                    percent_match = re.search(r"(\d+\.\d+)%", line)
                    time_left_match = re.search(r"Time left:\s+(.+?)\s+\d", line)

                    if percent_match:
                        percent = float(percent_match.group(1))
                        time_left = time_left_match.group(1).strip() if time_left_match else "unknown"

                        if job.get("current_key", 0) > 0:
                            current_password = job["current_key"]
                            progress_message = f"{current_password}/{total_keys} ({percent}%) - Time left: {time_left}"
                            print(f"Progress percentage: {percent}% - Time left: {time_left}")

                            yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","time_left":"{time_left}"}}\n\n'  # noqa
                            last_update_time = time.time()

                elif "Current passphrase:" in line:
                    passphrase_match = re.search(r"Current passphrase:\s+(\S+)", line)
                    if passphrase_match and current_password > 0:
                        current_passphrase = passphrase_match.group(1).strip()
                        print(f"Current passphrase: {current_passphrase}")

                        progress_message = f"{current_password}/{total_keys} - Testing: {current_passphrase}"
                        percent = job.get(
                            "percent",
                            min(99, int(current_password * 100 / max(1, total_keys))),
                        )

                        yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}","current_passphrase":"{current_passphrase}"}}\n\n'  # noqa
                        last_update_time = time.time()

                elif "/s" in line and ("k/s" in line or "M/s" in line):
                    try:
                        speed_match = re.search(r"Speed:\s*([\d\.]+)\s*([kM]?/s)", line)
                        if speed_match and current_password > 0:
                            speed = speed_match.group(1)
                            unit = speed_match.group(2)

                            progress_message = f"{current_password}/{total_keys} at {speed} {unit}"
                            percent = min(99, int(current_password * 100 / max(1, total_keys)))
                            print(f"Speed update: {progress_message}")

                            yield f'event: progress\ndata: {{"percent":{percent},"keys_tried":{current_password},"total_keys":{total_keys},"progress":"{progress_message}"}}\n\n'  # noqa
                            last_update_time = time.time()
                    except Exception as e:
                        print(f"Error parsing speed info: {e}")

                if "KEY FOUND!" in line:
                    match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", line)
                    if match:
                        password_found = match.group(1)
                        print(f"PASSWORD FOUND: {password_found}")
                        break

                await asyncio.sleep(0.1)

            if process.poll() is not None and not password_found:
                remaining_output, stderr = process.communicate()
                if remaining_output and "KEY FOUND!" in remaining_output:
                    match = re.search(r"KEY FOUND!\s*\[\s*(.+?)\s*\]", remaining_output)
                    if match:
                        password_found = match.group(1)
                        print(f"PASSWORD FOUND in final output: {password_found}")

            if password_found:
                job["password"] = password_found
                job["completed"] = True
                await self.repo.update_status(bssid, "Cracked")
                yield f'event: success\ndata: {{"password":"{password_found}","keys_tried":{current_password}}}\n\n'
            elif job.get("completed", False):
                yield f'event: error\ndata: {{"message":"Cracking stopped manually"}}\n\n'  # noqa
            else:
                job["completed"] = True
                await self.repo.update_status(bssid, "Failed")
                yield f'event: error\ndata: {{"message":"Password not found in wordlist"}}\n\n'  # noqa

        except Exception as e:
            print(f"Error monitoring aircrack-ng process: {str(e)}")
            import traceback

            traceback.print_exc()
            job["completed"] = True
            await self.repo.update_status(bssid, "Failed")
            yield f'event: error\ndata: {{"message":"Error during cracking: {str(e)}"}}\n\n'

        except Exception as e:
            job["completed"] = True
            await self.repo.update_status(bssid, "Failed")
            yield f'event: error\ndata: {{"message":"Error during cracking: {str(e)}"}}\n\n'

    def _count_words_in_dict(self, dict_path: str) -> int:
        try:
            with open(dict_path, "r", errors="ignore") as file:
                return sum(1 for _ in file)
        except Exception:
            return 0

    def _extract_current_key(self, line: str) -> Optional[int]:
        line = line.decode("utf-8", errors="ignore") if isinstance(line, bytes) else line
        try:
            if "keys tested" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "keys" and i > 0:
                        return int(parts[i - 1].replace(",", ""))
        except Exception:
            pass
        return None

    def _extract_password_from_output(self, output: str) -> Optional[str]:
        output = output.decode("utf-8", errors="ignore") if isinstance(output, bytes) else output
        try:
            if "KEY FOUND!" in output:
                lines = output.split("\n")
                for line in lines:
                    if "KEY FOUND!" in line:
                        start = line.find("[")
                        end = line.find("]")
                        if start > 0 and end > start:
                            return line[start + 1 : end].strip()  # noqa
        except Exception:
            pass
        return None
