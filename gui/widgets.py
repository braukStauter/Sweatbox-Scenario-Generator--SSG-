"""
Custom reusable GUI widgets with dark theme
"""
import tkinter as tk
from tkinter import ttk
from gui.theme import DarkTheme


class ThemedButton(tk.Button):
    """Themed button widget"""

    def __init__(self, parent, text="", command=None, primary=True, **kwargs):
        # Remove any padding/size overrides from kwargs to ensure consistent button sizing
        kwargs.pop('padx', None)
        kwargs.pop('pady', None)
        kwargs.pop('width', None)
        kwargs.pop('height', None)

        style = DarkTheme.get_button_style() if primary else DarkTheme.get_secondary_button_style()
        style.update(kwargs)

        super().__init__(
            parent,
            text=text,
            command=command,
            **style
        )

        # Set fixed padding that cannot be overridden - ensures consistent button appearance
        self.configure(height=2, padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_MEDIUM)

        # Store the original background color for hover state restoration
        self.default_bg = style.get('bg', DarkTheme.ACCENT_PRIMARY)

        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)

    def _on_enter(self, event):
        self['bg'] = DarkTheme.ACCENT_HOVER

    def _on_leave(self, event):
        self['bg'] = self.default_bg


class ThemedEntry(tk.Frame):
    """Themed entry widget with internal padding and optional validation"""

    def __init__(self, parent, placeholder="", validate_type=None, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_SECONDARY)

        self.configure(
            relief='solid',
            borderwidth=2,
            highlightthickness=2,
            highlightcolor=DarkTheme.ACCENT_PRIMARY,
            highlightbackground=DarkTheme.BORDER
        )

        style = DarkTheme.get_entry_style()
        if 'width' not in kwargs:
            style['width'] = 30

        style['relief'] = 'flat'
        style['borderwidth'] = 0
        style['highlightthickness'] = 0

        style.update(kwargs)

        self.entry = tk.Entry(self, **style)
        self.entry.pack(padx=8, pady=8, fill='both', expand=True)

        self.placeholder = placeholder
        self.placeholder_active = False
        self.validate_type = validate_type

        if placeholder:
            self._show_placeholder()

        # Set up validation if specified
        if validate_type:
            vcmd = (self.entry.register(self._validate_input), '%P')
            self.entry.config(validate='key', validatecommand=vcmd)

        self.entry.bind('<FocusIn>', self._on_focus_in)
        self.entry.bind('<FocusOut>', self._on_focus_out)

        self.entry.bind('<FocusIn>', lambda e: self.after(10, self._scroll_to_view), add='+')

    def _show_placeholder(self):
        if not self.entry.get():
            self.entry.insert(0, self.placeholder)
            self.entry['fg'] = DarkTheme.FG_DISABLED
            self.placeholder_active = True

    def _on_focus_in(self, event):
        self.configure(highlightbackground=DarkTheme.ACCENT_PRIMARY, highlightcolor=DarkTheme.ACCENT_PRIMARY)
        if self.placeholder_active:
            self.entry.delete(0, tk.END)
            self.entry['fg'] = DarkTheme.FG_PRIMARY
            self.placeholder_active = False

    def _on_focus_out(self, event):
        self.configure(highlightbackground=DarkTheme.BORDER, highlightcolor=DarkTheme.ACCENT_PRIMARY)
        if not self.entry.get():
            self._show_placeholder()

    def get(self):
        """Get the entry value (for compatibility)"""
        return self.entry.get()

    def get_value(self):
        """Get the actual value (excluding placeholder)"""
        if self.placeholder_active:
            return ""
        return self.entry.get()

    def set_value(self, value: str):
        """Set the entry value, clearing placeholder if active"""
        # Clear any existing content
        self.entry.delete(0, tk.END)

        if value:
            # Insert the new value
            self.entry.insert(0, value)
            # Ensure text color is correct (not placeholder color)
            self.entry['fg'] = DarkTheme.FG_PRIMARY
            self.placeholder_active = False
        else:
            # If empty value, show placeholder
            if self.placeholder:
                self._show_placeholder()

    def _validate_input(self, new_value):
        """Validate input based on validation type"""
        # Allow empty input
        if not new_value:
            return True

        # Skip validation if placeholder is active
        if self.placeholder_active:
            return True

        if self.validate_type == "integer":
            # Allow only digits
            return new_value.isdigit()

        elif self.validate_type == "number":
            # Allow digits, decimal point, and negative sign
            try:
                float(new_value)
                return True
            except ValueError:
                return False

        elif self.validate_type == "runway":
            # Runways: comma-separated list of runway identifiers (e.g., "7L, 25R")
            # Allow digits, letters, commas, spaces
            import re
            return bool(re.match(r'^[0-9A-Za-z,\s]*$', new_value))

        elif self.validate_type == "range":
            # Range or single number (e.g., "3-6" or "5")
            # Allow digits, dash, and spaces
            import re
            return bool(re.match(r'^[0-9\-\s]*$', new_value))

        elif self.validate_type == "waypoint":
            # Waypoints: period-separated format (e.g., "EAGUL.EAGUL6, PINNG.PINNG1")
            # Allow uppercase letters, digits, periods, commas, spaces
            import re
            return bool(re.match(r'^[A-Z0-9.,\s]*$', new_value))

        elif self.validate_type == "alphanumeric":
            # Letters, numbers, spaces only
            import re
            return bool(re.match(r'^[A-Za-z0-9\s]*$', new_value))

        # No validation specified or unknown type - allow all
        return True

    def _scroll_to_view(self):
        """Scroll the entry into view when focused"""
        try:
            widget = self
            canvas = None

            for _ in range(20):
                widget = widget.master
                if widget is None:
                    break
                if isinstance(widget, tk.Canvas):
                    canvas = widget
                    break

            if not canvas:
                return

            bbox = canvas.bbox('all')
            if not bbox:
                return

            scroll_height = bbox[3] - bbox[1]
            canvas_height = canvas.winfo_height()

            if scroll_height <= canvas_height:
                return

            try:
                widget_y = self.winfo_y()
                parent = self.master
                while parent and not isinstance(parent.master, tk.Canvas):
                    widget_y += parent.winfo_y()
                    parent = parent.master

                widget_height = self.winfo_height()

                target_y = widget_y - (canvas_height / 2) + (widget_height / 2)

                target_y = max(0, min(scroll_height - canvas_height, target_y))

                scroll_fraction = target_y / scroll_height

                canvas.yview_moveto(scroll_fraction)

            except Exception:
                pass

        except Exception:
            pass


class ThemedLabel(tk.Label):
    """Themed label widget"""

    def __init__(self, parent, text="", heading=False, **kwargs):
        style = DarkTheme.get_heading_style() if heading else DarkTheme.get_label_style()
        style.update(kwargs)

        super().__init__(parent, text=text, **style)


class ThemedFrame(tk.Frame):
    """Themed frame widget"""

    def __init__(self, parent, card=False, **kwargs):
        style = DarkTheme.get_card_style() if card else DarkTheme.get_frame_style()
        style.update(kwargs)

        super().__init__(parent, **style)


class Card(tk.Frame):
    """Card widget for grouping related content"""

    def __init__(self, parent, title=None, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_SECONDARY, **kwargs)

        self.configure(relief='flat', borderwidth=0)
        self._setup_padding()

        if title:
            title_label = ThemedLabel(self, text=title, heading=True)
            title_label.configure(bg=DarkTheme.BG_SECONDARY)
            title_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_MEDIUM))

    def _setup_padding(self):
        """Add internal padding"""
        self.configure(padx=DarkTheme.PADDING_LARGE, pady=DarkTheme.PADDING_LARGE)


class SelectableCard(tk.Frame):
    """Selectable card widget for options"""

    def __init__(self, parent, title, description, command=None, **kwargs):
        self.command = command

        super().__init__(
            parent,
            bg=DarkTheme.BG_SECONDARY,
            relief='flat',
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=DarkTheme.BORDER,
            cursor='hand2',
            **kwargs
        )

        self.selected = False

        title_label = ThemedLabel(self, text=title, font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'))
        title_label.configure(bg=DarkTheme.BG_SECONDARY)
        title_label.pack(anchor='w', padx=DarkTheme.PADDING_LARGE, pady=(DarkTheme.PADDING_LARGE, 4))

        desc_label = ThemedLabel(self, text=description, fg=DarkTheme.FG_SECONDARY, wraplength=600, justify='left')
        desc_label.configure(bg=DarkTheme.BG_SECONDARY)
        desc_label.pack(anchor='w', padx=DarkTheme.PADDING_LARGE, pady=(0, DarkTheme.PADDING_LARGE))

        self.bind('<Button-1>', self._on_click)
        title_label.bind('<Button-1>', self._on_click)
        desc_label.bind('<Button-1>', self._on_click)

        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        title_label.bind('<Enter>', self._on_enter)
        desc_label.bind('<Enter>', self._on_enter)

    def _on_click(self, event):
        if self.command:
            self.command()

    def _on_enter(self, event):
        if not self.selected:
            self['bg'] = DarkTheme.BG_TERTIARY
            for child in self.winfo_children():
                if isinstance(child, tk.Label):
                    child['bg'] = DarkTheme.BG_TERTIARY

    def _on_leave(self, event):
        if not self.selected:
            self['bg'] = DarkTheme.BG_SECONDARY
            for child in self.winfo_children():
                if isinstance(child, tk.Label):
                    child['bg'] = DarkTheme.BG_SECONDARY

    def select(self):
        """Mark this card as selected"""
        self.selected = True
        self['highlightbackground'] = DarkTheme.ACCENT_PRIMARY
        self['highlightthickness'] = 2

    def deselect(self):
        """Mark this card as not selected"""
        self.selected = False
        self['highlightbackground'] = DarkTheme.BORDER
        self['highlightthickness'] = 1

    def set_command(self, command):
        """Set the command callback"""
        self.command = command


class ScrollableFrame(tk.Frame):
    """Scrollable frame widget (without visible scrollbar)"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY, **kwargs)

        self.canvas = tk.Canvas(self, bg=DarkTheme.BG_PRIMARY, highlightthickness=0)

        self.scrollable_frame = ThemedFrame(self.canvas)

        self.scrollable_frame.bind(
            '<Configure>',
            lambda e: self._update_scrollregion()
        )

        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')

        self.canvas.pack(fill='both', expand=True)

        self.canvas.bind('<Configure>', self._on_canvas_configure)

        self.canvas.bind('<Enter>', self._bind_mousewheel)
        self.canvas.bind('<Leave>', self._unbind_mousewheel)

    def _update_scrollregion(self):
        """Update the scroll region to encompass all widgets"""
        self.canvas.update_idletasks()
        self.scrollable_frame.update_idletasks()
        bbox = self.canvas.bbox('all')
        if bbox:
            canvas_height = self.canvas.winfo_height()
            content_height = bbox[3] - bbox[1]
            self.canvas.configure(scrollregion=bbox)
            # Debug: print scroll region info
            #print(f"[DEBUG] Scroll region updated: bbox={bbox}, canvas_height={canvas_height}, content_height={content_height}")
            # Ensure mousewheel is bound after content changes
            if content_height > canvas_height:
                #print(f"[DEBUG] Scrolling enabled (content {content_height} > canvas {canvas_height})")
                # Re-bind mousewheel to ensure it works after dynamic content changes
                self._bind_mousewheel(None)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
        # Also update scroll region when canvas resizes
        self.after(10, self._update_scrollregion)

    def _bind_mousewheel(self, event):
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self.canvas.unbind_all('<MouseWheel>')

    def _on_mousewheel(self, event):
        # Scroll 3 units per wheel notch for better responsiveness
        scroll_amount = int(-1 * (event.delta / 120) * 3)
        self.canvas.yview_scroll(scroll_amount, "units")


class ProgressIndicator(tk.Frame):
    """Progress indicator widget"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY, **kwargs)

        self.label = ThemedLabel(self, text="Processing...")
        self.label.pack(pady=DarkTheme.PADDING_MEDIUM)

        # Create canvas-based progress bar for better control
        self.canvas = tk.Canvas(
            self,
            width=400,
            height=8,
            bg=DarkTheme.BG_SECONDARY,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(padx=DarkTheme.PADDING_LARGE)

        # Create moving bar
        self.bar_width = 80
        self.bar = self.canvas.create_rectangle(
            0, 0, self.bar_width, 8,
            fill=DarkTheme.ACCENT_PRIMARY,
            outline=""
        )

        self.animation_id = None
        self.position = 0
        self.direction = 1

    def start(self, message="Processing..."):
        """Start the progress animation"""
        self.label['text'] = message
        self._animate()

    def _animate(self):
        """Animate the progress bar"""
        # Move the bar
        self.position += self.direction * 5

        # Reverse direction at edges
        if self.position >= 400 - self.bar_width:
            self.direction = -1
        elif self.position <= 0:
            self.direction = 1

        # Update bar position
        self.canvas.coords(self.bar, self.position, 0, self.position + self.bar_width, 8)

        # Schedule next frame
        self.animation_id = self.after(20, self._animate)

    def stop(self):
        """Stop the progress animation"""
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None


class AccordionItem(tk.Frame):
    """Collapsible accordion item for sidebar navigation"""

    def __init__(self, parent, title, icon="▶", on_select=None, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_SECONDARY, **kwargs)

        self.title = title
        self.icon = icon
        self.on_select = on_select
        self.is_expanded = False
        self.is_selected = False
        self.children_items = []

        # Header frame (clickable)
        self.header = tk.Frame(self, bg=DarkTheme.BG_SECONDARY, cursor='hand2')
        self.header.pack(fill='x', padx=2, pady=1)

        # Icon label (for expand/collapse)
        self.icon_label = tk.Label(
            self.header,
            text="▶",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            fg=DarkTheme.FG_SECONDARY,
            bg=DarkTheme.BG_SECONDARY,
            width=2,
            cursor='hand2'
        )
        self.icon_label.pack(side='left', padx=(DarkTheme.PADDING_SMALL, 0))

        # Title label
        self.title_label = tk.Label(
            self.header,
            text=title,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            fg=DarkTheme.FG_PRIMARY,
            bg=DarkTheme.BG_SECONDARY,
            anchor='w',
            cursor='hand2'
        )
        self.title_label.pack(side='left', fill='x', expand=True, padx=DarkTheme.PADDING_SMALL, pady=DarkTheme.PADDING_SMALL)

        # Container for child items (hidden by default)
        self.children_container = tk.Frame(self, bg=DarkTheme.BG_PRIMARY)

        # Bind click events
        self.header.bind('<Button-1>', self._on_header_click)
        self.icon_label.bind('<Button-1>', self._on_header_click)
        self.title_label.bind('<Button-1>', self._on_header_click)

        # Hover effects
        self.header.bind('<Enter>', self._on_enter)
        self.header.bind('<Leave>', self._on_leave)
        self.title_label.bind('<Enter>', self._on_enter)
        self.icon_label.bind('<Enter>', self._on_enter)

    def _on_header_click(self, event):
        """Handle header click - select this item"""
        if self.on_select:
            self.on_select(self)

    def _on_enter(self, event):
        """Handle mouse enter"""
        if not self.is_selected:
            self.header['bg'] = DarkTheme.BG_TERTIARY
            self.icon_label['bg'] = DarkTheme.BG_TERTIARY
            self.title_label['bg'] = DarkTheme.BG_TERTIARY

    def _on_leave(self, event):
        """Handle mouse leave"""
        if not self.is_selected:
            self.header['bg'] = DarkTheme.BG_SECONDARY
            self.icon_label['bg'] = DarkTheme.BG_SECONDARY
            self.title_label['bg'] = DarkTheme.BG_SECONDARY

    def select(self):
        """Mark this item as selected"""
        self.is_selected = True
        self.header['bg'] = DarkTheme.ACCENT_PRIMARY
        self.icon_label['bg'] = DarkTheme.ACCENT_PRIMARY
        self.icon_label['fg'] = DarkTheme.FG_PRIMARY
        self.title_label['bg'] = DarkTheme.ACCENT_PRIMARY
        self.title_label['font'] = (DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold')

    def deselect(self):
        """Mark this item as not selected"""
        self.is_selected = False
        self.header['bg'] = DarkTheme.BG_SECONDARY
        self.icon_label['bg'] = DarkTheme.BG_SECONDARY
        self.icon_label['fg'] = DarkTheme.FG_SECONDARY
        self.title_label['bg'] = DarkTheme.BG_SECONDARY
        self.title_label['font'] = (DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL)

    def add_child(self, title, on_select=None):
        """Add a child item (subcategory)"""
        child = AccordionSubItem(self.children_container, title, on_select)
        child.pack(fill='x', padx=(DarkTheme.PADDING_LARGE, 0))
        self.children_items.append(child)

        # Show expand icon since we have children
        self.icon_label['text'] = "▼" if self.is_expanded else "▶"
        return child

    def toggle_expand(self):
        """Toggle expansion state"""
        if not self.children_items:
            return

        self.is_expanded = not self.is_expanded

        if self.is_expanded:
            self.icon_label['text'] = "▼"
            self.children_container.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))
        else:
            self.icon_label['text'] = "▶"
            self.children_container.pack_forget()

    def expand(self):
        """Expand to show children"""
        if not self.is_expanded and self.children_items:
            self.toggle_expand()

    def collapse(self):
        """Collapse to hide children"""
        if self.is_expanded:
            self.toggle_expand()


class AccordionSubItem(tk.Frame):
    """Sub-item within an accordion item"""

    def __init__(self, parent, title, on_select=None, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY, **kwargs)

        self.title = title
        self.on_select = on_select
        self.is_selected = False

        # Title label
        self.title_label = tk.Label(
            self,
            text=title,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            fg=DarkTheme.FG_SECONDARY,
            bg=DarkTheme.BG_PRIMARY,
            anchor='w',
            cursor='hand2',
            padx=DarkTheme.PADDING_MEDIUM,
            pady=DarkTheme.PADDING_SMALL
        )
        self.title_label.pack(fill='x')

        # Bind events
        self.title_label.bind('<Button-1>', self._on_click)
        self.title_label.bind('<Enter>', self._on_enter)
        self.title_label.bind('<Leave>', self._on_leave)

    def _on_click(self, event):
        """Handle click"""
        if self.on_select:
            self.on_select(self)

    def _on_enter(self, event):
        """Handle mouse enter"""
        if not self.is_selected:
            self.title_label['bg'] = DarkTheme.BG_TERTIARY

    def _on_leave(self, event):
        """Handle mouse leave"""
        if not self.is_selected:
            self.title_label['bg'] = DarkTheme.BG_PRIMARY

    def select(self):
        """Mark as selected"""
        self.is_selected = True
        self.title_label['bg'] = DarkTheme.ACCENT_PRIMARY
        self.title_label['fg'] = DarkTheme.FG_PRIMARY
        self.title_label['font'] = (DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL, 'bold')

    def deselect(self):
        """Mark as not selected"""
        self.is_selected = False
        self.title_label['bg'] = DarkTheme.BG_PRIMARY
        self.title_label['fg'] = DarkTheme.FG_SECONDARY
        self.title_label['font'] = (DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL)


class AccordionSidebar(tk.Frame):
    """Sidebar with collapsible accordion sections"""

    def __init__(self, parent, on_category_select=None, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_SECONDARY, **kwargs)

        self.on_category_select = on_category_select
        self.items = []
        self.selected_item = None

        # Title
        title_frame = tk.Frame(self, bg=DarkTheme.BG_SECONDARY)
        title_frame.pack(fill='x', padx=DarkTheme.PADDING_MEDIUM, pady=DarkTheme.PADDING_LARGE)

        title_label = tk.Label(
            title_frame,
            text="Configuration",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_LARGE, 'bold'),
            fg=DarkTheme.FG_PRIMARY,
            bg=DarkTheme.BG_SECONDARY
        )
        title_label.pack(anchor='w')

        # Divider
        divider = tk.Frame(self, bg=DarkTheme.DIVIDER, height=1)
        divider.pack(fill='x', pady=DarkTheme.PADDING_SMALL)

        # Scrollable container for items
        self.scroll_frame = ScrollableFrame(self)
        self.scroll_frame.pack(fill='both', expand=True)

        self.container = self.scroll_frame.scrollable_frame

    def add_item(self, title, category_id=None):
        """Add an accordion item"""
        item = AccordionItem(
            self.container,
            title,
            on_select=lambda i: self._on_item_select(i, category_id)
        )
        item.category_id = category_id  # Store category_id on the item for easy access
        item.pack(fill='x', pady=1)
        self.items.append(item)
        return item

    def _on_item_select(self, item, category_id):
        """Handle item selection"""
        # Deselect previous
        if self.selected_item:
            self.selected_item.deselect()

        # Select new item
        item.select()
        self.selected_item = item

        # Notify parent
        if self.on_category_select and category_id:
            self.on_category_select(category_id)


class Footer(tk.Frame):
    """Footer with copyright/developer information"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=DarkTheme.BG_PRIMARY, **kwargs)

        copyright_label = tk.Label(
            self,
            text="Developed by Creative Shrimp™ (Ethan M) for ZAB",
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            fg="#404040",
            bg=DarkTheme.BG_PRIMARY
        )
        copyright_label.pack(pady=(DarkTheme.PADDING_SMALL, DarkTheme.PADDING_MEDIUM))
