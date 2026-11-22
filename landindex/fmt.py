"""Number and text formatting shared by pages, charts and maps."""
import html

MINUS = "−"


def esc(text):
    return html.escape("" if text is None else str(text), quote=True)


def money(v, dash="n/a"):
    """$12,400 for whole dollars; $63.50 when the source publishes cents (cash rents)."""
    if v is None:
        return dash
    if abs(v - round(v)) < 0.005:
        return "$" + "{:,}".format(int(round(v)))
    return "$" + "{:,.2f}".format(v)


def money_short(v):
    """Axis style: $950, $12K, $1.2M."""
    if v is None:
        return ""
    if v >= 1e6:
        return "$%sM" % ("%.1f" % (v / 1e6)).rstrip("0").rstrip(".")
    if v >= 10000:
        return "$%sK" % ("%.1f" % (v / 1e3)).rstrip("0").rstrip(".")
    return "$" + "{:,}".format(int(round(v)))


def num(v, dash="n/a"):
    if v is None:
        return dash
    return "{:,}".format(int(round(v)))


def pct(v, digits=1, dash="n/a", signed=True):
    """+15.3% / −4.2% with a real minus sign; 0 stays unsigned."""
    if v is None:
        return dash
    r = round(v, digits)
    if r == 0:
        return "0%"
    body = ("%.*f" % (digits, abs(r)))
    if abs(r) >= 100:
        body = "{:,}".format(int(round(abs(r))))
    sign = (MINUS if r < 0 else "+") if signed else (MINUS if r < 0 else "")
    return sign + body + "%"


def share(v, dash="n/a"):
    """0.299 -> 29.9%"""
    if v is None:
        return dash
    return ("%.1f" % (v * 100)).rstrip("0").rstrip(".") + "%"


def ordinal(n):
    n = int(n)
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "{:,}{}".format(n, suffix)


def direction(v, up="up", down="down", flat="unchanged"):
    if v is None:
        return ""
    r = round(v, 1)
    return up if r > 0 else down if r < 0 else flat


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")
