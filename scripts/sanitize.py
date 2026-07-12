#!/usr/bin/env python3
# ============================================================================
# SoulMem — Sanitize Module
# Remove private UI fields and debug noise from content.
#
# Shared by all SoulMem scripts. Import this — don't duplicate regex logic.
# ============================================================================

import re

# Private fields: __timestampUI, __debugUI, _docVersion, etc.
PRIVATE_RE = re.compile(r'^__[a-zA-Z_][a-zA-Z0-9_]*\s*[:=]\s*.*$', re.MULTILINE)
INTERNAL_RE = re.compile(r'^_[a-zA-Z_][a-zA-Z0-9_]*\s*[:=]\s*.*$', re.MULTILINE)

# Debug/temp comments and blocks
DEBUG_RE = re.compile(
    r'^\s*#\s*(DEBUG|TODO|TEMP|FIXME).*$|^\s*\[(DEBUG|TEMP|PRIVATE)\].*$',
    re.MULTILINE,
)

# NEWLINE_COLLAPSE_RE = re.compile(r'\n{3,}')

def sanitize(text: str) -> str:
    """Remove private UI fields and debug noise from text."""
    if not text:
        return ''
    text = PRIVATE_RE.sub('', text)
    text = INTERNAL_RE.sub('', text)
    text = DEBUG_RE.sub('', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def sanitize_record(record: dict) -> dict:
    """Sanitize a memory record dict (summary, detail, tags fields)."""
    clean = dict(record)
    for f in ('summary', 'detail', 'tags'):
        if f in clean and clean[f]:
            clean[f] = sanitize(str(clean[f]))
    return clean


# --- Self-test ---
if __name__ == '__main__':
    dirty = """
__timestampUI: 2026-07-04T12:00:00Z
__debugUI: rendering:embed
_docVersion: 3

This is content that should be preserved.
# DEBUG this should be removed
[TEMP] this block should be removed
API_KEY=***
"""
    clean = sanitize(dirty)
    assert '__timestampUI' not in clean
    assert '__debugUI' not in clean
    assert '# DEBUG' not in clean
    assert '[TEMP]' not in clean
    assert 'API_KEY=***' in clean
    assert 'This is content' in clean
    print("✅ Sanitize tests passed")
