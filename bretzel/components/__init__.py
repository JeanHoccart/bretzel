"""Layer 5 — the user-facing ``ui`` namespace.

Apps consume components via ::

    from bretzel import ui

    with ui.vstack(gap="lg"):
        ui.text("Hello", size="xl", weight="bold")
        ui.button("Save", on_click=save_handler)

Le critère d'appartenance
-------------------------
**``ui.*`` s'appelle depuis un corps de RENDU** (``@page``, ``@layout``,
``@refreshable``) ; **``bretzel.*`` s'appelle depuis un HANDLER**. C'est
une frontière mécanique, pas un jugement : elle se vérifie, et
``tests/consistency/test_handler_helpers_have_one_home.py`` la vérifie.

Dit en langage humain : ``ui.*`` est tout ce dont l'effet est visible à
l'écran. Ça inclut des entrées qui ne retournent pas de nœud —
``ui.notification`` produit un toast (le runtime auto-monte le DOM), les
``ui.*_each`` produisent des clés d'itération, ``ui.column`` décrit une
colonne de table. Le critère n'est donc PAS « retourne un ``Node`` », et
c'est volontaire.

Un court-circuit HTTP comme :func:`bretzel.server.errors.abort` appartient
donc à la surface de handler, pas au namespace de rendu.
"""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.actions.icon_button import IconButton
from bretzel.components.actions.link import Link
from bretzel.components.base.events import pending as _pending
from bretzel.components.charts import Series
from bretzel.components.charts.bar_chart import BarChart
from bretzel.components.charts.line_chart import LineChart
from bretzel.components.charts.pie_chart import PieChart
from bretzel.components.charts.reference import Reference
from bretzel.components.charts.scatter_chart import ScatterChart
from bretzel.components.charts.sparkline import Sparkline
from bretzel.components.color_shapes import (
    dynamic_responsive_classes,
)
from bretzel.components.data.accordion import Accordion, AccordionItem
from bretzel.components.data.datatable import (
    Datatable,
    DatatableState,
    Query,
    apply_query,
)
from bretzel.components.data.diagram import Diagram, GraphEdge, GraphNode
from bretzel.components.data.diagram import edge as _edge
from bretzel.components.data.diagram import node as _node
from bretzel.components.data.table import Column, Table
from bretzel.components.data.table import column as _column
from bretzel.components.data.tree import Tree, TreeNode
from bretzel.components.feedback.alert import Alert
from bretzel.components.feedback.avatar import Avatar
from bretzel.components.feedback.badge import Badge
from bretzel.components.feedback.banner import Banner
from bretzel.components.feedback.empty_state import EmptyState
from bretzel.components.feedback.notification import (
    notification as _notification,
)
from bretzel.components.feedback.progress import Progress
from bretzel.components.feedback.skeleton import Skeleton
from bretzel.components.inputs.calendar import Calendar
from bretzel.components.inputs.checkbox import Checkbox
from bretzel.components.inputs.color_picker import ColorPicker
from bretzel.components.inputs.combobox import Combobox
from bretzel.components.inputs.date_picker import DatePicker
from bretzel.components.inputs.date_range_picker import DateRangePicker
from bretzel.components.inputs.file_upload import FileUpload
from bretzel.components.inputs.form import Form
from bretzel.components.inputs.form_field import FormField
from bretzel.components.inputs.input import Input
from bretzel.components.inputs.month_picker import MonthPicker
from bretzel.components.inputs.number_input import NumberInput
from bretzel.components.inputs.radio import Radio, RadioGroup
from bretzel.components.inputs.select import Select
from bretzel.components.inputs.signature_pad import SignaturePad
from bretzel.components.inputs.slider import Slider
from bretzel.components.inputs.switch import Switch
from bretzel.components.inputs.textarea import Textarea
from bretzel.components.inputs.time_picker import TimePicker
from bretzel.components.inputs.toggle_group import ToggleButton, ToggleGroup
from bretzel.components.inputs.week_picker import WeekPicker
from bretzel.components.layout.card import Card
from bretzel.components.layout.carousel import Carousel
from bretzel.components.layout.container import Container
from bretzel.components.layout.draggable import Draggable
from bretzel.components.layout.dropzone import Dropzone, Move
from bretzel.components.layout.flex import Flex
from bretzel.components.layout.grid import Grid
from bretzel.components.layout.pane import Pane
from bretzel.components.layout.resizable import Resizable, ResizablePanel
from bretzel.components.layout.stack import HStack, VStack
from bretzel.components.layout.viewport import Viewport
from bretzel.components.meta.fragment import Fragment
from bretzel.components.meta.interval import Interval
from bretzel.components.meta.iteration import (
    drag_each as _drag_each,
)
from bretzel.components.meta.iteration import (
    each as _each,
)
from bretzel.components.meta.iteration import (
    filter_each as _filter_each,
)
from bretzel.components.meta.iteration import (
    limit_each as _limit_each,
)
from bretzel.components.meta.iteration import (
    paginate_each as _paginate_each,
)
from bretzel.components.meta.iteration import (
    show_more as _show_more,
)
from bretzel.components.meta.meta_tag import MetaTag
from bretzel.components.meta.outlet import Outlet
from bretzel.components.meta.title import Title
from bretzel.components.navigation.bottom_bar import (
    BottomBar,
    BottomBarItem,
)
from bretzel.components.navigation.breadcrumb import Breadcrumb, BreadcrumbItem
from bretzel.components.navigation.navbar import (
    Navbar,
    NavbarItem,
    NavbarSection,
)
from bretzel.components.navigation.pagination import Pagination
from bretzel.components.navigation.sidebar import (
    Sidebar,
    SidebarFooter,
    SidebarFooterItem,
    SidebarItem,
    SidebarSection,
    SidebarTitle,
    SidebarTrigger,
)
from bretzel.components.navigation.stepper import Step, StepPanel, Stepper
from bretzel.components.navigation.tabs import Tab, TabPanel, Tabs
from bretzel.components.overlay.dialog import Dialog
from bretzel.components.overlay.drawer import Drawer
from bretzel.components.overlay.dropdown import Dropdown, DropdownItem
from bretzel.components.overlay.popover import Popover
from bretzel.components.overlay.tooltip import Tooltip
from bretzel.components.primitives.audio import Audio
from bretzel.components.primitives.code import Code
from bretzel.components.primitives.divider import Divider
from bretzel.components.primitives.heading import Heading

# ``Html`` le COMPOSANT, à ne pas confondre avec ``core.tree.Html``, le
# nœud d'arbre qu'il enveloppe. Le nœud n'est jamais exposé sur ``ui``.
from bretzel.components.primitives.html import Html
from bretzel.components.primitives.icon import Icon
from bretzel.components.primitives.iframe import SANDBOX_BASELINE, Iframe
from bretzel.components.primitives.image import Image
from bretzel.components.primitives.markdown import Markdown
from bretzel.components.primitives.spinner import Spinner
from bretzel.components.primitives.text import Text
from bretzel.components.primitives.video import Track, Video
from bretzel.components.primitives.video import track as _track


class _UI:
    """Lowercased aliases for the shipped components.

    Defined as a class so the lookup is cheap and uses Python's normal
    attribute resolution. App code typically reaches it via the
    module-level :data:`ui` instance below.
    """

    # Primitives
    text = Text
    heading = Heading
    icon = Icon
    image = Image
    divider = Divider
    spinner = Spinner
    code = Code
    markdown = Markdown
    html = Html
    video = Video
    track = staticmethod(_track)
    audio = Audio
    iframe = Iframe

    # Layout — flex + stacks + card + container + grid.
    flex = Flex
    vstack = VStack
    hstack = HStack
    card = Card
    carousel = Carousel
    draggable = Draggable
    dropzone = Dropzone
    container = Container
    grid = Grid
    resizable = Resizable
    resizable_panel = ResizablePanel
    # Le modèle « document gelé » : le cadre et ses régions qui
    # défilent. Explicite — le défaut de Bretzel reste le document
    # qui défile (cf. la docstring de Viewport).
    viewport = Viewport
    pane = Pane

    # Actions
    button = Button
    icon_button = IconButton
    link = Link

    # Form inputs
    input = Input
    number_input = NumberInput
    textarea = Textarea
    select = Select
    combobox = Combobox
    slider = Slider
    calendar = Calendar
    date_picker = DatePicker
    date_range_picker = DateRangePicker
    color_picker = ColorPicker
    time_picker = TimePicker
    month_picker = MonthPicker
    week_picker = WeekPicker
    checkbox = Checkbox
    switch = Switch
    radio = Radio
    radio_group = RadioGroup
    toggle_group = ToggleGroup
    toggle_button = ToggleButton
    signature_pad = SignaturePad
    file_upload = FileUpload
    form = Form
    form_field = FormField

    # Feedback
    alert = Alert
    progress = Progress
    badge = Badge
    avatar = Avatar
    skeleton = Skeleton
    empty_state = EmptyState
    banner = Banner

    # Data display
    table = Table
    datatable = Datatable
    # Column descriptor — sugar so users don't import the dataclass.
    column = staticmethod(_column)
    accordion = Accordion
    accordion_item = AccordionItem
    tree = Tree
    tree_node = TreeNode
    diagram = Diagram
    # Descripteurs du graphe — même sucre que ``column`` : l'auteur ne
    # va pas importer deux dataclasses pour décrire trois nœuds.
    node = staticmethod(_node)
    edge = staticmethod(_edge)

    # Data viz (Tier 8) — server-rendered SVG charts.
    sparkline = Sparkline
    bar_chart = BarChart
    line_chart = LineChart
    pie_chart = PieChart
    scatter_chart = ScatterChart

    # Navigation
    pagination = Pagination
    breadcrumb = Breadcrumb
    breadcrumb_item = BreadcrumbItem
    tabs = Tabs
    tab = Tab
    tab_panel = TabPanel
    stepper = Stepper
    step = Step
    step_panel = StepPanel
    sidebar = Sidebar
    sidebar_title = SidebarTitle
    sidebar_trigger = SidebarTrigger
    sidebar_section = SidebarSection
    sidebar_item = SidebarItem
    sidebar_footer = SidebarFooter
    sidebar_footer_item = SidebarFooterItem
    navbar = Navbar
    navbar_section = NavbarSection
    navbar_item = NavbarItem
    bottom_bar = BottomBar
    bottom_bar_item = BottomBarItem

    # Meta — render-pipeline markers + chrome helpers
    outlet = Outlet
    interval = Interval
    fragment = Fragment
    title = Title
    meta_tag = MetaTag

    # Overlays
    tooltip = Tooltip
    popover = Popover
    dialog = Dialog
    drawer = Drawer
    dropdown = Dropdown
    dropdown_item = DropdownItem
    # ``ui.notification(...)`` is a fire-and-forget server-side helper,
    # not a component. Appends a toast to the request's notification
    # queue ; the partial-renderer drains it into a ``$bz.notification
    # .show(...)`` script and the runtime's auto-mounted toaster DOM
    # (V1 idiom — no container to mount on the page) renders it.
    notification = staticmethod(_notification)

    # ``ui.pending(...)`` n'est pas un composant : c'est une SOURCE
    # réactive (une ``ClientExpression``) qui dit « une action est en
    # vol ». Elle se binde sur ``loading=`` / ``disabled=`` / ``visible=``
    # comme un champ de ``ClientState`` — le framework publie le
    # booléen, l'app décide quoi en afficher.
    pending = staticmethod(_pending)

    # Iteration helper (not a component — the spec calls it out as a
    # generator function pushing keys onto the render context).
    each = staticmethod(_each)
    drag_each = staticmethod(_drag_each)
    filter_each = staticmethod(_filter_each)
    paginate_each = staticmethod(_paginate_each)
    limit_each = staticmethod(_limit_each)
    show_more = staticmethod(_show_more)


# Module-level singleton — the canonical reach for app code.
ui = _UI()


__all__ = [
    # Class re-exports for ``from bretzel.components import Button`` etc.
    "Accordion",
    "AccordionItem",
    "Alert",
    "Audio",
    "Avatar",
    "Badge",
    "Banner",
    "BarChart",
    "BottomBar",
    "BottomBarItem",
    "Breadcrumb",
    "BreadcrumbItem",
    "Button",
    "Calendar",
    "Card",
    "Carousel",
    "Draggable",
    "Dropzone",
    "Move",
    "Checkbox",
    "Code",
    "Column",
    "Combobox",
    "Container",
    "DatePicker",
    "DateRangePicker",
    "Dialog",
    "Divider",
    "Drawer",
    "Dropdown",
    "DropdownItem",
    "EmptyState",
    "FileUpload",
    "Flex",
    "Form",
    "FormField",
    "Fragment",
    "Grid",
    "HStack",
    "Heading",
    "Html",
    "Iframe",
    # La valeur par DÉFAUT de ``ui.iframe(sandbox=)`` : une app qui
    # veut l'étendre doit pouvoir la nommer.
    "SANDBOX_BASELINE",
    "Icon",
    "IconButton",
    "Image",
    "Input",
    "LineChart",
    "Link",
    "Markdown",
    "MonthPicker",
    "MetaTag",
    "Navbar",
    "NavbarItem",
    "NavbarSection",
    "NumberInput",
    "Interval",
    "Outlet",
    "Pane",
    "Pagination",
    "PieChart",
    "Reference",
    "ScatterChart",
    "Popover",
    "Progress",
    "DatatableState",
    "Query",
    "Radio",
    "RadioGroup",
    "Resizable",
    "ResizablePanel",
    "SignaturePad",
    "Select",
    "Series",
    "Sidebar",
    "SidebarFooter",
    "SidebarFooterItem",
    "SidebarItem",
    "SidebarSection",
    "SidebarTitle",
    "SidebarTrigger",
    "Skeleton",
    "Sparkline",
    "Slider",
    "Spinner",
    "Step",
    "StepPanel",
    "Stepper",
    "Switch",
    "Tab",
    "TabPanel",
    "Datatable",
    "Table",
    "Tabs",
    "Text",
    "Textarea",
    "ColorPicker",
    "TimePicker",
    "WeekPicker",
    "Title",
    "ToggleButton",
    "ToggleGroup",
    "Tooltip",
    "Track",
    "Diagram",
    "GraphEdge",
    "GraphNode",
    "Tree",
    "TreeNode",
    "Video",
    "VStack",
    "Viewport",
    # The namespace
    "ui",
    # Le pipeline datatable : le type qu'un handler NOMME, et le
    # helper qui l'applique a une liste Python.
    "apply_query",
    # Introspection — ce que la safelist prod doit couvrir et que le
    # scanner Tailwind ne voit pas : gabarits couleur, tokens gradués.
    "dynamic_responsive_classes",
]
