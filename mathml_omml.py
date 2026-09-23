"""
Mini-LaTeX-like DSL -> MathML -> (via real Microsoft MML2OMML.XSL) -> OMML.
This guarantees schema-valid Word Math objects, since the XSLT is the
actual converter Microsoft ships with Office.

Supported DSL: ^{..} / ^x superscript, _{..} / _x subscript, \\frac{a}{b},
\\sqrt{x}, \\sqrt[n]{x}, {...} grouping, literal text/digits/operators,
unicode symbols typed directly (± ≤ ≥ ≠ · ÷ √ Δ etc.)
"""
import re
import os
from lxml import etree

MMLNS = "http://www.w3.org/1998/Math/MathML"
_XSLT_PATH = os.path.join(os.path.dirname(__file__), 'MML2OMML.XSL')
_xslt_transform = etree.XSLT(etree.parse(_XSLT_PATH))


def mml(tag, *children, text=None, **attrib):
    e = etree.Element(f"{{{MMLNS}}}{tag}")
    for k, v in attrib.items():
        e.set(k, v)
    if text is not None:
        e.text = text
    for c in children:
        if c is not None:
            e.append(c)
    return e


def _digits_or_op(tok):
    return mml('mn', text=tok) if re.fullmatch(r'[0-9]+([.,][0-9]+)?', tok) else mml('mo', text=tok)


def _emit_plain(text):
    """Split literal text into <mi> (letters) and <mn>/<mo> (digits/symbols) tokens."""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isalpha():
            j = i
            while j < n and text[j].isalpha():
                j += 1
            out.append(mml('mi', text=text[i:j]))
            i = j
        elif ch == ' ':
            i += 1
        else:
            j = i
            while j < n and (text[j].isdigit() or text[j] in '.,'):
                j += 1
            if j > i:
                out.append(mml('mn', text=text[i:j]))
                i = j
            else:
                out.append(mml('mo', text=ch))
                i += 1
    return out


class _P:
    def __init__(self, s):
        self.s, self.i, self.n = s, 0, len(s)

    def peek(self):
        return self.s[self.i] if self.i < self.n else ''

    def parse(self, stop=''):
        out = []
        buf = ''
        while self.i < self.n and self.s[self.i] not in stop:
            ch = self.s[self.i]
            if ch == '\\':
                if buf:
                    out.extend(_emit_plain(buf)); buf = ''
                out.append(self.cmd())
                continue
            if ch == '{':
                if buf:
                    out.extend(_emit_plain(buf)); buf = ''
                self.i += 1
                grp = self.parse(stop='}')
                self.i += 1  # skip }
                out.extend(self._scripts(grp))
                continue
            if ch in ('^', '_'):
                if buf:
                    base_char = buf[-1]
                    if len(buf) > 1:
                        out.extend(_emit_plain(buf[:-1]))
                    base = _emit_plain(base_char)
                    buf = ''
                else:
                    base = [out.pop()] if out else [mml('mi', text='')]
                out.extend(self._scripts(base))
                continue
            buf += ch
            self.i += 1
        if buf:
            out.extend(_emit_plain(buf))
        return out

    def _scripts(self, base):
        if self.peek() not in ('^', '_'):
            return base
        sup = sub = None
        while self.peek() in ('^', '_'):
            kind = self.s[self.i]; self.i += 1
            if self.peek() == '{':
                self.i += 1
                content = self.parse(stop='}')
                self.i += 1
            elif self.peek() == '\\':
                content = [self.cmd()]
            else:
                c = self.peek(); self.i += 1
                content = _emit_plain(c)
            if kind == '^':
                sup = content
            else:
                sub = content
        base_row = base[0] if len(base) == 1 else mml('mrow', *base)
        if sup is not None and sub is not None:
            sup_row = sup[0] if len(sup) == 1 else mml('mrow', *sup)
            sub_row = sub[0] if len(sub) == 1 else mml('mrow', *sub)
            return [mml('msubsup', base_row, sub_row, sup_row)]
        elif sup is not None:
            sup_row = sup[0] if len(sup) == 1 else mml('mrow', *sup)
            return [mml('msup', base_row, sup_row)]
        else:
            sub_row = sub[0] if len(sub) == 1 else mml('mrow', *sub)
            return [mml('msub', base_row, sub_row)]

    def cmd(self):
        self.i += 1  # skip backslash
        m = re.match(r'[a-zA-Z]+', self.s[self.i:])
        name = m.group(0)
        self.i += len(name)
        if name == 'frac':
            self.i += 1  # {
            num = self.parse(stop='}'); self.i += 1
            self.i += 1  # {
            den = self.parse(stop='}'); self.i += 1
            num_row = num[0] if len(num) == 1 else mml('mrow', *num)
            den_row = den[0] if len(den) == 1 else mml('mrow', *den)
            return mml('mfrac', num_row, den_row)
        elif name == 'sqrt':
            deg = None
            if self.peek() == '[':
                self.i += 1
                deg = self.parse(stop=']'); self.i += 1
            self.i += 1  # {
            content = self.parse(stop='}'); self.i += 1
            content_row = content[0] if len(content) == 1 else mml('mrow', *content)
            if deg is None:
                return mml('msqrt', content_row)
            else:
                deg_row = deg[0] if len(deg) == 1 else mml('mrow', *deg)
                return mml('mroot', content_row, deg_row)
        else:
            syms = {'pm': '\u00B1', 'le': '\u2264', 'ge': '\u2265', 'ne': '\u2260',
                    'times': '\u00D7', 'div': '\u00F7', 'cdot': '\u00B7', 'Delta': '\u0394'}
            if name in syms:
                return mml('mo', text=syms[name])
            raise ValueError(f"unknown command \\{name}")


def latex_to_mathml(latex):
    p = _P(latex)
    elems = p.parse()
    row = elems[0] if len(elems) == 1 else mml('mrow', *elems)
    root = mml('math', row)
    return root


def latex_to_omath(latex):
    """Return an <m:oMath> lxml element (already namespaced) for the given DSL string."""
    mathml_root = latex_to_mathml(latex)
    result = _xslt_transform(mathml_root)
    return result.getroot()


def insert_inline_math(paragraph, latex):
    """Append a real Word Math object inline to a python-docx Paragraph."""
    omath = latex_to_omath(latex)
    paragraph._p.append(omath)
    return omath


def insert_inline_math_in_cell_paragraph(paragraph, latex):
    return insert_inline_math(paragraph, latex)
