#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse
import time


def run_command(cmd, shell=False):
    print(f"\n[Running] {''.join(cmd) if not shell else cmd}")
    try:
        result = subprocess.run(cmd, shell=shell, text=True, capture_output=True, timeout=5)
        print(f"[Exit code] {result.returncode}")
        if result.stdout:
            print(f"[Output]\n{result.stdout.strip()}")
        if result.stderr:
            print(f"[Error]\n{result.stderr.strip()}")
        return result.returncode == 0, result.stdout
    except subprocess.TimeoutExpired:
        print("[Error] Command timed out after 5 seconds")
        return False, ""
    except Exception as e:
        print(f"[Error] {str(e)}")
        return False, ""


def check_installation():
    print("\n==== CHECKING INSTALLATION ====")
    success, path = run_command(["which", "aircrack-ng"])
    if success:
        run_command(["aircrack-ng", "--help"], shell=False)
        print("✅ aircrack-ng is installed and working")
    else:
        print("❌ aircrack-ng is not found in PATH")
        sys.exit(1)


def check_files(cap_file, wordlist):
    print("\n==== CHECKING FILES ====")
    errors = False

    if not cap_file or not os.path.exists(cap_file):
        print(f"❌ Capture file does not exist: {cap_file}")
        errors = True
    else:
        file_size = os.path.getsize(cap_file)
        print(f"✅ Capture file exists: {cap_file} ({file_size} bytes)")
        if file_size < 1000:
            print("⚠️ Warning: Capture file is very small, might not contain handshakes")

    if not wordlist or not os.path.exists(wordlist):
        print(f"❌ Wordlist does not exist: {wordlist}")
        errors = True
    else:
        file_size = os.path.getsize(wordlist)
        print(f"✅ Wordlist exists: {wordlist} ({file_size} bytes)")
        if file_size < 100:
            print("⚠️ Warning: Wordlist is very small")

        try:
            with open(wordlist, "r", errors="ignore") as f:
                line_count = sum(1 for line in f if line.strip())
            print(f"✅ Wordlist contains {line_count} passwords")
        except Exception as e:
            print(f"❌ Error reading wordlist: {str(e)}")
            errors = True

    return not errors


def test_aircrack(cap_file, bssid, wordlist):
    print("\n==== TESTING AIRCRACK-NG ====")

    print("\n[Checking if capture file contains the BSSID]")
    run_command(["aircrack-ng", "-b", bssid, cap_file, "-J", "test_output"], shell=False)

    print("\n[Testing aircrack with first 5 passwords from wordlist]")
    test_wordlist = "/tmp/test_wordlist.txt"
    try:
        with open(wordlist, "r", errors="ignore") as src:
            passwords = [line.strip() for line in src if line.strip()][:5]

        with open(test_wordlist, "w") as dest:
            for pwd in passwords:
                dest.write(f"{pwd}\n")

        print(f"Created test wordlist with {len(passwords)} passwords")
        print(f"Passwords: {', '.join(passwords)}")

        process = subprocess.Popen(
            ["aircrack-ng", "-a2", "-w", test_wordlist, "-b", bssid, cap_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        pid = process.pid
        print(f"Aircrack-ng started with PID: {pid}")

        ps_output = subprocess.check_output(f"ps -p {pid} -f", shell=True, text=True)
        print(f"Process verification:\n{ps_output}")

        grep_output = subprocess.check_output("ps aux | grep aircrack-ng", shell=True, text=True)
        print(f"Grep verification:\n{grep_output}")

        print("Letting process run for 5 seconds...")
        time.sleep(5)

        if process.poll() is None:
            print("✅ Process is still running after 5 seconds")
            for _ in range(5):
                line = process.stdout.readline()
                if line:
                    print(f"Output: {line.strip()}")
        else:
            print("❌ Process terminated unexpectedly")
            stdout, stderr = process.communicate()
            print(f"Output: {stdout}")
            print(f"Error: {stderr}")

        print("Terminating the process...")
        process.terminate()
        process.wait(timeout=3)
        print("✅ Process terminated successfully")

    except Exception as e:
        print(f"❌ Error during aircrack test: {str(e)}")
    finally:
        if os.path.exists(test_wordlist):
            os.remove(test_wordlist)


def main():
    parser = argparse.ArgumentParser(description="Diagnose aircrack-ng functionality")
    parser.add_argument("--bssid", required=True, help="BSSID of the access point")
    parser.add_argument("--cap-file", required=True, help="Path to the capture file")
    parser.add_argument("--wordlist", required=True, help="Path to the wordlist file")

    args = parser.parse_args()

    print("===== AIRCRACK-NG DIAGNOSTIC TOOL =====")
    print(f"BSSID: {args.bssid}")
    print(f"Capture file: {args.cap_file}")
    print(f"Wordlist: {args.wordlist}")

    check_installation()
    if check_files(args.cap_file, args.wordlist):
        test_aircrack(args.cap_file, args.bssid, args.wordlist)

    print("\n===== DIAGNOSTIC COMPLETE =====")


if __name__ == "__main__":
    main()
