init 1000 python:
    import rtr.hooks as _rtr

style rtr_text:
    font "DejaVuSans.ttf"
    size 24
    color "#eeeeee"
    outlines []

style rtr_label_text is rtr_text:
    size 34
    color "#ffffff"

style rtr_hint_text is rtr_text:
    size 18
    color "#9a9aa6"

style rtr_error_text is rtr_text:
    size 18
    color "#ff7a7a"

style rtr_button:
    background None
    padding (0, 6)

style rtr_button_text:
    font "DejaVuSans.ttf"
    size 24
    color "#b8b8c4"
    hover_color "#ffffff"
    selected_color "#66ccff"
    selected_hover_color "#99ddff"
    outlines []

screen rtr_settings():
    modal True
    zorder 1500
    $ s = _rtr.status()

    add Solid("#00000088")

    frame:
        style_prefix "rtr"
        xalign 0.5
        yalign 0.5
        xminimum 720
        padding (40, 30)
        background Solid("#1d1d24f0")

        vbox:
            spacing 12

            label "Автоперевод"

            hbox:
                spacing 16
                text "Переводчик:" yalign 0.5
                for key, title in s["providers"]:
                    textbutton title action Function(_rtr.set_provider, key) selected (s["provider"] == key)

            textbutton ("Переводить имена: " + ("да" if s["translate_names"] else "нет")) action Function(_rtr.toggle_names)
            textbutton ("Показывать оригинал: " + ("да" if s["show_original"] else "нет")) action Function(_rtr.toggle_original)
            if s["font_fallback"]:
                textbutton ("Шрифт: " + ("только DejaVuSans" if s["font_single"] else "игры + DejaVuSans")) action [Function(_rtr.toggle_font_single), _DisplayReset()]
            textbutton "Открыть список игнорирования" action Function(_rtr.open_glossary)
            text "Слово или фраза на строку. Изменения применятся после закрытия этого окна." style "rtr_hint_text"
            textbutton "Сбросить кэш переводов" action Function(_rtr.clear_cache)
            text ("Переведено строк в кэше: %d" % s["cached"]) style "rtr_hint_text"
            if s["error"]:
                text ("Ошибка переводчика: " + s["error"]) style "rtr_error_text"

            null height 8
            textbutton "Закрыть (F8)" action Hide("rtr_settings")

    key "game_menu" action Hide("rtr_settings")
    on "hide" action Function(_rtr.reload_terms)
