"""Хелперы для сборки HTML. Без зависимостей от браузера."""


def esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def opt(value, label, selected=False):
    return f"<option value='{esc(value)}'{' selected' if selected else ''}>{esc(label)}</option>"


def field(fid, label, value):
    return f"<div><label>{esc(label)}</label><input id='{fid}' value='{esc(value)}'></div>"


def rows(items, cols):
    """items: список кортежей -> строки таблицы."""
    out = ""
    for it in items:
        out += "<tr>" + "".join(f"<td>{c}</td>" for c in cols(it)) + "</tr>"
    return out
