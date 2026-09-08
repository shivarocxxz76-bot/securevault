#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

mkdir -p /tmp/uploads

echo "Build complete!"
