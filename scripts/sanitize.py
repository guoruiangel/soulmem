#!/usr/bin/env python3
# ============================================================================
# SoulMem — Sanitize
# Remove private UI fields (e.g. __timestampUI) and debug noise from content
# before injecting into model context.
# ============================================================================
import re

PRIVATE_RE = re.compile(r'^__[a-zA-Z_][a-zA-Z0-9_]*\s*[:=]\s*.*$', re.MULTILINE)
INTERNAL_RE = re.compile(r'^_[a-zA-Z_][a-zA-Z0-9_]*\s*[:=]\s*.*$', re.MULTILINE)
DEBUG_RE = re.compile(r'^\s*#\s*(DEBUG|TODO|TEMP|FIXME).*$|^\s*\[(DEBUG|TEMP|PRIVATE)\].*$', re.MULTILINE)

def sanitize(text: str) -> str:
    if not text: return ''
    text = PRIVATE_RE.sub('', text)
    text = INTERNAL_RE.sub('', text)
    text = DEBUG_RE.sub('', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def sanitize_record(record: dict) -> dict:
    """Sanitize a dict with summary/detail/tags fields"""
    clean = dict(record)
    for f in ('summary', 'detail', 'tags'):
        if f in clean and clean[f]:
            clean[f] = sanitize(str(clean[f]))
    return clean

if __name__ == '__main__':
    dirty = """
__timestampUI: 2026-07-04T12:00:00Z
__debugUI: rendering:embed
_docVersion: 3

This is content that should be preserved.
# DEBUG this should be removed
[TEMP] this block should be removed
API_KEY=sk-1234567890abcdef
"""
    clean = sanitize(dirty)
    assert '__timestampUI' not in clean
    assert '__debugUI' not in clean
    assert '# DEBUG' not in clean
    assert '[TEMP]' not in clean
    assert 'API_KEY=sk-1234567890abcdef' in clean
    assert 'This is content' in clean
    print("✅ Sanitize tests passed")
