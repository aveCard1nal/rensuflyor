# renpy-autotranslate

Синхронный машинный перевод диалогов игр на Ren'Py на русский язык через Google Translate.

Результат сборки — один файл `dist/zz_autotranslate_ru.rpy`, который кладётся в папку `game/` игры.

Поддерживаются Ren'Py 7 (Python 2.7) и Ren'Py 8 (Python 3).

## Сборка

```
python build.py
```

## Тесты

Код должен работать на обеих версиях Python, поэтому тесты на `unittest` гоняются под обеими:

```
python -m unittest discover -s tests -t .
"<игра>/lib/windows-x86_64/python.exe" -m unittest discover -s tests -t .
```
