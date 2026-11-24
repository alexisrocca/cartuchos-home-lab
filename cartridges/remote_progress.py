"""Show host-launcher events on the Cartridges game details page."""
import subprocess
from threading import Thread
from time import time

from gi.repository import Adw, GLib, Gtk, Pango

from cartridges import shared
from cartridges.home_lab_stages import STAGES
from cartridges.remote_stream import RemoteStream


class LaunchProgress:
    def __init__(self, window):
        self.window = window
        self.game = None
        self.process = None
        self.pending = False
        self.error = None

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                           margin_top=12, margin_bottom=12, visible=False)
        self.status = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=210,
        )
        self.status_labels = []
        for index in range(2):
            label = Gtk.Label(xalign=0, single_line_mode=True,
                              ellipsize=Pango.EllipsizeMode.END)
            label.add_css_class("heading")
            self.status.add_named(label, str(index))
            self.status_labels.append(label)
        status_area = Gtk.Overlay(width_request=280, height_request=30)
        status_area.add_overlay(self.status)
        status_area.set_measure_overlay(self.status, False)
        self.box.append(status_area)
        self.action = Gtk.Button(label="Cancelar", halign=Gtk.Align.START, width_request=148)
        self.action.add_css_class("pill")
        self.action.connect("clicked", self.on_action)
        self.box.append(self.action)

        self.toolbar = window.details_view_play_button.get_parent()
        self.toolbar.get_parent().insert_child_after(self.box, self.toolbar)
        window.connect("close-request", self.on_close)

    def refresh(self):
        visible = self.game is not None and self.window.active_game is self.game
        visible = visible and (self.pending or bool(self.error))
        self.box.set_visible(visible)
        self.toolbar.set_visible(not visible)

    def on_close(self, _window):
        if self.pending:
            self.cancel()
        return False

    def cancel(self):
        if self.process:
            self.process.cancel()
        self.pending = False
        self.set_status("Cancelando…")
        self.action.set_sensitive(False)

    def on_action(self, _button):
        if self.error:
            self.game.launch()
        else:
            self.cancel()

    def start(self, game, settings):
        if self.process:
            shared.win.toast_overlay.add_toast(Adw.Toast.new("Ya hay una conexión del Home Lab en curso."))
            return
        self.game = game
        self.error = None
        self.pending = True
        self.action.set_label("Cancelar")
        self.action.set_sensitive(True)
        self.process = RemoteStream(settings)
        self.event("locate", "")
        Thread(target=self.run_stream, args=(self.process,), daemon=True).start()

    def run_stream(self, stream):
        try:
            stream.run(lambda stage: GLib.idle_add(self.event, stage, ""))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            GLib.idle_add(self.event, "error", str(error))
        finally:
            GLib.idle_add(self.finished)

    def set_status(self, text, tooltip=None, *, error=False):
        current = self.status.get_visible_child()
        if current.get_text() == text and current.has_css_class("error") == error:
            return
        next_label = self.status_labels[int(current is self.status_labels[0])]
        next_label.set_label(text)
        next_label.set_tooltip_text(tooltip or text)
        if error:
            next_label.add_css_class("error")
        else:
            next_label.remove_css_class("error")
        self.status.set_visible_child(next_label)

    def fail(self, message):
        self.pending = False
        self.error = message
        self.set_status("No se pudo abrir el juego", message, error=True)
        self.action.set_label("Reintentar")
        self.action.set_sensitive(True)
        self.refresh()

    def event(self, key, detail):
        if not self.pending:
            return
        if key == "error":
            self.fail(detail)
            return
        if key == "video":
            self.pending = False
            self.game.last_played = int(time())
            self.game.save()
            self.game.update()
            self.refresh()
            return
        if key not in STAGES:
            return
        title, description = STAGES[key]
        self.set_status(title, description)
        self.refresh()

    def finished(self):
        self.process = None
        if self.pending:
            self.fail("La conexión terminó antes de mostrar el juego.")
        self.refresh()
