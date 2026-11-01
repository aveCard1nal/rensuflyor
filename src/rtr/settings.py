from __future__ import absolute_import, unicode_literals

provider = "google"
translate_names = False
settings_key = "K_F8"
font_fallback = True
fallback_font = "DejaVuSans.ttf"
source_lang = "auto"
target_lang = "ru"
glossary_file = "rtr_glossary.txt"
cache_file = "rtr_cache_ru_%s.jsonl"
timeout = 10
batch_size = 20
batch_chars = 4000
retries = 4
wait_timeout = 3.0
lookahead = 40
fail_cooldown = 30.0
error_pause = 5.0
max_error_pause = 60.0
coalesce = 0.3
