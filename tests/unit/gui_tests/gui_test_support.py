"""Small headless customtkinter stand-ins used by GUI screen unit tests."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from uuid import uuid4


class FakeWidget:
    created: list["FakeWidget"] = []

    def __init__(self, master=None, **kwargs):
        self.master = master
        self.options = dict(kwargs)
        self.children: list[FakeWidget] = []
        self.grid_calls: list[dict] = []
        self.pack_calls: list[dict] = []
        self.grid_forget_count = 0
        self.destroyed = False
        self.content = ""
        self.title_text = ""
        self.geometry_text = ""
        self.transient_parent = None
        self.grabbed = False

        if master is not None and hasattr(master, "children"):
            master.children.append(self)

        type(self).created.append(self)

    def configure(self, **kwargs):
        self.options.update(kwargs)

    config = configure

    def grid(self, **kwargs):
        self.grid_calls.append(dict(kwargs))
        return self

    def pack(self, **kwargs):
        self.pack_calls.append(dict(kwargs))
        return self

    def grid_forget(self):
        self.grid_forget_count += 1

    def grid_columnconfigure(self, *_args, **_kwargs):
        return None

    def grid_rowconfigure(self, *_args, **_kwargs):
        return None

    def winfo_children(self):
        return list(self.children)

    def destroy(self):
        self.destroyed = True

        if self.master is not None and hasattr(self.master, "children"):
            try:
                self.master.children.remove(self)
            except ValueError:
                pass

    def winfo_toplevel(self):
        return self

    def title(self, text):
        self.title_text = text

    def geometry(self, text):
        self.geometry_text = text

    def transient(self, parent):
        self.transient_parent = parent

    def grab_set(self):
        self.grabbed = True

    def delete(self, *_args):
        self.content = ""

    def insert(self, _index, text):
        self.content += str(text)

    def get(self):
        return self.content

    def invoke(self):
        command = self.options.get("command")

        if command is not None:
            return command()

        return None


class FakeFrame(FakeWidget):
    pass


class FakeLabel(FakeWidget):
    pass


class FakeButton(FakeWidget):
    pass


class FakeCheckBox(FakeButton):
    pass


class FakeOptionMenu(FakeWidget):
    def __init__(self, master=None, values=None, **kwargs):
        super().__init__(master, values=values or [], **kwargs)
        self._value = (values or [""])[0] if values else ""

    def set(self, value):
        self._value = value

    def get(self):
        return self._value


class FakeEntry(FakeWidget):
    pass


class FakeTextbox(FakeWidget):
    pass


class FakeToplevel(FakeWidget):
    pass


class FakeBooleanVar:
    def __init__(self, value=False):
        self._value = bool(value)

    def get(self):
        return self._value

    def set(self, value):
        self._value = bool(value)


def make_fake_ctk() -> ModuleType:
    """Return a module-shaped fake that implements the widgets used by screens."""
    for widget_type in (
        FakeWidget,
        FakeFrame,
        FakeLabel,
        FakeButton,
        FakeCheckBox,
        FakeOptionMenu,
        FakeEntry,
        FakeTextbox,
        FakeToplevel,
    ):
        widget_type.created = []

    module = ModuleType("customtkinter")
    module.CTkFrame = FakeFrame
    module.CTkScrollableFrame = FakeFrame
    module.CTkLabel = FakeLabel
    module.CTkButton = FakeButton
    module.CTkOptionMenu = FakeOptionMenu
    module.CTkEntry = FakeEntry
    module.CTkTextbox = FakeTextbox
    module.CTkToplevel = FakeToplevel
    module.CTkCheckBox = FakeCheckBox
    module.BooleanVar = FakeBooleanVar

    return module


def load_screen_module(filename: str):
    """Load one screen module under a private name with fake customtkinter bases."""
    project_root = Path(__file__).resolve().parents[3]
    source_path = project_root / "src" / "gui" / filename
    module_name = f"_headless_{source_path.stem}_{uuid4().hex}"

    spec = importlib.util.spec_from_file_location(module_name, source_path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {source_path}")

    fake_ctk = make_fake_ctk()
    module = importlib.util.module_from_spec(spec)

    with patch.dict(sys.modules, {"customtkinter": fake_ctk}):
        spec.loader.exec_module(module)

    return module, fake_ctk


def widgets_with_text(widget_type, text: str):
    return [
        widget
        for widget in widget_type.created
        if widget.options.get("text") == text
    ]
