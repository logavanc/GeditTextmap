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

import time
import sys
import math
import cairo
import re
import copy
import platform

from gi.repository import Gtk, GdkPixbuf, Gdk, GtkSource, Gio, Gedit, GObject

version = "0.2 beta - gtk3"

# ------------------------------------------------------------------------------

class struct:pass

# Timers are used for debugging rendering times
class TimeRec:
  def __init__(M):
    M.tot = M.N = M.childtot = M.heretot = 0
    M.start_ = None
    
class Timer:
  'L == label'
  def __init__(M):
    M.dat = {}
    M.stack = []
  def push(M,L):
    assert L not in M.stack,(L,M.stack)
    M.stack.append(L)
    tmrec = M.dat.setdefault(L,TimeRec())
    tmrec.start_=time.time()
  def pop(M,L):
    assert M.stack[-1]==L,(L,M.stack)
    M.stack.pop()
    tmrec = M.dat[L]
    dur = time.time()-tmrec.start_
    tmrec.start_ = None
    tmrec.tot += dur
    tmrec.N += 1
    #for parent in M.stack:
    #  M.dat[parent].childtot += dur
    if M.stack != []:
      M.dat[M.stack[-1]].childtot += dur
  def print_(M):
    for tmrec in M.dat.values():
      tmrec.heretot = tmrec.tot-tmrec.childtot
    R = sorted(M.dat.items(),lambda x,y:-cmp(x[1].heretot,y[1].heretot))
    print ('%7s %7s %5s' % ('Tm Here', 'Tm Avg', 'Count'))
    for L,tmrec in R:
      print ('%7s %7s %5d %s' % ('%.3f'%tmrec.heretot, '%.3f'%(tmrec.heretot/float(tmrec.N)), tmrec.N, L))
    print ()

#TIMER = Timer()
TIMER = None
   
def indent(s):
  x = 0
  for c in s:
    if c == ' ':
      x += 1
    elif c == '\t':
      x += 8
    else:
      break
  return x
  
def probj(ob,*substrs):
  meths = dir(ob)
  meths.sort()
  print (ob,type(ob))
  for m in meths:
    doprint=True
    if substrs:
      doprint=False
      for s in substrs:
        if s in m:
          doprint=True
          break
    if doprint:
      print ('%40s'%m)
      
def match_RE_list(str, REs):
  for r in REs:
    m = r.match(str)
    if m:
      return m.groups()[0]
  return None

def document_lines(document):
  if not document:
    return None
  #print 'document_lines',document
  STR = document.get_property('text')
  lines = STR.split('\n')
  ans = []
  for i,each in enumerate(lines):

    x = struct()
    x.i = i
    x.len = len(each)
    x.raw = each
    x.search_match = False

    ans.append(x)
  return ans

  
BUG_MASK = 0

BUG_CAIRO_MAC_FONT_REF  = 1
BUG_CAIRO_TEXT_EXTENTS  = 2
BUG_DOC_GET_SEARCH_TEXT = 4

if platform.system() == 'Darwin':
  BUG_MASK |= BUG_CAIRO_MAC_FONT_REF  # extra decref causes aborts, use less font ops

# major,minor,patch = Gedit.version
# if major<=2 and minor<28:
#   BUG_MASK |= BUG_CAIRO_TEXT_EXTENTS  # some reference problem
#   BUG_MASK |= BUG_DOC_GET_SEARCH_TEXT # missing INCREF then
  
def text_extents(str,cr):
  "code around bug in older cairo"
  
  if BUG_MASK & BUG_CAIRO_TEXT_EXTENTS:  
    if str:
      x, y = cr.get_current_point()
      cr.move_to(0,-5)
      cr.show_text(str)
      nx,ny = cr.get_current_point()
      cr.move_to(x,y)
    else:
      nx = 0
      ny = 0

    #print repr(str),x,nx,y,ny
    ascent, descent, height, max_x_advance, max_y_advance = cr.font_extents()
    
    return nx, height
  
  else:
  
    x_bearing, y_bearing, width, height, x_advance, y_advance = cr.text_extents(str)
    return width, height
    
def pr_text_extents(s,cr):
  x_bearing, y_bearing, width, height, x_advance, y_advance = cr.text_extents(s)
  print (repr(s),':','x_bearing',x_bearing,'y_bearing',y_bearing,'width',width,'height',height,'x_advance',x_advance,'y_advance',y_advance)
    
def fit_text(str, w, h, fg, bg, cr):
  moved_down = False
  originalx,_ = cr.get_current_point()
  sofarH = 0
  rn = []
  if dark(*bg):
    bg_rect_C = lighten(.1,*bg)
  else:
    bg_rect_C = darken(.1,*bg)
    
  while 1:
    # find the next chunk of the string that fits
    for i in range(len(str)):
      tw, th = text_extents(str[:i],cr)
      if tw > w:
        break
    disp = str[:i+1]
    str = str[i+1:]
    tw, th = text_extents(disp,cr)
    
    sofarH += th
    if sofarH > h:
      return rn
    if not moved_down:
      moved_down = True
      cr.rel_move_to(0, th)
      
    # bg rectangle
    x,y = cr.get_current_point()
    #cr.set_source_rgba(46/256.,52/256.,54/256.,.75)
    cr.set_source_rgba(bg_rect_C[0],bg_rect_C[1],bg_rect_C[2],.75)
    if str:
      cr.rectangle(x,y-th+2,tw,th+3)
    else: # last line does not need a very big rectangle
      cr.rectangle(x,y-th+2,tw,th)    
    cr.fill()
    cr.move_to(x,y)
    
    # actually display
    cr.set_source_rgb(*fg)
    cr.show_text(disp)
    
    # remember
    rec = struct()
    rec.x = x
    rec.y = y
    rec.th = th
    rec.tw = tw
    rn.append(rec)
    
    cr.rel_move_to(0,th+3)
    x,y = cr.get_current_point()
    cr.move_to(originalx,y)
    
    if not str:
      break
  return rn
      
def downsample_lines(lines, h, min_scale, max_scale):
  n = len(lines)
  
  # pick scale
  for scale in range(max_scale,min_scale-1,-1): 
    maxlines_ = h/(.85*scale)
    if n < 2*maxlines_:
      break
      
  if n <= maxlines_:
    downsampled = False
    return lines, scale, downsampled
    
  # need to downsample
  lines[0].score = sys.maxint # keep the first line
  for i in range(1, len(lines)):

    if lines[i].changed or lines[i].search_match:
      lines[i].score = sys.maxint/2
    else:
      if 1: # get rid of lines randomly
        lines[i].score = hash(lines[i].raw)
        if lines[i].score > sys.maxint/2:
          lines[i].score -= sys.maxint/2
                     
  scoresorted = sorted(lines, lambda x,y: cmp(x.score,y.score))
  erasures_ = int(math.ceil(n - maxlines_))
  #print 'erasures_',erasures_
  scoresorted[0:erasures_]=[]
    
  downsampled = True
  
  return sorted(scoresorted, lambda x,y:cmp(x.i,y.i)), scale, downsampled
      
def visible_lines_top_bottom(geditwin):
  view = geditwin.get_active_view()
  rect = view.get_visible_rect()
  topiter = view.get_line_at_y(rect.y)[0]
  botiter = view.get_line_at_y(rect.y+rect.height)[0]
  return topiter.get_line(), botiter.get_line()
      
def dark(r,g,b):
  "return whether the color is light or dark"
  if r+g+b < 1.5:
    return True
  else:
    return False
    
def darken(fraction,r,g,b):
  return r-fraction*r,g-fraction*g,b-fraction*b
  
def lighten(fraction,r,g,b):
  return r+(1-r)*fraction,g+(1-g)*fraction,b+(1-b)*fraction
  
def scrollbar(lines,topI,botI,w,h,bg,cr,scrollbarW=10):

  "highlights where in the textmap we are scrolled to"

  # figure out location
  topY = None
  botY = None
  for line in lines:
    if not topY:
      if line.i >= topI:
        topY = line.y
    if not botY:
      if line.i >= botI:
        botY = line.y
  
  if topY is None:
    topY = 0
  if botY is None:
    botY = lines[-1].y
  
  if 1: # view indicator  
    cr.set_source_rgba(.3,.3,.3,.35)
    #cr.set_source_rgba(.1,.1,.1,.35)
    cr.rectangle(0,topY,w,botY-topY)
    cr.fill()
    cr.stroke()

  if dark(*bg):
    color = (1,1,1)
  else:
    color = (0,0,0)
    
        
def queue_refresh(textmapview):
  try:
    win = textmapview.darea.get_window()
  except AttributeError:
    win = textmapview.darea.window
  if win:
#    w,h = win.get_size()
    textmapview.darea.queue_draw_area(0,0,win.get_width(),win.get_height())
    
def str2rgb(s):
  assert s.startswith('#') and len(s)==7,('not a color string',s)
  r = int(s[1:3],16)/256.
  g = int(s[3:5],16)/256.
  b = int(s[5:7],16)/256.
  return r,g,b
  
def init_original_lines_info(doc,lines):
  rn = []
  # now we insert marks at the end of every line
  iter = doc.get_start_iter()
  n = 0
  while 1:
    if n>=len(lines):
      break
    more_left = iter.forward_line()
    rec = struct()
    lines[n].mark = doc.create_mark(None,iter,False) 
    n+=1
    if not more_left:
      break
  assert n>=len(lines)-1,(n,len(lines),'something off with our iterator logic')
  if n==len(lines)-1:
    lines[-1].mark=doc.create_mark(None,doc.get_end_iter(),False)
  return lines
  
def mark_changed_lines(doc,original,current):
  'unfortunate choice of name, has nothing to do with GtkTextBuffer marks'

  # presume all current lines are changed
  for line in current:
    line.changed = True
  
  # mark any original lines we find as unchanged
  start = doc.get_start_iter()
  c=0
  for oline in original:
    end = doc.get_iter_at_mark(oline.mark)
    slice = doc.get_slice(start, end, False)
    # see if the first line between the marks is the original line
    if slice.split('\n',1)[0] == oline.raw:
      current[c].changed = False
    # forward through all the slice lines
    c += slice.count('\n')

    start = end

  return current
      
def lines_mark_search_matches(lines,docrec):
  for line in lines:
    if docrec.search_text and docrec.search_text in line.raw:
      line.search_match = True
    else:
      line.search_match = False
  return lines
  
Split_Off_Indent_Pattern = re.compile('(\s*)(.*)$')
      
class TextmapView(Gtk.VBox):
  def __init__(me, geditwin):
    Gtk.VBox.__init__(me)
    
    me.geditwin = geditwin
    
    darea = Gtk.DrawingArea()
    darea.connect("draw", me.draw)
    
    darea.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    darea.connect("button-press-event", me.button_press)
    darea.connect("scroll-event", me.on_darea_scroll_event)

    darea.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
    darea.connect("motion-notify-event", me.on_darea_motion_notify_event)
    
    
    me.pack_start(darea, True, True, 0)
    
    me.darea = darea
    #probj(me.darea)

    me.connected = {}
    me.draw_scrollbar_only = False
    me.draw_sections = False
    me.topL = None
    me.surface_textmap = None
    
    me.line_count = 0
    
    me.doc_attached_data = {}
    
    me.show_all()
    
    # need this bc of a cairo bug, keep references to all our font faces
    me.font_face_keepalive = None
    
     #'''
     #   gtk.gdk.SCROLL_UP, 
     #  gtk.gdk.SCROLL_DOWN, 
     #  gtk.gdk.SCROLL_LEFT, 
     #  gtk.gdk.SCROLL_RIGHT
   #
     #Example:
   #
     #  def on_button_scroll_event(button, event):
     #    if event.direction == gtk.gdk.SCROLL_UP:
     #       print "You scrolled up"
     #       
     #event = gtk.gdk.Event(gtk.gdk.EXPOSE)
     #
     #      def motion_notify(ruler, event):
     #          return ruler.emit("motion_notify_event", event)
     #      self.area.connect_object("motion_notify_event", motion_notify,
     #                               self.hruler)
     #      self.area.connect_object("motion_notify_event", motion_notify,
     #                               self.vruler)
     #'''
  
  def on_darea_motion_notify_event(me, widget, event):
    # used for clicking and dragging
    
    # TODO: speed this up

    if event.state & Gdk.ModifierType.BUTTON1_MASK:
      #print (event.y)
      me.scroll_from_y_mouse_pos(event.y)
    
  def on_darea_scroll_event(me, widget, event):
    
    #print ('on_darea_scroll_event ' , event.y)
    #pass
    # this scheme does not work
    # somehow pass this on, scroll the document/view
    #print type(widget),widget,type(event),event
    #probj(event)
    # view = me.geditwin.get_active_view()
    # if not view:
    #   return
    # return view.emit('scroll-event',event)

    pagesize = 12
    topI,botI = visible_lines_top_bottom(me.geditwin)
    if event.direction == Gdk.ScrollDirection.UP and topI > pagesize:
      newI = topI - pagesize
    elif event.direction == Gdk.ScrollDirection.DOWN:
      newI = botI + pagesize
    else:
      return
      
    view = me.geditwin.get_active_view()
    doc  = me.geditwin.get_active_tab().get_document()
    view.scroll_to_iter(doc.get_iter_at_line_index(newI,0),0,False,0,0)
    
    queue_refresh(me)
    
  def on_doc_cursor_moved(me, doc):
    #new_line_count = doc.get_line_count()
    #print 'new_line_count',new_line_count
    topL = visible_lines_top_bottom(me.geditwin)[0]
    if topL != me.topL:
      queue_refresh(me)
      me.draw_scrollbar_only = True
    
  def on_insert_text(me, doc, piter, text, len):
    queue_refresh(me)
    pass
    #if len < 20 and '\n' in text:
    #  print 'piter',piter,'text',repr(text),'len',len
    
  def scroll_from_y_mouse_pos(me,y):
    for line in me.lines:
      if line.y > y:
        break
#    print line.i, repr(line.raw)
    view = me.geditwin.get_active_view()
    doc = me.geditwin.get_active_tab().get_document()
    
    #doc.place_cursor(doc.get_iter_at_line_index(line.i,0))
    #view.scroll_to_cursor()
    #print view
    
    view.scroll_to_iter(doc.get_iter_at_line_index(line.i,0),0,True,0,.5)
    
    queue_refresh(me)
        
  def button_press(me, widget, event):
    me.scroll_from_y_mouse_pos(event.y)
    
  # def on_scroll_finished(me):
  #   #print 'in here',me.last_scroll_time,time.time()-me.last_scroll_time
  #   if time.time()-me.last_scroll_time > .47:
  #     if me.draw_sections:
  #       me.draw_sections = False
  #       me.draw_scrollbar_only = False
  #       queue_refresh(me)
  #   return False
    
  def on_scroll_event(me,view,event):
    me.last_scroll_time = time.time()
    # if me.draw_sections: # we are in the middle of scrolling
    #   me.draw_scrollbar_only = True
    # else:
    #   me.draw_sections = True # for the first scroll, turn on section names
    #GObject.timeout_add(500, me.on_scroll_finished) # this will fade out sections
    queue_refresh(me)
    
  def on_search_highlight_updated(me,doc,t,u):
    #print 'on_search_highlight_updated:',repr(doc.get_search_text())
    docrec = me.doc_attached_data[id(doc)]

    s = doc.get_search_text(0)  #  = doc.get_search_text(0)[0] # TODO fix flags
    if s != docrec.search_text:
      docrec.search_text = s
      queue_refresh(me)    
    
  def save_refs_to_all_font_faces(me, cr, *scales):
    me.font_face_keepalive = []
    for each in scales:
      cr.set_font_size(each)
      me.font_face_keepalive.append(cr.get_font_face())
    
  def draw(me, widget, cr):
    doc = me.geditwin.get_active_tab().get_document()
    if not doc:   # nothing open yet
      return
    
    if id(doc) not in me.connected:
      me.connected[id(doc)] = True
      doc.connect("cursor-moved", me.on_doc_cursor_moved)
      doc.connect("insert-text", me.on_insert_text)
      # TODO: handle text removal
      doc.connect("search-highlight-updated", me.on_search_highlight_updated)
      
    view = me.geditwin.get_active_view()
    if not view:
      return
    
    if TIMER: TIMER.push('draw')
    
    if id(view) not in me.connected:
      me.connected[id(view)] = True
      view.connect("scroll-event", me.on_scroll_event)
      #view.connect("start-interactive-goto-line", me.test_event)
      #view.connect("start-interactive-search", me.test_event)
      #view.connect("reset-searched-text", me.test_event)
      
    bg = (0,0,0)
    fg = (1,1,1)
    try:
      style = doc.get_style_scheme().get_style('text')
      if style is None: # there is a style scheme, but it does not specify default
        bg = (1,1,1)
        fg = (0,0,0)
      else:
        fg,bg = map(str2rgb, style.get_properties('foreground','background'))  
    except:
      pass  # probably an older version of gedit, no style schemes yet
    
    changeCLR = (1,0,1)
    
    #search_match_style = None
    #try:
    #  search_match_style = doc.get_style_scheme().get_style('search-match')
    #except:
    #  pass
    #if search_match_style is None:
    #  searchFG = fg
    #  searchBG = (0,1,0)
    #else:
    #  searchFG,searchBG = map(str2rgb, style.get_properties('foreground','background'))
    searchFG = fg
    searchBG = (0,1,0)
      
    
    #print doc
       
    try:
      win = widget.get_window()
    except AttributeError:
      win = widget.window
    w,h = map(float, (win.get_width(), win.get_height()) )
    cr = widget.get_window().cairo_create()
    
    #probj(cr,'rgb')
    
    # Are we drawing everything, or just the scrollbar?
    fontfamily = 'sans-serif'
    cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            
    if me.surface_textmap is None or not me.draw_scrollbar_only:
    
      if TIMER: TIMER.push('document_lines')

      lines = document_lines(doc)
      
      if TIMER: TIMER.pop('document_lines')
      
      if TIMER: TIMER.push('draw textmap')
      
      if id(doc) not in me.doc_attached_data:
        docrec = struct()
        me.doc_attached_data[id(doc)] = docrec
        docrec.original_lines_info = None # we skip the first one, its empty
        docrec.search_text = None
        for l in lines:
          l.changed = False
      else:
        docrec = me.doc_attached_data[id(doc)]
        if docrec.original_lines_info == None:
          docrec.original_lines_info = init_original_lines_info(doc,lines)
        lines = mark_changed_lines(doc, docrec.original_lines_info, lines)
        
      if BUG_MASK & BUG_DOC_GET_SEARCH_TEXT:
        pass
      else:
        docrec.search_text = doc.get_search_text(0)   # TODO make sure this flag is right
        lines = lines_mark_search_matches(lines,docrec)
     
      cr.push_group()
      
      # bg
      if 1:
        #cr.set_source_rgb(46/256.,52/256.,54/256.)
        cr.set_source_rgb(*bg)
        cr.move_to(0,0)
        cr.rectangle(0,0,w,h)
        cr.fill()
        cr.move_to(0,0)
      
      if not lines:
        return
        
      # translate everthing in
      margin = 3
      cr.translate(margin,0)
      w -= margin # an d here
            
      if TIMER: TIMER.push('downsample')
      max_scale = 3
      lines, scale, downsampled = downsample_lines(lines, h, 2, max_scale)
      if TIMER: TIMER.pop('downsample')
      
      smooshed = False
      if downsampled or scale < max_scale:
        smooshed = True

      n = len(lines)
      lineH = h/n
      
      #print 'doc',doc.get_uri(), lines[0].raw
      
      if BUG_MASK & BUG_CAIRO_MAC_FONT_REF and me.font_face_keepalive is None:
        me.save_refs_to_all_font_faces(cr,scale,scale+3,10,12)
      
      cr.set_font_size(scale)
      whitespaceW = text_extents('.',cr)[0]
      #print pr_text_extents(' ',cr)
      #print pr_text_extents('.',cr)
      #print pr_text_extents(' .',cr)
      
      # ------------------------ display text silhouette -----------------------
      if TIMER: TIMER.push('draw silhouette')
      
      if dark(*fg):
        faded_fg = lighten(.5,*fg)
      else:
        faded_fg = darken(.5,*fg)
      
      rectH = h/float(len(lines))
      sofarH= 0
      sections = []
      for i, line in enumerate(lines):
      
        line.y = sofarH
        lastH = sofarH
        cr.set_font_size(scale)
        
        if line.raw.strip(): # there is some text here
            
          tw,th = text_extents(line.raw,cr)
        
          if line.search_match:
            cr.set_source_rgb(*searchBG)
          elif line.changed:
            cr.set_source_rgb(*changeCLR)
          elif me.draw_sections:
            cr.set_source_rgb(*faded_fg)
          else:
            cr.set_source_rgb(*fg)
            
            #cr.select_font_face(fontfamily, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
          cr.set_font_size(scale)
          cr.show_text(line.raw)
          
          if smooshed:
            sofarH += lineH
          else:
            sofarH += th
        else: # empty line
          if smooshed:
            sofarH += lineH
          else:
            sofarH += scale-1
          
        # if line.section:
        #   sections.append((line, lastH))
          
        cr.move_to(0, sofarH)
        
      if TIMER: TIMER.pop('draw silhouette')
          
      # ------------------ translate back for the scroll bar -------------------
      
      cr.translate(-margin,0)
      w += margin

      # -------------------------- mark lines markers --------------------------
            
      if TIMER: TIMER.push('draw line markers')
      for line in lines:
        if line.search_match:
          clr = searchBG
        elif line.changed:
          clr = changeCLR
        else:
          continue # nothing interesting has happened with this line
        cr.set_source_rgb(*clr)      
        cr.rectangle(w-3,line.y-2,2,5)
        cr.fill()
      if TIMER: TIMER.pop('draw line markers')
        
      if TIMER: TIMER.pop('draw textmap')
      
      # save
      me.surface_textmap = cr.pop_group() # everything but the scrollbar
      me.lines = lines

    if TIMER: TIMER.push('surface_textmap')
    cr.set_source(me.surface_textmap)
    cr.rectangle(0,0,w,h)
    cr.fill()
    if TIMER: TIMER.pop('surface_textmap')
        
    # ------------------------------- scrollbar -------------------------------

    if TIMER: TIMER.push('scrollbar')
    
    topL,botL = visible_lines_top_bottom(me.geditwin)
    
    if topL==0 and botL==doc.get_end_iter().get_line():
      pass # everything is visible, don't draw scrollbar
    else:
      scrollbar(me.lines,topL,botL,w,h,bg,cr)
    
    if TIMER: TIMER.pop('scrollbar')
    
    me.topL = topL
    me.draw_scrollbar_only = False
    
    if TIMER: TIMER.pop('draw')
    if TIMER: TIMER.print_()
      
        
class TextmapWindowHelper:
  def __init__(me, plugin, window):
    me.window = window
    me.plugin = plugin

    panel = me.window.get_side_panel()
    image = Gtk.Image()
    image.set_from_stock(Gtk.STOCK_DND_MULTIPLE, Gtk.IconSize.BUTTON)
    me.textmapview = TextmapView(me.window)
    me.ui_id = panel.add_item(me.textmapview, "TextMap", "textMap", image)
    
    me.panel = panel

  def deactivate(me):
    me.window = None
    me.plugin = None
    me.textmapview = None

  def update_ui(me):
    queue_refresh(me.textmapview)
    
    
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

