#!/bin/bash
pkill -f "MainSupport-macos" && echo "Stopped." || echo "Not running."
read -r -p "Press Enter to close..."
