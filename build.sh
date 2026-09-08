#!/usr/bin/env bash
# Render build script — runs during deployment
set -o errexit

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Creating upload directory..."
mkdir -p /tmp/uploads

echo "Build complete."
