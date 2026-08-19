#!/bin/bash
# ============================================
# Cleanup Windows Zone.Identifier Files
# Removes ADS (Alternate Data Stream) markers
# that leak into WSL/Linux from Windows downloads
# 
# Usage:
#   chmod +x cleanup-zone-identifiers.sh
#   ./cleanup-zone-identifiers.sh              # runs in current directory
#   ./cleanup-zone-identifiers.sh /path/to/dir # runs in specified directory
# ============================================

set -e

TARGET_DIR="${1:-.}"

if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ Directory not found: $TARGET_DIR"
    exit 1
fi

echo "🔍 Scanning: $TARGET_DIR"
echo ""

# Find all Zone.Identifier files
COUNT=$(find "$TARGET_DIR" -type f -name "*Zone.Identifier*" 2>/dev/null | wc -l)

if [ "$COUNT" -eq 0 ]; then
    echo "✅ No Zone.Identifier files found. Already clean!"
    exit 0
fi

echo "Found $COUNT Zone.Identifier file(s):"
echo ""
find "$TARGET_DIR" -type f -name "*Zone.Identifier*" 2>/dev/null | while read -r f; do
    echo "  🗑  $f"
done

echo ""
read -p "Delete all $COUNT file(s)? [y/N] " confirm

if [[ "$confirm" =~ ^[Yy]$ ]]; then
    find "$TARGET_DIR" -type f -name "*Zone.Identifier*" -delete 2>/dev/null
    echo ""
    echo "✅ Deleted $COUNT Zone.Identifier file(s)."
else
    echo "⏭  Skipped. No files deleted."
fi
