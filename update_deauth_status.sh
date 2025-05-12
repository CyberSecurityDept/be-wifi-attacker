#!/bin/bash

# Script untuk mengupdate status "Deauth" atau "Attacked" menjadi "Attacking" di database MongoDB
# Pastikan MongoDB berjalan sebelum menjalankan script ini

echo "Mengupdate status 'Deauth' dan 'Attacked' menjadi 'Attacking' di database..."

# Gunakan MongoDB shell untuk mengupdate dokumen
mongo --eval '
db = db.getSiblingDB("wifi_attacker");

// Update status Deauth ke Attacking
var result1 = db.wifi_networks.updateMany(
  { "status": "Deauth" },
  { $set: { "status": "Attacking" } }
);

// Update status Attacked ke Attacking
var result2 = db.wifi_networks.updateMany(
  { "status": "Attacked" },
  { $set: { "status": "Attacking" } }
);

print("Dokumen yang diupdate dari Deauth: " + result1.modifiedCount);
print("Dokumen yang diupdate dari Attacked: " + result2.modifiedCount);
print("Total dokumen yang diupdate: " + (result1.modifiedCount + result2.modifiedCount));
'

echo "Update selesai!"
