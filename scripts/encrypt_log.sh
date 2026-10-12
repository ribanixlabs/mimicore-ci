#!/bin/bash
# Encrypt ./build.log for the owner (random AES key, itself encrypted with the RSA public key log_pub.pem), delete the plain text.
# The log may quote private source lines, so only the encrypted copy is ever uploaded.
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
[ -f build.log ] || { echo "no build.log"; exit 0; }
key=$(openssl rand -hex 32)
printf '%s' "$key" > k.txt
openssl enc -aes-256-cbc -pbkdf2 -md sha256 -salt -pass file:k.txt -in build.log -out build.log.enc
openssl rsautl -encrypt -oaep -pubin -inkey "$here/log_pub.pem" -in k.txt -out k.enc
rm -f k.txt build.log
echo "encrypted log: $(wc -c < build.log.enc) bytes"
