"""The part of libxkbcommon the driver uses, through ctypes.

Same names and behaviour as `xkbcommon.xkb` from the python-xkbcommon
package, so the driver only changes its import; that package is built with
a compiler at install time and Ubuntu 24.04 has no package for it, while
libxkbcommon itself is on every desktop. Only what dialpad.py calls is here:
keymaps from RMLVO names or a buffer (the Wayland compositor's keymap),
keycode iteration, the per-key layout/level/modifier queries, keyboard
state and keysym names.
"""

import ctypes
import enum
import sys

_lib = ctypes.CDLL("libxkbcommon.so.0")

_uint32 = ctypes.c_uint32
_context_p = ctypes.c_void_p
_keymap_p = ctypes.c_void_p
_state_p = ctypes.c_void_p

XKB_CONTEXT_NO_FLAGS = 0
XKB_CONTEXT_NO_DEFAULT_INCLUDES = 1 << 0
XKB_CONTEXT_NO_ENVIRONMENT_NAMES = 1 << 1
XKB_CONTEXT_NO_SECURE_GETENV = 1 << 2
XKB_KEYMAP_FORMAT_TEXT_V1 = 1
XKB_KEYMAP_COMPILE_NO_FLAGS = 0
XKB_KEYSYM_CASE_INSENSITIVE = 1 << 0
XKB_KEY_NoSymbol = 0


class _RuleNames(ctypes.Structure):
    _fields_ = [(name, ctypes.c_char_p) for name in ("rules", "model", "layout", "variant", "options")]


_KEY_FOR_EACH = ctypes.CFUNCTYPE(None, _keymap_p, _uint32, ctypes.c_void_p)


def _function(name, restype, *argtypes):
    function = getattr(_lib, name)
    function.restype = restype
    function.argtypes = argtypes
    return function


_context_new = _function("xkb_context_new", _context_p, ctypes.c_int)
_context_unref = _function("xkb_context_unref", None, _context_p)
_keymap_new_from_names = _function(
    "xkb_keymap_new_from_names", _keymap_p, _context_p, ctypes.POINTER(_RuleNames), ctypes.c_int)
_keymap_new_from_buffer = _function(
    "xkb_keymap_new_from_buffer", _keymap_p, _context_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int)
_keymap_unref = _function("xkb_keymap_unref", None, _keymap_p)
_keymap_key_for_each = _function("xkb_keymap_key_for_each", None, _keymap_p, _KEY_FOR_EACH, ctypes.c_void_p)
_keymap_num_mods = _function("xkb_keymap_num_mods", _uint32, _keymap_p)
_keymap_mod_get_name = _function("xkb_keymap_mod_get_name", ctypes.c_char_p, _keymap_p, _uint32)
_keymap_num_layouts = _function("xkb_keymap_num_layouts", _uint32, _keymap_p)
_keymap_layout_get_name = _function("xkb_keymap_layout_get_name", ctypes.c_char_p, _keymap_p, _uint32)
_keymap_num_layouts_for_key = _function("xkb_keymap_num_layouts_for_key", _uint32, _keymap_p, _uint32)
_keymap_num_levels_for_key = _function("xkb_keymap_num_levels_for_key", _uint32, _keymap_p, _uint32, _uint32)
_keymap_key_get_mods_for_level = _function(
    "xkb_keymap_key_get_mods_for_level", ctypes.c_size_t,
    _keymap_p, _uint32, _uint32, _uint32, ctypes.POINTER(_uint32), ctypes.c_size_t)
_keymap_key_get_syms_by_level = _function(
    "xkb_keymap_key_get_syms_by_level", ctypes.c_int,
    _keymap_p, _uint32, _uint32, _uint32, ctypes.POINTER(ctypes.POINTER(_uint32)))
_state_new = _function("xkb_state_new", _state_p, _keymap_p)
_state_unref = _function("xkb_state_unref", None, _state_p)
_state_update_key = _function("xkb_state_update_key", ctypes.c_int, _state_p, _uint32, ctypes.c_int)
_state_mod_index_is_active = _function("xkb_state_mod_index_is_active", ctypes.c_int, _state_p, _uint32, ctypes.c_int)
_state_layout_index_is_active = _function(
    "xkb_state_layout_index_is_active", ctypes.c_int, _state_p, _uint32, ctypes.c_int)
_keysym_get_name = _function("xkb_keysym_get_name", ctypes.c_int, _uint32, ctypes.c_char_p, ctypes.c_size_t)
_keysym_from_name = _function("xkb_keysym_from_name", _uint32, ctypes.c_char_p, ctypes.c_int)


# python-xkbcommon keeps the pre-3.11 IntFlag behaviour (str() names the flag).
if sys.version_info < (3, 11):
    _IntFlag = enum.IntFlag
else:
    class _IntFlag(int, enum.Flag, boundary=enum.KEEP):
        pass


class XKBError(Exception):
    """Base for all XKB exceptions"""


class XKBBufferTooSmall(XKBError):
    pass


class XKBInvalidKeysym(XKBError):
    pass


class XKBKeymapCreationFailure(XKBError):
    """Unable to create a keymap."""


class XKBInvalidModifierIndex(XKBError):
    pass


class XKBInvalidLayoutIndex(XKBError):
    pass


@enum.unique
class KeyDirection(enum.IntEnum):
    XKB_KEY_UP = 0
    XKB_KEY_DOWN = 1


class StateComponent(_IntFlag):
    XKB_STATE_MODS_DEPRESSED = 1 << 0
    XKB_STATE_MODS_LATCHED = 1 << 1
    XKB_STATE_MODS_LOCKED = 1 << 2
    XKB_STATE_MODS_EFFECTIVE = 1 << 3
    XKB_STATE_LAYOUT_DEPRESSED = 1 << 4
    XKB_STATE_LAYOUT_LATCHED = 1 << 5
    XKB_STATE_LAYOUT_LOCKED = 1 << 6
    XKB_STATE_LAYOUT_EFFECTIVE = 1 << 7
    XKB_STATE_LEDS = 1 << 8


def keysym_get_name(keysym):
    "Get the name of a keysym."
    name = ctypes.create_string_buffer(64)
    r = _keysym_get_name(keysym, name, len(name))
    if r == -1:
        raise XKBInvalidKeysym()
    if r > len(name):
        raise XKBBufferTooSmall()
    return name.value.decode("ascii")


def keysym_from_name(name, case_insensitive=False):
    "Get a keysym from its name; XKB_KEY_NoSymbol (0) if there is none."
    flags = XKB_KEYSYM_CASE_INSENSITIVE if case_insensitive else 0
    return _keysym_from_name(name.encode("ascii"), flags)


class Context:
    """xkbcommon library context; every keymap is compiled in one.

    Unless no_environment_names is set, libxkbcommon fills RMLVO names left
    empty from XKB_DEFAULT_RULES/MODEL/LAYOUT/VARIANT/OPTIONS.
    """

    def __init__(self, no_default_includes=False, no_environment_names=False,
                 no_secure_getenv=False):
        flags = XKB_CONTEXT_NO_FLAGS
        if no_default_includes:
            flags |= XKB_CONTEXT_NO_DEFAULT_INCLUDES
        if no_environment_names:
            flags |= XKB_CONTEXT_NO_ENVIRONMENT_NAMES
        if no_secure_getenv:
            flags |= XKB_CONTEXT_NO_SECURE_GETENV
        self._context = _context_new(flags)
        if not self._context:
            raise XKBError("Couldn't create XKB context")

    def __del__(self, unref=_context_unref):
        if getattr(self, "_context", None):
            unref(self._context)
            self._context = None

    def keymap_new_from_names(self, rules=None, model=None, layout=None,
                              variant=None, options=None):
        """Create a keymap from RMLVO names (comma-separated layouts and
        variants). Raises XKBKeymapCreationFailure if it does not compile."""
        names = _RuleNames(*(value.encode() if value else None
                             for value in (rules, model, layout, variant, options)))
        r = _keymap_new_from_names(self._context, ctypes.byref(names), XKB_KEYMAP_COMPILE_NO_FLAGS)
        if not r:
            raise XKBKeymapCreationFailure("xkb_keymap_new_from_names returned NULL")
        return Keymap(self, r, "names")

    def keymap_new_from_buffer(self, buffer, format=XKB_KEYMAP_FORMAT_TEXT_V1, length=None):
        """Create a Keymap from a memory buffer (bytes, mmap, ...)."""
        data = bytes(memoryview(buffer)[:length] if length is not None else memoryview(buffer))
        r = _keymap_new_from_buffer(self._context, data, len(data), format, XKB_KEYMAP_COMPILE_NO_FLAGS)
        if not r:
            raise XKBKeymapCreationFailure("xkb_keymap_new_from_buffer returned NULL")
        return Keymap(self, r, "buffer")


class Keymap:
    """A compiled keymap; create it with a Context's keymap_new_ methods.

    Iterating over it yields every valid keycode.
    """

    def __init__(self, context, pointer, load_method):
        self.load_method = load_method
        # libxkbcommon keeps its own reference; this one keeps the Python
        # object (and the flags it was made with) alive as well.
        self._context = context
        self._keymap = pointer
        self._valid_keycodes = None

    def __del__(self, unref=_keymap_unref):
        if getattr(self, "_keymap", None):
            unref(self._keymap)
            self._keymap = None

    def __iter__(self):
        if self._valid_keycodes is None:
            keycodes = []
            callback = _KEY_FOR_EACH(lambda _keymap, key, _data: keycodes.append(key))
            _keymap_key_for_each(self._keymap, callback, None)
            self._valid_keycodes = keycodes
        return iter(self._valid_keycodes)

    def num_mods(self):
        return _keymap_num_mods(self._keymap)

    def mod_get_name(self, idx):
        r = _keymap_mod_get_name(self._keymap, idx)
        if r is None:
            raise XKBInvalidModifierIndex()
        return r.decode("ascii")

    def num_layouts(self):
        return _keymap_num_layouts(self._keymap)

    def layout_get_name(self, idx):
        """Name of a layout ("Polish"), None if it has none."""
        if idx >= self.num_layouts():
            raise XKBInvalidLayoutIndex()
        r = _keymap_layout_get_name(self._keymap, idx)
        return r.decode("utf-8") if r is not None else None

    def num_layouts_for_key(self, key):
        return _keymap_num_layouts_for_key(self._keymap, key)

    def num_levels_for_key(self, key, layout):
        return _keymap_num_levels_for_key(self._keymap, key, layout)

    def key_get_mods_for_level(self, key, layout, level):
        """Every modifier mask that gives this shift level."""
        size = 4
        while True:
            masks = (_uint32 * size)()
            r = _keymap_key_get_mods_for_level(self._keymap, key, layout, level, masks, size)
            if r < size:
                return list(masks[:r])
            size <<= 1

    def key_get_syms_by_level(self, key, layout, level):
        """The keysyms of a key in a given layout and shift level."""
        syms = ctypes.POINTER(_uint32)()
        r = _keymap_key_get_syms_by_level(self._keymap, key, layout, level, ctypes.byref(syms))
        return [syms[i] for i in range(r)] if r > 0 else []

    def state_new(self):
        return KeyboardState(self)


class KeyboardState:
    def __init__(self, keymap):
        state = _state_new(keymap._keymap)
        if not state:
            raise XKBError("Couldn't create keyboard state")
        self.keymap = keymap
        self._state = state

    def __del__(self, unref=_state_unref):
        if getattr(self, "_state", None):
            unref(self._state)
            self._state = None

    def get_keymap(self):
        return self.keymap

    def update_key(self, key, direction):
        """Press or release a key; returns the state components it changed."""
        return StateComponent(_state_update_key(self._state, key, direction))

    def mod_index_is_active(self, idx, type):
        r = _state_mod_index_is_active(self._state, idx, type)
        if r == -1:
            raise XKBInvalidModifierIndex()
        return r == 1

    def layout_index_is_active(self, idx, type):
        r = _state_layout_index_is_active(self._state, idx, type)
        if r == -1:
            raise XKBInvalidLayoutIndex()
        return r == 1
