#!/usr/bin/env python3
"""
<summary>
Static checks for skin.functional: the cross reference checks that found the
September 2026 bugs, kept as a build gate. build_zip.py runs this before
packaging and refuses to build on any finding; it can also be run by hand:
    python3 checks/skin_checks.py
</summary>
<remarks>
Each check_* function returns a list of finding strings and touches no file.
A finding is a defect until an ALLOW_* entry below says otherwise, and every
allowance carries its reason so nobody has to rediscover it. The checks are
deliberately simple text and tree passes, not a Kodi emulator: they catch
the classes of mistake that have shipped before (an include parameter whose
default was written as value=, a navigation target that no longer exists once
includes are expanded, a string id missing from strings.po, a skin setting
whose name drifted between the XML and service.py, a helper call that no
longer resolves after a structural delete) and nothing subtler.

Exit status is the number of findings capped at 1, so a shell can gate on it.
</remarks>
"""
import ast
import builtins
import collections
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SKIN = os.path.join(REPO, "skin.functional")
XML_DIR = os.path.join(SKIN, "xml")
PO_PATH = os.path.join(SKIN, "language", "resource.language.en_gb", "strings.po")
SERVICE = os.path.join(SKIN, "service.py")
COLOURS = os.path.join(SKIN, "colors", "defaults.xml")
MEDIA = os.path.join(SKIN, "media")

# ---------------------------------------------------------------- allowances
# (file, id): DialogSeekBar carries Kodi's progress control id twice on purpose,
# one per position of the bar. Documented in PROJECT_NOTES.
ALLOW_DUPLICATE_IDS = {("DialogSeekBar.xml", "23")}
# Home properties another add-on writes; the skin only reads them.
ALLOW_PROPERTY_PREFIXES = ("JellyStat.",)
# Kodi's own "no texture" marker.
ALLOW_TEXTURES = {"-"}
# Focusable controls that may go without disabledcolor: none today. Add
# (file, id) pairs with a reason when one turns up.
ALLOW_NO_DISABLEDCOLOR = set()
# Skin settings the XML reads that only Kodi itself or the user ever sets.
ALLOW_UNSET_SETTINGS = set()

NAV_TAGS = ("onup", "ondown", "onleft", "onright", "onback", "oninfo")
FOCUSABLE = {"button", "radiobutton", "togglebutton", "spincontrol", "spincontrolex",
             "list", "panel", "wraplist", "fixedlist", "edit", "slider", "sliderex",
             "scrollbar", "colorbutton", "textbox", "grouplist"}
NEEDS_DISABLEDCOLOR = {"button", "radiobutton", "togglebutton", "spincontrolex",
                       "spincontrol", "sliderex", "edit", "colorbutton"}
COLOUR_TAGS = ("textcolor", "focusedcolor", "selectedcolor", "disabledcolor",
               "shadowcolor", "invalidcolor", "textcolorfocus", "textcolornofocus")
TEXTURE_TAGS = ("texture", "texturefocus", "texturenofocus", "texturebg", "lefttexture",
                "righttexture", "midtexture", "overlaytexture", "texturesliderbackground",
                "texturesliderbar", "texturesliderbarfocus", "textureslidernib",
                "textureslidernibfocus", "textureradioonfocus", "textureradioonnofocus",
                "textureradioofffocus", "textureradiooffnofocus", "textureradioondisabled",
                "textureradiooffdisabled", "alttexturefocus", "alttexturenofocus",
                "bordertexture", "imagefolder", "imagefolderfocus", "background")


def _read(path):
    """<summary>Read one UTF-8 text file.</summary>
    <param name="path">Absolute path.</param>
    <returns>The file's text.</returns>"""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _xml_files():
    """<summary>Every window and include file in the skin, sorted.</summary>
    <returns>List of absolute paths.</returns>"""
    return sorted(glob.glob(os.path.join(XML_DIR, "*.xml")))


def _trees():
    """<summary>Parse every skin XML file once.</summary>
    <returns>(dict of basename to ElementTree, list of parse error findings).</returns>"""
    trees, findings = {}, []
    for path in _xml_files():
        try:
            trees[os.path.basename(path)] = ET.parse(path)
        except ET.ParseError as exc:
            findings.append("{0}: not well formed: {1}".format(os.path.basename(path), exc))
    return trees, findings


def _include_defs(trees):
    """<summary>Named include definitions across all files.</summary>
    <param name="trees">Parsed files from _trees().</param>
    <returns>dict of name to (file, element); duplicates keep the first and are reported by check_includes.</returns>"""
    defs = {}
    for name, tree in trees.items():
        for el in tree.iter("include"):
            if el.get("name") and el.get("name") not in defs:
                defs[el.get("name")] = (name, el)
    return defs


def _subst(text, params):
    """<summary>Replace $PARAM[x] in text with the caller's values.</summary>
    <param name="text">Attribute or text content, may be None.</param>
    <param name="params">dict of parameter name to value.</param>
    <returns>The substituted text, empty for None.</returns>"""
    return re.sub(r"\$PARAM\[([A-Za-z0-9_]+)\]",
                  lambda m: params.get(m.group(1), ""), text or "")


def _expand(el, defs, params, depth=0, skip_conditional=False):
    """<summary>Copy of el with every include inlined and parameters substituted.</summary>
    <param name="el">Element to expand.</param>
    <param name="defs">Include definitions from _include_defs().</param>
    <param name="params">Parameters in force for this element.</param>
    <param name="depth">Recursion guard.</param>
    <returns>A new element tree; the original is untouched.</returns>
    <remarks>Defaults declared on the definition apply first, then the
    caller's param elements, then attribute style parameters, which is
    the order Kodi resolves them in.</remarks>"""
    if depth > 12:
        return el
    new = ET.Element(el.tag, {k: _subst(v, params) for k, v in el.attrib.items()})
    new.text = _subst(el.text, params)
    for child in el:
        if child.tag == "include" and not child.get("name") and not child.get("file"):
            if skip_conditional and child.get("condition"):
                continue
            name = child.get("content") or (child.text or "").strip()
            if name not in defs:
                continue
            definition = defs[name][1]
            merged = {p.get("name"): p.get("default") for p in definition.findall("param")
                      if p.get("default") is not None}
            for p in child.findall("param"):
                merged[p.get("name")] = _subst(p.get("value"), params)
            for key, value in child.attrib.items():
                if key not in ("content", "condition"):
                    merged[key] = _subst(value, params)
            for grandchild in _expand(definition, defs, merged, depth + 1, skip_conditional):
                if grandchild.tag != "param":
                    new.append(grandchild)
        elif child.tag != "param":
            new.append(_expand(child, defs, params, depth, skip_conditional))
    return new


def _variants(root, defs):
    """<summary>The expanded forms a window can take once Kodi picks its conditional includes.</summary>
    <param name="root">The window element.</param>
    <param name="defs">Include definitions.</param>
    <returns>List of (label, expanded element): the window with every
    conditional include left out, then one variant per conditional include
    with that include added, since Kodi resolves those at load time and a
    window such as DialogGameControllers is only ever one of them.</returns>"""
    base = _expand(root, defs, {}, skip_conditional=True)
    out = []
    for child in list(root.iter("include")):
        if child.get("condition") and not child.get("name") and not child.get("file"):
            name = child.get("content") or (child.text or "").strip()
            if name in defs:
                variant = ET.Element("window")
                for c in base:
                    variant.append(c)
                for c in _expand(defs[name][1], defs, {}):
                    if c.tag != "param":
                        variant.append(c)
                out.append((" [" + name + "]", variant))
    # A window with no conditional include is its own only variant; one that
    # is nothing but conditional includes has no bare form worth judging.
    return out or [("", base)]


# ------------------------------------------------------------------- checks
def check_includes(trees):
    """<summary>Include, parameter and variable cross references.</summary>
    <param name="trees">Parsed files.</param>
    <returns>Findings: unresolved or duplicate includes, value= on a definition
    parameter, duplicate parameters, parameters used without a default that a
    caller does not pass, unresolved or unused $VAR names.</returns>"""
    findings = []
    seen = collections.Counter()
    for name, tree in trees.items():
        for el in tree.iter("include"):
            if el.get("name"):
                seen[el.get("name")] += 1
    for inc, count in seen.items():
        if count > 1:
            findings.append("include {0} defined {1} times".format(inc, count))
    defs = _include_defs(trees)
    uses = collections.defaultdict(list)
    for name, tree in trees.items():
        for el in tree.iter("include"):
            if el.get("name") or el.get("file"):
                continue
            uses[el.get("content") or (el.text or "").strip()].append((name, el))
    for inc, callers in uses.items():
        if inc not in defs:
            findings.append("include {0} used in {1} but never defined".format(
                inc, sorted({c for c, _ in callers})))
    for inc in defs:
        if inc not in uses:
            findings.append("include {0} is defined but never used".format(inc))
    for inc, (where, el) in defs.items():
        declared, names = {}, []
        for p in el.findall("param"):
            names.append(p.get("name"))
            declared[p.get("name")] = p.get("default")
            if p.get("value") is not None:
                findings.append("include {0} declares param {1} with value=; a "
                                "definition default is default=".format(inc, p.get("name")))
        for dup, count in collections.Counter(names).items():
            if count > 1:
                findings.append("include {0} declares param {1} {2} times".format(inc, dup, count))
        used = set(re.findall(r"\$PARAM\[([A-Za-z0-9_]+)\]", ET.tostring(el, encoding="unicode")))
        for caller_file, caller in uses.get(inc, []):
            passed = {p.get("name") for p in caller.findall("param")}
            passed |= {k for k in caller.attrib if k not in ("content", "condition")}
            for param in used:
                if param not in passed and declared.get(param) is None:
                    findings.append("include {0}: $PARAM[{1}] has no default and {2} "
                                    "does not pass it".format(inc, param, caller_file))
    variables = set()
    for tree in trees.values():
        for el in tree.iter("variable"):
            if el.get("name"):
                variables.add(el.get("name"))
    var_uses = set()
    for path in _xml_files():
        var_uses |= set(re.findall(r"\$VAR\[([A-Za-z0-9_]+)", _read(path)))
    for var in sorted(var_uses - variables):
        findings.append("$VAR[{0}] is used but never defined".format(var))
    for var in sorted(variables - var_uses):
        findings.append("variable {0} is defined but never used".format(var))
    return findings


def check_strings():
    """<summary>strings.po against every string id the skin and service use.</summary>
    <returns>Findings: duplicate ids, 31xxx ids used but missing, orphan
    entries, and em or en dashes or a hyphen used as punctuation in an msgid.</returns>"""
    findings = []
    po = _read(PO_PATH)
    ids = {}
    for m in re.finditer(r'msgctxt "#(\d+)"\nmsgid "(.*)"\nmsgstr "(.*)"', po):
        number = int(m.group(1))
        if number in ids:
            findings.append("strings.po: id {0} appears twice".format(number))
        ids[number] = m.group(2)
    dash_chars = (chr(0x2014), chr(0x2013))
    for number, text in ids.items():
        if any(ch in text for ch in dash_chars):
            findings.append("strings.po {0}: contains an em or en dash: {1!r}".format(number, text))
        elif re.search(r"\S +- +\S", text):
            findings.append("strings.po {0}: hyphen used as punctuation: {1!r}".format(number, text))
    used = collections.defaultdict(set)
    for path in _xml_files():
        text = _read(path)
        base = os.path.basename(path)
        for m in re.finditer(r"\$LOCALIZE\[(\d+)\]", text):
            used[int(m.group(1))].add(base)
        for m in re.finditer(r"<(label|label2|description|altlabel|heading|hinttext)>\s*(\d+)\s*</\1>", text):
            used[int(m.group(2))].add(base)
        for m in re.finditer(r'\b(?:label|idloc)="(\d+)"', text):
            used[int(m.group(1))].add(base)
        for m in re.finditer(r"Skin\.SetColor\([^,)]+,(\d+)", text):
            used[int(m.group(1))].add(base)
    service = _read(SERVICE)
    for m in re.finditer(r"\b(31\d{3})\b", service):
        used[int(m.group(1))].add("service.py")
    for number in sorted(used):
        if 31000 <= number <= 31999 and number not in ids:
            findings.append("string {0} is used in {1} but missing from strings.po".format(
                number, sorted(used[number])))
    for number in sorted(ids):
        if number not in used:
            findings.append("strings.po {0} ({1!r}) is used nowhere".format(number, ids[number][:40]))
    return findings


def check_navigation(trees):
    """<summary>Every navigation target and id reference resolves once includes are expanded.</summary>
    <param name="trees">Parsed files.</param>
    <returns>Findings per window: duplicate ids outside the allowance, onup and
    friends pointing at missing ids, SetFocus and defaultcontrol targets that
    do not exist, and Control() or Container() references to missing ids.</returns>
    <remarks>A window with conditional includes is checked once per variant,
    since Kodi resolves those includes when the window loads and only one
    of them is ever present.</remarks>"""
    findings = []
    defs = _include_defs(trees)
    for fname, tree in trees.items():
        root = tree.getroot()
        if root.tag != "window":
            continue
        for suffix, expanded in _variants(root, defs):
            name = fname + suffix
            ids = collections.Counter()
            for control in expanded.iter("control"):
                if control.get("id") and control.get("id").strip():
                    ids[control.get("id").strip()] += 1
            for cid, count in ids.items():
                if count > 1 and (fname, cid) not in ALLOW_DUPLICATE_IDS:
                    findings.append("{0}: control id {1} appears {2} times".format(name, cid, count))
            for control in expanded.iter("control"):
                label = "{0} {1}".format(control.get("type"), control.get("id") or "(no id)")
                for node in control:
                    if node.tag in NAV_TAGS:
                        target = (node.text or "").strip()
                        if re.fullmatch(r"\d+", target) and target not in ids:
                            findings.append("{0}: {1} <{2}> points at missing id {3}".format(
                                name, label, node.tag, target))
                for node in control.iter():
                    if node.tag.startswith("on") and node.text:
                        for m in re.finditer(r"SetFocus\((\d+)", node.text):
                            if m.group(1) not in ids:
                                findings.append("{0}: {1} SetFocus({2}) targets a missing id".format(
                                    name, label, m.group(1)))
            for node in expanded.iter():
                if node.tag in ("onload", "onunload") and node.text:
                    for m in re.finditer(r"SetFocus\((\d+)", node.text):
                        if m.group(1) not in ids:
                            findings.append("{0}: <{1}> SetFocus({2}) targets a missing id".format(
                                name, node.tag, m.group(1)))
                if node.tag == "defaultcontrol" and node.text and node.text.strip() not in ids:
                    findings.append("{0}: defaultcontrol {1} does not exist".format(name, node.text.strip()))
            text = ET.tostring(expanded, encoding="unicode")
            refs = set(re.findall(r"Control\.(?:HasFocus|IsVisible|IsEnabled|GetLabel)\((\d+)\)", text))
            refs |= set(re.findall(r"Container\((\d+)\)", text))
            for ref in sorted(refs - set(ids)):
                findings.append("{0}: Control() or Container() reference to missing id {1}".format(name, ref))
    return findings


def check_settings_drift():
    """<summary>Skin setting and Home property names agree between the XML and service.py.</summary>
    <returns>Findings: a bool read but never set, toggled or reset anywhere; a
    string read but never written anywhere; a Home property the XML reads that
    service.py never mentions and no allowance covers.</returns>
    <remarks>service.py builds some names at run time, so "mentions" means the
    exact name appears as a literal anywhere in the file, or its first dotted
    segment does (the numbered families such as Fav.N.Label).</remarks>"""
    findings = []
    xml_text = {os.path.basename(p): _read(p) for p in _xml_files()}
    service = _read(SERVICE)
    # Every string literal in service.py. Ones with format placeholders
    # ({0}, {n}, {}, %s, %d) become patterns, so "bg_slot{0}_start" or
    # "%s.%d.Name" count as writing bg_slot1_start or Cast.1.Name.
    exact, patterns = set(), []
    for node in ast.walk(ast.parse(service)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literal = node.value
            if re.search(r"\{[^}]*\}|%[sd]", literal):
                patterns.append(re.compile(
                    "".join(".+?" if part in ("", None) or part.startswith("{") or part.startswith("%")
                            else re.escape(part)
                            for part in re.split(r"(\{[^}]*\}|%[sd])", literal)) + "$"))
            else:
                exact.add(literal)

    def names(pattern):
        found = collections.defaultdict(set)
        for fname, text in xml_text.items():
            for m in re.finditer(pattern, text):
                found[m.group(1)].add(fname)
        return found

    def mentioned(name):
        if name in ALLOW_UNSET_SETTINGS or name in exact:
            return True
        return any(p.match(name) for p in patterns)

    bool_read = names(r"Skin\.HasSetting\(([A-Za-z0-9_]+)\)")
    bool_set = names(r"Skin\.(?:SetBool|ToggleSetting|Reset)\(([A-Za-z0-9_]+)")
    for key in sorted(bool_read):
        if key not in bool_set and not mentioned(key):
            findings.append("setting {0} is read in {1} but never set anywhere".format(
                key, sorted(bool_read[key])))
    str_read = names(r"Skin\.String\(([A-Za-z0-9_]+)\)")
    str_set = names(r"Skin\.(?:SetString|SetImage|SetPath|SetNumeric|SetColor|Reset)\(([A-Za-z0-9_]+)")
    for key in sorted(str_read):
        if key not in str_set and not mentioned(key):
            findings.append("skin string {0} is read in {1} but never written anywhere".format(
                key, sorted(str_read[key])))
    prop_read = names(r"Window\((?:home|10000|Home)\)\.Property\(([A-Za-z0-9_.]+)\)")
    xml_set = set(re.findall(r"SetProperty\(([A-Za-z0-9_.]+),", "\n".join(xml_text.values())))
    for key in sorted(prop_read):
        if key.startswith(ALLOW_PROPERTY_PREFIXES) or key in xml_set:
            continue
        if mentioned(key):
            continue
        findings.append("Home property {0} is read in {1} but service.py never writes it".format(
            key, sorted(prop_read[key])))
    return findings


def check_visual(trees):
    """<summary>Colours, fonts, textures and disabledcolor.</summary>
    <param name="trees">Parsed files.</param>
    <returns>Findings: a colour name not in colors/defaults.xml, a font not in
    Font.xml, a texture file not under media/, and a focusable control that
    can be disabled but carries no disabledcolor (Kodi then draws no text).</returns>"""
    findings = []
    colours = set(re.findall(r'<color name="([^"]+)"', _read(COLOURS)))
    fonts = set(re.findall(r"<name>([^<]+)</name>", _read(os.path.join(XML_DIR, "Font.xml"))))
    media = set()
    for root, _dirs, files in os.walk(MEDIA):
        for fname in files:
            media.add(os.path.relpath(os.path.join(root, fname), MEDIA))
    for path in _xml_files():
        text = _read(path)
        base = os.path.basename(path)
        for m in re.finditer(r"<(%s)>([^<]*)</\1>" % "|".join(COLOUR_TAGS), text):
            value = m.group(2).strip()
            if value and not value.startswith("$") and not re.fullmatch(r"[0-9A-Fa-f]{8}", value) and value not in colours:
                findings.append("{0}: colour {1} is not defined".format(base, value))
        for m in re.finditer(r'colordiffuse="([^"]*)"', text):
            value = m.group(1).strip()
            if value and not value.startswith("$") and not re.fullmatch(r"[0-9A-Fa-f]{8}", value) and value not in colours:
                findings.append("{0}: colordiffuse {1} is not defined".format(base, value))
        for m in re.finditer(r"<font>([^<]*)</font>", text):
            value = m.group(1).strip()
            if value and not value.startswith("$") and value not in fonts:
                findings.append("{0}: font {1} is not defined".format(base, value))
        for m in re.finditer(r"<(%s)[^>]*>([^<$]*)</\1>" % "|".join(TEXTURE_TAGS), text):
            value = m.group(2).strip()
            if (value and value not in ALLOW_TEXTURES and "://" not in value
                    and not value.startswith("Default") and value not in media):
                findings.append("{0}: texture {1} is not under media/".format(base, value))
    defs = _include_defs(trees)
    for name, tree in trees.items():
        root = tree.getroot()
        if root.tag != "window":
            continue
        for control in _expand(root, defs, {}).iter("control"):
            if control.get("type") in NEEDS_DISABLEDCOLOR and control.find("disabledcolor") is None:
                if (name, control.get("id") or "") not in ALLOW_NO_DISABLEDCOLOR:
                    findings.append("{0}: {1} {2} has no disabledcolor".format(
                        name, control.get("type"), control.get("id") or "(no id)"))
    return findings


def check_service():
    """<summary>service.py resolves: every helper it calls exists, every function carries a summary.</summary>
    <returns>Findings: a bare name or self.method call that resolves to nothing,
    a self attribute read that is never assigned, a bare except:, a function
    without a summary tag, a mutable default argument.</returns>
    <remarks>This is the check that would have caught the dead service of
    September 2026, where a blanket except hid a removed helper and
    py_compile still passed.</remarks>"""
    findings = []
    source = _read(SERVICE)
    tree = ast.parse(source)
    module_names = set(dir(builtins))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for n in ast.walk(target):
                    if isinstance(n, ast.Name):
                        module_names.add(n.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                module_names.add((alias.asname or alias.name).split(".")[0])
    methods, class_attrs, funcs = set(), set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.add(item.name)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            class_attrs.add(target.id)
        if isinstance(node, ast.FunctionDef):
            funcs.append(node)
    assigned = {n.attr for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == "self" and isinstance(n.ctx, ast.Store)}
    known_self = methods | class_attrs | assigned

    def local_names(func):
        found = {a.arg for a in func.args.args + func.args.kwonlyargs}
        for n in ast.walk(func):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                found.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                found.add(n.name)
            elif isinstance(n, ast.arg):
                found.add(n.arg)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for alias in n.names:
                    found.add((alias.asname or alias.name).split(".")[0])
        return found

    for func in funcs:
        local = local_names(func)
        for n in ast.walk(func):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id not in module_names and n.func.id not in local:
                    findings.append("service.py:{0} {1}(): call to {2}() resolves to nothing".format(
                        n.lineno, func.name, n.func.id))
        docstring = ast.get_docstring(func)
        if not docstring or "<summary>" not in docstring:
            findings.append("service.py:{0} {1}(): no <summary> doc comment".format(func.lineno, func.name))
        for default in func.args.defaults + func.args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                findings.append("service.py:{0} {1}(): mutable default argument".format(func.lineno, func.name))
    seen = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "self" and node.attr not in known_self and node.attr not in seen):
            seen.add(node.attr)
            findings.append("service.py:{0} self.{1} is never defined".format(node.lineno, node.attr))
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append("service.py:{0} bare except:".format(node.lineno))
    return findings


def check_house_rules():
    """<summary>No em or en dash and no AI attribution in anything that ships.</summary>
    <returns>Findings with file and line.</returns>
    <remarks>The file set is what build_zip.py packs: the skin folder plus
    the tracked text files at the root. The attribution words are assembled
    at run time so this file does not trip the publish scan itself.</remarks>"""
    findings = []
    files = [p for p in glob.glob(os.path.join(SKIN, "**", "*"), recursive=True)
             if os.path.isfile(p) and p.endswith((".xml", ".py", ".po", ".txt", ".xsp"))]
    files += glob.glob(os.path.join(REPO, "*.md")) + glob.glob(os.path.join(REPO, "*.py"))
    files += glob.glob(os.path.join(HERE, "*.py"))
    attribution = re.compile("|".join(("cl" + "aude", "anthr" + "opic", "co-auth" + "ored-by",
                                       "generated " + "with")), re.IGNORECASE)
    skip = ("PROJECT_NOTES.md", "Packaging.md", "GITHUB-RELEASE-GUIDE.md")
    for path in sorted(set(files)):
        base = os.path.basename(path)
        if base in skip or base.startswith("CL" + "AUDE"):
            continue
        try:
            lines = _read(path).splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            if chr(0x2014) in line or chr(0x2013) in line:
                findings.append("{0}:{1}: em or en dash".format(os.path.relpath(path, REPO), number))
            if attribution.search(line):
                findings.append("{0}:{1}: AI attribution".format(os.path.relpath(path, REPO), number))
    return findings


def main():
    """<summary>Run every check, print the findings, exit 1 if there were any.</summary>
    <returns>Process exit status: 0 clean, 1 findings.</returns>"""
    trees, findings = _trees()
    results = [("well formed", findings)]
    if not findings:
        results += [("includes", check_includes(trees)),
                    ("strings", check_strings()),
                    ("navigation", check_navigation(trees)),
                    ("settings drift", check_settings_drift()),
                    ("visual", check_visual(trees)),
                    ("service", check_service()),
                    ("house rules", check_house_rules())]
    total = 0
    for name, found in results:
        print("{0:15s} {1}".format(name, "clean" if not found else "{0} finding(s)".format(len(found))))
        for item in found:
            print("    " + item)
        total += len(found)
    print("checks: {0}".format("all clean" if not total else "{0} finding(s)".format(total)))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
