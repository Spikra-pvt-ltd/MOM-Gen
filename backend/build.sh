#!/usr/bin/env bash
# Render build script for the backend.
# Installs ffmpeg system dependency and Python packages.

set -e

# Install ffmpeg (required for audio extraction/compression via ffmpeg-python)
apt-get update -y && apt-get install -y ffmpeg

# Install Python dependencies
pip install -r requirements.txt
