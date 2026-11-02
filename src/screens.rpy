init 1000 python:
    import rensuflyor.hooks as _rensuflyor

style rensuflyor_text:
    font "DejaVuSans.ttf"
    size 24
    color "#eeeeee"
    outlines []

style rensuflyor_label_text is rensuflyor_text:
    size 34
    color "#ffffff"

style rensuflyor_hint_text is rensuflyor_text:
    size 18
    color "#9a9aa6"

style rensuflyor_error_text is rensuflyor_text:
    size 18
    color "#ff7a7a"

style rensuflyor_button:
    background None
    padding (0, 6)

style rensuflyor_button_text:
    font "DejaVuSans.ttf"
    size 24
    color "#b8b8c4"
    hover_color "#ffffff"
    selected_color "#66ccff"
    selected_hover_color "#99ddff"
    outlines []

screen rensuflyor_settings():
    modal True
    zorder 1500
    $ s = _rensuflyor.status()

    add Solid("#00000088")

    frame:
        style_prefix "rensuflyor"
        xalign 0.5
        yalign 0.5
        xminimum 720
        padding (40, 30)
        background Solid("#1d1d24f0")

        vbox:
            spacing 12

            label "RenSuflyor"

            hbox:
                spacing 16
                text "Переводчик:" yalign 0.5
                for key, title in s["providers"]:
                    textbutton title action Function(_rensuflyor.set_provider, key) selected (s["provider"] == key)

            textbutton ("Переводить имена: " + ("да" if s["translate_names"] else "нет")) action Function(_rensuflyor.toggle_names)
            textbutton ("Перевод: " + ("включён" if s["enabled"] else "выключен, показывается оригинал")) action Function(_rensuflyor.toggle_enabled)
            if s["enabled"]:
                textbutton ("Оригинал под переводом: " + ("да" if s["show_both"] else "нет")) action Function(_rensuflyor.toggle_both)
            text "Применяется со следующей реплики." style "rensuflyor_hint_text"
            if s["font_fallback"]:
                textbutton ("Шрифт: " + ("только DejaVuSans" if s["font_single"] else "от игры + DejaVuSans")) action [Function(_rensuflyor.toggle_font_single), _DisplayReset()]
            textbutton "Открыть список игнорирования" action Function(_rensuflyor.open_glossary)
            text "Слово или фраза на строку. После закрытия окна затронутые строки будут переведены заново." style "rensuflyor_hint_text"
            textbutton "Сбросить кэш переводов" action Confirm("Удалить все сохранённые переводы и перевести заново?", Function(_rensuflyor.clear_cache))
            text ("Переведено строк в кэше: %d" % s["cached"]) style "rensuflyor_hint_text"
            if s["error"]:
                text ("Ошибка переводчика: " + s["error"]) style "rensuflyor_error_text" substitute False

            null height 8
            textbutton "Закрыть (F8)" action Hide("rensuflyor_settings")

    key "game_menu" action Hide("rensuflyor_settings")
    on "hide" action Function(_rensuflyor.reload_terms)
