# Copyright 2011, Dan Gindikin <dgindikin@gmail.com>
# Copyright 2012, Jono Finger <jono@foodnotblogs.com>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
"""textmap is a Python3 plugin for Gedit.

This plugin is used for displaying a 10,000 foot view of your code in the
sidebar.  It is based on Dan Gindikin's original code, but has been updated
to work with Gedit 3.

To install this plugin copy the files into ~/.local/share/gedit/plugins/ and
restart Gedit. Then activate the plugin through the preferences.

"""

__version__ = "0.2 beta - gtk3"

import cairo

from gi.repository import Gtk, GdkPixbuf, Gdk, GtkSource, Gio, Gedit, GObject


def document_lines(document):
    if not document:
        return None

    return document.get_property('text').split('\n')


def visible_lines_top_bottom(geditwin):
    view = geditwin.get_active_view()
    rect = view.get_visible_rect()
    topiter = view.get_line_at_y(rect.y)[0]
    botiter = view.get_line_at_y(rect.y + rect.height)[0]
    return topiter.get_line(), botiter.get_line()


def is_dark(red, green, blue):
    """ This function determines if an rgb value is dark or not.
    """
    if red + green + blue < 1.5:
        return True
    else:
        return False


def darken(fraction, r, g, b):
    return (
        r - fraction * r,
        g - fraction * g,
        b - fraction * b
    )


def lighten(fraction, r, g, b):
    return (
        r + (1 - r) * fraction,
        g + (1 - g) * fraction,
        b + (1 - b) * fraction
    )


def queue_refresh(textmapview):
    try:
        win = textmapview.darea.get_window()
    except AttributeError:
        win = textmapview.darea.window
    if win:
        textmapview.darea.queue_draw_area(0, 0, win.get_width(),
                                          win.get_height())


def str2rgb(s):
    assert s.startswith('#') and len(s) == 7, ('not a color string', s)
    r = int(s[1:3], 16) / 256.
    g = int(s[3:5], 16) / 256.
    b = int(s[5:7], 16) / 256.
    return r, g, b


class TextmapView(Gtk.VBox):
    def __init__(self, geditwin):
        Gtk.VBox.__init__(self)

        self.geditwin = geditwin

        self.geditwin.connect("active-tab-changed", self.tab_changed)
        self.geditwin.connect("tab-added", self.tab_added)

        darea = Gtk.DrawingArea()
        darea.connect("draw", self.draw)

        darea.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        darea.connect("button-press-event", self.button_press)
        darea.connect("scroll-event", self.on_darea_scroll_event)

        darea.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        darea.connect("motion-notify-event", self.on_darea_motion_notify_event)

        self.pack_start(darea, True, True, 0)

        self.show_all()

        self.topL = None
        self.botL = None
        self.scale = 4  # TODO: set this smartly somehow
        self.darea = darea

        self.winHeight = 0
        self.winWidth = 0
        self.linePixelHeight = 0

        self.currentDoc = None
        self.currentView = None

    def tab_added(self, window, tab):
        self.currentView = tab.get_view()
        self.currentDoc = tab.get_document()

        self.currentDoc.connect(
            'changed',
            self.on_doc_changed
        )

        self.currentView.get_vadjustment().connect(
            'value-changed',
            self.on_vadjustment_changed
        )

# TODO: make sure value-changed is not conflicting with darea move events

    def tab_changed(self, window, event):
        self.currentView = self.geditwin.get_active_view()
        self.currentDoc = self.geditwin.get_active_tab().get_document()

        self.lines = document_lines(self.currentDoc)
        queue_refresh(self)

    def on_doc_changed(self, buffer):
        self.lines = document_lines(self.currentDoc)
        queue_refresh(self)

    def on_vadjustment_changed(self, adjustment):
        queue_refresh(self)

    def on_darea_motion_notify_event(self, widget, event):
        "used for clicking and dragging"

        if event.state & Gdk.ModifierType.BUTTON1_MASK:
            self.scroll_from_y_mouse_pos(event.y)

    def on_darea_scroll_event(self, widget, event):

# TODO: match this to self.currentView.get_vadjustment().get_page_size()
        pagesize = 12
        topL, botL = visible_lines_top_bottom(self.geditwin)
        if event.direction == Gdk.ScrollDirection.UP and topL > pagesize:
            newI = topL - pagesize
        elif event.direction == Gdk.ScrollDirection.DOWN:
            newI = botL + pagesize
        else:
            return

        self.currentView.scroll_to_iter(
            self.currentDoc.get_iter_at_line_index(newI, 0), 0, False, 0, 0)

        queue_refresh(self)

    def scroll_from_y_mouse_pos(self, y):

        self.currentView.scroll_to_iter(
            self.currentDoc.get_iter_at_line_index(
                int(
                    (
                        len(self.lines) + (self.botL - self.topL)
                    ) * y / self.winHeight
                ),
                0
            ),
            0,
            True,
            0,
            0.5
        )
        queue_refresh(self)

    def button_press(self, widget, event):
        self.scroll_from_y_mouse_pos(event.y)

    def draw(self, widget, cr):

        if not self.currentDoc or not self.currentView:  # nothing open yet
            return

        bg = (0, 0, 0)
        fg = (1, 1, 1)
        try:
            style = self.currentDoc.get_style_scheme().get_style('text')
            # there is a style scheme, but it does not specify default
            if style is None:
                bg = (1, 1, 1)
                fg = (0, 0, 0)
            else:
                fg, bg = map(
                    str2rgb,
                    style.get_properties('foreground', 'background'))

        except:
            pass  # probably an older version of gedit, no style schemes yet

        try:
            win = widget.get_window()
        except AttributeError:
            win = widget.window

        cr = win.cairo_create()

        self.winHeight = win.get_height()
        self.winWidth = win.get_width()

        cr.push_group()

        # draw the background
        cr.set_source_rgb(*bg)
        cr.move_to(0, 0)
        cr.rectangle(0, 0, self.winWidth, self.winHeight)
        cr.fill()
        cr.move_to(0, 0)

        if not self.lines:
            return

        # draw the text
        cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(self.scale)

        if self.linePixelHeight == 0:
            self.linePixelHeight = cr.text_extents("L")[
                3]  # height # TODO: make this more global

        self.topL, self.botL = visible_lines_top_bottom(self.geditwin)

        if is_dark(*fg):
            faded_fg = lighten(.5, *fg)
        else:
            faded_fg = darken(.5, *fg)

        cr.set_source_rgb(*fg)

        textViewLines = int(self.winHeight / self.linePixelHeight)

        firstLine = self.topL - int(
            (textViewLines - (self.botL - self.topL)) *
            float(self.topL) / float(len(self.lines))
        )

        if firstLine < 0:
            firstLine = 0

        lastLine = firstLine + textViewLines
        if lastLine > len(self.lines):
            lastLine = len(self.lines)

        sofarH = 0

        for i in range(firstLine, lastLine, 1):
            cr.show_text(self.lines[i])
            sofarH += self.linePixelHeight
            cr.move_to(0, sofarH)

        cr.set_source(cr.pop_group())
        cr.rectangle(0, 0, self.winWidth, self.winHeight)
        cr.fill()

        # draw the scrollbar
        topY = (self.topL - firstLine) * self.linePixelHeight

        if topY < 0:
            topY = 0

        botY = topY + self.linePixelHeight * (self.botL - self.topL)
        # TODO: handle case   if botY > ?

        cr.set_source_rgba(.3, .3, .3, .35)
        cr.rectangle(0, topY, self.winWidth, botY - topY)
        cr.fill()
        cr.stroke()


class TextmapWindowHelper:
    def __init__(self, plugin, window):
        self.window = window
        self.plugin = plugin

        panel = self.window.get_side_panel()
        image = Gtk.Image()
        image.set_from_stock(Gtk.STOCK_DND_MULTIPLE, Gtk.IconSize.BUTTON)
        self.textmapview = TextmapView(self.window)
        self.ui_id = panel.add_titled(self.textmapview, "TextMap", "textMap")

        self.panel = panel

    def deactivate(self):
        self.window = None
        self.plugin = None
        self.textmapview = None

    def update_ui(self):
        queue_refresh(self.textmapview)


class WindowActivatable(GObject.Object, Gedit.WindowActivatable):
    window = GObject.property(type=Gedit.Window)

    def __init__(self):
        GObject.Object.__init__(self)
        self._instances = {}

    def do_activate(self):
        self._instances[self.window] = TextmapWindowHelper(self, self.window)

    def do_deactivate(self):
        if self.window in self._instances:
            self._instances[self.window].deactivate()

    def update_ui(self):
        if self.window in self._instances:
            self._instances[self.window].update_ui()
