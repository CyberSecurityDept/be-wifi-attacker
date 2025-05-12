#!/usr/bin/env python3
# Script untuk mengupdate status "Deauth" atau "Attacked" menjadi "Attacking" di database MongoDB
# Menggunakan pymongo yang lebih umum tersedia

import pymongo


def update_status():
    print("Mengupdate status 'Deauth' dan 'Attacked' menjadi 'Attacking' di database...")

    # Koneksi ke MongoDB
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["wifi_attacker"]
    collection = db["wifi_networks"]

    # Update status Deauth ke Attacking
    result1 = collection.update_many({"status": "Deauth"}, {"$set": {"status": "Attacking"}})

    # Update status Attacked ke Attacking
    result2 = collection.update_many({"status": "Attacked"}, {"$set": {"status": "Attacking"}})

    print(f"Dokumen yang diupdate dari Deauth: {result1.modified_count}")
    print(f"Dokumen yang diupdate dari Attacked: {result2.modified_count}")
    print(f"Total dokumen yang diupdate: {result1.modified_count + result2.modified_count}")

    print("Update selesai!")


if __name__ == "__main__":
    update_status()
